// Dark Mode for DSM: loader started by DSM after login (autoLaunch).
//
// DSM requests this file with its own build number as version parameter
// ("?v=90080-s0"), so browsers keep it cached until the next DSM update, even
// across package updates. It therefore only loads the actual code,
// DarkMode.core.js, under a URL that changes with every package build
// (build.json is never cached). Keep this file small and stable.
Ext.namespace("SYNO.SDS.DarkMode");

SYNO.SDS.DarkMode.BASE = "webman/3rdparty/DarkMode/";

Ext.define("SYNO.SDS.DarkMode.Instance", {
  extend: "SYNO.SDS.AppInstance",
  initInstance: function (config) {
    if (this.loading || this.trayItem) return;
    this.loading = true;
    const base = SYNO.SDS.DarkMode.BASE;
    const finish = () => {
      this.loading = false;
      this.checkAlive();
    };
    fetch(base + "build.json?_=" + Date.now(), { credentials: "same-origin", cache: "no-store" })
      .then(res => res.json())
      .catch(() => ({ build: String(Date.now()) }))
      .then(info => {
        const script = document.createElement("script");
        script.src = base + "DarkMode.core.js?v=" + encodeURIComponent(info.build);
        script.onload = () => {
          SYNO.SDS.DarkMode.start(this, config);
          finish();
        };
        script.onerror = finish;
        document.head.appendChild(script);
      });
  },
  // DSM destroys an app instance without sub-instances right after
  // initInstance. The tray (the sub-instance) is only added once
  // DarkMode.core.js has loaded, so stay alive until then.
  checkAlive: function () {
    if (!this.loading) {
      SYNO.SDS.DarkMode.Instance.superclass.checkAlive.apply(this, arguments);
    }
  }
});
