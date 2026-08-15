#!/usr/bin/env python3
"""给公共资金专题的父页注入「点击下钻到二级详情子页」入口（幂等，可反复跑）。

用法：
    python3 tools/inject_drilldown.py            # 注入 / 更新
    python3 tools/inject_drilldown.py --remove   # 撤销

做法：在父页尾部追加一个独立 <script>，它在页面渲染完成后：
  1) 扫描指定选择器下的行/卡片/标签，用「已知对象名列表」去 textContent 里匹配出该元素代表的对象；
  2) 命中的元素加 .xx-drill（cursor:pointer + 悬停高亮 + 右上角 ↗ 角标）；
  3) 点击跳到子页并用 hash 传参：<子页>#<对象名>，子页据此直接定位。
父页的表格/卡片是 setInterval 轮播重绘的，故用 MutationObserver 持续重新标记，不与父页逻辑耦合。

一个父页可以挂多组入口，互不干扰（按文件写一个标记块，块内是三张表）：
  targets  行级下钻：DOM 元素 → 子页#对象。同一页可有多组，分别指向不同子页。
  charts   画布下钻：treemap / 环形图的图形块不是 DOM，只能绑 ECharts 实例的 click。
  panels   面板级入口：子页是全量台账、没有切换对象时，在面板头挂一枚直达 chip。

新增父页只需在 PAGES 里加一条配置，不必改父页源码。
"""
import io
import os
import re
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 公共资金专题 27 块屏所在目录（页面互链是同目录相对路径，移动目录时只改这里）
PAGES_DIR = os.path.join(ROOT, "screens", "public-funds")

CITIES = ["苏州", "南京", "无锡", "南通", "常州", "徐州", "盐城", "扬州", "泰州", "淮安", "镇江", "宿迁", "连云港"]
INDUSTRIES = ["制造业", "批发和零售业", "房地产业", "金融业", "建筑业", "租赁和商务服务业",
              "信息传输软件和信息技术服务业", "电力热力燃气及水生产供应业", "交通运输仓储和邮政业",
              "科学研究和技术服务业", "住宿和餐饮业", "农林牧渔业", "其他行业"]
COUNTIES = ["昆山", "江阴", "张家港", "常熟", "太仓", "宜兴", "如皋", "海安", "溧阳"]
ALERT_AREAS = ["连云港", "宿迁", "淮安", "徐州", "镇江"]
BLOCKS = ["苏南", "苏中", "苏北"]
CLASSES4 = ["高新技术企业", "数字经济核心产业", "专精特新企业", "绿色新能源"]
TRACKS12 = ["新能源汽车", "光伏", "集成电路", "生物医药", "工业机器人", "动力电池",
            "物联网", "高端装备", "新材料", "软件服务", "人工智能", "氢能"]
# 现金管理：子页对象 id ← 父页台账行里可唯一识别的「起息日」
CASH_TERMS = ["2026-%02d" % i for i in range(1, 15)]
CASH_MATCH = ["01-14", "01-28", "02-11", "02-25", "03-11", "03-25", "04-15",
              "04-29", "05-13", "05-27", "06-10", "06-24", "07-08", "07-22"]

SUB_CITY = "大屏样板间-公共资金地市收入详情1920.html"
SUB_BLOCK = "大屏样板间-公共资金三大板块地市分布1920.html"
SUB_INDUSTRY = "大屏样板间-公共资金行业税收详情1920.html"
SUB_COUNTY = "大屏样板间-公共资金重点县区详情1920.html"
SUB_ALERT = "大屏样板间-公共资金余额预警详情1920.html"
SUB_CASH = "大屏样板间-公共资金现金操作详情1920.html"
SUB_CLASS = "大屏样板间-公共资金新动能四大类地市分布1920.html"
SUB_TRACK = "大屏样板间-公共资金新动能赛道地市分布1920.html"
SUB_BOND = "大屏样板间-公共资金债券发行台账1920.html"
SUB_LAND = "大屏样板间-公共资金土地成交台账1920.html"
SUB_ITEM = "大屏样板间-公共资金分项目收入明细1920.html"
SUB_ZONE = "大屏样板间-公共资金四大板块分省明细1920.html"
SUB_MONTH = "大屏样板间-公共资金主体税种月度走势1920.html"

# 主体税种月度节奏：小多图矩阵的 6 个子图，点击取 seriesName（params.name 是月份类目）
SM6 = ["增值税", "企业所得税", "个人所得税", "契税", "土地增值税", "城市维护建设税"]

