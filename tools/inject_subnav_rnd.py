#!/usr/bin/env python3
"""把研发管理专题 17 个父页页头右上的两枚 chip（DATA AS OF / HEALTH 等）
替换为一枚「二级子页」导航标签（幂等，可反复跑）。

本文件是 tools/inject_subnav_kitchen.py（厨电专题）的**专用副本**，只作用于
screens/rnd-ipd/，与厨电/公共资金版互不干扰。相对厨电脚本的三处差异：
  1) PAGES_DIR / SUB 换成研发专题的 17 个专题页（10 个有二级子页、7 个为 None）；
  2) label() 的公共前缀改为「大屏样板间-研发」（比厨电版短切多一个字会切坏，勿沿用）；
  3) 配色由厨电青橙系换成研发星蓝系（面板底 rgba(18,34,78,.55)、描边
     rgba(96,140,255,.22)、主色蓝 #5c9dff、次文字 #7f92c4、主文字 #dce8ff）。

用法：
    python3 tools/inject_subnav_rnd.py            # 注入 / 更新
    python3 tools/inject_subnav_rnd.py --remove   # 还原为原来的两枚 chip

要点：
- 原 chips 块里各有一个被主脚本 `textContent` 赋值的 id（如 hq-chip-idx）。
  直接删掉会让那行赋值报空引用，所以替换时**保留同 id 的隐藏桩元素**，主脚本无需改动。
- 有子页的父页，标签渲染成 <a>，点击直达子页；无子页的渲染成静态 <div>。
- 原 chips 块整体存进注释备份，--remove 时原样还原。
- 分波交付：文件不存在的父页自动跳过，每波重跑即可。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 研发管理专题所在目录（页面互链是同目录相对路径，移动目录时只改这里）
PAGES_DIR = os.path.join(ROOT, "screens", "rnd-ipd")

# 父页 → [(子页展示名, 页内入口位置, 子页文件), ...]；无子页则为 None 或空列表。
# 归属与 docs/RndIpdThemed.md §3 / §5.1 一致。
# ★ 一个父页可挂多个子页：value 是**列表**，渲染成一枚标签内的多个链接 chip
#   （页头右侧只剩 ~380px，多枚独立标签放不下第 3 枚，故走「一标签多链接」形态）。
SUB = {
    "大屏样板间-研发产品组合与路标1920.html": [
        ("单线路标", "产品线概览表行", "大屏样板间-研发单产品线路标详情1920.html"),
        ("Charter台账", "Charter 立项漏斗", "大屏样板间-研发Charter立项台账1920.html"),
        ("四线对比", "组合四象限图", "大屏样板间-研发四线组合对比1920.html"),
    ],
    "大屏样板间-研发IPD管道与评审1920.html": [
        ("单项目详情", "重点项目表行", "大屏样板间-研发单项目IPD详情1920.html"),
        ("TR评审台账", "TR 通过率矩阵", "大屏样板间-研发TR评审台账1920.html"),
        ("阶段对比", "阶段停留箱线图", "大屏样板间-研发阶段停留对比1920.html"),
    ],
    "大屏样板间-研发需求全生命周期1920.html": [
        ("需求条目台账", "来源明细表行", "大屏样板间-研发需求条目台账1920.html"),
        ("需求复盘", "需求状态 CFD", "大屏样板间-研发单需求全链路复盘1920.html"),
    ],
    "大屏样板间-研发投入与预算1920.html": [
        ("单类别详情", "投入五类明细行", "大屏样板间-研发单投入类别详情1920.html"),
        ("预算执行台账", "预算达成子弹图", "大屏样板间-研发预算执行台账1920.html"),
    ],
    "大屏样板间-研发敏捷交付总览1920.html": [
        ("单队冲刺", "团队速率表行", "大屏样板间-研发单团队冲刺详情1920.html"),
        ("障碍台账", "障碍清单面板头", "大屏样板间-研发障碍与回顾台账1920.html"),
        ("团队对比", "12 团队速率图", "大屏样板间-研发12团队效能对比1920.html"),
    ],
    "大屏样板间-研发看板流动效率1920.html": [
        ("阻塞台账", "阻塞帕累托面板头", "大屏样板间-研发阻塞在制品台账1920.html"),
        ("单队看板", "WIP 违限热力", "大屏样板间-研发单团队看板详情1920.html"),
    ],
    "大屏样板间-研发工程效能1920.html": [
        ("单仓库群", "覆盖率箱线面板头", "大屏样板间-研发单仓库群工程详情1920.html"),
        ("流水线台账", "成功率日历面板头", "大屏样板间-研发流水线运行台账1920.html"),
        ("五群对比", "XP 实践雷达", "大屏样板间-研发五群能力对比1920.html"),
    ],
    "大屏样板间-研发质量与缺陷1920.html": [
        ("缺陷台账", "缺陷域明细行", "大屏样板间-研发缺陷台账1920.html"),
        ("单模块质量", "缺陷来源旭日", "大屏样板间-研发单模块质量详情1920.html"),
    ],
    "大屏样板间-研发软硬云AI集成协同1920.html": [
        ("单基线详情", "基线列车甘特行", "大屏样板间-研发单集成基线详情1920.html"),
        ("接口台账", "联调接口达成图", "大屏样板间-研发跨域接口台账1920.html"),
        ("依赖图谱", "跨域依赖热力", "大屏样板间-研发四域依赖图谱1920.html"),
    ],
    "大屏样板间-研发硬件与样机1920.html": [
        ("单批次详情", "样机批次表行", "大屏样板间-研发单样机批次详情1920.html"),
        ("物料认证台账", "物料认证面板头", "大屏样板间-研发物料认证台账1920.html"),
    ],
    "大屏样板间-研发AI模型迭代1920.html": [
        ("单模型详情", "模型台账行", "大屏样板间-研发单模型详情1920.html"),
        ("数据集台账", "训练排期面板头", "大屏样板间-研发数据集与训练台账1920.html"),
    ],
    "大屏样板间-研发云端服务与发布1920.html": [
        ("线上事件台账", "最近线上事件行", "大屏样板间-研发线上事件台账1920.html"),
        ("发布复盘", "发布列车日历", "大屏样板间-研发单发布批次复盘1920.html"),
    ],
    "大屏样板间-研发交付流水线数字孪生1920.html": [
        ("单链路节点详情", "等距链路节点", "大屏样板间-研发单链路节点详情1920.html"),
        ("瓶颈台账", "域×基线交付热力", "大屏样板间-研发链路瓶颈台账1920.html"),
    ],
    # 多中心布局挂两个：指标视角（单中心详情）与孪生视角（园区数字孪生），两者互为姊妹页
    "大屏样板间-研发多中心布局1920.html": [
        ("单中心详情", "站点明细表行", "大屏样板间-研发单中心详情1920.html"),
        ("园区数字孪生", "站点孪生视角", "大屏样板间-研发园区数字孪生1920.html"),
        ("协作图谱", "跨站协作力导向", "大屏样板间-研发跨站协作图谱1920.html"),
    ],
    "大屏样板间-研发人才与能力1920.html": [
        ("岗位台账", "关键岗位饱和度面板头", "大屏样板间-研发关键岗位与招聘台账1920.html"),
        ("单职能人才", "职级金字塔", "大屏样板间-研发单职能人才详情1920.html"),
        ("技能图谱", "技能热词词云", "大屏样板间-研发技能图谱1920.html"),
    ],
    "大屏样板间-研发技术资产与复用1920.html": [
        ("开源与债务", "开源组件合规行", "大屏样板间-研发开源合规与技术债台账1920.html"),
        ("单CBB域", "CBB 货架 treemap", "大屏样板间-研发单CBB域详情1920.html"),
        ("专利台账", "专利 24 月走势", "大屏样板间-研发专利资产台账1920.html"),
    ],
    "大屏样板间-研发效能指数1920.html": [
        ("单维度追溯详情", "加权明细可追溯表行", "大屏样板间-研发单维度追溯详情1920.html"),
        ("季度复盘", "指数 24 月走势", "大屏样板间-研发季度指数复盘1920.html"),
        ("行动台账", "改进行动追踪", "大屏样板间-研发改进行动台账1920.html"),
    ],
}

CSS_BEGIN = "  /* subnav:begin —— 由 tools/inject_subnav_rnd.py 注入，勿手改 */"
CSS_END = "  /* subnav:end */"
HTML_BEGIN = "<!-- subnav:begin -->"
HTML_END = "<!-- subnav:end -->"

# 配色取自研发专题的 --rnd-* 色板：底 rgba(18,34,78,.55)、线 rgba(96,140,255,.22)、
# 主色蓝 #5c9dff、次文字 #7f92c4、主文字 #dce8ff。无子页时整枚标签保持静默灰蓝。
CSS_TPL = """
  .{p}-subnav {{
    display: flex; flex-direction: column; justify-content: center; gap: 3px; flex: none;
    min-width: 176px; padding: 7px 14px; border-radius: 9px; text-decoration: none;
    border: 1px solid rgba(96, 140, 255, 0.34); background: rgba(18, 34, 78, 0.55);
  }}
  .{p}-subnav > span {{ font-size: 10.5px; letter-spacing: 0.16em; color: #7f92c4; white-space: nowrap; }}
  .{p}-subnav > u {{ display: flex; align-items: baseline; gap: 6px; text-decoration: none; white-space: nowrap; }}
  .{p}-subnav b {{ font-size: 14px; font-weight: 700; letter-spacing: 0.04em; color: #a3b4dc; }}
  .{p}-subnav i {{ font-style: normal; font-size: 10.5px; color: #7f92c4; }}
  /* 有子页：整枚标签转星蓝。★ 多子页时每个链接是独立 chip，故 cursor/hover 下沉到 <a>，
     不再挂在外层——外层挂了会让「标签空白处」也显示成可点，实际点不动。 */
  .{p}-subnav.is-on {{
    border-color: rgba(92, 157, 255, 0.55);
    background: linear-gradient(160deg, rgba(92, 157, 255, 0.16), rgba(18, 34, 78, 0.6));
    box-shadow: inset 0 0 14px rgba(92, 157, 255, 0.1);
  }}
  .{p}-subnav a {{
    display: inline-flex; align-items: baseline; gap: 5px; cursor: pointer;
    text-decoration: none; border-radius: 5px; padding: 1px 5px; margin: 0 -2px;
    transition: background .18s, box-shadow .18s;
  }}
  .{p}-subnav a b {{ color: #9cc2ff; }}
  .{p}-subnav a i {{ color: #6f8ec4; }}
  .{p}-subnav a:hover {{ background: rgba(92, 157, 255, 0.22); box-shadow: 0 0 12px -3px rgba(92, 157, 255, 0.85); }}
  .{p}-subnav a:hover b {{ color: #dce8ff; }}
  /* 多链接之间的分隔点 */
  .{p}-subnav em {{ font-style: normal; color: rgba(127, 146, 196, 0.5); font-size: 12px; }}
"""

# 研发专题的色板 token 是 `--rnd-*`（3 字母，全专题共用），页面里没有 `--xx-bg`，
# 因此从舞台容器 `<div class="xx-stage">` 探测每页独有的 2 字母 CSS 前缀
# （与 tools/inject_mock_flag.py 的 STAGE_RE 保持一致）。
STAGE_RE = re.compile(r'<div class="([a-z]{2})-stage"')


def label(fname):
    """日志用短名：摘掉「大屏样板间-研发」这段公共前缀。"""
    return fname[len("大屏样板间-研发"):]


def prefix_of(html):
    m = STAGE_RE.search(html)
    if not m:
        raise SystemExit("无法识别 CSS 前缀（找不到 .xx-stage）")
    return m.group(1)


def chips_re(p):
    return re.compile(r'( *)<div class="%s-chips">.*?</div>\s*\n(?=\s*<div class="%s-clock")' % (p, p), re.S)


def apply(fname, remove=False):
    path = os.path.join(PAGES_DIR, fname)
    html = io.open(path, encoding="utf-8").read()
    p = prefix_of(html)

    # 还原：把备份的原 chips 块放回去
    m_inj = re.search(re.escape(HTML_BEGIN) + r"\n<!--ORIG\n(.*?)\nORIG-->\n.*?" + re.escape(HTML_END) + r"\n", html, re.S)
    if m_inj:
        html = html[:m_inj.start()] + m_inj.group(1) + "\n" + html[m_inj.end():]
    html = re.sub(re.escape(CSS_BEGIN) + r".*?" + re.escape(CSS_END) + r"\n?", "", html, flags=re.S)
    if remove:
        io.open(path, "w", encoding="utf-8").write(html)
        return "%-40s 已还原原 chips" % label(fname)

    m = chips_re(p).search(html)
    if not m:
        raise SystemExit("%s 未找到 chips 块" % fname)
    orig, indent = m.group(0).rstrip("\n"), m.group(1)
    # 原 chips 内被主脚本赋值的 id，保留隐藏桩，避免 textContent 报空引用
    stubs = "".join('<span id="%s" hidden></span>' % i for i in re.findall(r'id="([^"]+)"', orig))

    info = SUB.get(fname)
    if info:
        # 一枚标签内 N 个链接 chip（N=1 时与旧形态视觉一致）：
        # 单子页保留「名称 · 页内入口」两段；多子页时入口说明下沉到 title，只留名称，省宽度。
        multi = len(info) > 1
        links = []
        for name, where, sub in info:
            inner = ("<b>%s</b>" % name) if multi else ("<b>%s</b><i>· %s</i>" % (name, where))
            links.append('<a href="%s" title="点击进入子页：%s（页内入口：%s）">%s</a>'
                         % (sub, name, where, inner))
        head = "二级子页 · SUB-PAGE" + ("　×%d" % len(info) if multi else "")
        tag = ('%s<div class="%s-subnav is-on"><span>%s</span><u>%s</u></div>'
               % (indent, p, head, '<em>·</em>'.join(links)))
    else:
        tag = ('%s<div class="%s-subnav" title="本专题页没有二级详情子页">'
               '<span>二级子页 · SUB-PAGE</span><u><b>本页无</b><i>· 详见门户页导航</i></u></div>'
               % (indent, p))

    block = (HTML_BEGIN + "\n<!--ORIG\n" + orig + "\nORIG-->\n"
             + tag + stubs + "\n" + indent + HTML_END + "\n")
    html = html[:m.start()] + block + html[m.end():]
    # CSS 块固定插在 carousel 块之前（无 carousel 块时才退回 </style>）。两个注入脚本
    # 都往 </style> 前插，若不钉死相对位置，换个先后跑就会产生纯顺序假 diff。
    anchor = "  /* carousel:begin"
    css = CSS_BEGIN + CSS_TPL.format(p=p) + CSS_END + "\n"
    if anchor in html:
        html = html.replace(anchor, css + anchor, 1)
    else:
        html = html.replace("</style>", css + "</style>", 1)
    io.open(path, "w", encoding="utf-8").write(html)
    desc = "；".join("%s ← %s" % (n, w) for n, w, _s in info) if info else "本页无子页"
    return "%-40s 前缀 %s · %s" % (label(fname), p, desc)


def main():
    remove = "--remove" in sys.argv
    for f in SUB:
        if not os.path.exists(os.path.join(PAGES_DIR, f)):
            print("跳过（尚未落地）：" + f)
            continue
        print(apply(f, remove))
    print(("已还原 " if remove else "已注入 ") + "父页子页导航标签处理完毕")


if __name__ == "__main__":
    main()
