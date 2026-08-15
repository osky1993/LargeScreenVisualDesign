#!/usr/bin/env python3
"""给所有 `大屏样板间-*.html` 顶部注入一枚「模拟数据」标识（幂等，可反复跑）。

用法：
    python3 tools/inject_mock_flag.py            # 注入 / 更新
    python3 tools/inject_mock_flag.py --remove   # 移除

要点：
- 样板间页内数据全是内联的模拟数据，公开发布时需在页面上明确标注，避免被当成真实业务数据。
- 标识挂在 `.xx-stage` 顶边正中（stage 是 1920×1080 舞台，随整台等比缩放），
  `position:absolute` + `pointer-events:none`，不参与页头 flex 布局、不挡交互。
- class 沿用每屏两字母前缀（从 `<div class="xx-stage">` 提取），各屏互不干扰。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSS_BEGIN = "  /* mockflag:begin —— 由 tools/inject_mock_flag.py 注入，勿手改 */"
CSS_END = "  /* mockflag:end */"
HTML_BEGIN = "<!-- mockflag:begin -->"
HTML_END = "<!-- mockflag:end -->"

CSS_TPL = """
  .{p}-mockflag {{
    position: absolute; top: 0; left: 50%; transform: translateX(-50%); z-index: 9000;
    padding: 3px 20px 4px; border-radius: 0 0 10px 10px; pointer-events: none;
    background: linear-gradient(180deg, #f2ab42, #de8524); color: #24130a;
    font-size: 13px; line-height: 1.15; font-weight: 700;
    letter-spacing: 0.3em; text-indent: 0.3em; white-space: nowrap;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.45);
  }}
"""

STAGE_RE = re.compile(r'<div class="([a-z]{2})-stage"[^>]*>')


def strip_block(text, begin, end):
    """删除 begin…end 整块（含标记与块前的换行缩进），不存在则原样返回。

    只吃块**前**的空白，块尾的换行留给原文，这样 inject → remove 能精确还原。
    """
    pat = re.compile(r"\n?[ \t]*" + re.escape(begin) + r".*?" + re.escape(end), re.S)
    return pat.sub("", text)


def remove(html):
    html = strip_block(html, CSS_BEGIN, CSS_END)
    return strip_block(html, HTML_BEGIN, HTML_END)


def inject(html, path):
    m = STAGE_RE.search(html)
    if not m:
        raise RuntimeError("找不到 .xx-stage 舞台容器")
    p = m.group(1)
    if "</style>" not in html:
        raise RuntimeError("找不到 </style> 插入点")

    css = CSS_BEGIN + CSS_TPL.format(p=p) + CSS_END + "\n"
    i = html.index("</style>")
    html = html[:i] + css + html[i:]

    # CSS 插入后偏移量变了，重新定位 stage 开标签
    m = STAGE_RE.search(html)
    tag = m.group(0)
    flag = (
        '\n    %s<div class="%s-mockflag" role="note" aria-label="本页为模拟数据">模拟数据</div>%s'
        % (HTML_BEGIN, p, HTML_END)
    )

    return html[: m.end()] + flag + html[m.end():]


def main():
    do_remove = "--remove" in sys.argv
    names = sorted(n for n in os.listdir(ROOT) if n.startswith("大屏样板间-") and n.endswith(".html"))
    done = 0
    for name in names:
        path = os.path.join(ROOT, name)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        out = remove(src)          # 先清旧块，保证幂等
        if not do_remove:
            out = inject(out, path)
        if out != src:
            with open(path, "w", encoding="utf-8") as f:
                f.write(out)
            done += 1
    print("%s：处理 %d 个文件，改动 %d 个" % ("移除" if do_remove else "注入", len(names), done))


if __name__ == "__main__":
    main()
