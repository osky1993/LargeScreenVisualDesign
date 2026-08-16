#!/usr/bin/env python3
"""把厨电制造专题 18 个父页页头右上的两枚 chip（DATA AS OF / FPY 等）
替换为一枚「二级子页」导航标签（幂等，可反复跑）。

本文件是 tools/inject_subnav.py（公共资金专题）的**专用副本**，只作用于
screens/kitchen-appliance/，与公共资金版互不干扰。相对原脚本的三处差异：
  1) PAGES_DIR / SUB 换成厨电专题的 18 个专题页（13 个有二级子页、5 个为 None）；
  2) prefix_of() 改从 `<div class="xx-stage">` 提取 2 字母 CSS 前缀 —— 厨电专题的
     色板 token 统一是 `--mfg-*`（3 字母），页面里根本没有 `--xx-bg`，沿用原脚本的
     正则会直接抛错；顺带补上原脚本缺失的 None 检查；
  3) 配色由公共资金的蓝金系换成厨电的青橙系（面板底 rgba(14,46,50,.55)、描边
     rgba(64,196,190,.22)、主色青 #35e0d0、次文字 #7fa6a3、主文字 #d8f2ef）。

用法：
    python3 tools/inject_subnav_kitchen.py            # 注入 / 更新
    python3 tools/inject_subnav_kitchen.py --remove   # 还原为原来的两枚 chip

要点：
- 原 chips 块里各有一个被主脚本 `textContent` 赋值的 id（如 pz-chip-fpy）。
  直接删掉会让那行赋值报空引用，所以替换时**保留同 id 的隐藏桩元素**，主脚本无需改动。
- 有子页的父页，标签渲染成 <a>，点击直达子页；无子页的渲染成静态 <div>。
- 原 chips 块整体存进注释备份，--remove 时原样还原。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 厨电制造专题 31 块屏所在目录（页面互链是同目录相对路径，移动目录时只改这里）
PAGES_DIR = os.path.join(ROOT, "screens", "kitchen-appliance")

# 父页 → (子页展示名, 页内入口位置, 子页文件)；无子页则为 None
SUB = {
    "大屏样板间-厨电原料采购总览1920.html": None,
    "大屏样板间-厨电供应商协同1920.html": ("供应商台账", "C 级预警表行", "大屏样板间-厨电供应商台账1920.html"),
    "大屏样板间-厨电供应链风险图谱1920.html": ("供应商风险画像", "高风险供应商行", "大屏样板间-厨电供应商风险画像1920.html"),
    "大屏样板间-厨电研发与新品孵化1920.html": ("单项目研发详情", "在研项目明细行", "大屏样板间-厨电单项目研发详情1920.html"),
    "大屏样板间-厨电生产制造总览1920.html": ("基地生产详情", "三大基地看板行", "大屏样板间-厨电基地生产详情1920.html"),
    "大屏样板间-厨电设备与工艺参数1920.html": ("单产线设备详情", "设备类别台账行", "大屏样板间-厨电单产线设备详情1920.html"),
    "大屏样板间-厨电工厂能碳中心1920.html": ("单基地能耗详情", "三基地能碳看板行", "大屏样板间-厨电单基地能耗详情1920.html"),
    "大屏样板间-厨电品质管理1920.html": ("故障部件分析", "缺陷帕累托面板头", "大屏样板间-厨电故障部件分析1920.html"),
    "大屏样板间-厨电仓储库存1920.html": ("库存库龄台账", "库龄结构面板头", "大屏样板间-厨电库存库龄台账1920.html"),
    "大屏样板间-厨电物流运输1920.html": ("物流线路详情", "干线明细表行", "大屏样板间-厨电物流线路详情1920.html"),
    "大屏样板间-厨电全链路流转1920.html": None,
    "大屏样板间-厨电门店零售1920.html": ("省区门店分布", "省区明细表行", "大屏样板间-厨电省区门店分布1920.html"),
    "大屏样板间-厨电电商全渠道1920.html": ("单品销售详情", "平台明细表行", "大屏样板间-厨电单品销售详情1920.html"),
    "大屏样板间-厨电海外出口与全球布局1920.html": ("单国家市场详情", "海外仓布局行", "大屏样板间-厨电单国家市场详情1920.html"),
    "大屏样板间-厨电营销活动1920.html": None,
    "大屏样板间-厨电售后服务1920.html": ("售后工单台账", "工单流转面板头", "大屏样板间-厨电售后工单台账1920.html"),
    "大屏样板间-厨电用户会员运营1920.html": None,
    "大屏样板间-厨电经营健康指数1920.html": None,
}

CSS_BEGIN = "  /* subnav:begin —— 由 tools/inject_subnav_kitchen.py 注入，勿手改 */"
CSS_END = "  /* subnav:end */"
HTML_BEGIN = "<!-- subnav:begin -->"
HTML_END = "<!-- subnav:end -->"

# 配色取自厨电专题的 --mfg-* 色板：底 rgba(14,46,50,.55)、线 rgba(64,196,190,.22)、
# 主色青 #35e0d0、次文字 #7fa6a3、主文字 #d8f2ef。无子页时整枚标签保持静默灰青。
CSS_TPL = """
  .{p}-subnav {{
    display: flex; flex-direction: column; justify-content: center; gap: 3px; flex: none;
    min-width: 176px; padding: 7px 14px; border-radius: 9px; text-decoration: none;
    border: 1px solid rgba(64, 196, 190, 0.34); background: rgba(14, 46, 50, 0.55);
  }}
  .{p}-subnav > span {{ font-size: 10.5px; letter-spacing: 0.16em; color: #7fa6a3; white-space: nowrap; }}
  .{p}-subnav > u {{ display: flex; align-items: baseline; gap: 6px; text-decoration: none; white-space: nowrap; }}
  .{p}-subnav b {{ font-size: 14px; font-weight: 700; letter-spacing: 0.04em; color: #9fbfbb; }}
  .{p}-subnav i {{ font-style: normal; font-size: 10.5px; color: #7fa6a3; }}
  /* 有子页：转青色并可点击 */
  .{p}-subnav.is-on {{
    cursor: pointer; border-color: rgba(53, 224, 208, 0.55);
    background: linear-gradient(160deg, rgba(53, 224, 208, 0.16), rgba(14, 46, 50, 0.6));
    box-shadow: inset 0 0 14px rgba(53, 224, 208, 0.1);
    transition: border-color .18s, box-shadow .18s;
  }}
  .{p}-subnav.is-on b {{ color: #8ff0e6; }}
  .{p}-subnav.is-on i {{ color: #6fc4bd; }}
  .{p}-subnav.is-on:hover {{ border-color: rgba(53, 224, 208, 0.95); box-shadow: 0 0 16px -2px rgba(53, 224, 208, 0.7); }}
"""

# 厨电专题的色板 token 是 `--mfg-*`（3 字母，全专题共用），页面里没有 `--xx-bg`，
# 因此改从舞台容器 `<div class="xx-stage">` 探测每页独有的 2 字母 CSS 前缀
# （与 tools/inject_mock_flag.py 的 STAGE_RE 保持一致）。
STAGE_RE = re.compile(r'<div class="([a-z]{2})-stage"')


def label(fname):
    """日志用短名：摘掉「大屏样板间-厨电」这段公共前缀（原脚本按公共资金的前缀长度硬切，
    厨电前缀短一个字，直接沿用会把首字也切掉）。"""
    return fname[len("大屏样板间-厨电"):]


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
        name, where, sub = info
        tag = ('%s<a class="%s-subnav is-on" href="%s" title="点击进入子页：%s（页内入口：%s）">'
               '<span>二级子页 · SUB-PAGE</span><u><b>%s</b><i>· %s</i></u></a>'
               % (indent, p, sub, name, where, name, where))
    else:
        tag = ('%s<div class="%s-subnav" title="本专题页没有二级详情子页">'
               '<span>二级子页 · SUB-PAGE</span><u><b>本页无</b><i>· 详见门户页导航</i></u></div>'
               % (indent, p))

    block = (HTML_BEGIN + "\n<!--ORIG\n" + orig + "\nORIG-->\n"
             + tag + stubs + "\n" + indent + HTML_END + "\n")
    html = html[:m.start()] + block + html[m.end():]
    # CSS 块固定插在 carousel 块之前（无 carousel 块时才退回 </style>）。厨电专题的两个
    # 注入脚本都往 </style> 前插，若不钉死相对位置，换个先后跑就会产生「12 增 12 删、
    # 集合相同」的纯顺序假 diff。
    anchor = "  /* carousel:begin"
    css = CSS_BEGIN + CSS_TPL.format(p=p) + CSS_END + "\n"
    if anchor in html:
        html = html.replace(anchor, css + anchor, 1)
    else:
        html = html.replace("</style>", css + "</style>", 1)
    io.open(path, "w", encoding="utf-8").write(html)
    return "%-40s 前缀 %s · %s" % (label(fname), p, (info[0] + " ← " + info[1]) if info else "本页无子页")


def main():
    remove = "--remove" in sys.argv
    for f in SUB:
        if not os.path.exists(os.path.join(PAGES_DIR, f)):
            print("跳过（不存在）：" + f)
            continue
        print(apply(f, remove))
    print(("已还原 " if remove else "已注入 ") + "%d 个父页的子页导航标签" % len(SUB))


if __name__ == "__main__":
    main()
