#!/usr/bin/env python3
"""给「厨电制造专题」的父页注入「点击下钻到二级子页」入口（幂等，可反复跑）。

本文件是 tools/inject_drilldown.py（公共资金专题）的**厨电专用副本**：机制完全一样，
只换了三样东西——① 目录指向 screens/kitchen-appliance；② CSS 前缀探测锚点换成 .xx-stage
（厨电页的色板 token 统一是 --mfg-*，没有 --xx-bg，原来的正则在这里探不到）；
③ 对象名表 / PAGES 配置 / 配色换成厨电口径（青 #35e0d0 + 橙 #ff9d45）。
公共资金那份脚本不受本文件影响，两边各改各的。

用法：
    python3 tools/inject_drilldown_kitchen.py            # 注入 / 更新
    python3 tools/inject_drilldown_kitchen.py --remove   # 撤销

做法：在父页尾部追加一个独立 <script>，它在页面渲染完成后：
  1) 扫描指定选择器下的行/卡片/标签，用「已知对象名列表」去 textContent 里匹配出该元素代表的对象；
  2) 命中的元素加 .xx-drill（cursor:pointer + 悬停高亮 + 右上角 ↗ 角标）；
  3) 点击跳到子页并用 hash 传参：<子页>#<对象名>，子页据此直接定位（8 个子页都实现了
     hash 定位 + hashchange 监听，父页可以反复跳同一子页只换 hash）。
父页的表格/卡片是 setInterval 轮播重绘的，故用 MutationObserver 持续重新标记，不与父页逻辑耦合。

一个父页可以挂多组入口，互不干扰（按文件写一个标记块，块内是三张表）：
  targets  行级下钻：DOM 元素 → 子页#对象。同一页可有多组，分别指向不同子页。
  charts   画布下钻：帕累托 / 旭日 / 仪表 / 地图的图形块不是 DOM，只能绑 ECharts 实例的 click。
  panels   面板级入口：子页是全量台账、父页没有可切换对象时，在面板头挂一枚直达 chip。

新增父页只需在 PAGES 里加一条配置，不必改父页源码。
"""
import io
import os
import re
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 厨电制造专题所在目录（页面互链是同目录相对路径，移动目录时只改这里）
PAGES_DIR = os.path.join(ROOT, "screens", "kitchen-appliance")

# ---------------------------------------------------------------- 对象名表
# 供应商四级（父页 .gx-tier-row 卡片里写全称；四象限散点的 series 名是「S 战略」这种简写）
TIERS = ["战略供应商", "优选供应商", "合格供应商", "观察供应商"]
TIERS_SERIES = ["S 战略", "A 优选", "B 合格", "C 观察"]

# 三大生产基地（子页认全名 / 简称 / 城市 / key，这里统一给全名）
BASES = ["杭州临平", "安徽芜湖", "广东佛山"]

# 八类缺陷（品质管理页帕累托的 x 轴类目）与其主责部件（售后页旭日图外圈）
# 「故障部件分析」子页的 hash 别名表同时认部件名与缺陷名，故两张表都能直接当对象名用。
DEFECTS = ["电控失效", "密封不良", "焊接虚焊", "面板划伤",
           "噪音超标", "点火异常", "涂层脱落", "装配错位"]
PARTS = ["电控板", "密封圈", "线束端子", "面板玻璃",
         "风机总成", "点火针", "腔体内胆", "结构件"]

# 七大区域仓：库龄台账子页认「华东-杭州」这种全名；
# 而呆滞预警表里的「大区」列只写「华东」，故那一组用 match 做映射。
WAREHOUSES = ["华东-杭州", "华北-天津", "华南-佛山", "华中-武汉",
              "西南-成都", "东北-沈阳", "西北-西安"]
WH_ZONES = ["华东", "华北", "华南", "华中", "西南", "东北", "西北"]

