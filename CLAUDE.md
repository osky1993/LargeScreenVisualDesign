# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

面向管理大屏的 **ECharts 6 视觉方案库**：一堆自包含静态 HTML，每个页面是可运行的图表/大屏样例。无构建系统、无 npm 依赖、无测试框架——所有产物就是能双击打开的 HTML，运行时从 CDN 加载 echarts。首页 `index.html` 是索引，收录并可筛选/搜索全部方案。文档与业务口径以中文为主（银行/金融题材）。

## 常用命令

```bash
# 本地预览（务必用 HTTP，不要用 file://——地图内联数据大、CSP 严、部分浏览器会拦）
python3 -m http.server 8000        # 然后开 http://localhost:8000/index.html

# 在内容目录里新增/改名/改内容后，重建索引（幂等，可反复跑）
python3 tools/build_index.py

# 新增样板间后，补上顶边「模拟数据」标识（幂等；--remove 整批摘掉）
python3 tools/inject_mock_flag.py

# 编辑某个「实验室」文件的内容（见下：实验室是 srcdoc 套壳，不能直接改）
python3 tools/labtool.py decode charts/ECharts视觉实验室-柱状图8.html   # → 生成 *.inner.html
#   ...编辑 charts/ECharts视觉实验室-柱状图8.inner.html...
python3 tools/labtool.py encode charts/ECharts视觉实验室-柱状图8.html   # 转义写回 srcdoc

# 改了 shared/lab-addons.js 或 themes.js 后，把公共模块重新注入某实验室（幂等）
python3 tools/inject_addons.py charts/<实验室.html> '{"headSelector":".xxx-panel-header","chartSelector":".xxx-chart"}'

# 再生成共享资源（改了源文件才需要）
python3 tools/extract_themes.py    # 从两个配色实验室重抽 33 套主题 → shared/themes.js
python3 tools/fetch_geo.py         # 从阿里 DataV 抓边界 → shared/geo-data.js（需联网 + 可选 shapely）
```

无自动化测试。验证方式 = `build_index.py` 打印的「分类/方案数/大小」汇总（人工核对分类和 count 是否对）+ 起 HTTP 服务后浏览器逐页目检（控制台零报错、窗口缩放等比、图表渲染、数字勾稽）。

## 架构要点

**目录约定**：根目录只放 `index.html` 与 README/CLAUDE，产物按类别分目录，新增文件请对号入座——
`charts/`（图表方案画廊）、`screens/`（通用样板间）、`screens/public-funds/`（公共资金专题 27 块，
页面互链是同目录相对路径）、`components/`（大屏组件与脚手架）、`palettes/`（配色陈列）、
`studies/`（选型/效果对比）、`docs/`（文档）、`shared/`（再生成的共享资源）、`tools/`（维护脚本）。
新开一个分类目录必须同时加进 `build_index.py` 的 `CONTENT_DIRS`，否则索引扫不到。

**两类产物文件形态完全不同，编辑方式也不同：**

1. **实验室**（`ECharts视觉实验室-*.html`、`大屏组件实验室*.html`、配色实验室等）——外层是带严格 CSP 的外壳，真实内容 HTML 转义后内嵌在 `<iframe srcdoc="...">` 里。**绝不能直接编辑 srcdoc**；用 `labtool.py decode/encode` 走内页。新建实验室：写好独立内页 → `wrap_lab.py <inner> <out> <标题>` 套壳 → `inject_addons.py` 注入换肤+复制模块。这类文件自带「配色主题」下拉（33 套）和每卡「复制配置」按钮，来自 `shared/lab-addons.js` + `shared/themes.js`。

2. **样板间**（`大屏样板间-*.html`）——纯自包含单文件，**不套壳**，直接用编辑器改。是 1920×1080 成品大屏样例。当前 30 块：10 总览首页 + 19 专题内容页 + 1 轮播多页组。

**`index.html` 是自动生成的，不要手改数据区。** `build_index.py` 扫 `CONTENT_DIRS` 里各内容目录**本层**的 `*.html`（跳过 `*.inner.html`、隐藏文件；新增分类目录要加进这个常量），manifest 的 `file` 是相对仓库根的路径、index.html 直接当 href 用，从每个文件的 `<title>`、srcdoc 内文案、编号数组等自动抽卡片标题、分类、方案名。对已存在的 index.html 只**原地替换 4 个数据区**（`<script id="manifest">` 卡片 JSON、`CATEGORIES`、`FAMILY_OF`、`BADGE_COLORS`）和统计行——页面顶部/底部的说明文字是手工维护的，重建不覆盖。跑完看输出是「已原地更新」还是「整页重建」，若整页重建说明某数据区正则没匹配到，`git checkout -- index.html` 恢复手工文字再排查。两个易踩的特判都在 `build_index.py`：① 样板间强制 `count=1`（文件名里的 `1920` 是分辨率不是方案数）；② `CATEGORY_RULES` 按顺序首个子串命中，「样板间」规则必须在列首，否则名字含「地图/柱状图/饼图」等关键词的样板间会被图表分类抢走、绕过 count=1 特判。