ZONES4 = ["东部", "中部", "西部", "东北"]

# 收入分项目：桑基三级共 21 个节点。前 3 个是根与两个口径层，其余 18 个是末级项目。
# 桑基图上非税 3 项用的是简称，子页 hash 认全称，故 MATCH（图上名）与 NAMES（hash 名）分列。
ITEM_MATCH = [
    "一般公共预算收入", "税收收入", "非税收入",
    "增值税", "企业所得税", "个人所得税", "契税", "土地增值税", "城市维护建设税",
    "房产税", "城镇土地使用税", "印花税", "耕地占用税", "车船税", "资源税",
    "专项收入", "国有资源有偿使用", "行政事业性收费", "罚没收入", "国有资本经营", "其他收入",
]
ITEM_NAMES = ITEM_MATCH[:16] + [
    "国有资源（资产）有偿使用收入", "行政事业性收费收入", "罚没收入", "国有资本经营收入", "其他收入",
]

PAGES = [
    # 地市收入：左侧明细表 13 市 + 右侧三大板块卡片，两组入口指向不同子页
    {"file": "大屏样板间-公共资金江苏地市收入1920.html", "targets": [
        {"rows": ".js-tbody li", "names": CITIES, "sub": SUB_CITY,
         "hint": "点击行下钻至地市详情", "scope": "js-table-scope"},
        {"rows": ".js-bk", "names": BLOCKS, "sub": SUB_BLOCK,
         "hint": "点击板块下钻至地市分布", "scope": "js-ring-scope"},
    ]},
    # 税收分行业：明细表行 + 中央 treemap 分块，同指向行业详情
    {"file": "大屏样板间-公共资金税收分行业1920.html", "targets": [
        {"rows": ".hy-tbody li", "names": INDUSTRIES, "sub": SUB_INDUSTRY,
         "hint": "点击行或树图分块下钻至行业详情", "scope": "hy-tb-scope"},
    ], "charts": [
        {"chartId": "hy-chart-tree", "names": INDUSTRIES, "sub": SUB_INDUSTRY},
    ]},
    # 新动能：左①四大类富图例（含环形图分块）→ 四大类地市分布；右①赛道标签墙 → 赛道地市分布
    {"file": "大屏样板间-公共资金新动能税收1920.html", "targets": [
        {"rows": ".xd-legend li", "names": CLASSES4, "sub": SUB_CLASS,
         "hint": "点击类别下钻至地市分布", "scope": "xd-mix-scope"},
        {"rows": ".xd-tag", "names": TRACKS12, "sub": SUB_TRACK,
         "hint": "点击赛道下钻至地市分布", "scope": "xd-tag-scope"},
    ], "charts": [
        {"chartId": "xd-chart-mix", "names": CLASSES4, "sub": SUB_CLASS},
    ]},
    # 分地区收入：右下「四大板块收入结构」的表行与环形图分块 → 四大板块分省明细
    {"file": "大屏样板间-公共资金分地区收入1920.html", "targets": [
        {"rows": "#gs-zone-tbody li", "names": ZONES4, "sub": SUB_ZONE,
         "hint": "点击板块下钻至分省明细", "scope": "gs-zone-scope"},
    ], "charts": [
        {"chartId": "gs-chart-zone", "names": ZONES4, "sub": SUB_ZONE},
    ]},
    # 收入分项目：中央桑基图的节点即层级，点任一节点（根 / 税收 / 非税 / 18 个末级）下钻。
    # 桑基叶子用简称、子页 hash 用全称，故 match 与 names 分开给。
    {"file": "大屏样板间-公共资金收入分项目1920.html", "charts": [
        {"chartId": "xm-chart-sankey", "names": ITEM_NAMES, "match": ITEM_MATCH, "sub": SUB_ITEM},
        {"chartId": "xm-chart-sm", "names": SM6, "sub": SUB_MONTH, "by": "seriesName"},
    ], "panels": [
        {"panelTitle": "收入分项目流向", "label": "嵌套明细", "sub": SUB_ITEM},
        {"panelTitle": "主体税种月度节奏", "label": "六税叠加", "sub": SUB_MONTH},
    ]},
    {"file": "大屏样板间-公共资金重点城市县区1920.html", "targets": [
        {"rows": ".zd-cell", "names": COUNTIES, "sub": SUB_COUNTY,
         "hint": "点击卡片下钻至县区详情", "scope": None},
    ]},
    {"file": "大屏样板间-公共资金余额分析1920.html", "targets": [
        {"rows": ".kc-tbody li", "names": ALERT_AREAS, "sub": SUB_ALERT,
         "hint": "点击行下钻至预警详情", "scope": "kc-list-scope"},
    ]},
    # 现金管理：行级下钻，但父页台账行显示的是「起息日」，与子页的期次 id 不同，故用 match 做映射
    {"file": "大屏样板间-公共资金现金管理1920.html", "targets": [
        {"rows": ".xj-tbody li", "names": CASH_TERMS, "match": CASH_MATCH, "sub": SUB_CASH,
         "hint": "点击行下钻至单期详情", "scope": None},
    ]},
    # 债券 / 土地：子页是全量台账、无切换对象，故不做行级下钻，改在相关面板头挂一枚入口 chip
    {"file": "大屏样板间-公共资金政府债券发行1920.html", "panels": [
        {"panelTitle": "全年发行节奏日历热力", "label": "逐笔台账", "sub": SUB_BOND},
    ]},
    {"file": "大屏样板间-公共资金土地出让形势1920.html", "panels": [
        {"panelTitle": "13 设区市出让金与同比", "label": "逐宗台账", "sub": SUB_LAND},
    ]},
]