# 21 条干线 = 7 区域仓 × 3 基地（枚举顺序与父页 TRUNK 一致：仓在外、基地在内）。
# 父页 label 形如「临平 → 华东仓」（箭头两侧带空格），但行级匹配是拿**去掉所有空白**的
# textContent 去找子串，故 match 必须是无空格版；names 保留空格版，子页 hash 会做 norm 归一。
_RDC_SHORT = ["华东仓", "华北仓", "华南仓", "华中仓", "西南仓", "东北仓", "西北仓"]
_BASE_SHORT = ["临平", "芜湖", "佛山"]
TRUNKS = ["%s → %s" % (b, r) for r in _RDC_SHORT for b in _BASE_SHORT]
TRUNKS_MATCH = [t.replace(" ", "") for t in TRUNKS]

# 31 省：省区门店分布子页认「广东」也认「广东省」，地图 series 的 name 是带后缀的 mapName
PROVS = ["广东", "江苏", "浙江", "山东", "河南", "四川", "河北", "湖北", "湖南", "福建",
         "安徽", "上海", "北京", "辽宁", "陕西", "江西", "广西", "云南", "重庆", "山西",
         "黑龙江", "吉林", "贵州", "天津", "内蒙古", "新疆", "甘肃", "海南", "宁夏", "青海", "西藏"]
PROVS_MAP = ["广东省", "江苏省", "浙江省", "山东省", "河南省", "四川省", "河北省", "湖北省",
             "湖南省", "福建省", "安徽省", "上海市", "北京市", "辽宁省", "陕西省", "江西省",
             "广西壮族自治区", "云南省", "重庆市", "山西省", "黑龙江省", "吉林省", "贵州省",
             "天津市", "内蒙古自治区", "新疆维吾尔自治区", "甘肃省", "海南省", "宁夏回族自治区",
             "青海省", "西藏自治区"]

# ---------------------------------------------------------------- 子页
SUB_SUPPLIER = "大屏样板间-厨电供应商台账1920.html"
SUB_BASE = "大屏样板间-厨电基地生产详情1920.html"
SUB_PART = "大屏样板间-厨电故障部件分析1920.html"
SUB_AGE = "大屏样板间-厨电库存库龄台账1920.html"
SUB_LINE = "大屏样板间-厨电物流线路详情1920.html"
SUB_PROV = "大屏样板间-厨电省区门店分布1920.html"
SUB_SKU = "大屏样板间-厨电单品销售详情1920.html"
SUB_ORDER = "大屏样板间-厨电售后工单台账1920.html"

