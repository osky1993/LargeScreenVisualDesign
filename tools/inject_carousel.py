#!/usr/bin/env python3
"""向「公共资金」专题的 13 块样板间注入轮播导航（幂等，可反复跑）。

用法：
    python3 tools/inject_carousel.py            # 注入 / 更新全部 13 页
    python3 tools/inject_carousel.py --remove   # 撤销注入，还原为无导航状态

注入三处，均由 begin/end 标记包裹，重跑时整段替换而非追加：
  1) <style> 内：导航样式
  2) 页头 .xx-clock 之后：导航 DOM（时钟因此自然左移，右侧空出来放按钮）
  3) </body> 之前：独立 <script> 模块（不依赖 echarts，echarts 挂了导航照样能用）

每页停留秒数：改本文件 inject() 里的 `seconds=30`，改完重跑本脚本即可全量生效。
导航含四个控件：上一页 / 页码与倒计时条 / 下一页 / 暂停继续；快捷键 ← → 翻页、空格暂停。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 轮播页序 = 需求提出 13 个专题时的原始顺序，勿随意调整
PAGES = [
    ("大屏样板间-公共资金全国收入总览1920.html", "全国地方一般公共预算收入情况"),
    ("大屏样板间-公共资金分地区收入1920.html", "全国各地区地方一般公共预算收入情况"),
    ("大屏样板间-公共资金江苏地市收入1920.html", "全省各地市相关收入情况"),
    ("大屏样板间-公共资金收入分项目1920.html", "一般公共预算收入分项目情况"),
    ("大屏样板间-公共资金重点城市县区1920.html", "重点城市及县区相关收入"),
    ("大屏样板间-公共资金税收分行业1920.html", "全省税收分行业情况"),
    ("大屏样板间-公共资金新动能税收1920.html", "全省新动能企业税收情况"),
    ("大屏样板间-公共资金土地出让形势1920.html", "江苏省土地出让收入形势"),
    ("大屏样板间-公共资金国资社保预算1920.html", "江苏省国有资本经营预算收入及社保基金预算收入情况"),
    ("大屏样板间-公共资金现金管理1920.html", "公共资金现金管理开展情况"),
    ("大屏样板间-公共资金运行指数1920.html", "资金运行指数"),
    ("大屏样板间-公共资金政府债券发行1920.html", "地方政府债券发行情况"),
    ("大屏样板间-公共资金余额分析1920.html", "全省资金余额情况分析"),
]

CSS_BEGIN = "  /* carousel:begin —— 由 tools/inject_carousel.py 注入，勿手改，改脚本后重跑 */"
CSS_END = "  /* carousel:end */"
HTML_BEGIN = "<!-- carousel:begin -->"
HTML_END = "<!-- carousel:end -->"
JS_BEGIN = "<!-- carousel-js:begin -->"
JS_END = "<!-- carousel-js:end -->"

CSS_TPL = """
  .{p}-carousel {{
    display: flex; align-items: center; gap: 9px; flex: none;
    padding-left: 18px; margin-left: 2px;
    border-left: 1px solid rgba(92, 156, 226, 0.25);
  }}
  .{p}-cbtn {{
    width: 36px; height: 36px; flex: none; padding: 0; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    border-radius: 10px; font-family: inherit;
    border: 1px solid rgba(240, 192, 96, 0.34);
    background: linear-gradient(160deg, rgba(240, 192, 96, 0.17), rgba(16, 46, 86, 0.6));
    color: #ffdc8f;
    transition: border-color .18s, box-shadow .18s, color .18s, transform .18s;
  }}
  .{p}-cbtn svg {{ width: 18px; height: 18px; display: block; }}
  .{p}-cbtn:hover {{
    color: #fff6e2; border-color: rgba(240, 192, 96, 0.85);
    box-shadow: 0 0 14px rgba(240, 192, 96, 0.42), inset 0 0 12px rgba(240, 192, 96, 0.14);
  }}
  .{p}-cbtn:active {{ transform: scale(0.93); }}
  .{p}-cmeta {{ display: flex; flex-direction: column; align-items: center; gap: 5px; min-width: 62px; }}
  .{p}-cidx {{ font: 700 15px/1 var(--{p}-mono); color: #ffdc8f; letter-spacing: 0.06em; font-variant-numeric: tabular-nums; }}
  .{p}-cidx i {{ font-style: normal; font-size: 11px; font-weight: 400; color: #8ea9cc; margin-left: 1px; }}
  .{p}-cbar {{ width: 58px; height: 3px; border-radius: 2px; background: rgba(63, 120, 200, 0.28); overflow: hidden; }}
  .{p}-cbar u {{
    display: block; height: 100%; width: 0; border-radius: 2px;
    background: linear-gradient(90deg, #b8863a, #ffdc8f);
    box-shadow: 0 0 8px rgba(240, 192, 96, 0.55);
  }}
  /* 暂停态：进度条停在原地并转灰，播放键换成三角、按钮描边转青，一眼可辨 */
  .{p}-carousel.is-paused .{p}-cbar u {{ background: linear-gradient(90deg, #4a6c96, #8ea9cc); box-shadow: none; }}
  .{p}-cplay .{p}-ic-play {{ display: none; }}
  .{p}-carousel.is-paused .{p}-cplay .{p}-ic-pause {{ display: none; }}
  .{p}-carousel.is-paused .{p}-cplay .{p}-ic-play {{ display: block; }}
  .{p}-carousel.is-paused .{p}-cplay {{
    color: #9fe8ec; border-color: rgba(57, 208, 216, 0.6);
    background: linear-gradient(160deg, rgba(57, 208, 216, 0.2), rgba(16, 46, 86, 0.6));
    box-shadow: 0 0 12px rgba(57, 208, 216, 0.34);
  }}
"""

HTML_TPL = """
        <nav class="{p}-carousel" id="{p}-carousel" aria-label="专题轮播导航">
          <button class="{p}-cbtn" id="{p}-c-prev" type="button" aria-label="上一页" title="上一页（← 方向键）">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 4 L7 12 L15 20"/></svg>
          </button>
          <div class="{p}-cmeta">
            <span class="{p}-cidx"><b id="{p}-c-cur">--</b><i>/ {total}</i></span>
            <span class="{p}-cbar" aria-hidden="true"><u id="{p}-c-bar"></u></span>
          </div>
          <button class="{p}-cbtn" id="{p}-c-next" type="button" aria-label="下一页" title="下一页（→ 方向键）">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 4 L17 12 L9 20"/></svg>
          </button>
          <button class="{p}-cbtn {p}-cplay" id="{p}-c-play" type="button" aria-label="暂停轮播" aria-pressed="false" title="暂停 / 继续（空格键）">
            <svg class="{p}-ic-pause" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6.5" y="5" width="4" height="14" rx="1.4"/><rect x="13.5" y="5" width="4" height="14" rx="1.4"/></svg>
            <svg class="{p}-ic-play" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.2 L19 12 L8 18.8 Z"/></svg>
          </button>
        </nav>
"""

JS_TPL = """
<script>
/* ===== 公共资金专题轮播导航（tools/inject_carousel.py 注入） =====
   独立于主脚本运行：即使 echarts 加载失败，翻页仍然可用。 */
(() => {{
  "use strict";

  /* —— 可配置项 —— */
  const SECONDS = {seconds};              /* ← 每页停留秒数，改这里再重跑 tools/inject_carousel.py */

  /* 轮播页序 = 需求提出的 13 个专题原始顺序 */
  const PAGES = {pages};

  const P = "{p}";
  const $ = (id) => document.getElementById(id);
  const nav = $(P + "-carousel");
  if (!nav) return;

  /* 当前页在序列中的位置：按文件名匹配，允许带 ?query */
  const here = decodeURIComponent((location.pathname.split("/").pop() || "")).trim();
  let idx = PAGES.findIndex((x) => x.f === here);
  if (idx < 0) idx = {fallback};      /* 直接从本地打开且路径取不到文件名时的兜底位次 */

  $(P + "-c-cur").textContent = String(idx + 1).padStart(2, "0");
  nav.title = (idx + 1) + " / " + PAGES.length + "　" + PAGES[idx].t;

  function go(step) {{
    const n = (idx + step + PAGES.length) % PAGES.length;
    location.href = PAGES[n].f;
  }}

  /* —— 倒计时：累计已用时长，暂停时冻结在原地（不清零），继续时接着走 —— */
  const bar = $(P + "-c-bar");
  const playBtn = $(P + "-c-play");
  let elapsed = 0;               /* 本页已停留毫秒 */
  let last = Date.now();
  let userPaused = false;        /* 用户点了暂停 */
  let hidden = false;            /* 标签页被切到后台 */

  function render() {{
    const pct = Math.min(100, elapsed / (SECONDS * 1000) * 100);
    bar.style.width = pct.toFixed(2) + "%";
  }}
  function tick() {{
    const now = Date.now();
    if (!userPaused && !hidden) {{
      elapsed += now - last;
      render();
      if (elapsed >= SECONDS * 1000) go(1);
    }}
    last = now;
  }}
  const timer = setInterval(tick, 100);

  function setPaused(v) {{
    userPaused = v;
    nav.classList.toggle("is-paused", v);
    playBtn.setAttribute("aria-pressed", v ? "true" : "false");
    playBtn.setAttribute("aria-label", v ? "继续轮播" : "暂停轮播");
    last = Date.now();           /* 避免把暂停这段时间补算进 elapsed */
  }}

  playBtn.addEventListener("click", () => setPaused(!userPaused));
  $(P + "-c-prev").addEventListener("click", () => go(-1));
  $(P + "-c-next").addEventListener("click", () => go(1));
  document.addEventListener("keydown", (e) => {{
    if (e.key === "ArrowLeft") go(-1);
    else if (e.key === "ArrowRight") go(1);
    else if (e.key === " " || e.code === "Space") {{ e.preventDefault(); setPaused(!userPaused); }}
  }});

  /* 切到后台时冻结计时，回到前台接着走（不重置，也不会补跳好几页） */
  document.addEventListener("visibilitychange", () => {{
    hidden = document.hidden;
    last = Date.now();
  }});
  window.addEventListener("pagehide", () => clearInterval(timer));
}})();
</script>
"""


def prefix_of(html: str) -> str:
    m = re.search(r"--([a-z]{2})-bg\s*:", html)
    if not m:
        raise SystemExit("无法识别 CSS 前缀（找不到 --xx-bg）")
    return m.group(1)


def strip_block(html: str, begin: str, end: str) -> str:
    pat = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.S)
    return pat.sub("", html)


def inject(path: str, idx: int, remove: bool = False) -> str:
    full = os.path.join(ROOT, path)
    html = io.open(full, encoding="utf-8").read()
    p = prefix_of(html)

    # 先撤掉旧注入，保证幂等
    html = strip_block(html, CSS_BEGIN, CSS_END)
    html = strip_block(html, HTML_BEGIN, HTML_END)
    html = strip_block(html, JS_BEGIN, JS_END)
    if remove:
        io.open(full, "w", encoding="utf-8").write(html)
        return "%s  已撤销" % path

    # 1) CSS —— 插在 </style> 之前
    css = CSS_BEGIN + CSS_TPL.format(p=p) + CSS_END + "\n"
    if "</style>" not in html:
        raise SystemExit("%s 缺少 </style>" % path)
    html = html.replace("</style>", css + "</style>", 1)

    # 2) 导航 DOM —— 插在页头时钟块之后（时钟因此左移，右侧空出来放按钮）
    clock = re.search(r'<div class="%s-clock"[\s\S]*?</div>' % p, html)
    if not clock:
        raise SystemExit("%s 找不到 .%s-clock 块" % (path, p))
    block = HTML_BEGIN + HTML_TPL.format(p=p, total=len(PAGES)) + "        " + HTML_END
    html = html[: clock.end()] + "\n" + block + html[clock.end():]

    # 3) JS 模块 —— 插在 </body> 之前
    import json
    js = JS_BEGIN + JS_TPL.format(
        p=p,
        seconds=30,
        fallback=idx,
        pages=json.dumps([{"f": f, "t": t} for f, t in PAGES], ensure_ascii=False, indent=4),
    ) + JS_END + "\n"
    if "</body>" not in html:
        raise SystemExit("%s 缺少 </body>" % path)
    html = html.replace("</body>", js + "</body>", 1)

    io.open(full, "w", encoding="utf-8").write(html)
    return "%-44s 前缀 %s · 第 %2d 页 · %.0f KB" % (path, p, idx + 1, os.path.getsize(full) / 1024)


def main():
    remove = "--remove" in sys.argv
    for i, (f, _t) in enumerate(PAGES):
        if not os.path.exists(os.path.join(ROOT, f)):
            print("跳过（文件不存在）：" + f)
            continue
        print(inject(f, i, remove))
    print(("已撤销 " if remove else "已注入 ") + "%d 页轮播导航" % len(PAGES))


if __name__ == "__main__":
    main()
