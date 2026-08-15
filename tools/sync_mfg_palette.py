#!/usr/bin/env python3
"""把厨电制造专题的公共色板同步进 `screens/kitchen-appliance/` 各页（幂等，可反复跑）。

用法：
    python3 tools/sync_mfg_palette.py            # 按色源 JSON 重写各页色板
    python3 tools/sync_mfg_palette.py --remove   # 清空两个块的内容（标记保留）

要点：
- 色板单一源是 `shared/palette-manufacturing.json`：`tokens` 是 token → 色值，
  `_series` 是 ECharts 系列色的 token 名顺序。改色只改这一份，跑本脚本整套页面同步。
- 每页有两处落点，各由一对标记包裹，重跑时**整段替换**而非追加：
    CSS 侧 `:root{}` 内 —— `/* mfgpalette:begin … */ … /* mfgpalette:end */`，写 `--mfg-*` 变量；
    JS  侧主 `<script>` 内 —— `/* mfgpalette-js:begin … */ … /* mfgpalette-js:end */`，写 `const PAL`。
  两份是镜像关系：ECharts option 里读不到 CSS 变量，所以 JS 侧必须留一份硬编码。
- `PAL.series` 由 `_series` 查表展开成**实际色值数组**，页面可直接 `color: PAL.series`。
- `--remove` 只清内容、**保留标记**：标记是页面结构的一部分（脚本靠它定位落点），
  删了下次就找不到该往哪儿写了。这点与 `inject_mock_flag.py` 的整块删除不同。
- 找不到标记的页面只告警不中断：专题按阶段逐页加入，早期大部分页面还不存在。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(ROOT, "screens", "kitchen-appliance")
PALETTE_JSON = os.path.join(ROOT, "shared", "palette-manufacturing.json")

CSS_BEGIN = "  /* mfgpalette:begin —— 由 tools/sync_mfg_palette.py 注入，勿手改 */"
CSS_END = "  /* mfgpalette:end */"
JS_BEGIN = "  /* mfgpalette-js:begin —— 由 tools/sync_mfg_palette.py 注入，勿手改 */"
JS_END = "  /* mfgpalette-js:end */"

# 标记宽松匹配：认 `mfgpalette:begin` 这个词即可，注释尾巴的说明文字改了也照样能定位；
# 每次写回都落成上面的规范形态，所以第二次跑必然零改动。
CSS_BLOCK_RE = re.compile(r"[ \t]*/\* *mfgpalette:begin.*?/\* *mfgpalette:end *\*/", re.S)
JS_BLOCK_RE = re.compile(r"[ \t]*/\* *mfgpalette-js:begin.*?/\* *mfgpalette-js:end *\*/", re.S)

# 合法 JS 标识符：不是的（如 cyan-deep）在对象字面量里必须加引号
IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def load_palette():
    """读色源 JSON，返回 (tokens 有序字典, series 色值数组)。

    `_series` 存的是 token 名而非色值，避免同一个颜色在文件里写两遍、改色时漏改一处。
    """
    with open(PALETTE_JSON, encoding="utf-8") as f:
        data = json.load(f)
    tokens = data.get("tokens") or {}
    if not tokens:
        raise SystemExit("色源缺少 tokens：" + PALETTE_JSON)
    series = []
    for name in data.get("_series", []):
        if name not in tokens:
            raise SystemExit("_series 里的 %r 在 tokens 中不存在：%s" % (name, PALETTE_JSON))
        series.append(tokens[name])
    return tokens, series


def css_body(tokens):
    """CSS 侧块体：`--mfg-<token>: <色值>;`，顺序与 JSON 键序一致，便于人工比对。"""
    return "".join("    --mfg-%s: %s;\n" % (k, v) for k, v in tokens.items())


def js_body(tokens, series):
    """JS 侧块体：`const PAL = {...}`，含连字符的键加引号，末位补展开后的 series 数组。"""
    lines = ["  const PAL = {\n"]
    for k, v in tokens.items():
        key = k if IDENT_RE.match(k) else '"%s"' % k
        lines.append('    %s: "%s",\n' % (key, v))
    lines.append("    series: [%s]\n" % ", ".join('"%s"' % c for c in series))
    lines.append("  };\n")
    return "".join(lines)


def replace_block(html, pattern, begin, end, body):
    """把 begin…end 整段换成 begin + body + end；找不到标记返回 (原文, False) 交由调用方告警。

    body 为空串即 `--remove` 的效果：内容清掉、标记留着（下次还能定位）。
    """
    if not pattern.search(html):
        return html, False
    block = begin + "\n" + body + end
    return pattern.sub(lambda _m: block, html, count=1), True


def main():
    do_remove = "--remove" in sys.argv
    tokens, series = load_palette()
    css = "" if do_remove else css_body(tokens)
    js = "" if do_remove else js_body(tokens, series)

    names = []
    if os.path.isdir(PAGES_DIR):
        names = [n for n in sorted(os.listdir(PAGES_DIR))
                 if n.startswith("大屏样板间-") and n.endswith(".html")
                 and not n.endswith(".inner.html") and not n.startswith(".")]

    done = 0
    for name in names:
        path = os.path.join(PAGES_DIR, name)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        out, ok_css = replace_block(src, CSS_BLOCK_RE, CSS_BEGIN, CSS_END, css)
        out, ok_js = replace_block(out, JS_BLOCK_RE, JS_BEGIN, JS_END, js)
        if not ok_css:
            print("警告：%s 找不到 mfgpalette 标记（CSS 侧），已跳过该块" % name)
        if not ok_js:
            print("警告：%s 找不到 mfgpalette-js 标记（JS 侧），已跳过该块" % name)
        if out != src:
            with open(path, "w", encoding="utf-8") as f:
                f.write(out)
            done += 1
    print("%s：处理 %d 个文件，改动 %d 个（%d 个 token，%d 色系列）"
          % ("清空" if do_remove else "同步", len(names), done, len(tokens), len(series)))


if __name__ == "__main__":
    main()
