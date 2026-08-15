#!/usr/bin/env python3
"""把独立的内页 HTML 打包成与现有实验室一致的外壳格式（CSP + iframe srcdoc）。

用法：
  python3 tools/wrap_lab.py <inner.html> <输出.html> <页面标题>
"""
import html
import sys
from pathlib import Path

CSP = (
    "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob: data: "
    "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://esm.sh https://fonts.bunny.net "
    "https://fonts.googleapis.com https://fonts.gstatic.com https://unpkg.com; "
    "style-src 'unsafe-inline' blob: data: https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://esm.sh "
    "https://fonts.bunny.net https://fonts.googleapis.com https://fonts.gstatic.com https://unpkg.com; "
    "img-src blob: data: https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://esm.sh https://fonts.bunny.net "
    "https://fonts.googleapis.com https://fonts.gstatic.com https://unpkg.com; "
    "font-src blob: data: https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://esm.sh https://fonts.bunny.net "
    "https://fonts.googleapis.com https://fonts.gstatic.com https://unpkg.com; "
    "media-src blob: data: https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://esm.sh https://fonts.bunny.net "
    "https://fonts.googleapis.com https://fonts.gstatic.com https://unpkg.com; "
    "worker-src blob:; connect-src blob: data:; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'"
)

SHELL = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<title>{title}</title>
<style>:root{{background:rgb(10,30,60)}}html,body{{width:100%;height:100%;margin:0;overflow:hidden;background:rgb(10,30,60)}}body{{box-sizing:border-box}}iframe{{display:block;width:100%;max-width:none;height:100vh;margin:0;border:0;background:rgb(10,30,60)}}</style>
</head>
<body>
<iframe sandbox="allow-scripts" referrerpolicy="no-referrer" title="{title}" srcdoc="{srcdoc}"></iframe>
<!--LAB_PROBE_START--><script>window.__labProbe=[];window.addEventListener("message",function(e){{if(typeof e.data==="string"&&e.data.indexOf("LABADDONS:")===0){{window.__labProbe.push(e.data);}}}});</script><!--LAB_PROBE_END-->
</body>
</html>
"""


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    inner, out, title = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    payload = html.escape(inner.read_text(encoding="utf-8"), quote=True)
    out.write_text(SHELL.format(csp=CSP, title=html.escape(title, quote=True), srcdoc=payload), encoding="utf-8")
    print(f"已打包 -> {out} ({out.stat().st_size} 字节)")


if __name__ == "__main__":
    main()
