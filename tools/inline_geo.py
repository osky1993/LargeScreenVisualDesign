#!/usr/bin/env python3
"""把 `shared/geo-data.js` 里的 GeoJSON 数据集内联进大屏页面（幂等，可反复跑）。

用法：
    python3 tools/inline_geo.py <页面路径> <数据集名> [更多数据集名...]
    python3 tools/inline_geo.py <页面路径> --remove       # 清空内容，保留两行标记

    # 例：给某地图页内联全国 + 江苏两套边界
    python3 tools/inline_geo.py screens/public-funds/大屏样板间-XXX1920.html china jiangsu

页面路径可以是相对仓库根的路径，也可以是绝对路径。

要点：
- 样板间必须**自包含、无外网请求**，所以地图页不 fetch geo-data.js，而是把需要的数据集
  直接内联成页内的 `const GEO_DATA = {...}`（既有做法见「公共资金分地区收入」那一屏）。
- 单个 `china` 就约 450KB，人工复制粘贴不现实，故工具化。
- 落点靠页面里预留的标记块，整段替换 ——

      /* geo:begin —— 由 tools/inline_geo.py 注入，勿手改。数据源：shared/geo-data.js */
      const GEO_DATA = {
        china: {...},
      };
      /* geo:end */

  页面里**没有**这对标记就直接报错退出，不猜插入位置：新页请先在 `<script>` 开头手写
  `/* geo:begin */` 与 `/* geo:end */` 两行占位，再跑本脚本。
- `--remove` 只清块内容、保留两行标记 —— 标记是页面结构的一部分，删了下次就找不到落点。
- JSON 压紧成一行（不 indent）：450KB 数据 pretty print 只会膨胀，且页内没人读。
"""
import json
import os
import re
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO_JS = os.path.join(ROOT, "shared", "geo-data.js")

BEGIN_LINE = "/* geo:begin —— 由 tools/inline_geo.py 注入，勿手改。数据源：shared/geo-data.js */"
END_LINE = "/* geo:end */"

# 整块：从 begin 标记所在行的行首缩进，一直吃到 end 标记行尾（不含尾部换行）
BLOCK_RE = re.compile(
    r"^([ \t]*)/\*\s*geo:begin.*?^[ \t]*/\*\s*geo:end\s*\*/",
    re.S | re.M,
)
# 顶层键名：`  china: {` 里的 china
KEY_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*:")


def scan_value(text, i):
    """从 text[i]（必是 `{`）起做括号配平扫描，返回值结束位置的**下一个**下标。

    GeoJSON 里的字符串不含花括号，但仍老实做字符串/转义防护 —— 免得哪天数据源
    加了带括号的地名，正则式的贪婪匹配把整段吞掉还不报错。
    """
    depth, in_str, esc = 0, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SystemExit("解析 shared/geo-data.js 失败：花括号不配平")


def load_datasets():
    """解析 geo-data.js，返回 {数据集名: 已 json.loads 的对象}（保持文件里的先后顺序）。

    它是 JS 不是 JSON（有顶层 `const` 和注释），但结构规整：顶层对象里每个数据集
    一行 `  <名字>: <合法 JSON 值>,`，逐个切出来再用 json.loads 验证。
    """
    if not os.path.exists(GEO_JS):
        raise SystemExit("找不到 %s" % GEO_JS)
    with open(GEO_JS, encoding="utf-8") as f:
        src = f.read()

    m = re.search(r"const\s+GEO_DATA\s*=\s*\{", src)
    if not m:
        raise SystemExit("解析 shared/geo-data.js 失败：找不到 `const GEO_DATA = {`")

    out = OrderedDict()
    i = m.end()                      # 停在顶层 `{` 之后
    while i < len(src):
        km = KEY_RE.match(src, i) or KEY_RE.search(src, i)
        if not km or src.find("}", i, km.start()) != -1:
            break                    # 顶层对象已闭合，收工
        j = src.index("{", km.end())
        end = scan_value(src, j)
        raw = src[j:end]
        try:
            out[km.group(1)] = json.loads(raw)
        except ValueError as e:
            raise SystemExit("数据集 %s 不是合法 JSON：%s" % (km.group(1), e))
        i = end
    if not out:
        raise SystemExit("解析 shared/geo-data.js 失败：没切出任何数据集")
    return out


def render_block(indent, datasets):
    """按既有页面形态渲染整块（每个数据集压成一行）。"""
    lines = [indent + BEGIN_LINE, indent + "const GEO_DATA = {"]
    for name, value in datasets:
        dumped = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        lines.append("%s  %s: %s," % (indent, name, dumped))
    lines += [indent + "};", indent + END_LINE]
    return "\n".join(lines)


def replace_block(html, make_body):
    """定位标记块并整段替换；make_body(indent, 原块文本) 返回新块文本。"""
    m = BLOCK_RE.search(html)
    if not m:
        raise SystemExit(
            "页面里找不到 /* geo:begin */ … /* geo:end */ 标记块。\n"
            "请先在页面 <script> 里手写这两行占位（本脚本不猜插入位置）：\n"
            "    /* geo:begin */\n"
            "    /* geo:end */"
        )
    return html[: m.start()] + make_body(m.group(1), m.group(0)) + html[m.end():]


def main():
    argv = sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)

    page = argv[0] if os.path.isabs(argv[0]) else os.path.join(ROOT, argv[0])
    if not os.path.exists(page):
        raise SystemExit("找不到页面 %s" % page)
    names = argv[1:]
    do_remove = "--remove" in names
    names = [n for n in names if n != "--remove"]
    if do_remove and names:
        raise SystemExit("--remove 不能和数据集名同时给")
    if not do_remove and not names:
        raise SystemExit("请至少给一个数据集名，或用 --remove")

    with open(page, encoding="utf-8") as f:
        src = f.read()

    if do_remove:
        # 保留原样的两行标记（含用户可能手写的简写形式），只清中间内容
        def body(indent, old):
            first = old.split("\n", 1)[0].strip()
            return indent + first + "\n" + indent + END_LINE
        out = replace_block(src, body)
        note = "已清空 geo 块（标记保留）"
    else:
        pool = load_datasets()
        bad = [n for n in names if n not in pool]
        if bad:
            raise SystemExit(
                "未知数据集：%s\n可用数据集：%s"
                % ("、".join(bad), "、".join(pool.keys()))
            )
        picked = [(n, pool[n]) for n in names]
        out = replace_block(src, lambda indent, old: render_block(indent, picked))
        note = "已内联：" + "、".join(
            "%s（%d 个要素）" % (n, len(v.get("features", []))) for n, v in picked
        )

    changed = out != src
    if changed:
        with open(page, "w", encoding="utf-8") as f:
            f.write(out)
    print("%s → %s%s（%d 字节）" % (
        note, os.path.relpath(page, ROOT),
        "" if changed else "，内容未变",
        os.path.getsize(page),
    ))


if __name__ == "__main__":
    main()