PAGES = [
    # ① 供应商协同：左上「供应商分级结构」四张级别卡 + 中栏四象限散点（series 按级别分）
    #    分级面板的头上没有 id，故不挂 hint chip，改用 panels 直达 chip 兜住可发现性。
    {"file": "大屏样板间-厨电供应商协同1920.html", "targets": [
        {"rows": ".gx-tier-row", "names": TIERS, "sub": SUB_SUPPLIER,
         "hint": None, "scope": None},
    ], "charts": [
        {"chartId": "gx-chart-quad", "names": TIERS, "match": TIERS_SERIES,
         "sub": SUB_SUPPLIER, "by": "seriesName"},
    ], "panels": [
        {"panelTitle": "供应商分级结构", "label": "供应商台账", "sub": SUB_SUPPLIER},
    ]},

    # ② 生产制造总览：右栏「三大基地产能看板」三行卡 + 中栏 OEE 三联仪表（data.name = 基地全名）
    {"file": "大屏样板间-厨电生产制造总览1920.html", "targets": [
        {"rows": ".zz-base-row", "names": BASES, "sub": SUB_BASE,
         "hint": "点击基地下钻", "scope": "zz-base-scope"},
    ], "charts": [
        {"chartId": "zz-chart-oee", "names": BASES, "sub": SUB_BASE},
    ]},

    # ③ 品质管理：缺陷类型只活在帕累托的 x 轴类目里（没有对应的 DOM 行），故只做画布下钻
    {"file": "大屏样板间-厨电品质管理1920.html", "charts": [
        {"chartId": "pz-chart-pareto", "names": DEFECTS, "sub": SUB_PART},
    ], "panels": [
        {"panelTitle": "缺陷类型帕累托", "label": "部件分析", "sub": SUB_PART},
    ]},

    # ④ 仓储库存：右栏「七大区域仓利用率」七行卡（写全名）+ 呆滞预警表行（只写大区，用 match 映射）
    {"file": "大屏样板间-厨电仓储库存1920.html", "targets": [
        {"rows": ".ck-wh-row", "names": WAREHOUSES, "sub": SUB_AGE,
         "hint": None, "scope": None},
        {"rows": ".ck-tbody li", "names": WAREHOUSES, "match": WH_ZONES, "sub": SUB_AGE,
         "hint": "点击行下钻", "scope": "ck-dead-scope"},
    ]},

    # ⑤ 物流运输：「基地 → 区域仓干线明细」21 条滚动行
    {"file": "大屏样板间-厨电物流运输1920.html", "targets": [
        {"rows": ".wl-tbody li", "names": TRUNKS, "match": TRUNKS_MATCH, "sub": SUB_LINE,
         "hint": "点击行下钻", "scope": "wl-trunk-scope"},
    ]},

    # ⑥ 门店零售：右栏「省区零售明细」表行 + 中栏 31 省地图（地图 name 带行政后缀，用 match 映射）。
    #    hint chip 挂在地图面板（#md-prov-scope）上——那是主要的下钻画面，明细表没有 id 可挂。
    #    另：单品销售详情兼作本页子页（文档 §3），用 panels 挂一枚直达入口。
    {"file": "大屏样板间-厨电门店零售1920.html", "targets": [
        {"rows": ".md-tbody li", "names": PROVS, "sub": SUB_PROV,
         "hint": "点击省份或表行下钻", "scope": "md-prov-scope"},
    ], "charts": [
        {"chartId": "md-chart-map", "names": PROVS, "match": PROVS_MAP, "sub": SUB_PROV},
    ], "panels": [
        {"panelTitle": "三渠道类型结构", "label": "单品明细", "sub": SUB_SKU},
    ]},

    # ⑦ 电商全渠道：子页「单品销售详情」是按单品切换的，平台名当不了 hash 对象，
    #    故不做行级下钻，改在「平台经营明细」面板头挂一枚直达 chip。
    {"file": "大屏样板间-厨电电商全渠道1920.html", "panels": [
        {"panelTitle": "平台经营明细", "label": "单品明细", "sub": SUB_SKU},
    ]},

    # ⑧ 售后服务：父页没有渲染工单状态（待派单/在途/已完结/已超时）的 DOM，故工单台账走面板级入口；
    #    另有「故障类型旭日」外圈就是部件名，直接绑画布下钻到故障部件分析（文档 §3 的复用关系）。
    {"file": "大屏样板间-厨电售后服务1920.html", "charts": [
        {"chartId": "sf-chart-sun", "names": PARTS, "sub": SUB_PART},
    ], "panels": [
        {"panelTitle": "工单流转甘特", "label": "工单台账", "sub": SUB_ORDER},
        {"panelTitle": "故障类型旭日", "label": "部件分析", "sub": SUB_PART},
    ]},
]

CSS_BEGIN = "  /* drill:begin —— 由 tools/inject_drilldown_kitchen.py 注入，勿手改 */"
CSS_END = "  /* drill:end */"
JS_BEGIN = "<!-- drill-js:begin -->"
JS_END = "<!-- drill-js:end -->"