**`shared/`** 是运行时共享资源，由 `tools/` 脚本从源文件再生成，不手编：`geo-data.js`（全国/长三角/江苏/苏南苏中苏北三板块的 GeoJSON，供页面**内联**用，页面本身不联网取地图）、`themes.js`（33 套主题）、`lab-addons.js`（复制+换肤公共模块）。

## 样板间专题页范式（新增/修改成品大屏时必守）

所有 `大屏样板间-*.html` 遵循同一套骨架，改动或新建时照抄现有页（模仿基准 `screens/大屏样板间-客群画像专题1920.html`；地图页参考 `screens/大屏样板间-指挥调度1920.html`）：

- **舞台**：暗底 `#04101f` + 一个 `.xx-stage` 固定 1920×1080，`position:absolute; left/top:50%; transform:translate(-50%,-50%) scale()`；`fitStage()` 用 `Math.min(innerWidth/1920, innerHeight/1080)` 等比缩放，监听 resize。因为整台靠 CSS transform 缩放，**ECharts 即时 `init` 后不调 `chart.resize()`**（像素尺寸恒定）。
- **CSS 前缀隔离**：每屏一个唯一 2 字母前缀（`dp-`/`np-`/`fc-`…），所有 class/id/CSS 变量都带该前缀，各屏独立不冲突。新页选一个没被占用的前缀（`grep -rho -- '--[a-z]\{2\}-' screens charts components | sort | uniq` 查占用）。
- **双份色板**：`:root` 定义 `--xx-*` CSS 变量，JS 里再维护一份 `const C={...}` 硬编码镜像（ECharts option 里不便读 CSS 变量）。
- **资源守卫**：预置隐藏的 `.xx-error` 告警条 + 脚本开头 `if(!window.echarts){ ...classList.add("is-visible"); return; }`；echarts 走 `cdn.jsdelivr.net/npm/echarts@6.1.0`。
- **数据全内联**，单一数据源派生所有视图（合计=分项之和、比率/达成率 JS 现算，不复制数字）；`setInterval` 驱动"活性"（轮播/翻牌/扫描），CSS `@keyframes` 驱动动画，kiosk 常驻不做 teardown。
- **模拟数据标识**：页内数字都是编的，所以每页 `.xx-stage` 顶边正中挂一枚 `.xx-mockflag` 橙色胶囊（绝对定位 + `pointer-events:none`，不参与页头 flex 布局）。**不要手写**，新增样板间后跑 `python3 tools/inject_mock_flag.py` 注入（幂等，`--remove` 整批摘掉）。新页页头正中别放内容，否则会被这枚标识压住。
- **表格**用 CSS grid 模拟（`.xx-thead` + JS 生成 `<li>` 行同列宽），非 `<table>`；斑马纹 `nth-child(odd)`、状态徽章 `.xx-badge.is-xxx`。
- **地图页**把 `shared/geo-data.js` 需要的数据集内联进 `<script>` 后 `echarts.registerMap(...)`，保持页面自包含无外网请求。
- **坑**：ECharts 容器的 `flex:1` 只在**直接父级也是 flex 容器**时才有高度；若图表 div 外套了一层非 flex 的 wrapper 会算出高度 0、图不渲染——保证图表容器父链都是 flex 或显式高度。
- **坑**：与图表**同属一个 flex 容器的兄弟块**，若其内容是 `init` 之后才由 JS 填充的，会在填充后把 `flex:1` 的图表容器**压矮**。此时脚本早先读到的 `clientHeight` 是偏大的旧值，按它算出来的 `geo` 布局（`layoutCenter` / `layoutSize`）就偏了——地图整体下移、底部被**静默裁掉**。规则：**所有与图表同属 flex 容器的 DOM 必须在 `echarts.init` 之前填充完**；做不到就给那个兄弟块**写死高度**（并配 `min-height:0; overflow:hidden` 防内容撑破）。实测案例：`screens/kitchen-appliance/大屏样板间-厨电物流线路详情1920.html` 的「线路剖面」块由 `renderProfile()` 延迟填充，导致读到 578 而实际 477，海南本岛南端落到 y=502 被裁；给该 section 固定 195px 后 `layoutCenter.y` 由 289 回到 239，六个极点全部回到画布内。
- **坑**：KPI/评分常用"翻牌缓动从 0 计数到目标"，验证截图时数字可能是缓动中途值——要等收敛后再判勾稽，别把中途值当 bug。
- **坑**：`GEO_DATA.china` 直接registerMap 画出来的全国图会被压扁。纬度下界是 3.4° 而非大陆的 18.1°，因为①有个**空名要素**（`adcode` 为 `100000_JD`）是九段线，②**海南省自身含三沙群岛**（133 个多边形里 129 个是低纬岛点）。按国标做法拆成「主图 + 右下角南海小地图」：以纬度 17.5° 为界把这两部分切到独立的 `FeatureCollection` 另行 `registerMap`。小地图用第二个 `geo` 组件（`zlevel` 抬高压住 `graphic` 边框），它自身包围盒就是全部内容，不会溢出小框；把它紧贴主图右下、与主图底对齐，两张图才读得出是同一张全国图。见 `screens/public-funds/大屏样板间-公共资金分地区收入1920.html`。
- **坑（最坑的一条）**：`geo` / `series-map` 默认带 **`aspectScale: 0.75`**——经度方向被压到 3/4。所以**有效宽高比 = Δlon × 0.75 / Δlat**，不是经纬跨度之比（全国图是 1.30 而非 1.74）。`layoutSize` 只作用在较长的那条边上：按经纬比估算会高估宽度，反推出的高度超出画布，地图上下被**静默裁掉**——没有任何报错，只是漠河和海南跑到画布外（实测 y = −40 与 441，画布高才 402）。定位方法：`chart.convertToPixel({geoIndex:0},[lon,lat])` 打几个极点坐标出来看是否落在 `[0, clientHeight]` 内。正确做法是按容器与真实包围盒**运行时现算** `layoutSize`，并把同一个 `aspectScale` 显式下发给 geo 与 series，别依赖默认值。
- **坑**：`visualMap` 分段式（`type:"piecewise"`）一旦设了两端文字 `text`，`showLabel` 默认值就变成 `false`，**每一档的 `label` 会被整体吞掉**，图例只剩色块。要么别设 `text`，要么显式补 `showLabel: true`。
- **坑（最难查的一条）**：`setOption` 会**深拷贝整个 option**，option 里只要有**循环引用**就无限递归，浏览器直接 `RangeError: Maximum call stack size exceeded`，**整页图表全空**，堆栈里只有 echarts.min.js 的内部帧、指不到自己的代码。成因是建模时给业务对象加了双向引用（如 `rdc.provs` 持有省对象、省对象又 `p.rdc = rdc` 回指；或 `r.trunkLines` 持有线路、线路又 `l.rdc = r`），然后把这些对象整个塞进了 `series.data`（常见于为 tooltip 方便而写的 `raw: obj`）。**规则：进 option 的数据只放标量与数组，业务对象之间用 id/name/索引关联，绝不用对象引用回指。** 定位方法：`echarts.dispose` 掉旧实例后包一层 `setOption` 拦截，对 option 跑 `JSON.stringify` —— 它会直接报出成环路径（`property 'trunkLines' -> index 0 -> property 'rdc' closes the circle`）。⚠️ **node 打桩测不出这个 bug**：桩的 `setOption` 是空函数，不走深拷贝；只有真浏览器 + 真 echarts 才会暴露。见 `screens/kitchen-appliance/大屏样板间-厨电物流运输1920.html` 里的三处 `★` 注释。
- **坑**：`read_console_messages` 之类的控制台读取是**会话累积**的，不随页面导航清空。判断"某页零报错"要看**相对基线的增量**，别把上一页留下的错误算到当前页头上（也别因为看到旧错误就去改一个本来是好的页面）。

## Git 约定

样板间按"波次"提交，延续现有风格：`样板间N期：<一句话>，README 同步 N 文件/M 方案`。新增文件后需**手工**同步两处统计：`README.md` 的总数（文件数、方案数）和 `docs/方案清单.md` 里对应板块的条目（`build_index.py` 只改 index.html 的统计，不碰这两份文档）。README 只放总览与文档索引，细节写进 `docs/`（方案清单 / 使用说明 / 维护指南），别再把长清单塞回 README。