CSS_BEGIN = "  /* drill:begin —— 由 tools/inject_drilldown.py 注入，勿手改 */"
CSS_END = "  /* drill:end */"
JS_BEGIN = "<!-- drill-js:begin -->"
JS_END = "<!-- drill-js:end -->"

CSS_TPL = """
  .{p}-drill {{ cursor: pointer; position: relative; }}
  .{p}-drill::after {{
    content: "↗"; position: absolute; right: 6px; top: 50%; transform: translateY(-50%) translateX(-3px);
    font-size: 11px; font-weight: 700; line-height: 1; color: var(--{p}-gold-soft);
    opacity: 0; transition: opacity .2s ease, transform .2s ease; pointer-events: none; z-index: 3;
  }}
  .{p}-drill:hover::after {{ opacity: 0.95; transform: translateY(-50%) translateX(0); }}
  .{p}-drill:hover {{
    background: rgba(240, 192, 96, 0.16) !important;
    box-shadow: inset 0 0 0 1px rgba(240, 192, 96, 0.5), 0 0 16px -4px rgba(240, 192, 96, 0.6);
  }}
  .{p}-drill-hint {{
    margin-left: 10px; font-size: 10.5px; letter-spacing: 0.04em; color: #b39a5e;
    padding: 1px 7px; border-radius: 999px; border: 1px dashed rgba(240, 192, 96, 0.5); white-space: nowrap;
  }}
  /* 面板级入口：子页是全量台账、无切换对象时用它，挂在相关面板头上 */
  .{p}-drill-entry {{
    margin-left: 10px; cursor: pointer; white-space: nowrap;
    font-size: 11px; font-weight: 700; letter-spacing: 0.06em; line-height: 1;
    padding: 4px 9px; border-radius: 999px; color: #06182c;
    background: linear-gradient(140deg, #9fe8ec, #39d0d8);
    box-shadow: 0 0 9px -1px rgba(57, 208, 216, 0.75);
    transition: filter .18s ease, box-shadow .18s ease;
  }}
  .{p}-drill-entry:hover {{ filter: brightness(1.12); box-shadow: 0 0 16px -1px rgba(57, 208, 216, 0.95); }}
"""

