/* lab-addons：为各 ECharts 视觉实验室提供「复制配置」与「主题切换」能力。
 * 依赖：先于本脚本注入的 LAB_THEMES（shared/themes.js），以及页面已加载的 echarts。
 * 机制：包装 echarts.init 拦截 setOption —— 原始 option 挂到图容器 DOM（__vizRaw），
 * 激活主题时在 set 时做颜色映射（__vizShown 为实际展示的 option）。 */
(function () {
  "use strict";
  if (!window.echarts || window.LabAddons) return;
  function probe(tag, data) {
    try { if (parent !== window) parent.postMessage("LABADDONS:" + tag + ":" + JSON.stringify(data || {}), "*"); } catch (_) { /* noop */ }
  }
  window.addEventListener("error", function (e) {
    probe("err", { m: String(e.message).slice(0, 120), l: e.lineno });
  });
  window.addEventListener("message", function (e) {
    if (e.data !== "LABADDONS_PING") return;
    var w = document.getElementById("lab-theme-widget");
    probe("state", {
      widget: !!w,
      rect: w ? w.getBoundingClientRect().toJSON() : null,
      display: w ? getComputedStyle(w).display : null,
      vw: window.innerWidth, vh: window.innerHeight
    });
  });

  function allThemes() {
    try { return LAB_THEMES || []; } catch (e) { return window.LAB_THEMES || []; }
  }

  var registry = new Set();
  var activeTheme = null;
  var config = { headSelector: null, chartSelector: null };

  /* ---------- 颜色解析 ---------- */
  function hueDist(a, b) {
    var d = Math.abs(a - b) % 360;
    return d > 180 ? 360 - d : d;
  }
  function parseColor(str) {
    if (typeof str !== "string") return null;
    var s = str.trim(), m;
    if ((m = /^#([0-9a-f]{3})$/i.exec(s))) {
      return rgbToHsla(parseInt(m[1][0] + m[1][0], 16), parseInt(m[1][1] + m[1][1], 16), parseInt(m[1][2] + m[1][2], 16), 1);
    }
    if ((m = /^#([0-9a-f]{6})([0-9a-f]{2})?$/i.exec(s))) {
      var v = parseInt(m[1], 16);
      return rgbToHsla(v >> 16, (v >> 8) & 255, v & 255, m[2] ? parseInt(m[2], 16) / 255 : 1);
    }
    if ((m = /^rgba?\(\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*[, ]\s*([\d.]+)\s*(?:[,/ ]\s*([\d.]+%?)\s*)?\)$/i.exec(s))) {
      var a = m[4] == null ? 1 : (m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
      return rgbToHsla(+m[1], +m[2], +m[3], a);
    }
    if ((m = /^hsla?\(\s*([\d.]+)(?:deg)?\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%\s*(?:[,/ ]\s*([\d.]+%?)\s*)?\)$/i.exec(s))) {
      var al = m[4] == null ? 1 : (m[4].endsWith("%") ? parseFloat(m[4]) / 100 : parseFloat(m[4]));
      return { h: +m[1] % 360, s: +m[2] / 100, l: +m[3] / 100, a: al };
    }
    return null;
  }
  function rgbToHsla(r, g, b, a) {
    r /= 255; g /= 255; b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, h = 0, s = 0;
    if (max !== min) {
      var d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      h = max === r ? ((g - b) / d + (g < b ? 6 : 0)) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h *= 60;
    }
    return { h: h, s: s, l: l, a: a };
  }
  function fmtHsla(c) {
    var h = Math.round(c.h * 10) / 10, s = Math.round(c.s * 1000) / 10, l = Math.round(c.l * 1000) / 10;
    return c.a >= 1 ? "hsl(" + h + ", " + s + "%, " + l + "%)" : "hsla(" + h + ", " + s + "%, " + l + "%, " + Math.round(c.a * 1000) / 1000 + ")";
  }
  function isChromatic(c) {
    return c && c.s >= 0.14 && c.a > 0.04 && c.l > 0.02 && c.l < 0.98;
  }

  /* ---------- 主题颜色映射（色相族 → 主题色板槽位；保留原明度/透明度层次） ---------- */
  function buildMapper(option, theme) {
    var families = []; // {hue}
    collect(option);
    function collect(node) {
      if (node == null) return;
      if (typeof node === "string") {
        var c = parseColor(node);
        if (isChromatic(c) && familyOf(c.h) === -1) families.push({ hue: c.h });
        return;
      }
      if (Array.isArray(node)) { node.forEach(collect); return; }
      if (typeof node === "object") {
        for (var k in node) {
          if (k === "formatter" || k === "text" || k === "subtext") continue;
          collect(node[k]);
        }
      }
    }
    function familyOf(h) {
      for (var i = 0; i < families.length; i++) if (hueDist(families[i].hue, h) <= 26) return i;
      return -1;
    }
    var targets = theme.colors.map(parseColor);
    return function mapColorStr(str) {
      var c = parseColor(str);
      if (!isChromatic(c)) return str;
      var fi = familyOf(c.h);
      var t = targets[fi === -1 ? 0 : fi % targets.length];
      return fmtHsla({ h: t.h, s: t.s, l: c.l, a: c.a });
    };
  }

  function mapOption(option, theme) {
    var mapColor = buildMapper(option, theme);
    function walk(node, key) {
      if (node == null || typeof node === "function") return node;
      if (typeof node === "object" && (node.nodeType || node.getContext)) return node; // DOM/canvas 纹理等原样保留
      if (typeof node === "string") {
        if (key === "formatter" || key === "text" || key === "subtext") return node;
        return parseColor(node) ? mapColor(node) : node;
      }
      if (Array.isArray(node)) return node.map(function (v) { return walk(v, key); });
      if (typeof node === "object") {
        var out = {};
        for (var k in node) out[k] = walk(node[k], k);
        return out;
      }
      return node;
    }
    return walk(option, null);
  }

  /* ---------- echarts.init / setOption 拦截 ---------- */
  var realInit = echarts.init.bind(echarts);
  echarts.init = function (dom, theme, opts) {
    var chart = realInit(dom, theme, opts);
    if (!dom || !chart) return chart;
    chart.__vizDom = dom;
    registry.add(chart);
    var realSet = chart.setOption.bind(chart);
    chart.__vizRealSetOption = realSet;
    chart.setOption = function (opt) {
      var rest = Array.prototype.slice.call(arguments, 1);
      if (opt && opt.series) dom.__vizRaw = opt;
      var shown = activeTheme && opt ? mapOption(opt, activeTheme) : opt;
      if (opt && opt.series) dom.__vizShown = shown;
      return realSet.apply(null, [shown].concat(rest));
    };
    return chart;
  };

  /* ---------- 主题应用 ---------- */
  var stageEls = null;
  function findStageEls() {
    // 全屏级不透明底色容器（各实验室的"舞台"div），换主题时一并换底
    var out = [];
    var vw = window.innerWidth, vh = window.innerHeight;
    var candidates = document.body.querySelectorAll(":scope > *, :scope > * > *");
    candidates.forEach(function (el) {
      if (el.id === "lab-theme-widget" || el.id === "lab-copy-modal") return;
      if (el.offsetWidth < vw * 0.9 || el.offsetHeight < vh * 0.6) return;
      var c = parseColor(getComputedStyle(el).backgroundColor);
      if (c && c.a > 0.5) out.push({ el: el, orig: el.style.getPropertyValue("background-color") });
    });
    return out;
  }

  function applyTheme(theme) {
    activeTheme = theme;
    var root = document.documentElement;
    if (!stageEls) stageEls = findStageEls();
    stageEls.forEach(function (s) {
      if (theme && theme.bg) s.el.style.setProperty("background-color", theme.bg, "important");
      else if (s.orig) s.el.style.setProperty("background-color", s.orig);
      else s.el.style.removeProperty("background-color");
    });
    for (var i = 1; i <= 6; i++) {
      if (theme && theme.colors[i - 1]) root.style.setProperty("--viz-series-" + i, theme.colors[i - 1]);
      else root.style.removeProperty("--viz-series-" + i);
    }
    if (theme && theme.colors[0]) root.style.setProperty("--primary", theme.colors[0]);
    else root.style.removeProperty("--primary");
    if (theme && theme.bg) {
      root.style.setProperty("--background", theme.bg);
      root.style.setProperty("--lab-bg", theme.bg);
      root.classList.add("lab-themed");
    } else {
      root.style.removeProperty("--background");
      root.style.removeProperty("--lab-bg");
      root.classList.remove("lab-themed");
    }
    registry.forEach(function (chart) {
      if (chart.isDisposed && chart.isDisposed()) { registry.delete(chart); return; }
      var raw = chart.__vizDom && chart.__vizDom.__vizRaw;
      if (raw) chart.setOption(raw, { notMerge: true });
    });
  }

  /* ---------- 复制配置 ---------- */
  function serializeJS(value, indent) {
    var pad = "  ".repeat(indent), padIn = "  ".repeat(indent + 1);
    if (value === null) return "null";
    if (value === undefined) return "undefined";
    var t = typeof value;
    if (t === "number" || t === "boolean") return String(value);
    if (t === "string") return JSON.stringify(value);
    if (t === "function") {
      return String(value).split("\n").map(function (line, i) { return i === 0 ? line : padIn + line.trim(); }).join("\n");
    }
    if (Array.isArray(value)) {
      if (!value.length) return "[]";
      var flat = value.every(function (v) { return v === null || ["number", "string", "boolean"].indexOf(typeof v) !== -1; });
      var items = value.map(function (v) { return serializeJS(v, indent + 1); });
      if (flat && items.join(", ").length < 100) return "[" + items.join(", ") + "]";
      return "[\n" + items.map(function (s) { return padIn + s; }).join(",\n") + "\n" + pad + "]";
    }
    if (t === "object") {
      var keys = Object.keys(value).filter(function (k) { return value[k] !== undefined; });
      if (!keys.length) return "{}";
      var body = keys.map(function (k) {
        var key = /^[A-Za-z_$][\w$]*$/.test(k) ? k : JSON.stringify(k);
        return padIn + key + ": " + serializeJS(value[k], indent + 1);
      });
      return "{\n" + body.join(",\n") + "\n" + pad + "}";
    }
    return "null";
  }

  function copyText(text, done) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); }, function () { legacyCopy(text, done); });
    } else legacyCopy(text, done);
  }
  function legacyCopy(text, done) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      ta.remove();
      if (ok) return done(true);
    } catch (e) { /* fall through */ }
    showModal(text);
    done(false);
  }
  function showModal(text) {
    var old = document.getElementById("lab-copy-modal");
    if (old) old.remove();
    var wrap = document.createElement("div");
    wrap.id = "lab-copy-modal";
    wrap.innerHTML =
      '<div class="lab-copy-mask"></div><div class="lab-copy-box"><p>自动复制受限，请手动全选复制：</p>' +
      '<textarea readonly></textarea><button type="button">关闭</button></div>';
    wrap.querySelector("textarea").value = text;
    wrap.querySelector("button").addEventListener("click", function () { wrap.remove(); });
    wrap.querySelector(".lab-copy-mask").addEventListener("click", function () { wrap.remove(); });
    document.body.appendChild(wrap);
    wrap.querySelector("textarea").select();
  }

  function schemeTitle(head) {
    var el = head.querySelector("h1,h2,h3,h4");
    return el ? el.textContent.trim() : "方案";
  }

  function onCopyClick(btn, head) {
    var card = head.parentElement;
    var chartNode = card ? card.querySelector(config.chartSelector) : null;
    var opt = chartNode && (chartNode.__vizShown || chartNode.__vizRaw);
    if (!opt) { flash(btn, "图表未渲染"); return; }
    var text = "/* 方案：" + schemeTitle(head) + " · ECharts 6.1.0" +
      (activeTheme ? " · 主题：" + activeTheme.name : "") +
      " · 用法：echarts.init(dom).setOption(option) */\n" +
      "const option = " + serializeJS(opt, 0) + ";\n";
    copyText(text, function (ok) { flash(btn, ok ? "已复制" : "见弹窗"); });
  }
  function flash(btn, msg) {
    var origin = btn.dataset.label;
    btn.textContent = msg;
    btn.disabled = true;
    setTimeout(function () { btn.textContent = origin; btn.disabled = false; }, 1200);
  }

  var injectQueued = false;
  function injectButtons() {
    if (!config.headSelector) return;
    document.querySelectorAll(config.headSelector).forEach(function (head) {
      if (head.querySelector(".lab-copy-btn")) return;
      var card = head.parentElement;
      if (!card || !card.querySelector(config.chartSelector)) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "lab-copy-btn";
      btn.textContent = "复制配置";
      btn.dataset.label = "复制配置";
      btn.addEventListener("click", function () { onCopyClick(btn, head); });
      head.appendChild(btn);
    });
  }
  function queueInject() {
    if (injectQueued) return;
    injectQueued = true;
    setTimeout(function () { injectQueued = false; injectButtons(); }, 120);
  }

  /* ---------- 主题切换悬浮组件 ---------- */
  function buildWidget() {
    var wrap = document.createElement("div");
    wrap.id = "lab-theme-widget";
    var groups = { "行业": [], "风格": [] };
    allThemes().forEach(function (t) { (groups[t.group] = groups[t.group] || []).push(t); });
    var optionsHtml = Object.keys(groups).map(function (g) {
      return '<optgroup label="' + (g === "行业" ? "行业主题" : "风格皮肤") + '">' +
        groups[g].map(function (t) { return '<option value="' + t.id + '">' + t.name + " · " + t.use + "</option>"; }).join("") +
        "</optgroup>";
    }).join("");
    wrap.innerHTML =
      '<span class="lab-theme-label">配色主题</span>' +
      '<select aria-label="切换配色主题"><option value="">默认（原始配色）</option>' + optionsHtml + "</select>" +
      '<button type="button">还原</button>';
    var select = wrap.querySelector("select");
    select.addEventListener("change", function () {
      var theme = allThemes().find(function (t) { return t.id === select.value; }) || null;
      applyTheme(theme);
    });
    wrap.querySelector("button").addEventListener("click", function () {
      select.value = "";
      applyTheme(null);
    });
    // 沙箱 srcdoc iframe 对悬浮定位层绘制不可靠，工具栏内嵌又易被局部布局裁剪，
    // 统一采用顶部独立横条（文档流内、全宽，绘制稳定）。
    document.body.insertBefore(wrap, document.body.firstChild);
  }

  function injectStyles() {
    var css =
      "html.lab-themed{background:var(--lab-bg) !important;background-color:var(--lab-bg) !important}" +
      "html.lab-themed body{background:var(--lab-bg) !important}" +
      "html.lab-themed body::before,html.lab-themed body::after{opacity:.22}" +
      ".lab-copy-btn{margin-left:8px;flex:none;font:inherit;font-size:11px;line-height:1;padding:5px 9px;border-radius:999px;" +
      "border:1px solid rgba(140,190,255,.4);background:rgba(40,90,160,.28);color:#cfe6ff;cursor:pointer;white-space:nowrap}" +
      ".lab-copy-btn:hover{background:rgba(70,130,210,.45)}.lab-copy-btn:disabled{opacity:.85;cursor:default}" +
      "#lab-theme-widget{display:flex;gap:10px;align-items:center;justify-content:flex-start;padding:8px 24px;" +
      "border-bottom:1px solid rgba(140,190,255,.18);background:rgba(8,22,45,.6);font-size:12px;color:#cfe6ff;white-space:nowrap}" +
      "#lab-theme-widget select{max-width:170px;font:inherit;padding:4px 6px;border-radius:8px;border:1px solid rgba(140,190,255,.4);" +
      "background:rgba(15,35,70,.9);color:#e6f2ff}" +
      "#lab-theme-widget button{font:inherit;padding:4px 10px;border-radius:8px;border:1px solid rgba(140,190,255,.4);" +
      "background:rgba(40,90,160,.3);color:#cfe6ff;cursor:pointer}" +
      "#lab-copy-modal{position:fixed;inset:0;z-index:2147483100}" +
      "#lab-copy-modal .lab-copy-mask{position:absolute;inset:0;background:rgba(0,0,0,.55)}" +
      "#lab-copy-modal .lab-copy-box{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:min(720px,90vw);" +
      "background:#0d1f3d;border:1px solid rgba(140,190,255,.4);border-radius:12px;padding:16px;color:#cfe6ff;font-size:13px}" +
      "#lab-copy-modal textarea{width:100%;height:300px;margin:10px 0;background:#081422;color:#d7e8ff;border:1px solid rgba(140,190,255,.3);" +
      "border-radius:8px;font-family:monospace;font-size:12px;padding:8px;box-sizing:border-box}" +
      "#lab-copy-modal button{font:inherit;padding:6px 14px;border-radius:8px;border:1px solid rgba(140,190,255,.4);" +
      "background:rgba(40,90,160,.3);color:#cfe6ff;cursor:pointer}";
    var style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
  }

  window.LabAddons = {
    setup: function (cfg) {
      config = cfg || {};
      function whenViewportReady(fn) {
        // srcdoc iframe 在脚本执行时视口可能还是 0×0，bottom/right 锚定的 fixed
        // 元素此时创建会错过重绘；等视口就绪后再建。
        if (window.innerWidth > 0 && window.innerHeight > 0) { fn(); return; }
        var done = false;
        function tryRun() {
          if (done || window.innerWidth === 0 || window.innerHeight === 0) return;
          done = true;
          clearInterval(timer);
          window.removeEventListener("resize", tryRun);
          fn();
        }
        var timer = setInterval(tryRun, 250);
        window.addEventListener("resize", tryRun);
      }
      function boot() {
        injectStyles();
        whenViewportReady(buildWidget);
        injectButtons();
        new MutationObserver(queueInject).observe(document.body, { childList: true, subtree: true });
        var w = document.getElementById("lab-theme-widget");
        probe("boot", {
          widget: !!w,
          rect: w ? w.getBoundingClientRect().toJSON() : null,
          btns: document.querySelectorAll(".lab-copy-btn").length,
          vw: window.innerWidth, vh: window.innerHeight
        });
      }
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
      else boot();
    },
    applyTheme: applyTheme,
    mapOption: mapOption,
    _registry: registry
  };
})();