# 配色走厨电系：面板底 rgba(14,46,50,.55)、描边 rgba(64,196,190,.22)、主色青 #35e0d0、
# 强调橙 #ff9d45、次文字 #7fa6a3。这些页的 CSS 变量是 --mfg-*（跨页共用），
# 但下钻块要能独立整段删除，故一律写死字面值，不引用页面变量。
CSS_TPL = """
  .{p}-drill {{ cursor: pointer; position: relative; }}
  .{p}-drill::after {{
    content: "↗"; position: absolute; right: 6px; top: 50%; transform: translateY(-50%) translateX(-3px);
    font-size: 11px; font-weight: 700; line-height: 1; color: #ff9d45;
    opacity: 0; transition: opacity .2s ease, transform .2s ease; pointer-events: none; z-index: 3;
  }}
  .{p}-drill:hover::after {{ opacity: 0.95; transform: translateY(-50%) translateX(0); }}
  .{p}-drill:hover {{
    background: rgba(53, 224, 208, 0.15) !important;
    box-shadow: inset 0 0 0 1px rgba(53, 224, 208, 0.5), 0 0 16px -4px rgba(53, 224, 208, 0.6);
  }}
  /* 提示 chip：挂在面板头 h2 后面。margin-right:auto 吃掉 space-between 的空档，
     免得把面板头原有的 .xx-panel-tag 挤到中间去。 */
  .{p}-drill-hint {{
    margin-left: 8px; margin-right: auto; font-size: 10.5px; letter-spacing: 0.04em;
    color: #7fa6a3; padding: 1px 7px; border-radius: 999px; white-space: nowrap;
    background: rgba(14, 46, 50, 0.55); border: 1px dashed rgba(64, 196, 190, 0.45);
  }}
  /* 面板级入口：子页是全量台账、无切换对象时用它，挂在相关面板头上 */
  .{p}-drill-entry {{
    margin-left: 10px; cursor: pointer; white-space: nowrap;
    font-size: 11px; font-weight: 700; letter-spacing: 0.06em; line-height: 1;
    padding: 4px 9px; border-radius: 999px; color: #04191a;
    background: linear-gradient(140deg, #7ff0e2, #35e0d0);
    box-shadow: 0 0 9px -1px rgba(53, 224, 208, 0.75);
    transition: filter .18s ease, box-shadow .18s ease;
  }}
  .{p}-drill-entry:hover {{ filter: brightness(1.12); box-shadow: 0 0 16px -1px rgba(53, 224, 208, 0.95); }}
"""

