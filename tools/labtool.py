#!/usr/bin/env python3
"""srcdoc 解码/回写工具：实验室 HTML 的真实内容内嵌在 <iframe srcdoc="..."> 中（HTML 转义）。

用法：
  python3 tools/labtool.py decode <lab.html>   # 输出内页到 <lab>.inner.html
  python3 tools/labtool.py encode <lab.html>   # 把 <lab>.inner.html 转义后写回 <lab.html> 的 srcdoc
  python3 tools/labtool.py roundtrip <lab.html># 校验 decode→encode 语义不变
"""
import html
import re
import sys
from pathlib import Path

SRCDOC_RE = re.compile(r'(srcdoc=")(.*?)(")', re.S)


def split(shell_text):
    m = SRCDOC_RE.search(shell_text)
    if not m:
        raise SystemExit("未找到 srcdoc 属性")
    return shell_text[: m.start(2)], m.group(2), shell_text[m.end(2):]


def inner_path(path: Path) -> Path:
    return path.with_suffix(".inner.html")


def decode(path: Path):
    _, payload, _ = split(path.read_text(encoding="utf-8"))
    out = inner_path(path)
    out.write_text(html.unescape(payload), encoding="utf-8")
    print(f"已解码 -> {out} ({out.stat().st_size} 字节)")


def encode(path: Path):
    src = inner_path(path)
    if not src.exists():
        raise SystemExit(f"缺少 {src}，请先 decode")
    head, _, tail = split(path.read_text(encoding="utf-8"))
    payload = html.escape(src.read_text(encoding="utf-8"), quote=True)
    path.write_text(head + payload + tail, encoding="utf-8")
    print(f"已回写 -> {path} ({path.stat().st_size} 字节)")


def roundtrip(path: Path):
    text = path.read_text(encoding="utf-8")
    _, payload, _ = split(text)
    decoded = html.unescape(payload)
    re_encoded = html.escape(decoded, quote=True)
    if re_encoded == payload:
        print("round-trip 完全一致（字节级）")
    elif html.unescape(re_encoded) == decoded:
        print(f"round-trip 语义一致（转义写法有差异：原 {len(payload)} 字节，重编码 {len(re_encoded)} 字节）")
    else:
        raise SystemExit("round-trip 失败：解码结果不一致")


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in {"decode", "encode", "roundtrip"}:
        raise SystemExit(__doc__)
    {"decode": decode, "encode": encode, "roundtrip": roundtrip}[sys.argv[1]](Path(sys.argv[2]))


if __name__ == "__main__":
    main()
