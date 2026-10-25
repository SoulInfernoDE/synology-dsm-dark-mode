// Dark Mode for DSM: theme switch, chart colors and the taskbar tray menu.
// Loaded by DarkMode.js (see there why the code lives in a separate file).
//
// The stylesheet (style.css next to this file) is generated on the NAS and
// holds all dark rules in one "@media (prefers-color-scheme: dark)" block, so
// the login page and the desktop follow the operating system without any
// script. This file adds the per-user choice (automatic, light, dark) by
// rewriting the condition of that block, themes ECharts charts (they paint on
// a canvas, which CSS cannot reach) and keeps the stylesheet up to date when
// DSM or packages change their stylesheets.
Ext.namespace("SYNO.SDS.DarkMode");

// Runs once per page: a second start of the app loads this file again, and
// redefining the objects would replace the running theme state.
if (!SYNO.SDS.DarkMode.start) (function () {

  SYNO.SDS.DarkMode.APP = "SYNO.SDS.DarkMode.Instance";
  SYNO.SDS.DarkMode.BASE = "webman/3rdparty/DarkMode/";
  SYNO.SDS.DarkMode.AUTO_MEDIA = "(prefers-color-scheme: dark)";

  // --------------------------------------------------------------------------
  // Color palette (same transform as src/lib/darkgen.py, kept in sync by hand)
  // --------------------------------------------------------------------------

  SYNO.SDS.DarkMode.Palette = (function () {
    const NEUTRAL_CHROMA = 0.045, SURFACE_L = 0.235, SURFACE_SPAN = 0.48;
    const TEXT_L = 0.93, TEXT_SPAN = 0.40, BORDER_L = 0.355, BORDER_SPAN = 0.45;
    const ACCENT_TEXT_MIN_L = 0.72, INVISIBLE_BORDER_L = 0.97;

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

    const cache = {};
    function transform(value, role) {
      const key = role + "|" + value;
      if (key in cache) return cache[key];
      const c = parse(value);
      let out = value;
      if (c && c[3] > 0) {
        const lch = toOklch(c[0], c[1], c[2]);
        const next = roles[role](lch[0], lch[1]);
        const rgb = fromOklch(next[0], next[1], lch[2]);
        out = c[3] >= 0.999 ? "#" + rgb.map(v => v.toString(16).padStart(2, "0")).join("")
          : "rgba(" + rgb.join(",") + "," + Math.round(c[3] * 1000) / 1000 + ")";
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
    let dark = false;

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
        if (option && key in option) keep[key] = option[key];
      }
    }

    function patch(chart) {
      if (!chart || chart.__dsmDarkPatched) return;
      chart.__dsmDarkPatched = true;
      const setOption = chart.setOption;
      chart.setOption = function (option) {
        remember(chart, option);
        const args = Array.prototype.slice.call(arguments);
        if (dark && option && typeof option === "object") args[0] = darken(option, [], "");
        return setOption.apply(chart, args);
      };
      if (!chart[ORIGINAL]) {
        const current = chart.getOption && chart.getOption();
        if (current) remember(chart, current);
      }
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
      const block = darkBlock();
      if (block) {
        const text = mode === "dark" ? "all" : mode === "light" ? "not all" : DM.AUTO_MEDIA;
        if (block.media.mediaText !== text) block.media.mediaText = text;
      }
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
        setMode(SYNO.SDS.UserSettings.getProperty(DM.APP, "mode") || "auto", false);
        if (media) {
          const onChange = () => { if (mode === "auto") apply(); };
          media.addEventListener ? media.addEventListener("change", onChange) : media.addListener(onChange);
        }
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
      this.status.setValue(_TT(SYNO.SDS.DarkMode.APP, "panel", key));
      this.status.show();
      if (this.rendered) this.doLayout();
    }
  });
})();
