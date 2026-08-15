#!/usr/bin/env python3
"""把 shared/themes.js + shared/lab-addons.js 注入实验室 HTML 的 srcdoc 内页。

用法：
  python3 tools/inject_addons.py <lab.html> '<setup-config-json>'
例：
  python3 tools/inject_addons.py ECharts视觉实验室-柱状图8.html '{"headSelector": ".e6-panel-header", "chartSelector": ".e6-chart"}'

幂等：重复运行会替换 LAB_ADDONS 标记块。注入点：第一个 echarts CDN <script> 之后。
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = "<!--LAB_ADDONS_START-->"
END = "<!--LAB_ADDONS_END-->"


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    lab = Path(sys.argv[1])
    cfg = json.loads(sys.argv[2])

    shell = lab.read_text(encoding="utf-8")
    m = re.search(r'(srcdoc=")(.*?)(")', shell, re.S)
    if not m:
        raise SystemExit("未找到 srcdoc")
    inner = html.unescape(m.group(2))

    themes = (ROOT / "shared" / "themes.js").read_text(encoding="utf-8")
    addons = (ROOT / "shared" / "lab-addons.js").read_text(encoding="utf-8")
    block = (
        f"{START}\n<script>\n{themes}\n</script>\n<script>\n{addons}\n</script>\n"
        f"<script>\nwindow.LabAddons && LabAddons.setup({json.dumps(cfg, ensure_ascii=False)});\n</script>\n{END}"
    )

    if START in inner:
        inner = re.sub(re.escape(START) + ".*?" + re.escape(END), lambda _: block, inner, flags=re.S)
        action = "已替换既有注入块"
    else:
        anchor = re.search(r'<script[^>]*src="[^"]*echarts[^"]*"[^>]*>\s*</script>', inner)
        if not anchor:
            raise SystemExit("未找到 echarts CDN script 注入锚点")
        pos = anchor.end()
        inner = inner[:pos] + "\n" + block + inner[pos:]
        action = "已注入"

    payload = html.escape(inner, quote=True)
    out = shell[: m.start(2)] + payload + shell[m.end(2):]

    # 外壳侧探针接收器（同源，便于自动化验证读取 window.__labProbe）
    listener = (
        "<!--LAB_PROBE_START--><script>window.__labProbe=[];window.addEventListener(\"message\",function(e){"
        "if(typeof e.data===\"string\"&&e.data.indexOf(\"LABADDONS:\")===0){window.__labProbe.push(e.data);}"
        "});</script><!--LAB_PROBE_END-->"
    )
    if "<!--LAB_PROBE_START-->" in out:
        out = re.sub(r"<!--LAB_PROBE_START-->.*?<!--LAB_PROBE_END-->", lambda _: listener, out, flags=re.S)
    else:
        out = out.replace("</body>", listener + "</body>", 1)

    lab.write_text(out, encoding="utf-8")
    print(f"{action} -> {lab} ({lab.stat().st_size} 字节)")


if __name__ == "__main__":
    main()
