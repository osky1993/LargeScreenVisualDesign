#!/usr/bin/env python3
"""为视觉效果库生成索引页 index.html。

用法：
  python3 tools/build_index.py

行为：
  - 扫描 CONTENT_DIRS 里各内容目录本层的 .html（排除 *.inner.html、隐藏文件）；
    manifest 的 file 字段是相对仓库根的路径，index.html 直接拿它当 href
  - 「ECharts视觉实验室*」与「管理大屏配色专项*」类文件内容内嵌在 <iframe srcdoc="...">
    中（HTML 转义），参照 tools/labtool.py 的方式解码后提取 <title> 与方案名
  - 普通 HTML（如 图表配色方案-21套.html）直接取 <title>
  - 生成自包含 index.html：内嵌 manifest JSON + 内联 CSS/JS，无任何外部依赖
  - 可重跑：目录新增文件后重新运行即可更新
"""
import html
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "index.html"

# 内容目录（只扫这几个目录的本层 .html；新增分类目录时加到这里）
CONTENT_DIRS = [
    "charts",               # 图表方案画廊
    "screens",              # 通用样板间
    "screens/public-funds",  # 公共资金专题样板间
    "components",           # 大屏组件与脚手架
    "palettes",             # 配色陈列
    "studies",              # 选型/效果对比
]