JS_TPL = """
<script>
/* ===== 下钻入口（tools/inject_drilldown.py 注入） =====
   独立于父页主脚本：父页表格/卡片由 setInterval 轮播重绘，故用 MutationObserver 持续重新标记。 */
(() => {{
  "use strict";
  const P = "{p}";
  /* 长名优先匹配，避免「制造业」把「电力热力燃气及水生产供应业」这类含子串的名字截胡 */
  const TARGETS = {targets}.map((t) => {{
    const match = t.match || t.names;
    return Object.assign({{}}, t, {{
      order: match.map((m, i) => ({{ m: m, n: t.names[i] }})).sort((a, b) => b.m.length - a.m.length)
    }});
  }});
  const CHARTS = {charts};
  const PANELS = {panels};

  function markOne(t) {{
    document.querySelectorAll(t.rows).forEach((el) => {{
      const txt = (el.textContent || "").replace(/\\s+/g, "");
      let hit = null;
      for (let i = 0; i < t.order.length; i++) {{
        if (txt.indexOf(t.order[i].m) >= 0) {{ hit = t.order[i].n; break; }}
      }}
      if (!hit) return;
      if (el.dataset.drill === hit && el.dataset.drillSub === t.sub) return;  /* 未变则跳过 */
      el.dataset.drill = hit;
      el.dataset.drillSub = t.sub;
      el.classList.add(P + "-drill");
      el.setAttribute("title", "点击查看「" + hit + "」二级详情");
    }});
  }}

  /* 面板头提示 chip 也放进重扫循环里：父页有些 scope 是被 setInterval 重写 textContent 的，
     一旦被冲掉，下一次 DOM 变动会把它补回来。 */
  function chipOne(t) {{
    if (!t.scope || !t.hint) return;
    const s = document.getElementById(t.scope);
    if (!s || s.querySelector("." + P + "-drill-hint")) return;
    const b = document.createElement("span");
    b.className = P + "-drill-hint";
    b.textContent = t.hint;
    s.appendChild(b);
  }}

  function scan() {{ TARGETS.forEach(markOne); TARGETS.forEach(chipOne); }}

  /* 事件委托：行会被父页轮播重绘，委托到 document 上最稳 */
  document.addEventListener("click", (e) => {{
    const row = e.target.closest ? e.target.closest("." + P + "-drill") : null;
    if (!row || !row.dataset.drill || !row.dataset.drillSub) return;
    location.href = row.dataset.drillSub + "#" + encodeURIComponent(row.dataset.drill);
  }});

  /* ECharts 画布下钻：treemap / 环形图的图形块不是 DOM，只能绑图表实例的 click。
     取 params.name 或 params.data.name 去对象名列表里反查，命中即跳子页。 */
  CHARTS.forEach((c) => {{
    if (!window.echarts) return;
    /* 与行级下钻一样支持 match：图上标签常是简称（桑基「国有资源有偿使用」），
       而子页 hash 要全称（「国有资源（资产）有偿使用收入」），两者需分开。 */
    const cm = c.match || c.names;
    const pairs = cm.map((m, i) => ({{ m: m, n: c.names[i] }})).sort((a, b) => b.m.length - a.m.length);
    const bind = () => {{
      const el = document.getElementById(c.chartId);
      const inst = el && echarts.getInstanceByDom(el);
      if (!inst) return false;
      if (inst.__drillBound) return true;
      inst.__drillBound = true;
      el.style.cursor = "pointer";
      inst.on("click", (pm) => {{
        /* 取名顺序：seriesName 优先于 name。小多图/折线的 params.name 是 x 轴类目
           （"1".."7" 这种月份），只有 seriesName 才是税种名；treemap / 环形图则相反，
           name 才是分块名而 seriesName 是整个系列名。故按配置 by 决定先取哪个。 */
        const bySeries = c.by === "seriesName";
        const raw = (pm && (bySeries
          ? (pm.seriesName || pm.name)
          : (pm.name || (pm.data && pm.data.name) || pm.seriesName))) || "";
        if (!raw) return;
        /* ★ 精确命中优先：行级下钻是拿整行文本去找子串，长名优先才对；但画布点击拿到的
           就是节点名本身，此时长名优先反而有害——「增值税」是「土地增值税」的子串，
           点增值税会被截胡跳到土地增值税去（实测 21 个节点里就这一个会错）。 */
        const hit = pairs.filter((p) => p.m === raw)[0]
          || pairs.filter((p) => raw.indexOf(p.m) >= 0 || p.m.indexOf(raw) >= 0)[0];
        if (hit) location.href = c.sub + "#" + encodeURIComponent(hit.n);
      }});
      return true;
    }};
    /* 图表可能晚于本脚本 init，轮询几次直到拿到实例 */
    if (!bind()) {{
      let tries = 0;
      const iv = setInterval(() => {{ if (bind() || ++tries > 40) clearInterval(iv); }}, 150);
    }}
  }});

  /* 面板级入口：按面板标题文本定位面板头，挂一枚可点 chip（不必改父页标记） */
  PANELS.forEach((pn) => {{
    const head = Array.prototype.slice.call(document.querySelectorAll("." + P + "-panel-head"))
      .filter((h) => {{ const t = h.querySelector("h2"); return t && t.textContent.trim() === pn.panelTitle; }})[0];
    if (!head || head.querySelector("." + P + "-drill-entry")) return;
    const b = document.createElement("span");
    b.className = P + "-drill-entry";
    b.textContent = pn.label + " ↗";
    b.setAttribute("title", "查看" + pn.label + "（全量明细）");
    b.addEventListener("click", (ev) => {{ ev.stopPropagation(); location.href = pn.sub; }});
    head.appendChild(b);
  }});

  if (TARGETS.length) {{
    scan();
    new MutationObserver(scan).observe(document.body, {{ childList: true, subtree: true }});
  }}
}})();
</script>
"""


