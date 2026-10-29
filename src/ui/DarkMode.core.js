// Dark Mode for DSM: theme switch, chart colors and the taskbar tray menu.
// Loaded by DarkMode.js (see there why the code lives in a separate file).
//
// The stylesheet (style.css next to this file) is generated on the NAS and
// holds all dark rules in one "@media (prefers-color-scheme: dark)" block, so
// the login page and the desktop follow the operating system without any
// script. This file adds the per-user choice (automatic, light, dark) by
// rewriting the condition of that block, themes ECharts charts (they paint on
// a canvas, which CSS cannot reach), marks package icons that need a light
// plate and keeps the stylesheet up to date when DSM or packages change their
// stylesheets.
Ext.namespace("SYNO.SDS.DarkMode");

// Runs once per page: a second start of the app loads this file again, and
// redefining the objects would replace the running theme state.
if (!SYNO.SDS.DarkMode.start) (function () {

  SYNO.SDS.DarkMode.APP = "SYNO.SDS.DarkMode.Instance";
  // The package folder in the DSM web root ("webman/3rdparty/<package>/"), from
  // DSM's own app configuration: the package name differs between the GitHub
  // and the SynoCommunity package.
  SYNO.SDS.DarkMode.BASE = (function () {
    const entry = SYNO.SDS.Config.FnMap["SYNO.SDS.DarkMode.Instance"];
    const url = entry && entry.config && entry.config.jsBaseURL;
    return url ? url.replace(/\/?$/, "/") : "webman/3rdparty/DarkMode/";
  })();
  SYNO.SDS.DarkMode.AUTO_MEDIA = "(prefers-color-scheme: dark)";

  // --------------------------------------------------------------------------
  // Color palette (same transform as src/lib/darkgen.py, kept in sync by hand)
  // --------------------------------------------------------------------------

  SYNO.SDS.DarkMode.Palette = (function () {
    const NEUTRAL_CHROMA = 0.045, SURFACE_L = 0.235, SURFACE_SPAN = 0.48;
    const TEXT_L = 0.93, TEXT_SPAN = 0.40, BORDER_L = 0.355, BORDER_SPAN = 0.45;
    const ACCENT_TEXT_MIN_L = 0.80, INVISIBLE_BORDER_L = 0.97, TINT_MAX_ALPHA = 0.3;

    const lin = c => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
    const unlin = c => (c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(c, 1 / 2.4) - 0.055);

    function toOklch(r, g, b) {
      r = lin(r / 255); g = lin(g / 255); b = lin(b / 255);
      const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
      const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
      const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
      const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s;
      const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
      const B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
      return [L, Math.hypot(A, B), Math.atan2(B, A)];
    }

    function toLinear(L, C, h) {
      const A = C * Math.cos(h), B = C * Math.sin(h);
      const l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3);
      const m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3);
      const s = Math.pow(L - 0.0894841775 * A - 1.2914855480 * B, 3);
      return [
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
      ];
    }

    function fromOklch(L, C, h) {
      L = Math.min(1, Math.max(0, L));
      const inGamut = v => v.every(x => x >= -1e-4 && x <= 1 + 1e-4);
      let rgb = toLinear(L, C, h);
      if (!inGamut(rgb)) {
        let lo = 0, hi = C;
        for (let i = 0; i < 20; i++) {
          const mid = (lo + hi) / 2;
          if (inGamut(toLinear(L, mid, h))) lo = mid; else hi = mid;
        }
        rgb = toLinear(L, lo, h);
      }
      return rgb.map(v => Math.round(Math.min(1, Math.max(0, unlin(Math.min(1, Math.max(0, v))))) * 255));
    }

    const roles = {
      bg(L, C) {
        if (C < NEUTRAL_CHROMA || L > 0.9) {
          return L >= 0.5 ? [SURFACE_L + (1 - L) * SURFACE_SPAN, Math.min(C, 0.03) * 0.6] : [Math.max(L, 0.16), C];
        }
        if (L > 0.8) return [SURFACE_L + (1 - L) * SURFACE_SPAN + 0.04, Math.min(C, 0.06)];
        return [Math.min(L, 0.68), C];
      },
      text(L, C) {
        if (C < NEUTRAL_CHROMA) return L > 0.9 ? [L, C] : [Math.min(TEXT_L, 1 - L * TEXT_SPAN), C * 0.5];
        return [Math.max(L, ACCENT_TEXT_MIN_L), C];
      },
      border(L, C) {
        if (C < NEUTRAL_CHROMA) {
          if (L >= INVISIBLE_BORDER_L) return roles.bg(L, C);
          return L >= 0.5 ? [BORDER_L + (1 - L) * BORDER_SPAN * 0.5, Math.min(C, 0.02)] : [Math.max(0.45, 1 - L * 0.9), C * 0.5];
        }
        return [Math.max(L, 0.55), C];
      }
    };

    let probe = null;
    function parse(value) {
      if (typeof value !== "string" || !value || /gradient|url\(/i.test(value)) return null;
      const hex = value.trim().match(/^#([0-9a-f]{3,8})$/i);
      if (hex && [3, 4, 6, 8].indexOf(hex[1].length) >= 0) {
        const h = hex[1].length < 6 ? hex[1].replace(/./g, c => c + c) : hex[1];
        return [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16)).concat([h.length === 8 ? parseInt(h.substr(6, 2), 16) / 255 : 1]);
      }
      const rgb = value.trim().match(/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/i);
      if (rgb) {
        const a = rgb[4] === undefined ? 1 : rgb[4].endsWith("%") ? parseFloat(rgb[4]) / 100 : parseFloat(rgb[4]);
        return [+rgb[1], +rgb[2], +rgb[3], a];
      }
      // Let the browser parse every CSS color syntax.
      probe = probe || document.createElement("span");
      probe.style.color = "";
      probe.style.color = value;
      if (!probe.style.color) return null;
      document.body.appendChild(probe);
      const m = getComputedStyle(probe).color.match(/rgba?\(([^)]+)\)/);
      probe.remove();
      if (!m) return null;
      const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    }

    const format = (rgb, a) => (a >= 0.999 ? "#" + rgb.map(v => v.toString(16).padStart(2, "0")).join("")
      : "rgba(" + rgb.join(",") + "," + Math.round(a * 1000) / 1000 + ")");

    const cache = {};
    function transform(value, role) {
      const key = role + "|" + value;
      if (key in cache) return cache[key];
      const c = parse(value);
      let out = value;
      if (c && c[3] > 0 && role === "shadow") {
        // Light emboss shadows look like glow on dark backgrounds.
        out = toOklch(c[0], c[1], c[2])[0] > 0.6 ? format([0, 0, 0], c[3] * 0.5)
          : format([c[0], c[1], c[2]].map(Math.round), Math.min(1, c[3] * 1.6));
      } else if (c && c[3] > 0) {
        const lch = toOklch(c[0], c[1], c[2]);
        if (role === "bg" && c[3] <= TINT_MAX_ALPHA && lch[1] < NEUTRAL_CHROMA && lch[0] < 0.5) {
          // Faint dark tints shade white surfaces; on dark ones they lighten.
          out = format([255, 255, 255], c[3]);
          cache[key] = out;
          return out;
        }
        const next = roles[role](lch[0], lch[1]);
        out = format(fromOklch(next[0], next[1], lch[2]), c[3]);
      }
      cache[key] = out;
      return out;
    }

    return { transform: transform };
  })();

  // --------------------------------------------------------------------------
  // Charts: ECharts draws on a canvas, so its options get the dark palette.
  // --------------------------------------------------------------------------

  SYNO.SDS.DarkMode.Charts = (function () {
    const P = SYNO.SDS.DarkMode.Palette;
    const ORIGINAL = "__dsmDarkOriginal";
    const TEXT_KEYS = /^(textStyle|axisLabel|label|title|subtextStyle|legend|nameTextStyle|axisPointer)$/;
    const BORDER_KEYS = /^(axisLine|splitLine|axisTick|minorSplitLine|lineStyle)$/;
    const DEFAULT_TEXT = "#333";  // ECharts 4 text and axis label color
    let dark = false;

    // Colors ECharts derives itself (axis labels take the axis line color,
    // other text the theme color) are made explicit: dark mode can then set
    // them, and null hands them back to ECharts in light mode.
    function withDefaults(key, value) {
      const axis = a => (a && typeof a === "object" ? Object.assign({}, a, {
        axisLabel: Object.assign({ color: null }, a.axisLabel),
        nameTextStyle: Object.assign({ color: null }, a.nameTextStyle)
      }) : a);
      if (key === "xAxis" || key === "yAxis") return Array.isArray(value) ? value.map(axis) : axis(value);
      if (key === "textStyle") return Object.assign({ color: null }, value);
      return value;
    }

    function explicit(option) {
      const out = Object.assign({}, option);
      for (const key of ["xAxis", "yAxis", "textStyle"]) {
        if (key in out) out[key] = withDefaults(key, out[key]);
      }
      return out;
    }

    function roleFor(key, path) {
      if (!/color$/i.test(key)) return null;
      if (key === "backgroundColor") return "bg";
      if (key === "borderColor" || key === "shadowColor") return "border";
      if (path.some(p => TEXT_KEYS.test(p))) return "text";
      if (path.some(p => BORDER_KEYS.test(p))) return "border";
      return null;  // e.g. the top level series palette
    }

    // Returns a copy of an option object with dark colors. Series and data
    // colors stay: they carry meaning and work on dark backgrounds.
    function darken(value, path, key) {
      if (path[0] === "series") return value;
      if (Array.isArray(value)) return value.map(v => darken(v, path, key));
      if (typeof value === "string") {
        const role = roleFor(key || "", path);
        return role ? P.transform(value, role) : value;
      }
      if (value === null && roleFor(key || "", path) === "text") return P.transform(DEFAULT_TEXT, "text");
      if (!value || typeof value !== "object") return value;
      const out = {};
      for (const k of Object.keys(value)) out[k] = darken(value[k], path.concat(k), k);
      return out;
    }

    // Colors the chart itself set (or got from DSM) before it was darkened, so
    // switching back to light restores them.
    function remember(chart, option) {
      const keep = chart[ORIGINAL] || (chart[ORIGINAL] = {});
      for (const key of ["backgroundColor", "grid", "xAxis", "yAxis", "textStyle", "legend", "title", "tooltip"]) {
        if (option && key in option) keep[key] = withDefaults(key, option[key]);
      }
    }

    function patch(chart) {
      if (!chart || chart.__dsmDarkPatched) return;
      chart.__dsmDarkPatched = true;
      const setOption = chart.setOption;
      chart.setOption = function (option) {
        remember(chart, option);
        const args = Array.prototype.slice.call(arguments);
        if (dark && option && typeof option === "object") args[0] = darken(explicit(option), [], "");
        return setOption.apply(chart, args);
      };
      if (!chart[ORIGINAL]) {
        const current = chart.getOption && chart.getOption();
        if (current) remember(chart, current);
      }
      // General text color as well, even when the chart never set textStyle.
      if (chart[ORIGINAL] && !chart[ORIGINAL].textStyle) chart[ORIGINAL].textStyle = { color: null };
      apply(chart);
    }

    function apply(chart) {
      const original = chart[ORIGINAL];
      if (!original || chart.isDisposed && chart.isDisposed()) return;
      chart.setOption(original);  // goes through the patched setOption
    }

    function each(fn) {
      if (!window.echarts) return;
      document.querySelectorAll("[_echarts_instance_]").forEach(el => {
        const chart = echarts.getInstanceByDom(el);
        if (chart) fn(chart);
      });
    }

    function hookInit() {
      if (!window.echarts || echarts.__dsmDarkHooked) return;
      echarts.__dsmDarkHooked = true;
      const init = echarts.init;
      echarts.init = function () {
        const chart = init.apply(this, arguments);
        patch(chart);
        return chart;
      };
    }

    return {
      setDark(value) {
        dark = value;
        hookInit();
        each(chart => { patch(chart); apply(chart); });
      }
    };
  })();

  // --------------------------------------------------------------------------
  // Runtime styles: apps such as Container Manager insert their CSS as <style>
  // elements from JavaScript when they open. That CSS is not on the NAS as a
  // file, so the generator cannot see it. The same dark copies are made here,
  // from the rules the browser parsed (same roles, palette and boost as
  // darkgen.py).
  // --------------------------------------------------------------------------

  SYNO.SDS.DarkMode.RuntimeStyles = (function () {
    const P = SYNO.SDS.DarkMode.Palette;
    const BOOST = ":not(#dsmdark)";
    const ROLES = {
      "color": "text", "caret-color": "text", "column-rule-color": "text", "text-decoration-color": "text",
      "-webkit-text-fill-color": "text", "fill": "text", "stroke": "text",
      "background-color": "bg", "background-image": "bg",
      "border-top-color": "border", "border-right-color": "border", "border-bottom-color": "border",
      "border-left-color": "border", "outline-color": "border",
      "box-shadow": "shadow", "text-shadow": "shadow"
    };
    // Shorthands that hold the value when it uses a variable (the longhands
    // are empty in the CSSOM then).
    const SHORTHANDS = {
      "background-color": ["background"], "background-image": ["background"],
      "border-top-color": ["border-top", "border-color", "border"], "border-right-color": ["border-right", "border-color", "border"],
      "border-bottom-color": ["border-bottom", "border-color", "border"], "border-left-color": ["border-left", "border-color", "border"],
      "outline-color": ["outline"]
    };
    const COLOR = /#[0-9a-f]{3,8}\b|(?:rgba?|hsla?)\([^()]*\)|\b(?:white|black|gray|grey|silver|whitesmoke|gainsboro|lightgray|lightgrey|darkgray|darkgrey|dimgray|dimgrey|snow|ivory|aliceblue|ghostwhite)\b/gi;
    const PSEUDO_ELEMENT = /^:(?::|(?:before|after|first-line|first-letter|selection|-moz-selection|-moz-placeholder|-ms-input-placeholder|-webkit-input-placeholder)\b)/i;
    const converted = new WeakMap();  // <style> element -> [css text, dark rules]
    let own = null;
    let media = "not all";
    let rootVars = null;
    let timer = null;

    function customRole(name) {
      const n = name.toLowerCase().split("__")[0];
      if (n.indexOf("shadow") >= 0) return "shadow";
      if (/bkg|(?:^|[^a-z])bg|background/.test(n)) return "bg";
      if (/border|outline|divider|split|separator|stroke/.test(n)) return "border";
      return "text";
    }

    // Light values of DSM's global variables (from the original stylesheets,
    // not computed: in dark mode those are already dark).
    function originalRootVars() {
      if (rootVars) return rootVars;
      rootVars = {};
      for (const sheet of document.styleSheets) {
        if (!sheet.href || sheet.href.indexOf(SYNO.SDS.DarkMode.BASE) >= 0) continue;
        let rules;
        try { rules = sheet.cssRules; } catch (e) { continue; }
        for (const rule of rules) {
          if (rule.type !== CSSRule.STYLE_RULE || !/^(:root|html)$/.test(rule.selectorText.trim())) continue;
          for (let i = 0; i < rule.style.length; i++) {
            const name = rule.style[i];
            if (name.startsWith("--")) rootVars[name] = rule.style.getPropertyValue(name).trim();
          }
        }
      }
      return rootVars;
    }

    function resolveVar(name, seen) {
      const vars = originalRootVars();
      if (!(name in vars) || seen.indexOf(name) >= 0) return null;
      const value = vars[name];
      const m = value.match(/^var\(\s*(--[\w-]+)\s*\)$/);
      if (m) return resolveVar(m[1], seen.concat(name));
      COLOR.lastIndex = 0;
      return COLOR.test(value) && value.replace(COLOR, "").trim() === "" ? value : null;
    }

    function darken(value, role) {
      value = value.replace(/var\(\s*(--[\w-]+)\s*(?:,[^()]*)?\)/g, (m, name) => resolveVar(name, []) || m);
      return value.split(/(url\([^)]*\))/i).map(part => (/^url\(/i.test(part) ? part
        : part.replace(COLOR, c => P.transform(c, role)))).join("");
    }

    function splitTop(text) {
      const parts = [];
      let depth = 0, start = 0, quote = null;
      for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (quote) { if (c === quote) quote = null; continue; }
        if (c === '"' || c === "'") quote = c;
        else if (c === "(" || c === "[") depth++;
        else if (c === ")" || c === "]") depth--;
        else if (c === "," && depth === 0) { parts.push(text.slice(start, i)); start = i + 1; }
      }
      parts.push(text.slice(start));
      return parts.map(p => p.trim()).filter(Boolean);
    }

    // Inserts the boost into the subject compound, before a pseudo-element.
    function boost(selector) {
      let depth = 0, last = 0, quote = null;
      for (let i = 0; i < selector.length; i++) {
        const c = selector[i];
        if (quote) { if (c === quote) quote = null; continue; }
        if (c === '"' || c === "'") quote = c;
        else if (c === "(" || c === "[") depth++;
        else if (c === ")" || c === "]") depth--;
        else if (depth === 0 && /[\s>+~]/.test(c)) last = i + 1;
      }
      const compound = selector.slice(last);
      let cut = compound.length;
      depth = 0;
      for (let i = 0; i < compound.length; i++) {
        const c = compound[i];
        if (c === "(" || c === "[") depth++;
        else if (c === ")" || c === "]") depth--;
        else if (depth === 0 && c === ":" && PSEUDO_ELEMENT.test(compound.slice(i))) { cut = i; break; }
      }
      return selector.slice(0, last) + compound.slice(0, cut) + BOOST + compound.slice(cut);
    }

    function convertRules(rules, out) {
      for (const rule of rules) {
        if (rule.type === CSSRule.STYLE_RULE) {
          const st = rule.style;
          const decls = [];
          const shorthands = {};
          for (let i = 0; i < st.length; i++) {
            const prop = st[i];
            const custom = prop.startsWith("--");
            const role = custom ? customRole(prop) : ROLES[prop];
            if (!role) continue;
            let name = prop;
            let value = st.getPropertyValue(prop).trim();
            if (!value && SHORTHANDS[prop]) {
              name = SHORTHANDS[prop].find(s => st.getPropertyValue(s).trim()) || prop;
              if (shorthands[name]) continue;
              shorthands[name] = true;
              value = st.getPropertyValue(name).trim();
            }
            if (!value) continue;
            COLOR.lastIndex = 0;
            if (custom && !COLOR.test(value) && !/var\(/.test(value)) continue;
            const priority = st.getPropertyPriority(name) ? " !important" : "";
            decls.push(name + ":" + darken(value, role) + priority);
          }
          if (decls.length) out.push(splitTop(rule.selectorText).map(boost).join(",") + "{" + decls.join(";") + "}");
        } else if (rule.cssRules && (rule.type === CSSRule.MEDIA_RULE || rule.type === CSSRule.SUPPORTS_RULE)) {
          const inner = [];
          convertRules(rule.cssRules, inner);
          if (inner.length) {
            const head = rule.type === CSSRule.MEDIA_RULE ? "@media " + rule.media.mediaText : "@supports " + rule.conditionText;
            out.push(head + "{" + inner.join("") + "}");
          }
        }
      }
    }

    function rebuild() {
      timer = null;
      const chunks = [];
      for (const el of document.querySelectorAll("style")) {
        if (el === own || !el.sheet) continue;
        const text = el.textContent;
        let entry = converted.get(el);
        if (!entry || entry[0] !== text) {
          const out = [];
          try { convertRules(el.sheet.cssRules, out); } catch (e) { /* unreadable sheet */ }
          entry = [text, out.join("\n")];
          converted.set(el, entry);
        }
        if (entry[1]) chunks.push(entry[1]);
      }
      const css = chunks.length ? "@media " + media + "{\n" + chunks.join("\n") + "\n}" : "";
      if (own.textContent !== css) own.textContent = css;
    }

    function schedule() {
      if (!timer) timer = setTimeout(rebuild, 250);
    }

    return {
      start() {
        if (own) return;
        own = document.createElement("style");
        own.id = "dsm-dark-runtime";
        document.head.appendChild(own);
        new MutationObserver(records => {
          for (const r of records) {
            const nodes = [r.target].concat(Array.from(r.addedNodes), Array.from(r.removedNodes));
            if (nodes.some(n => n !== own && (n.nodeName === "STYLE" || (n.parentNode && n.parentNode.nodeName === "STYLE" && n.parentNode !== own)))) {
              schedule();
              return;
            }
          }
        }).observe(document.head, { childList: true, subtree: true, characterData: true });
        rebuild();
      },
      // Same condition as the dark block of the generated stylesheet.
      setMedia(text) {
        if (text === media) return;
        media = text;
        if (own) rebuild();
      }
    };
  })();

  // --------------------------------------------------------------------------
  // Package icons: Package Center shows the icon each package brings, drawn
  // for light pages. Icons that largely vanish on the dark surface (dark
  // shapes on a transparent background) are marked here; extra.css puts a
  // light plate behind them in dark mode, so the artwork itself stays as it is.
  // --------------------------------------------------------------------------

  SYNO.SDS.DarkMode.PackageIcons = (function () {
    const SELECTOR = "img.syno-pkg-icon-img";
    const PLATE = "dsmdark-icon-plate";
    const SIZE = 64;           // analysis resolution
    const REACH = 3;           // a pixel counts as seen when a visible one is this close
    const MIN_CONTRAST = 2.0;  // against the dark surface
    const MIN_SEEN = 0.7;      // share of the icon that has to be seen without a plate
    const TILE_FILL = 0.85;    // shapes this solid are tiles with their own background
    const verdicts = new Map();  // icon URL without the session token -> Promise<boolean>
    let surface = null;
    let timer = null;
    let started = false;

    const lin = c => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
    const luminance = (r, g, b) => 0.2126 * lin(r / 255) + 0.7152 * lin(g / 255) + 0.0722 * lin(b / 255);

    // Luminance of the dark surface that replaces DSM's white pages.
    function surfaceLuminance() {
      if (surface === null) {
        const hex = SYNO.SDS.DarkMode.Palette.transform("#ffffff", "bg").slice(1);
        surface = luminance(parseInt(hex.substr(0, 2), 16), parseInt(hex.substr(2, 2), 16), parseInt(hex.substr(4, 2), 16));
      }
      return surface;
    }

    async function needsPlate(url) {
      const img = new Image();
      img.src = url;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = SIZE;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, SIZE, SIZE);
      const d = ctx.getImageData(0, 0, SIZE, SIZE).data;
      const Ls = surfaceLuminance();
      const visible = new Uint8Array(SIZE * SIZE);
      let solid = 0, x0 = SIZE, x1 = -1, y0 = SIZE, y1 = -1;
      for (let k = 0; k < SIZE * SIZE; k++) {
        if (d[k * 4 + 3] < 128) continue;
        const x = k % SIZE, y = (k - x) / SIZE;
        solid++;
        x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
        const L = luminance(d[k * 4], d[k * 4 + 1], d[k * 4 + 2]);
        if ((Math.max(L, Ls) + 0.05) / (Math.min(L, Ls) + 0.05) >= MIN_CONTRAST) visible[k] = 1;
      }
      // A (rounded) square tile is a background of its own, also when dark.
      if (!solid || solid >= TILE_FILL * (x1 - x0 + 1) * (y1 - y0 + 1)) return false;
      // Dark outlines and dark details next to visible parts still read well;
      // what has no visible pixel nearby is lost.
      const seen = new Uint8Array(SIZE * SIZE);
      for (let y = 0; y < SIZE; y++) {
        for (let x = 0; x < SIZE; x++) {
          if (!visible[y * SIZE + x]) continue;
          for (let j = Math.max(0, y - REACH); j <= Math.min(SIZE - 1, y + REACH); j++) {
            seen.fill(1, j * SIZE + Math.max(0, x - REACH), j * SIZE + Math.min(SIZE, x + REACH + 1));
          }
        }
      }
      // A visible outline keeps the shape readable however dark the inside is.
      const solidAt = (x, y) => x >= 0 && y >= 0 && x < SIZE && y < SIZE && d[(y * SIZE + x) * 4 + 3] >= 128;
      let weight = 0, shown = 0, edge = 0, edgeShown = 0;
      for (let k = 0; k < SIZE * SIZE; k++) {
        const a = d[k * 4 + 3] / 255;
        weight += a;
        if (seen[k]) shown += a;
        if (a < 0.5) continue;
        const x = k % SIZE, y = (k - x) / SIZE;
        if (solidAt(x - 1, y) && solidAt(x + 1, y) && solidAt(x, y - 1) && solidAt(x, y + 1)) continue;
        edge++;
        if (seen[k]) edgeShown++;
      }
      return shown / weight < MIN_SEEN && edgeShown / edge < MIN_SEEN;
    }

    function verdict(key, url) {
      if (!verdicts.has(key)) {
        // Unreadable images (other origin, broken) keep their look.
        verdicts.set(key, needsPlate(url).catch(() => false));
      }
      return verdicts.get(key);
    }

    function scan() {
      timer = null;
      for (const el of document.querySelectorAll(SELECTOR)) {
        const m = (el.style.backgroundImage || "").match(/url\(["']?([^"')]+)["']?\)/);
        if (!m) continue;
        const key = m[1].replace(/([?&])SynoToken=[^&]*&?/, "$1");
        if (el.dataset.dsmdarkIcon === key) continue;
        el.dataset.dsmdarkIcon = key;
        el.classList.remove(PLATE);
        verdict(key, m[1]).then(plate => {
          if (el.dataset.dsmdarkIcon === key) el.classList.toggle(PLATE, plate);
        });
      }
    }

    function schedule() {
      if (!timer) timer = setTimeout(scan, 200);
    }

    return {
      start() {
        if (started) return;
        started = true;
        new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });
        scan();
      }
    };
  })();

  // --------------------------------------------------------------------------
  // Theme: user choice, stylesheet switch and stylesheet freshness
  // --------------------------------------------------------------------------

  SYNO.SDS.DarkMode.Theme = (function () {
    const DM = SYNO.SDS.DarkMode;
    const MODES = ["auto", "light", "dark"];
    const media = window.matchMedia ? window.matchMedia(DM.AUTO_MEDIA) : null;
    const listeners = [];
    let mode = "auto";

    function ownLinks() {
      return Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
        .filter(l => (l.getAttribute("href") || "").indexOf(DM.BASE + "style.css") >= 0);
    }

    // DSM may insert its links again (login -> desktop): the last one counts.
    function ownSheet() {
      const links = ownLinks().filter(l => l.sheet);
      return links.length ? links[links.length - 1].sheet : null;
    }

    // The generated file has exactly one top level @media block: the dark rules.
    function darkBlock() {
      const sheet = ownSheet();
      if (!sheet) return null;
      try {
        for (const rule of sheet.cssRules) {
          if (rule.type === CSSRule.MEDIA_RULE) return rule;
        }
      } catch (e) { /* not loaded yet */ }
      return null;
    }

    // The dark blocks of every loaded copy: after login DSM inserts its links
    // again, and an older copy with the original condition would keep the page
    // dark although the user chose "Light".
    function darkBlocks() {
      const blocks = [];
      for (const link of ownLinks()) {
        try {
          for (const rule of link.sheet ? link.sheet.cssRules : []) {
            if (rule.type === CSSRule.MEDIA_RULE) {
              blocks.push(rule);
              break;
            }
          }
        } catch (e) { /* not loaded yet */ }
      }
      return blocks;
    }

    // Build signature written by the generator into the dark block.
    function loadedSignature() {
      const block = darkBlock();
      if (!block) return "";
      for (const rule of block.cssRules) {
        const value = rule.style && rule.style.getPropertyValue("--dsm-dark-signature");
        if (value) return value.trim();
      }
      return "";
    }

    function isDark() {
      return mode === "dark" || (mode === "auto" && !!media && media.matches);
    }

    // True once the stylesheet built on the NAS is loaded (the placeholder
    // shipped with the package has no signature).
    function ready() {
      return loadedSignature() !== "";
    }

    // Build state on the NAS: "running", "ok", "failed" or "unknown".
    async function buildState() {
      try {
        const res = await fetch(DM.BASE + "status.json?_=" + Date.now(), { credentials: "same-origin" });
        const info = await res.json();
        // A build that was killed (package update) leaves "running" behind.
        if (info.state === "running" && Date.now() / 1000 - info.time > 30 * 60) return "failed";
        return info.state || "unknown";
      } catch (e) {
        return "unknown";
      }
    }

    function apply() {
      const text = mode === "dark" ? "all" : mode === "light" ? "not all" : DM.AUTO_MEDIA;
      for (const block of darkBlocks()) {
        if (block.media.mediaText !== text) block.media.mediaText = text;
      }
      // Runtime styles only while the generated stylesheet is there as well.
      DM.RuntimeStyles.setMedia(ready() ? text : "not all");
      // Charts and the page attribute follow the stylesheet: while the NAS is
      // still building it, everything stays light.
      const dark = isDark() && ready();
      document.documentElement.setAttribute("data-dsm-theme", dark ? "dark" : "light");
      DM.Charts.setDark(dark);
      listeners.forEach(fn => { try { fn(dark, mode); } catch (e) { /* ignore */ } });
    }

    function setMode(next, save) {
      mode = MODES.indexOf(next) >= 0 ? next : "auto";
      apply();
      if (save) {
        SYNO.SDS.UserSettings.setProperty(DM.APP, "mode", mode);
        SYNO.SDS.UserSettings.syncSave && SYNO.SDS.UserSettings.syncSave();
      }
    }

    // Stylesheets the desktop loaded, as paths relative to the DSM web root.
    function loadedSheets() {
      const list = [];
      for (const link of document.querySelectorAll('link[rel="stylesheet"][href]')) {
        const href = link.getAttribute("href").replace(/^[a-z]+:\/\/[^/]+/i, "").replace(/^(\.?\/)+/, "");
        if (href.indexOf(DM.BASE) !== 0) list.push(href);
      }
      return list;
    }

    async function checkFresh() {
      let manifest;
      try {
        const res = await fetch(DM.BASE + "manifest.json?_=" + Date.now(), { credentials: "same-origin" });
        if (!res.ok) return;
        manifest = await res.json();
      } catch (e) { return; }
      // DSM links style.css with a version parameter from its own cache, which
      // does not change when the NAS rebuilds the file: browsers may keep an
      // older build. Swap it for the current one.
      if (manifest.signature && manifest.signature !== loadedSignature()) {
        reloadSheet(manifest.signature);
      }
      const known = new Set((manifest.hrefs || []).map(h => h.replace(/^(\.?\/)+/, "")));
      const missing = loadedSheets().filter(h => !known.has(h));
      // The NAS rebuilds when a stylesheet is new (new URL) or changed on disk
      // under the same URL; it answers quickly when everything is current.
      let answer;
      try {
        const res = await fetch(DM.BASE + "regen.cgi", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-DSM-Dark": "1", "X-SYNO-TOKEN": SYNO.SDS.Session.SynoToken || "" },
          // "all" lets the NAS build even when it cannot fetch DSM's start page.
          body: JSON.stringify({ sheets: missing, all: loadedSheets() })
        });
        answer = await res.json();
      } catch (e) { return; }
      if ((answer && answer.started) || !ready()) waitForRebuild(manifest.signature, 0);
    }

    // Polls for a new build. The first build on a slow NAS can take minutes.
    function waitForRebuild(oldSignature, attempt) {
      if (attempt > 360) return;
      setTimeout(async () => {
        try {
          const res = await fetch(DM.BASE + "manifest.json?_=" + Date.now(), { credentials: "same-origin" });
          const manifest = await res.json();
          if (manifest.signature !== oldSignature) {
            reloadSheet(manifest.signature);
            return;
          }
        } catch (e) { /* try again */ }
        waitForRebuild(oldSignature, attempt + 1);
      }, 5000);
    }

    function reloadSheet(version) {
      const links = ownLinks();
      if (!links.length) return;
      const last = links[links.length - 1];
      const href = DM.BASE + "style.css?v=" + encodeURIComponent(version);
      if (last.getAttribute("href") === href) return;
      const link = last.cloneNode();
      link.href = href;
      link.onload = () => {
        ownLinks().forEach(l => { if (l !== link) l.remove(); });
        apply();
      };
      last.parentNode.insertBefore(link, last.nextSibling);
    }

    return {
      MODES: MODES,
      init() {
        DM.RuntimeStyles.start();
        DM.PackageIcons.start();
        setMode(SYNO.SDS.UserSettings.getProperty(DM.APP, "mode") || "auto", false);
        if (media) {
          const onChange = () => { if (mode === "auto") apply(); };
          media.addEventListener ? media.addEventListener("change", onChange) : media.addListener(onChange);
        }
        // A copy of the stylesheet DSM inserts later starts with the original
        // condition: give it the user's choice once it has loaded.
        new MutationObserver(records => {
          for (const record of records) {
            for (const node of record.addedNodes) {
              if (node.tagName === "LINK" && ownLinks().indexOf(node) >= 0) {
                node.addEventListener("load", apply, { once: true });
              }
            }
          }
        }).observe(document.head, { childList: true });
        checkFresh();
      },
      getMode: () => mode,
      setMode: next => setMode(next, true),
      isDark: () => isDark() && ready(),
      ready: ready,
      buildState: buildState,
      onChange: fn => listeners.push(fn)
    };
  })();

  // --------------------------------------------------------------------------
  // App instance and taskbar tray
  // --------------------------------------------------------------------------

  // Called by SYNO.SDS.DarkMode.Instance (DarkMode.js) once this file is loaded.
  SYNO.SDS.DarkMode.start = function (instance, config) {
    // One tray per page, also when DSM starts the app a second time or an older
    // loader from the browser cache let DSM drop the first instance.
    if (SYNO.SDS.DarkMode.tray || instance.trayItem) return;
    // DSM attaches the "config" entry of a class to its prototype when it loads
    // the file that declares the class (DarkMode.js). The tray class is defined
    // here, later, so it gets its entry the same way.
    const entry = SYNO.SDS.Config.FnMap["SYNO.SDS.DarkMode.Tray"];
    if (entry && !SYNO.SDS.DarkMode.Tray.prototype.jsConfig) {
      SYNO.SDS.DarkMode.Tray.prototype.jsConfig = entry.config;
    }
    SYNO.SDS.DarkMode.Theme.init();
    // A single object: DSM calls instance.trayItem.open() when the app is
    // started again.
    instance.trayItem = new SYNO.SDS.DarkMode.Tray({ appInstance: instance });
    instance.addInstance(instance.trayItem);
    instance.trayItem.open(config);
    SYNO.SDS.DarkMode.tray = instance.trayItem;
  };

  Ext.define("SYNO.SDS.DarkMode.Tray", {
    extend: "SYNO.SDS.Tray.ArrowTray",
    initPanel: function () {
      return new SYNO.SDS.DarkMode.Panel({ module: this });
    },
    onButtonReady: function (button) {
      button.show();
      const update = dark => button.setIconClass("sds-tray-item-darkmode " + (dark ? "is-dark" : "is-light"));
      update(SYNO.SDS.DarkMode.Theme.isDark());
      SYNO.SDS.DarkMode.Theme.onChange(update);
    }
  });

  Ext.define("SYNO.SDS.DarkMode.Panel", {
    extend: "SYNO.SDS.Tray.Panel",
    constructor: function (config) {
      const T = (sec, key) => _TT(SYNO.SDS.DarkMode.APP, sec, key);
      const current = SYNO.SDS.DarkMode.Theme.getMode();
      this.radios = SYNO.SDS.DarkMode.Theme.MODES.map(value => new SYNO.ux.Radio({
        name: "dsm-dark-mode",
        inputValue: value,
        boxLabel: T("mode", value),
        checked: value === current,
        listeners: {
          check: (radio, checked) => { if (checked) SYNO.SDS.DarkMode.Theme.setMode(value); }
        }
      }));
      this.callParent([Ext.apply({
        title: T("app", "title"),
        cls: "sds-darkmode-panel",
        width: 260,
        autoHeight: true,
        padding: "8px 16px 12px",
        items: [{ xtype: "syno_displayfield", value: T("panel", "desc"), cls: "sds-darkmode-desc" }]
          .concat(this.radios, [this.status = new SYNO.ux.DisplayField({ hidden: true, cls: "sds-darkmode-status" })])
      }, config)]);
      this.on("beforeshow", this.refreshStatus, this);
      SYNO.SDS.DarkMode.Theme.onChange(() => this.refreshStatus());
    },

    // Explains why DSM stays light while the stylesheet is missing.
    refreshStatus: async function () {
      const Theme = SYNO.SDS.DarkMode.Theme;
      if (Theme.ready()) {
        this.status.hide();
        return;
      }
      const state = await Theme.buildState();
      if (Theme.ready()) return;
      const key = state === "failed" ? "failed" : "preparing";
      const pkg = SYNO.SDS.DarkMode.BASE.replace(/\/$/, "").split("/").pop();
      this.status.setValue(String.format(_TT(SYNO.SDS.DarkMode.APP, "panel", key), "/var/packages/" + pkg + "/var/regen.log"));
      this.status.show();
      if (this.rendered) this.doLayout();
    }
  });
})();
