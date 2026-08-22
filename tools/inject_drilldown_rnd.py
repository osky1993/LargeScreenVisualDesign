#!/usr/bin/env python3
"""向「研发管理」专题的父页注入二级子页下钻入口（幂等，可反复跑）。

本文件是 tools/inject_drilldown_kitchen.py（厨电专题）的**专用副本**，只作用于
screens/rnd-ipd/。机制逐字沿用（MutationObserver 持续重标记、事件委托、画布 click、
面板级入口、写盘前 preflight），仅换目录、配色与业务配置。

用法：
    python3 tools/inject_drilldown_rnd.py            # preflight 全过才注入
    python3 tools/inject_drilldown_rnd.py --remove   # 撤销注入

对象名与下钻契约以 docs/RndIpdThemed.md §6 为唯一权威：父页行 textContent 含对象名原文，
点击跳 `子页#encodeURIComponent(对象名)`，子页 hashchange 定位。锚点（rows 选择器 /
chartId / panelTitle）均须实测于页面源码；preflight 任何一条不过，一个文件都不写。

分波交付：file 不存在的父页跳过；sub 不存在会被 preflight 拦下——新增波次先落子页再跑本脚本。
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(ROOT, "screens", "rnd-ipd")

# ---- 对象名词表（与 docs/RndIpdThemed.md §6 逐字一致，勿改动） ----
LINES4 = ["智家终端", "云平台服务", "AIoT模组", "行业方案"]
PROJECTS8 = ["星澜S3", "星澜Pro2", "云枢3.0", "云盾2.1", "澜芯M60", "澜芯M80", "智楼5.0", "车联1.0"]
SOURCES4 = ["客户直采", "市场洞察", "技术规划", "内部运营"]
TEAMS12 = ["天枢", "天璇", "天玑", "天权", "玉衡", "开阳", "摇光", "青龙", "白虎", "朱雀", "玄武", "紫微"]
BLOCKS5 = ["跨域依赖", "环境与资源", "需求变更", "外部供应", "评审等待"]
DOMAINS4 = ["软件", "硬件", "云端", "AI"]
BASELINES4 = ["R26.2", "R26.4", "R26.6", "R26.8"]
BATCHES5 = ["星澜S3-EVT2", "星澜S3-DVT1", "星澜Pro2-DVT2", "星澜Pro2-PVT1", "澜芯M60-EVT1"]
MODELS5 = ["灵犀", "慧眼", "澜音", "智荐", "御风"]
SITES6 = ["北京总部", "上海中心", "深圳中心", "成都中心", "西安中心", "南京中心"]

SUB_DL = "大屏样板间-研发单产品线路标详情1920.html"
SUB_DJ = "大屏样板间-研发单项目IPD详情1920.html"
SUB_TZ = "大屏样板间-研发需求条目台账1920.html"
SUB_CQ = "大屏样板间-研发单团队冲刺详情1920.html"
SUB_BS = "大屏样板间-研发阻塞在制品台账1920.html"
SUB_QX = "大屏样板间-研发缺陷台账1920.html"
SUB_JX = "大屏样板间-研发单集成基线详情1920.html"
SUB_PC = "大屏样板间-研发单样机批次详情1920.html"
SUB_ML = "大屏样板间-研发单模型详情1920.html"
SUB_BY = "大屏样板间-研发单中心详情1920.html"
SUB_QJ = "大屏样板间-研发园区数字孪生1920.html"
# ---- 二期补齐（S12–S18）：7 个原本没有子页的专题页各配 1 个 ----
SUB_YZ = "大屏样板间-研发单投入类别详情1920.html"
SUB_GC = "大屏样板间-研发单仓库群工程详情1920.html"
SUB_RZ = "大屏样板间-研发线上事件台账1920.html"
SUB_LJ = "大屏样板间-研发单链路节点详情1920.html"
SUB_RL = "大屏样板间-研发关键岗位与招聘台账1920.html"
SUB_SM = "大屏样板间-研发开源合规与技术债台账1920.html"
SUB_ZB = "大屏样板间-研发单维度追溯详情1920.html"

# 二期新增的对象名词表（与 docs/RndIpdThemed.md §6 逐字一致）
COSTS5 = ["人力", "样机物料", "云资源算力", "外协", "工具与其他"]
REPOS5 = ["应用软件", "嵌入式", "云服务", "AI 平台", "工具链"]
INCLV4 = ["P1", "P2", "P3", "P4"]
NODES12 = ["需求池", "规划台", "软件集群", "硬件实验室", "云平台集群", "AI算法集群",
           "CI 构建中心", "单测门", "集成测试台", "系统实验室", "发布列车站", "运营监控塔"]
# ★ 行级匹配串：`markOne` 会先把元素 textContent 里的**所有空白剔除**再做子串匹配，
#   所以对象名中带空格的（「CI 构建中心」）必须另给一份无空格的 match，否则永远匹配不上、
#   该节点静默不可点（实测 16 个 SVG 节点里唯独 ci 漏标）。names 保持契约原文作 hash 键。
NODES12_MATCH = [n.replace(" ", "") for n in NODES12]
POSTS10 = ["产品经理", "数据工程", "云平台架构", "测试架构", "硬件结构",
           "系统架构师", "SRE 站点可靠性", "算法专家", "安全架构", "射频与天线"]
OSS10 = ["netty", "ffmpeg", "mysql-connector-j", "ghostscript-lite", "qt-embedded",
         "mongodb-core", "openssl", "tflite-micro", "zlib", "libsass-fork"]
DIMS6 = ["交付", "质量", "效率", "投入产出", "协同", "人才"]

# ---- 父页接线配置（锚点均实测于页面源码；rows 是 CSS 选择器，names 是 §6 对象名） ----
# 分波追加：W2 先接一期三对「表格行级」下钻，图表画布级与面板级入口视各波页面实况扩充。
# ---- 二期扩充 W7：每个专题页的第 2 个子页 ----
# 锚点一律避开已被首个子页占用的行锚（同一批 li 挂两条 target 会互相覆盖 dataset.drillSub）
CHARTER3 = ["创意提案", "Charter 评审", "正式立项"]
CHARTER3_MATCH = [n.replace(" ", "") for n in CHARTER3]   # ★ 匹配前会剔空白，含空格名须另给 match
TRPTS6 = ["TR1", "TR2", "TR3", "TR4", "TR5", "TR6"]
IFPAIRS6 = ["软件↔硬件", "软件↔云端", "软件↔AI", "硬件↔云端", "硬件↔AI", "云端↔AI"]

SUB_CH = "大屏样板间-研发Charter立项台账1920.html"
SUB_YV = "大屏样板间-研发TR评审台账1920.html"
SUB_HG = "大屏样板间-研发预算执行台账1920.html"
SUB_DM = "大屏样板间-研发障碍与回顾台账1920.html"
SUB_PT = "大屏样板间-研发流水线运行台账1920.html"
SUB_RY = "大屏样板间-研发跨域接口台账1920.html"


PAGES = [
    {
        "file": "大屏样板间-研发产品组合与路标1920.html",
        "charts": [
            {"chartId": "lb-chart-funnel", "names": CHARTER3, "match": CHARTER3_MATCH, "sub": SUB_CH},
        ],
        "targets": [
            {"rows": "#lb-tbody li", "names": LINES4, "sub": SUB_DL},
        ],
    },
    {
        "file": "大屏样板间-研发IPD管道与评审1920.html",
        "charts": [
            {"chartId": "ip-chart-tr", "names": TRPTS6, "sub": SUB_YV},
        ],
        "targets": [
            {"rows": "#ip-tbody li", "names": PROJECTS8, "sub": SUB_DJ},
        ],
    },
    {
        "file": "大屏样板间-研发需求全生命周期1920.html",
        "targets": [
            {"rows": "#rq-tbody li", "names": SOURCES4, "sub": SUB_TZ},
        ],
    },
    # ---- 二期 · 敏捷执行（W3）----
    {
        "file": "大屏样板间-研发敏捷交付总览1920.html",
        "panels": [
            {"panelTitle": "障碍清单", "label": "障碍台账", "sub": SUB_DM},
        ],
        "targets": [
            {"rows": "#ag-tbody li", "names": TEAMS12, "sub": SUB_CQ},
        ],
    },
    {
        "file": "大屏样板间-研发看板流动效率1920.html",
        "targets": [
            {"rows": "#ks-tbody li", "names": BLOCKS5, "sub": SUB_BS},
        ],
    },
    {
        "file": "大屏样板间-研发质量与缺陷1920.html",
        "targets": [
            {"rows": "#qa-tbody li", "names": DOMAINS4, "sub": SUB_QX},
        ],
    },
    # ---- 三期 · 多域协同（W4）----
    {
        "file": "大屏样板间-研发软硬云AI集成协同1920.html",
        "charts": [
            {"chartId": "ct-chart-if", "names": IFPAIRS6, "sub": SUB_RY},
        ],
        "targets": [
            {"rows": "#ct-tbody li", "names": BASELINES4, "sub": SUB_JX},
        ],
    },
    {
        "file": "大屏样板间-研发硬件与样机1920.html",
        "targets": [
            {"rows": "#hj-tbody li", "names": BATCHES5, "sub": SUB_PC},
        ],
    },
    {
        "file": "大屏样板间-研发AI模型迭代1920.html",
        "targets": [
            {"rows": "#ai-tbody li", "names": MODELS5, "sub": SUB_ML},
        ],
    },
    # ---- 四期 · 组织与资产（W5）----
    {
        "file": "大屏样板间-研发多中心布局1920.html",
        "targets": [
            {"rows": "#gq-tbody li", "names": SITES6, "sub": SUB_BY},
        ],
        # 园区孪生是站点明细表的姊妹视角，行锚已被单中心详情占用（同一批 li 不能挂两条
        # target，会互相覆盖 dataset.drillSub），故走面板级入口，与行锚互不干扰。
        "panels": [
            {"panelTitle": "站点明细表", "label": "园区孪生", "sub": SUB_QJ},
        ],
    },
    # ---- 二期补齐（S12–S18）：7 个原本没有子页的专题页 ----
    {
        "file": "大屏样板间-研发投入与预算1920.html",
        "charts": [
            {"chartId": "ty-chart-bullet", "names": COSTS5, "sub": SUB_HG},
        ],
        "targets": [
            {"rows": "#ty-tbody li", "names": COSTS5, "sub": SUB_YZ},
        ],
    },
    {
        # 该页无表格：走图表画布 click（覆盖率箱线，类目名即五域仓库群）+ 面板级入口兜底
        "file": "大屏样板间-研发工程效能1920.html",
        "charts": [
            {"chartId": "dx-chart-coverage", "names": REPOS5, "sub": SUB_GC},
        ],
        "panels": [
            {"panelTitle": "单测覆盖率箱线", "label": "仓库群详情", "sub": SUB_GC},
            {"panelTitle": "流水线成功率日历热力", "label": "流水线台账", "sub": SUB_PT},
        ],
    },
    {
        # 事件行文本含 P1/P2/P3/P4 等级标记，按等级下钻到台账并定位该等级
        "file": "大屏样板间-研发云端服务与发布1920.html",
        "targets": [
            {"rows": "#cy-list li", "names": INCLV4, "sub": SUB_RZ},
        ],
        "panels": [
            {"panelTitle": "线上事件等级分布", "label": "事件台账", "sub": SUB_RZ},
        ],
    },
    {
        # 等距 SVG 的 16 个节点组带 data-node，textContent 含节点名原文（已浏览器实测）
        "file": "大屏样板间-研发交付流水线数字孪生1920.html",
        "targets": [
            {"rows": "[data-node]", "names": NODES12, "match": NODES12_MATCH, "sub": SUB_LJ},
        ],
        "panels": [
            {"panelTitle": "链路预警", "label": "节点详情", "sub": SUB_LJ},
        ],
    },
    {
        # 岗位只存在于图表里（rc-tbody 是六职能，不是岗位），故走画布 click + 面板入口
        "file": "大屏样板间-研发人才与能力1920.html",
        "charts": [
            {"chartId": "rc-chart-post", "names": POSTS10, "sub": SUB_RL},
        ],
        "panels": [
            {"panelTitle": "关键岗位饱和度", "label": "岗位台账", "sub": SUB_RL},
        ],
    },
    {
        "file": "大屏样板间-研发技术资产与复用1920.html",
        "targets": [
            {"rows": "#ta-tbody li", "names": OSS10, "sub": SUB_SM},
        ],
    },
    {
        "file": "大屏样板间-研发效能指数1920.html",
        "targets": [
            {"rows": "#pi-tbody li", "names": DIMS6, "sub": SUB_ZB},
        ],
    },
]

CSS_BEGIN = "  /* drill:begin —— 由 tools/inject_drilldown_rnd.py 注入，勿手改 */"
CSS_END = "  /* drill:end */"
JS_BEGIN = "<!-- drill-js:begin -->"
JS_END = "<!-- drill-js:end -->"

# 配色走研发系：底 rgba(18,34,78,.55)、描边 rgba(96,140,255,.22)、主色蓝 #5c9dff、
# 强调琥珀 #ffc24d、次文字 #7f92c4。这些页的 CSS 变量是 --rnd-*（跨页共用），
# 但下钻块要能独立整段删除，故一律写死字面值，不引用页面变量。
CSS_TPL = """
  .{p}-drill {{ cursor: pointer; position: relative; }}
  .{p}-drill::after {{
    content: "↗"; position: absolute; right: 6px; top: 50%; transform: translateY(-50%) translateX(-3px);
    font-size: 11px; font-weight: 700; line-height: 1; color: #ffc24d;
    opacity: 0; transition: opacity .2s ease, transform .2s ease; pointer-events: none; z-index: 3;
  }}
  .{p}-drill:hover::after {{ opacity: 0.95; transform: translateY(-50%) translateX(0); }}
  .{p}-drill:hover {{
    background: rgba(92, 157, 255, 0.15) !important;
    box-shadow: inset 0 0 0 1px rgba(92, 157, 255, 0.5), 0 0 16px -4px rgba(92, 157, 255, 0.6);
  }}
  /* 提示 chip：挂在面板头 h2 后面。margin-right:auto 吃掉 space-between 的空档，
     免得把面板头原有的 .xx-panel-tag 挤到中间去。 */
  .{p}-drill-hint {{
    margin-left: 8px; margin-right: auto; font-size: 10.5px; letter-spacing: 0.04em;
    color: #7f92c4; padding: 1px 7px; border-radius: 999px; white-space: nowrap;
    background: rgba(18, 34, 78, 0.55); border: 1px dashed rgba(96, 140, 255, 0.45);
  }}
  /* 面板级入口：子页是全量台账、无切换对象时用它，挂在相关面板头上 */
  .{p}-drill-entry {{
    margin-left: 10px; cursor: pointer; white-space: nowrap;
    font-size: 11px; font-weight: 700; letter-spacing: 0.06em; line-height: 1;
    padding: 4px 9px; border-radius: 999px; color: #061029;
    background: linear-gradient(140deg, #9cc2ff, #5c9dff);
    box-shadow: 0 0 9px -1px rgba(92, 157, 255, 0.75);
    transition: filter .18s ease, box-shadow .18s ease;
  }}
  .{p}-drill-entry:hover {{ filter: brightness(1.12); box-shadow: 0 0 16px -1px rgba(92, 157, 255, 0.95); }}
"""

JS_TPL = """
<script>
/* ===== 下钻入口（tools/inject_drilldown_rnd.py 注入） =====
   独立于父页主脚本：父页表格/卡片由 setInterval 轮播重绘，故用 MutationObserver 持续重新标记。 */
(() => {{
  "use strict";
  const P = "{p}";
  /* 长名优先匹配，避免短名把含它的长名截胡（如「星澜S3」与「星澜S3-EVT2」同表出现时） */
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
     一旦被冲掉，下一次 DOM 变动会把它补回来。scope 若挂在 <section class="xx-panel"> 上，
     先在 scope 内找面板头，找到就插在 h2 后面；找不到再退回元素自身。 */
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

  /* ECharts 画布下钻：柱 / 扇区 / 热力格 / 地图省份不是 DOM，只能绑图表实例的 click。
     取 params.name 或 params.data.name 去对象名列表里反查，命中即跳子页。 */
  CHARTS.forEach((c) => {{
    if (!window.echarts) return;
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
        const bySeries = c.by === "seriesName";
        const raw = (pm && (bySeries
          ? (pm.seriesName || pm.name)
          : (pm.name || (pm.data && pm.data.name) || pm.seriesName))) || "";
        if (!raw) return;
        /* 精确命中优先：画布点击拿到的就是节点名本身，松匹配会把不该跳的点也跳走 */
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

# 研发页的色板 token 统一是 --rnd-*（三字母、跨页共用），每页没有 --xx-bg，
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

    # CSS 块钉死插在 subnav 块之前（退化锚点：carousel → </style>）。
    # 若三支脚本都往 </style> 前插，每次重跑都会把自己顶到末位、彼此循环换位，
    # 整链永远不收敛（W3 实测：drill / carousel / mock_flag 三支轮流改写同一批文件）。
    # 钉死后波尾链序 drill→subnav→carousel→mock_flag 的固定点是
    # [drill, subnav, carousel, mockflag]，第二轮起零改动。
    css = CSS_BEGIN + CSS_TPL.format(p=p) + CSS_END + "\n"
    for anchor in ("  /* subnav:begin", "  /* carousel:begin"):
        if anchor in html:
            html = html.replace(anchor, css + anchor, 1)
            break
    else:
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
            m = re.match(r"#([\w-]+)", t.get("rows", ""))
            if m and ('id="%s"' % m.group(1)) not in html:
                bad.append("%s：rows 选择器根 id「%s」不存在" % (cfg["file"], m.group(1)))
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