def prefix_of(html):
    m = re.search(r"--([a-z]{2})-bg\s*:", html)
    if not m:
        raise SystemExit("无法识别 CSS 前缀")
    return m.group(1)


def strip(html, begin, end):
    return re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", html, flags=re.S)


def apply(cfg, remove=False):
    path = os.path.join(PAGES_DIR, cfg["file"])
    html = io.open(path, encoding="utf-8").read()
    p = prefix_of(html)
    html = strip(html, CSS_BEGIN, CSS_END)
    html = strip(html, JS_BEGIN, JS_END)
    if remove:
        io.open(path, "w", encoding="utf-8").write(html)
        return "%-44s 已撤销" % cfg["file"]

    targets = cfg.get("targets", [])
    charts = cfg.get("charts", [])
    panels = cfg.get("panels", [])
    for t in targets:                      # match 缺省时与 names 等长，JS 侧靠下标配对
        if t.get("match") and len(t["match"]) != len(t["names"]):
            raise SystemExit("%s：match 与 names 长度不一致" % cfg["file"])

    css = CSS_BEGIN + CSS_TPL.format(p=p) + CSS_END + "\n"
    html = html.replace("</style>", css + "</style>", 1)
    js = JS_BEGIN + JS_TPL.format(
        p=p,
        targets=json.dumps(targets, ensure_ascii=False),
        charts=json.dumps(charts, ensure_ascii=False),
        panels=json.dumps(panels, ensure_ascii=False),
    ) + JS_END + "\n"
    html = html.replace("</body>", js + "</body>", 1)
    io.open(path, "w", encoding="utf-8").write(html)

    bits = []
    for t in targets:
        bits.append("%d 对象 → %s" % (len(t["names"]), t["sub"][9:]))
    for c in charts:
        bits.append("图表 %s → %s" % (c["chartId"], c["sub"][9:]))
    for pn in panels:
        bits.append("面板「%s」→ %s" % (pn["panelTitle"], pn["sub"][9:]))
    return "%-44s 前缀 %s · %s" % (cfg["file"], p, "；".join(bits))


def preflight():
    """写盘前先把配置里引用的 DOM 锚点核一遍。

    scope / chartId / panelTitle 写错时页面不会报错，只是提示 chip 或画布下钻**静默消失**，
    肉眼极难发现（js 页的 js-tbl-scope 笔误就这样潜伏了一整期）。故在此拦下。
    """
    bad = []
    for cfg in PAGES:
        path = os.path.join(PAGES_DIR, cfg["file"])
        if not os.path.exists(path):
            continue
        html = io.open(path, encoding="utf-8").read()
        for t in cfg.get("targets", []):
            if t.get("scope") and ('id="%s"' % t["scope"]) not in html:
                bad.append("%s：scope id「%s」不存在" % (cfg["file"], t["scope"]))
        for c in cfg.get("charts", []):
            if ('id="%s"' % c["chartId"]) not in html:
                bad.append("%s：chartId「%s」不存在" % (cfg["file"], c["chartId"]))
        for pn in cfg.get("panels", []):
            if ">%s</h2>" % pn["panelTitle"] not in html:
                bad.append("%s：面板标题「%s」未匹配到" % (cfg["file"], pn["panelTitle"]))
        for s in [t["sub"] for t in cfg.get("targets", [])] + \
                 [c["sub"] for c in cfg.get("charts", [])] + \
                 [pn["sub"] for pn in cfg.get("panels", [])]:
            if not os.path.exists(os.path.join(PAGES_DIR, s)):
                bad.append("%s：子页「%s」不存在" % (cfg["file"], s))
    if bad:
        raise SystemExit("配置预检未通过，未写入任何文件：\n  " + "\n  ".join(bad))


def main():
    remove = "--remove" in sys.argv
    if not remove:
        preflight()
    n = 0
    for cfg in PAGES:
        if not os.path.exists(os.path.join(PAGES_DIR, cfg["file"])):
            print("跳过（不存在）：" + cfg["file"])
            continue
        print(apply(cfg, remove))
        n += 1
    print(("已撤销 " if remove else "已注入 ") + "%d 个父页的下钻入口" % n)


if __name__ == "__main__":
    main()
