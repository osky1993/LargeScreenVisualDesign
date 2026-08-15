#!/usr/bin/env python3
"""从两个配色文件提取 33 套主题，生成 shared/themes.js。

- 《管理大屏配色专项与行业主体实现实验室.html》srcdoc 内 `var themes`：12 套行业主题
- 《图表配色方案-21套.html》text/x-dc 脚本内 `const palettes`：21 套风格皮肤
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def slice_array(text: str, start: int) -> str:
    """从 start（'[' 的位置）起做括号配对，返回完整数组字面量。"""
    depth = 0
    in_str = None
    i = start
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in "'\"`":
            in_str = c
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise SystemExit("数组括号不配对")


def node_eval(js: str):
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        raise SystemExit("node 求值失败")
    return json.loads(out.stdout)


def extract_industry():
    s = (ROOT / "管理大屏配色专项与行业主体实现实验室.html").read_text(encoding="utf-8")
    m = re.search(r'srcdoc="(.*?)"', s, re.S)
    inner = html.unescape(m.group(1))
    idx = re.search(r"var themes\s*=\s*\[", inner)
    arr = slice_array(inner, inner.index("[", idx.start()))
    return node_eval(f"const themes = {arr}; console.log(JSON.stringify(themes));")


def extract_styles():
    s = (ROOT / "图表配色方案-21套.html").read_text(encoding="utf-8")
    # text/x-dc 脚本内的源码带字面 \n 与 \" 转义
    start = s.find("const data = [")
    if start < 0:
        raise SystemExit("未找到 21 套源码起点")
    seg = s[start : s.find("const charts", start)]
    seg = seg.replace('\\"', '"').replace("\\n", "\n")
    p = re.search(r"const palettes\s*=\s*\[", seg)
    body = seg[: p.start()] + "const palettes = " + slice_array(seg, seg.index("[", p.start())) + ";"
    js = f"""
{body}
const toHex = (c) => {{
  const m = /^hsl\\((\\d+(?:\\.\\d+)?) (\\d+(?:\\.\\d+)?)% (\\d+(?:\\.\\d+)?)%\\)$/.exec(c);
  if (!m) return c;
  const [h, s, l] = [Number(m[1]), Number(m[2]) / 100, Number(m[3]) / 100];
  const a = s * Math.min(l, 1 - l);
  const f = (n) => {{
    const k = (n + h / 30) % 12;
    const v = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(v * 255).toString(16).padStart(2, "0");
  }};
  return `#${{f(0)}}${{f(8)}}${{f(4)}}`;
}};
console.log(JSON.stringify(palettes.map(p => ({{ ...p, colors: p.colors.map(toHex) }}))));
"""
    return node_eval(js)


def main():
    industry = extract_industry()
    styles = extract_styles()
    if len(industry) != 12 or len(styles) != 21:
        raise SystemExit(f"数量不符：行业 {len(industry)}，风格 {len(styles)}")
    themes = []
    for t in industry:
        themes.append({
            "id": t["code"], "group": "行业", "name": t["name"], "use": t["use"],
            "bg": None,  # 行业主题不换页面底色，保留实验室原深蓝底
            "colors": t["cat"], "seq": t["seq"], "div": t["div"], "sem": t["sem"],
            "text": None, "muted": None, "accent": t["cat"][0],
        })
    for i, p in enumerate(styles, 1):
        themes.append({
            "id": f"P{i:02d}", "group": "风格", "name": p["title"], "use": p["subtitle"],
            "bg": p["bg"], "colors": p["colors"], "seq": None, "div": None, "sem": None,
            "text": p.get("centerText"), "muted": p.get("centerSub"), "accent": p.get("legendPct"),
        })
    out = ROOT / "shared" / "themes.js"
    out.parent.mkdir(exist_ok=True)
    payload = json.dumps(themes, ensure_ascii=False, indent=2)
    out.write_text(
        "/* 自动生成：tools/extract_themes.py（源：管理大屏配色专项 12 套 + 图表配色方案 21 套） */\n"
        f"const LAB_THEMES = {payload};\n",
        encoding="utf-8",
    )
    print(f"已生成 {out}：{len(themes)} 套（行业 12 + 风格 21）")


if __name__ == "__main__":
    main()