JS_TPL = """
<script>
/* ===== 下钻入口（tools/inject_drilldown_kitchen.py 注入） =====
   独立于父页主脚本：父页表格/卡片由 setInterval 轮播重绘，故用 MutationObserver 持续重新标记。 */
(() => {{
  "use strict";
  const P = "{p}";
  /* 长名优先匹配，避免短名把含它的长名截胡（如「华东」与「华东-杭州」同表出现时） */
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
     一旦被冲掉，下一次 DOM 变动会把它补回来。
     ★ 厨电页把 scope id 挂在 <section class="xx-panel"> 上（公共资金是挂在面板头的 tag span 上），
       故先在 scope 内找面板头，找到就插在 h2 后面；找不到再退回元素自身，
       免得提示 chip 被塞到面板正文末尾、把 flex:1 的图表容器压矮。 */
  function chipOne(t) {{
    if (!t.scope || !t.hint) return;
    const s = document.getElementById(t.scope);
    if (!s) return;
    const head = s.classList && s.classList.contains(P + "-panel-head")
      ? s : (s.querySelector("." + P + "-panel-head") || s);
    if (head.querySelector("." + P + "-drill-hint")) return;
    const b = document.createElement("span");
    b.className = P + "-drill-hint";
    b.textContent = t.hint;
    const h2 = head.querySelector("h2");
    if (h2 && h2.parentNode === head) head.insertBefore(b, h2.nextSibling);
    else head.appendChild(b);
  }}

  function scan() {{ TARGETS.forEach(markOne); TARGETS.forEach(chipOne); }}

  /* 事件委托：行会被父页轮播重绘，委托到 document 上最稳 */
  document.addEventListener("click", (e) => {{
    const row = e.target.closest ? e.target.closest("." + P + "-drill") : null;
    if (!row || !row.dataset.drill || !row.dataset.drillSub) return;
    location.href = row.dataset.drillSub + "#" + encodeURIComponent(row.dataset.drill);
  }});

  /* ECharts 画布下钻：帕累托柱 / 旭日扇区 / 仪表盘 / 地图省份不是 DOM，只能绑图表实例的 click。
     取 params.name 或 params.data.name 去对象名列表里反查，命中即跳子页。 */
  CHARTS.forEach((c) => {{
    if (!window.echarts) return;
    /* 与行级下钻一样支持 match：图上标签常与子页口径不同（地图是「广东省」、
       四象限 series 是「S 战略」），而子页 hash 要的是「广东」「战略供应商」，两者需分开。 */
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
        /* 取名顺序：seriesName 优先于 name。四象限散点的 params.name 是空的，
           只有 seriesName 才是级别名；帕累托 / 旭日 / 地图则相反，name 才是分块名。
           故按配置 by 决定先取哪个。 */
        const bySeries = c.by === "seriesName";
        const raw = (pm && (bySeries
          ? (pm.seriesName || pm.name)
          : (pm.name || (pm.data && pm.data.name) || pm.seriesName))) || "";
        if (!raw) return;
        /* ★ 精确命中优先：行级下钻是拿整行文本去找子串，长名优先才对；但画布点击拿到的
           就是节点名本身，此时长名优先反而有害（旭日内圈的产品线名与外圈部件名混在一张图上，
           松匹配会把不该跳的点也跳走）。 */
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

# 厨电页的色板 token 统一是 --mfg-*（三字母、跨页共用），每页没有 --xx-bg，
# 故前缀改从舞台容器 .xx-stage 上取——那是每屏唯一的 2 字母私有前缀。
STAGE_RE = re.compile(r'<div class="([a-z]{2})-stage"')


def prefix_of(html):
    m = STAGE_RE.search(html)
    if not m:
        raise SystemExit("无法识别 CSS 前缀（找不到 .xx-stage）")
    return m.group(1)


def strip(html, begin, end):
    return re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", html, flags=re.S)


def short(sub):
    """报告里把子页文件名截短：去掉「大屏样板间-」前缀。"""
    return sub[6:] if sub.startswith("大屏样板间-") else sub


def apply(cfg, remove=False):
    path = os.path.join(PAGES_DIR, cfg["file"])
    html = io.open(path, encoding="utf-8").read()
    p = prefix_of(html)
    html = strip(html, CSS_BEGIN, CSS_END)
    html = strip(html, JS_BEGIN, JS_END)
    if remove:
        io.open(path, "w", encoding="utf-8").write(html)
        return "%-46s 已撤销" % cfg["file"]

    targets = cfg.get("targets", [])
    charts = cfg.get("charts", [])
    panels = cfg.get("panels", [])
    for t in targets:                      # match 缺省时与 names 等长，JS 侧靠下标配对
        if t.get("match") and len(t["match"]) != len(t["names"]):
            raise SystemExit("%s：match 与 names 长度不一致" % cfg["file"])
    for c in charts:
        if c.get("match") and len(c["match"]) != len(c["names"]):
            raise SystemExit("%s：图表 %s 的 match 与 names 长度不一致" % (cfg["file"], c["chartId"]))

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
        bits.append("%d 对象 → %s" % (len(t["names"]), short(t["sub"])))
    for c in charts:
        bits.append("图表 %s → %s" % (c["chartId"], short(c["sub"])))
    for pn in panels:
        bits.append("面板「%s」→ %s" % (pn["panelTitle"], short(pn["sub"])))
    return "%-46s 前缀 %s · %s" % (cfg["file"], p, "；".join(bits))


def preflight():
    """写盘前先把配置里引用的 DOM 锚点核一遍。

    scope / chartId / panelTitle 写错时页面不会报错，只是提示 chip 或画布下钻**静默消失**，
    肉眼极难发现。故在此拦下：任何一条不过，一个文件都不写。
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