SRCDOC_RE = re.compile(r'srcdoc="(.*?)"', re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
HAN_RE = re.compile(r"[一-鿿]")

# 文件名 -> 图表类型（按顺序匹配，先匹配更具体的）
CATEGORY_RULES = [
    # 须列首中的列首：公共资金专题系列文件名同时含「样板间」与「地图/柱状图」等关键词，
    # 更具体的前缀必须先匹配，才能与通用样板间分开成组。
    ("大屏样板间-公共资金", "公共资金专题"),
    ("样板间", "样板间"),  # 须列首：样板间文件名可能含「地图」「柱状图」等图表关键词，成品屏优先归类
    ("柱线混合", "柱线混合"),
    ("动态排序柱状图", "动态排序"),
    ("柱状图", "柱状图"),
    ("折线图", "折线图"),
    ("饼图", "饼图"),
    ("仪表盘", "仪表盘"),
    ("雷达图", "雷达图"),
    ("散点气泡", "散点气泡"),
    ("日历热力", "日历热力"),
    ("热力图", "热力图"),
    ("地图", "地图"),
    ("桑基", "桑基图"),
    ("词云", "词云"),
    ("漏斗", "漏斗图"),
    ("瀑布", "瀑布图"),
    ("水球", "水球图"),
    ("象形柱", "象形柱图"),
    ("矩形树图", "矩形树图"),
    ("旭日", "旭日图"),
    ("大规模网络", "关系图"),  # graphGL 大规模网络图，归入关系图族
    ("关系图", "关系图"),
    ("甘特", "甘特图"),
    ("树图", "树图"),
    ("主题河流", "主题河流"),
    ("平行坐标", "平行坐标"),
    ("3D", "三维"),
    ("K线", "K线图"),
    ("组合图表", "组合图表"),
    ("联动与时间轴", "联动时间轴"),
    ("矩阵小多图", "矩阵小多图"),
    ("统计分布", "统计分布"),
    ("区间与目标", "区间目标"),
    ("弦图", "弦图"),
    ("路径图", "路径图"),
    ("数据集变换", "数据集变换"),
    ("大屏组件", "大屏组件"),
    ("大屏业务组件", "大屏组件"),  # 别名：业务组件实验室文件名不含「大屏组件」连续子串
    ("配色", "配色方案"),
]

# 前端筛选 chip 顺序与卡片徽章色：分类名须与 CATEGORY_RULES 字面一致。
# index.html 首次生成时注入模板、日常重建时原地更新，两份前端常量的唯一数据源在此。
FRONT_CATEGORIES = [
    "全部", "柱状图", "动态排序", "象形柱图", "折线图", "饼图", "柱线混合", "瀑布图",
    "漏斗图", "水球图", "仪表盘", "雷达图", "散点气泡", "热力图", "日历热力", "K线图",
    "地图", "三维", "桑基图", "关系图", "树图", "矩形树图", "旭日图", "主题河流",
    "平行坐标", "词云", "甘特图", "组合图表", "联动时间轴", "矩阵小多图", "统计分布",
    "区间目标", "弦图", "路径图", "数据集变换", "大屏组件", "公共资金专题", "样板间", "配色方案", "其他",
]
FRONT_BADGE_COLORS = {
    "柱状图": "#4dd8ff", "动态排序": "#63e6ff", "折线图": "#37e2c8", "饼图": "#ffb454",
    "柱线混合": "#7f9dff", "地图": "#5ce08a", "桑基图": "#ff8fa8", "仪表盘": "#c792ff",
    "雷达图": "#b0a4ff", "散点气泡": "#7fd0ff", "热力图": "#ff9d6b", "日历热力": "#ffc36b",
    "词云": "#8fe0b8", "漏斗图": "#f0a4d8", "瀑布图": "#9fd483", "水球图": "#5ad7ff",
    "象形柱图": "#6fc2ff", "矩形树图": "#66d9a8", "旭日图": "#ffb36b", "关系图": "#c79aff",
    "甘特图": "#7fa8ff", "树图": "#7edb9a", "主题河流": "#6bd4d0", "平行坐标": "#a8b8ff",
    "三维": "#66e0ff", "K线图": "#ff9d8a", "组合图表": "#ffd28a", "联动时间轴": "#8ad4ff",
    "矩阵小多图": "#7fc8e8", "统计分布": "#a4e07f", "区间目标": "#ff9db8", "弦图": "#d2a8ff",
    "大屏组件": "#e0c46b", "样板间": "#ffb0d0", "配色方案": "#ffd75e", "路径图": "#5ce0d0", "数据集变换": "#d0a0ff", "其他": "#8fb4d9",
    "公共资金专题": "#f0c060",  # 琥珀金，与该系列页面主色一致
}

# 顶部筛选 chip 合并为 8 大类（卡片徽章仍按细分类别 FRONT_BADGE_COLORS 着色）。
# FRONT_FAMILIES = chip 顺序；FAMILY_OF = 细分类别 -> 大类映射（键须与 CATEGORY_RULES 字面一致）。
FRONT_FAMILIES = [
    "全部", "对比趋势", "占比构成", "评估分布", "关系流向", "地图三维", "专题联动",
    "公共资金专题样板间", "样板间", "大屏组件", "其他",
]
FAMILY_OF = {
    "柱状图": "对比趋势", "动态排序": "对比趋势", "象形柱图": "对比趋势", "折线图": "对比趋势",
    "柱线混合": "对比趋势", "瀑布图": "对比趋势", "矩阵小多图": "对比趋势", "主题河流": "对比趋势",
    "饼图": "占比构成", "漏斗图": "占比构成", "旭日图": "占比构成", "矩形树图": "占比构成", "词云": "占比构成",
    "雷达图": "评估分布", "仪表盘": "评估分布", "水球图": "评估分布", "散点气泡": "评估分布",
    "区间目标": "评估分布", "统计分布": "评估分布", "热力图": "评估分布", "日历热力": "评估分布", "平行坐标": "评估分布",
    "关系图": "关系流向", "树图": "关系流向", "桑基图": "关系流向", "弦图": "关系流向", "路径图": "关系流向",
    "地图": "地图三维", "三维": "地图三维",
    "K线图": "专题联动", "甘特图": "专题联动", "组合图表": "专题联动", "联动时间轴": "专题联动", "数据集变换": "专题联动",
    "大屏组件": "大屏组件", "样板间": "样板间", "配色方案": "大屏组件",
    "公共资金专题": "公共资金专题样板间",  # 独立成组，不与通用样板间混排
    "其他": "其他",
}

# ECharts 组件/工具栏等界面文案，不是方案名
UI_BLOCKLIST = {
    "数据视图", "还原", "保存为图片", "区域缩放", "区域缩放还原",
    "切换为折线图", "切换为柱状图", "切换为堆叠", "切换为平铺",
    "横向选择", "纵向选择", "保持选择", "清除选择", "矩形选择",
    "刷新全部数据", "演示控制",
}
CALENDAR_RE = re.compile(
    r"^(?:[一二三四五六七八九十]{1,3}月|\d{1,2}月|星期[一二三四五六日天]|周[一二三四五六日天])$"
)


def is_scheme_name(name: str, min_len: int) -> bool:
    """过滤模板占位符、界面文案、历法词等非方案名条目。"""
    if not name or len(name) < min_len or len(name) > 40:
        return False
    if not HAN_RE.search(name):
        return False
    if "${" in name or "' +" in name or '" +' in name or "<" in name or "&" in name:
        return False
    if name.startswith("_"):  # 内部图层键（如 __金额底座）
        return False
    if re.search(r"[。，；！？]", name):  # 整句文案不是方案名
        return False
    if name in UI_BLOCKLIST or CALENDAR_RE.match(name):
        return False
    return True


def extract_schemes(doc: str) -> list:
    """从内页 HTML 中提取中文方案名（多策略并集，按出现顺序去重）。

    策略（按可信度排序）：
      1. 静态 <h2>/<h3> 文本（剔除 ${...}、' + 等模板占位符）
      2. 编号数组行：["01", "方案名", ...]
      3. JS 对象字段：title: "方案名"
      4. 中文开头的数组行：["方案名", "副标题", ...]（要求 >= 4 字，降噪）
      5. JS 对象字段：name: "方案名"（要求 >= 4 字，避免命中系列名/轴名）
    """
    found = {}

    def add(name, min_len):
        name = re.sub(r"\s+", " ", name).strip()
        if is_scheme_name(name, min_len) and name not in found:
            found[name] = True

    for m in re.findall(r"<h[23][^>]*>([^<]{1,60})</h[23]>", doc):
        add(m, 2)
    for m in re.findall(r'\[\s*"\d{1,3}"\s*,\s*"([^"\n]{2,40})"', doc):
        add(m, 2)
    for m in re.findall(r'\btitle\s*:\s*["\']([^"\'\n]{2,40})["\']', doc):
        add(m, 2)
    for m in re.findall(r'\[\s*["\']([^"\'\n]{2,40})["\']\s*,\s*["\']', doc):
        add(m, 4)
    for m in re.findall(r'\bname\s*:\s*["\']([^"\'\n]{2,40})["\']', doc):
        add(m, 4)
    return list(found)


def categorize(stem: str) -> str:
    for key, cat in CATEGORY_RULES:
        if key in stem:
            return cat
    return "其他"


def human_size(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    return f"{n / 1024:.0f} KB"


def get_title(doc: str) -> str:
    m = TITLE_RE.search(doc)
    return m.group(1).strip() if m else ""


# 拆分自综合库的四个文件：应用脚本保留了其他组的死代码，
# 方案名从对应组的 items 块中精确提取，避免搜索误命中
SPLIT_GROUP_ID = {
    "仪表盘28": "gauge",
    "雷达图24": "radar",
    "散点气泡图28": "scatter",
    "热力图25": "heatmap",
}


def split_group_schemes(doc: str, gid: str) -> list:
    start = doc.find('id: "%s"' % gid)
    if start < 0:
        return []
    nxt = re.search(r'id:\s*"(?:gauge|radar|scatter|heatmap)"', doc[start + 20:])
    block = doc[start:start + 20 + (nxt.start() if nxt else 24000)]
    found = {}
    for m in re.findall(r'\[\s*"([^"\n]{2,40})"\s*,\s*"', block):
        name = re.sub(r"\s+", " ", m).strip()
        if is_scheme_name(name, 2) and name not in found:
            found[name] = True
    return list(found)


def scan_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    stem = path.stem

    m = SRCDOC_RE.search(raw)
    if m:  # 实验室类：真实内容在 iframe srcdoc 中（HTML 转义）
        inner = html.unescape(m.group(1))
        title = get_title(inner) or get_title(raw)
        schemes = extract_schemes(inner)
    else:  # 普通 HTML
        title = get_title(raw)
        schemes = extract_schemes(raw)
    if not title or not HAN_RE.search(title):
        title = title or stem

    # 方案数：优先取文件名中的数字之和（如 仪表盘28-雷达图24-... = 104），否则取提取到的方案名数
    digits = re.findall(r"\d+", stem)
    count = sum(int(d) for d in digits) if digits else len(schemes)

    cat = categorize(stem)
    if "配色方案-21套" in stem:  # 普通 HTML，方案数标 21 套配色
        count = 21
    if cat in ("样板间", "公共资金专题"):  # 整屏样板间为 1 个成品大屏，文件名数字是分辨率而非方案数
        count = 1
    if "3D地球与立体柱" in stem:  # 文件名含 "3D" 会被数字求和污染，方案数以实际卡数为准
        count = 11
    for key, gid in SPLIT_GROUP_ID.items():
        if key in stem and m:
            grouped = split_group_schemes(inner, gid)
            if grouped:
                schemes = grouped
            break

    size = path.stat().st_size
    return {
        "file": path.relative_to(ROOT).as_posix(),   # 带目录的相对路径，index.html 直接当 href 用
        "title": title,
        "category": cat,
        "count": count,
        "schemes": schemes,
        "size": size,
        "size_label": human_size(size),
    }


PUBFUND_PORTAL = "大屏样板间-公共资金专题总览1920.html"


def pubfund_rank() -> dict:
    """公共资金专题组的固定排序：总览门户 → 13 个专题页 → 各专题页各自的二级子页。

    次序不在这里重复维护，而是从既有的两份权威来源推导，避免第三份副本各自漂移：
      · 13 个专题页的先后 = inject_carousel.PAGES（轮播页序，即需求给的原始顺序）
      · 父页 → 子页的归属 = inject_drilldown.PAGES（下钻入口配置）
    子页整体排在 13 个专题页之后，组内按其父页的位置排。
    未登记的公共资金文件排到末尾并按文件名兜底，不会因为漏配而丢卡片。
    """
    rank = {PUBFUND_PORTAL: 0}
    try:
        import inject_carousel
        import inject_drilldown
    except Exception as e:                       # 工具脚本缺失时退化为文件名排序，不阻断建索引
        print("  ! 公共资金固定排序不可用（%s），该组回退为文件名排序" % e)
        return rank
    parents = [f for f, _ in inject_carousel.PAGES]
    for i, f in enumerate(parents):
        rank[f] = 100 + i
    subs_of = {}
    for cfg in inject_drilldown.PAGES:
        seen = []
        for grp in ("targets", "charts", "panels"):
            for t in cfg.get(grp, []):
                if t["sub"] not in seen:
                    seen.append(t["sub"])
        subs_of[cfg["file"]] = seen
    n = 0
    for f in parents:
        for s in subs_of.get(f, []):
            if s not in rank:
                rank[s] = 1000 + n
                n += 1
    return rank


def scan() -> list:
    entries = []
    for d in CONTENT_DIRS:
        for p in sorted((ROOT / d).glob("*.html")):   # 只扫该目录本层，子目录各自登记在 CONTENT_DIRS
            name = p.name
            if name.endswith(".inner.html") or name.startswith("."):
                continue
            entries.append(scan_file(p))
    order = {cat: i for i, (_, cat) in enumerate(CATEGORY_RULES)}
    rank = pubfund_rank()
    entries.sort(key=lambda e: (
        order.get(e["category"], 99),
        rank.get(Path(e["file"]).name, 9999) if e["category"] == "公共资金专题" else 0,
        e["file"],
    ))
    return entries


TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ECharts 视觉效果库 · 索引</title>
<style>
:root{
  --bg:rgb(10,30,60); --bg2:rgb(7,22,46);
  --accent:#4dd8ff; --accent2:#37e2c8;
  --ink:#dcecff; --ink-dim:#7fa3cc;
  --card:rgba(20,52,96,.45); --card-border:rgba(77,216,255,.18);
}
*{box-sizing:border-box;margin:0;padding:0}
html{background:var(--bg)}
body{
  min-height:100vh;color:var(--ink);
  font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;
  background:
    radial-gradient(1100px 500px at 15% -10%, rgba(45,120,220,.28), transparent 60%),
    radial-gradient(900px 480px at 85% -5%, rgba(55,226,200,.14), transparent 55%),
    linear-gradient(180deg, var(--bg) 0%, var(--bg2) 100%);
  background-attachment:fixed;
  padding:34px clamp(16px,4vw,56px) 60px;
}
header{margin-bottom:26px}
.head-line{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.beacon{width:10px;height:10px;border-radius:50%;background:var(--accent);
  box-shadow:0 0 12px var(--accent),0 0 28px rgba(77,216,255,.6);flex:none}
h1{font-size:clamp(22px,3.4vw,34px);font-weight:700;letter-spacing:.06em;
  background:linear-gradient(92deg,#eaf6ff 20%,var(--accent) 75%,var(--accent2));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.subtitle{margin-top:10px;color:var(--ink-dim);font-size:14px;letter-spacing:.05em}
.subtitle strong{color:var(--accent);font-weight:600}
.toolbar{margin:24px 0 20px;display:flex;flex-direction:column;gap:14px}
.searchbox{position:relative;max-width:560px}
.searchbox input{
  width:100%;padding:12px 16px 12px 42px;font-size:15px;color:var(--ink);
  background:rgba(12,36,70,.75);border:1px solid var(--card-border);border-radius:10px;
  outline:none;transition:border-color .2s, box-shadow .2s;
}
.searchbox input::placeholder{color:rgba(127,163,204,.65)}
.searchbox input:focus{border-color:rgba(77,216,255,.55);box-shadow:0 0 0 3px rgba(77,216,255,.12)}
.searchbox .icon{position:absolute;left:14px;top:50%;transform:translateY(-50%);
  width:16px;height:16px;pointer-events:none;opacity:.7}
.filters{display:flex;flex-wrap:wrap;gap:8px}
.filter-chip{
  padding:6px 14px;font-size:13px;letter-spacing:.04em;color:var(--ink-dim);
  background:rgba(14,40,76,.6);border:1px solid rgba(77,216,255,.14);border-radius:999px;
  cursor:pointer;user-select:none;transition:all .15s;
}
.filter-chip:hover{color:var(--ink);border-color:rgba(77,216,255,.4)}
.filter-chip.active{
  color:#04182e;background:linear-gradient(92deg,var(--accent),var(--accent2));
  border-color:transparent;font-weight:600;box-shadow:0 0 14px rgba(77,216,255,.35);
}
.filter-chip .n{opacity:.75;font-size:12px;margin-left:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px}
.card{
  display:flex;flex-direction:column;gap:12px;padding:18px 18px 16px;
  background:var(--card);border:1px solid var(--card-border);border-radius:14px;
  text-decoration:none;color:var(--ink);position:relative;overflow:hidden;
  transition:transform .18s, border-color .18s, box-shadow .18s;
  backdrop-filter:blur(6px);
}
.card::before{content:"";position:absolute;inset:0 0 auto 0;height:2px;
  background:linear-gradient(90deg,transparent,rgba(77,216,255,.65),transparent);
  opacity:0;transition:opacity .2s}
.card:hover{transform:translateY(-3px);border-color:rgba(77,216,255,.5);
  box-shadow:0 10px 30px rgba(0,10,30,.45),0 0 18px rgba(77,216,255,.12)}
.card:hover::before{opacity:1}
.card-top{display:flex;justify-content:space-between;align-items:center;gap:10px}
.badge{
  font-size:12px;letter-spacing:.08em;padding:4px 11px;border-radius:6px;
  border:1px solid;font-weight:600;flex:none;
}
.size{color:var(--ink-dim);font-size:12px;letter-spacing:.04em}
.fname{font-size:17px;font-weight:700;line-height:1.45;letter-spacing:.02em;word-break:break-all}
.ftitle{color:var(--ink-dim);font-size:12.5px;margin-top:-6px;letter-spacing:.03em}
.meta{display:flex;gap:14px;color:var(--ink-dim);font-size:12.5px;letter-spacing:.04em}
.meta strong{color:var(--accent);font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto}
.chip{
  font-size:11.5px;padding:3px 9px;border-radius:999px;color:#a9cef2;
  background:rgba(77,216,255,.08);border:1px solid rgba(77,216,255,.16);
  letter-spacing:.02em;white-space:nowrap;
}
.chip.hit{color:#04182e;background:linear-gradient(92deg,var(--accent),var(--accent2));
  border-color:transparent;font-weight:600}
.chip mark{background:transparent;color:inherit;font-weight:700;text-decoration:underline;
  text-underline-offset:2px}
.more{font-size:11.5px;color:var(--ink-dim);padding:3px 4px;letter-spacing:.03em}
.empty{grid-column:1/-1;text-align:center;color:var(--ink-dim);padding:70px 0;
  font-size:15px;letter-spacing:.08em}
footer{margin-top:44px;color:rgba(127,163,204,.55);font-size:12px;letter-spacing:.06em;
  text-align:center}
</style>
</head>
<body>
<header>
  <div class="head-line"><span class="beacon" aria-hidden="true"></span><h1>ECharts 视觉效果库 · 索引</h1></div>
  <p class="subtitle">收录 <strong>__FILE_COUNT__</strong> 个文件 · 方案 <strong>__SCHEME_COUNT__</strong> 项 · 提取方案名 <strong>__NAME_COUNT__</strong> 个 · 构建于 __BUILD_TIME__</p>
</header>

<div class="toolbar">
  <div class="searchbox">
    <svg class="icon" viewBox="0 0 16 16" fill="none" stroke="#7fa3cc" stroke-width="1.6">
      <circle cx="7" cy="7" r="4.6"/><path d="M10.6 10.6 L14 14"/>
    </svg>
    <input id="q" type="search" placeholder="搜索文件名、图表类型或方案名（如：霓虹、金属、仪表盘）" autocomplete="off">
  </div>
  <div class="filters" id="filters"></div>
</div>

<main class="grid" id="grid" aria-label="视觉效果文件卡片"></main>

<footer>ECharts 视觉效果库 · 由 tools/build_index.py 生成 · 点击卡片在新标签页打开</footer>

<script id="manifest" type="application/json">__MANIFEST__</script>
<script>
(function(){
  "use strict";
  var MANIFEST = JSON.parse(document.getElementById("manifest").textContent);
  var CATEGORIES = __CATEGORIES__;
  var FAMILY_OF = __FAMILY_OF__;
  function famOf(e){ return FAMILY_OF[e.category] || "其他"; }
  var BADGE_COLORS = __BADGE_COLORS__;
  var MAX_CHIPS = 6;
  var state = { q: "", cat: "全部" };
  var grid = document.getElementById("grid");
  var filtersEl = document.getElementById("filters");

  function esc(s){
    return String(s).replace(/[&<>"']/g, function(c){
      return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[c];
    });
  }
  function highlight(text, tokens){
    var safe = esc(text);
    if(!tokens.length) return safe;
    tokens.forEach(function(t){
      var re = new RegExp("(" + esc(t).replace(/[.*+?^${}()|[\\]\\\\]/g,"\\\\$&") + ")","gi");
      safe = safe.replace(re, "<mark>$1</mark>");
    });
    return safe;
  }
  function tokens(){
    return state.q.trim().toLowerCase().split(/\\s+/).filter(Boolean);
  }
  function matchEntry(e, toks){
    if(!toks.length) return {ok:true, hits:[]};
    var hitSchemes = {};
    var ok = toks.every(function(t){
      var base = (e.file + " " + e.title + " " + e.category).toLowerCase().indexOf(t) >= 0;
      var schemeHit = false;
      e.schemes.forEach(function(s){
        if(s.toLowerCase().indexOf(t) >= 0){ schemeHit = true; hitSchemes[s] = true; }
      });
      return base || schemeHit;
    });
    return {ok: ok, hits: Object.keys(hitSchemes)};
  }
  function chipHtml(name, hit, toks){
    return '<span class="chip' + (hit ? " hit" : "") + '">' + highlight(name, toks) + "</span>";
  }
  function cardHtml(e, hits, toks){
    var color = BADGE_COLORS[e.category] || BADGE_COLORS["其他"];
    var shown = [], used = {};
    hits.forEach(function(s){ if(shown.length < 8 && !used[s]){ shown.push([s,true]); used[s]=1; } });
    e.schemes.forEach(function(s){ if(shown.length < Math.max(MAX_CHIPS, hits.length) && !used[s]){ shown.push([s,false]); used[s]=1; } });
    var rest = e.schemes.length - shown.length;
    var chips = shown.map(function(p){ return chipHtml(p[0], p[1], toks); }).join("");
    if(rest > 0) chips += '<span class="more">+' + rest + "</span>";
    if(!e.schemes.length) chips = '<span class="more">—</span>';
    var fname = e.file.split("/").pop().replace(/\\.html$/,"");   // 卡片只显示文件名，目录信息在 href 里
    var titleLine = (e.title && e.title !== fname) ?
      '<div class="ftitle">' + highlight(e.title, toks) + "</div>" : "";
    return '<a class="card" href="' + encodeURI(e.file) + '" target="_blank" rel="noopener">' +
      '<div class="card-top">' +
        '<span class="badge" style="color:' + color + ";border-color:" + color + '55;background:' + color + '14">' + esc(e.category) + "</span>" +
        '<span class="size">' + esc(e.size_label) + "</span>" +
      "</div>" +
      '<div class="fname">' + highlight(fname, toks) + "</div>" +
      titleLine +
      '<div class="meta"><span>方案 <strong>' + e.count + "</strong></span>" +
        '<span>提取方案名 <strong>' + e.schemes.length + "</strong></span></div>" +
      '<div class="chips">' + chips + "</div>" +
    "</a>";
  }
  function render(){
    var toks = tokens();
    var htmlParts = [];
    MANIFEST.forEach(function(e){
      if(state.cat !== "全部" && famOf(e) !== state.cat) return;
      var m = matchEntry(e, toks);
      if(!m.ok) return;
      htmlParts.push(cardHtml(e, m.hits, toks));
    });
    grid.innerHTML = htmlParts.length ? htmlParts.join("") :
      '<div class="empty">没有匹配的文件 —— 换个关键词试试</div>';
  }
  function renderFilters(){
    var counts = {};
    MANIFEST.forEach(function(e){ var f = famOf(e); counts[f] = (counts[f]||0) + 1; });
    filtersEl.innerHTML = CATEGORIES.filter(function(c){
      return c !== "其他" || counts["其他"];
    }).map(function(c){
      var n = c === "全部" ? MANIFEST.length : (counts[c] || 0);
      return '<button type="button" class="filter-chip' + (state.cat===c?" active":"") +
        '" data-cat="' + esc(c) + '">' + esc(c) + '<span class="n">' + n + "</span></button>";
    }).join("");
  }
  filtersEl.addEventListener("click", function(ev){
    var btn = ev.target.closest(".filter-chip");
    if(!btn) return;
    state.cat = btn.dataset.cat;
    renderFilters(); render();
  });
  document.getElementById("q").addEventListener("input", function(ev){
    state.q = ev.target.value; render();
  });
  renderFilters(); render();
})();
</script>
</body>
</html>
"""


def dump_manifest_json(manifest: list) -> str:
    manifest_json = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    return manifest_json.replace("</", "<\\/")  # 防止提前闭合 script 标签


def build_html(manifest: list) -> str:
    return (
        TEMPLATE
        .replace("__MANIFEST__", dump_manifest_json(manifest))
        .replace("__CATEGORIES__", json.dumps(FRONT_FAMILIES, ensure_ascii=False))
        .replace("__FAMILY_OF__", json.dumps(FAMILY_OF, ensure_ascii=False))
        .replace("__BADGE_COLORS__", json.dumps(FRONT_BADGE_COLORS, ensure_ascii=False))
        .replace("__FILE_COUNT__", str(len(manifest)))
        .replace("__SCHEME_COUNT__", str(sum(e["count"] for e in manifest)))
        .replace("__NAME_COUNT__", str(sum(len(e["schemes"]) for e in manifest)))
        .replace("__BUILD_TIME__", time.strftime("%Y-%m-%d %H:%M"))
    )


def patch_existing(doc: str, manifest: list):
    """原地只更新数据区，保留手工维护的头部/底部说明文字。

    数据区共四处：卡片 manifest JSON、CATEGORIES、BADGE_COLORS、统计行。
    任一数据区匹配失败返回 None（由调用方整页重建并提示）。"""
    def counts_line(prefix: str) -> str:
        # prefix 保留手工可能加的「最后」等修饰（如「最后构建于」），避免原地更新时丢失
        return (
            "收录 <strong>%d</strong> 个文件 · 方案 <strong>%d</strong> 项 · "
            "提取方案名 <strong>%d</strong> 个 · %s构建于 %s"
            % (
                len(manifest),
                sum(e["count"] for e in manifest),
                sum(len(e["schemes"]) for e in manifest),
                prefix,
                time.strftime("%Y-%m-%d %H:%M"),
            )
        )
    manifest_json = dump_manifest_json(manifest)
    substitutions = [
        (
            r'(<script id="manifest" type="application/json">).*?(</script>)',
            lambda m: m.group(1) + manifest_json + m.group(2),
        ),
        (
            r"var CATEGORIES = \[.*?\];",
            lambda m: "var CATEGORIES = " + json.dumps(FRONT_FAMILIES, ensure_ascii=False) + ";",
        ),
        (
            r"var FAMILY_OF = \{.*?\};",
            lambda m: "var FAMILY_OF = " + json.dumps(FAMILY_OF, ensure_ascii=False) + ";",
        ),
        (
            r"var BADGE_COLORS = \{.*?\};",
            lambda m: "var BADGE_COLORS = " + json.dumps(FRONT_BADGE_COLORS, ensure_ascii=False) + ";",
        ),
        (
            r"收录 <strong>\d+</strong> 个文件 · 方案 <strong>\d+</strong> 项 · "
            r"提取方案名 <strong>\d+</strong> 个 · (最后)?构建于 [^<]*",
            lambda m: counts_line(m.group(1) or ""),
        ),
    ]
    for pattern, repl in substitutions:
        doc, n = re.subn(pattern, repl, doc, count=1, flags=re.S)
        if n != 1:
            return None
    return doc


def main():
    manifest = scan()
    if OUT.exists():
        patched = patch_existing(OUT.read_text(encoding="utf-8"), manifest)
        if patched is not None:
            OUT.write_text(patched, encoding="utf-8")
            print(f"已原地更新数据区 -> {OUT}（头部/底部手工说明文字未改动）")
        else:
            OUT.write_text(build_html(manifest), encoding="utf-8")
            print(f"警告：未匹配到全部数据区，已整页重建 -> {OUT}；如有手工说明文字请从 git 恢复后重跑")
    else:
        OUT.write_text(build_html(manifest), encoding="utf-8")
        print(f"已生成 -> {OUT}")
    print(f"文件 {len(manifest)} 个，方案合计 {sum(e['count'] for e in manifest)} 项")
    for e in manifest:
        print(f"  [{e['category']}] {e['file']}  方案 {e['count']} · 提取名 {len(e['schemes'])} · {e['size_label']}")


if __name__ == "__main__":
    main()
