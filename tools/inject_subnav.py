#!/usr/bin/env python3
"""把公共资金 13 个父页页头右上的两枚 chip（DATA AS OF / TIME PROGRESS 等）
替换为一枚「二级子页」导航标签（幂等，可反复跑）。

用法：
    python3 tools/inject_subnav.py            # 注入 / 更新
    python3 tools/inject_subnav.py --remove   # 还原为原来的两枚 chip

要点：
- 原 chips 块里各有一个被主脚本 `textContent` 赋值的 id（如 nr-timeprog）。
  直接删掉会让那行赋值报空引用，所以替换时**保留同 id 的隐藏桩元素**，主脚本无需改动。
- 有子页的父页，标签渲染成 <a>，点击直达子页；无子页的渲染成静态 <div>。
- 原 chips 块整体存进注释备份，--remove 时原样还原。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 父页 → (子页展示名, 页内入口位置, 子页文件)；无子页则为 None
SUB = {
    "大屏样板间-公共资金全国收入总览1920.html": None,
    "大屏样板间-公共资金分地区收入1920.html": ("四大板块分省明细", "四大板块面板行或环图", "大屏样板间-公共资金四大板块分省明细1920.html"),
    "大屏样板间-公共资金江苏地市收入1920.html": ("地市收入详情 / 三大板块", "明细表行 · 板块卡片", "大屏样板间-公共资金地市收入详情1920.html"),
    "大屏样板间-公共资金收入分项目1920.html": ("分项目收入明细 / 六税叠加", "桑基图节点 · 月度小多图", "大屏样板间-公共资金分项目收入明细1920.html"),
    "大屏样板间-公共资金重点城市县区1920.html": ("重点县区详情", "百亿县区卡片", "大屏样板间-公共资金重点县区详情1920.html"),
    "大屏样板间-公共资金税收分行业1920.html": ("行业税收详情", "明细表行或树图", "大屏样板间-公共资金行业税收详情1920.html"),
    "大屏样板间-公共资金新动能税收1920.html": ("四大类 / 赛道地市分布", "左侧图例 · 右侧标签墙", "大屏样板间-公共资金新动能四大类地市分布1920.html"),
    "大屏样板间-公共资金土地出让形势1920.html": ("土地成交台账", "地市面板头入口", "大屏样板间-公共资金土地成交台账1920.html"),
    "大屏样板间-公共资金国资社保预算1920.html": None,
    "大屏样板间-公共资金现金管理1920.html": ("现金操作详情", "操作台账行", "大屏样板间-公共资金现金操作详情1920.html"),
    "大屏样板间-公共资金运行指数1920.html": None,
    "大屏样板间-公共资金政府债券发行1920.html": ("债券发行台账", "日历面板头入口", "大屏样板间-公共资金债券发行台账1920.html"),
    "大屏样板间-公共资金余额分析1920.html": ("资金余额预警详情", "预警清单行", "大屏样板间-公共资金余额预警详情1920.html"),
}

CSS_BEGIN = "  /* subnav:begin —— 由 tools/inject_subnav.py 注入，勿手改 */"
CSS_END = "  /* subnav:end */"
HTML_BEGIN = "<!-- subnav:begin -->"
HTML_END = "<!-- subnav:end -->"

CSS_TPL = """
  .{p}-subnav {{
    display: flex; flex-direction: column; justify-content: center; gap: 3px; flex: none;
    min-width: 176px; padding: 7px 14px; border-radius: 9px; text-decoration: none;
    border: 1px solid rgba(92, 156, 226, 0.4); background: rgba(16, 46, 86, 0.55);
  }}
  .{p}-subnav > span {{ font-size: 10.5px; letter-spacing: 0.16em; color: #5f88b8; white-space: nowrap; }}
  .{p}-subnav > u {{ display: flex; align-items: baseline; gap: 6px; text-decoration: none; white-space: nowrap; }}
  .{p}-subnav b {{ font-size: 14px; font-weight: 700; letter-spacing: 0.04em; color: #9fb6d4; }}
  .{p}-subnav i {{ font-style: normal; font-size: 10.5px; color: #5f88b8; }}
  /* 有子页：转青色并可点击 */
  .{p}-subnav.is-on {{
    cursor: pointer; border-color: rgba(57, 208, 216, 0.55);
    background: linear-gradient(160deg, rgba(57, 208, 216, 0.16), rgba(16, 46, 86, 0.6));
    box-shadow: inset 0 0 14px rgba(57, 208, 216, 0.1);
    transition: border-color .18s, box-shadow .18s;
  }}
  .{p}-subnav.is-on b {{ color: #9fe8ec; }}
  .{p}-subnav.is-on i {{ color: #7fb8c8; }}
  .{p}-subnav.is-on:hover {{ border-color: rgba(57, 208, 216, 0.95); box-shadow: 0 0 16px -2px rgba(57, 208, 216, 0.7); }}
"""


def prefix_of(html):
    return re.search(r"--([a-z]{2})-bg", html).group(1)


def chips_re(p):
    return re.compile(r'( *)<div class="%s-chips">.*?</div>\s*\n(?=\s*<div class="%s-clock")' % (p, p), re.S)


def apply(fname, remove=False):
    path = os.path.join(ROOT, fname)
    html = io.open(path, encoding="utf-8").read()
    p = prefix_of(html)

    # 还原：把备份的原 chips 块放回去
    m_inj = re.search(re.escape(HTML_BEGIN) + r"\n<!--ORIG\n(.*?)\nORIG-->\n.*?" + re.escape(HTML_END) + r"\n", html, re.S)
    if m_inj:
        html = html[:m_inj.start()] + m_inj.group(1) + "\n" + html[m_inj.end():]
    html = re.sub(re.escape(CSS_BEGIN) + r".*?" + re.escape(CSS_END) + r"\n?", "", html, flags=re.S)
    if remove:
        io.open(path, "w", encoding="utf-8").write(html)
        return "%-40s 已还原原 chips" % fname[9:]

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
    # CSS 块固定插在 drill 块之前（无 drill 块时才退回 </style>）。两个注入脚本都往
    # </style> 前插，若不钉死相对位置，换个先后跑就会产生「21 增 21 删、集合相同」的
    # 纯顺序假 diff。
    anchor = "  /* drill:begin"
    css = CSS_BEGIN + CSS_TPL.format(p=p) + CSS_END + "\n"
    if anchor in html:
        html = html.replace(anchor, css + anchor, 1)
    else:
        html = html.replace("</style>", css + "</style>", 1)
    io.open(path, "w", encoding="utf-8").write(html)
    return "%-40s 前缀 %s · %s" % (fname[9:], p, (info[0] + " ← " + info[1]) if info else "本页无子页")


def main():
    remove = "--remove" in sys.argv
    for f in SUB:
        if not os.path.exists(os.path.join(ROOT, f)):
            print("跳过（不存在）：" + f)
            continue
        print(apply(f, remove))
    print(("已还原 " if remove else "已注入 ") + "%d 个父页的子页导航标签" % len(SUB))


if __name__ == "__main__":
    main()
