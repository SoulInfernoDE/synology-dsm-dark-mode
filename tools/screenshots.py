#!/usr/bin/env python3
"""Take README screenshots of DSM with Dark Mode, in English and German.

Drives a headless Firefox through its built-in Marionette protocol (JSON over
TCP), so nothing has to be installed besides Firefox. Signs in through the DSM
Web API, opens the views and writes PNG files.

  DSM_USER=... DSM_PASS=... python3 tools/screenshots.py \
      --url http://127.0.0.1:26000 --out docs/screenshots
"""

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

PORT = 28282
WIDTH, HEIGHT = 1440, 900


class Marionette:
    def __init__(self, port):
        deadline = time.time() + 30
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=120)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.3)
        self.buf = b""
        self.msg_id = 0
        self._read()  # handshake

    def _read(self):
        while b":" not in self.buf:
            self.buf += self.sock.recv(65536)
        length, _, rest = self.buf.partition(b":")
        length = int(length)
        while len(rest) < length:
            rest += self.sock.recv(65536)
        self.buf = rest[length:]
        return json.loads(rest[:length])

    def call(self, name, params=None):
        self.msg_id += 1
        data = json.dumps([0, self.msg_id, name, params or {}]).encode()
        self.sock.sendall(str(len(data)).encode() + b":" + data)
        while True:
            msg = self._read()
            if msg[0] == 1 and msg[1] == self.msg_id:
                if msg[2]:
                    raise RuntimeError("%s: %s" % (name, msg[2].get("message", msg[2])))
                return msg[3]

    def js(self, script, *args):
        return self.call("WebDriver:ExecuteScript", {"script": script, "args": list(args)}).get("value")

    def js_async(self, script, *args, timeout=60000):
        self.call("WebDriver:SetTimeouts", {"script": timeout})
        return self.call("WebDriver:ExecuteAsyncScript", {"script": script, "args": list(args)}).get("value")

    def screenshot(self, path, clip=None):
        params = {"full": False}
        data = base64.b64decode(self.call("WebDriver:TakeScreenshot", params)["value"])
        with open(path, "wb") as f:
            f.write(data)
        if clip:
            x, y, w, h = clip
            subprocess.run(["convert", path, "-crop", "%dx%d+%d+%d" % (w, h, x, y), "+repage", path], check=True)


def login(base, user, password):
    data = urllib.parse.urlencode({
        "api": "SYNO.API.Auth", "version": "6", "method": "login", "account": user,
        "passwd": password, "session": "webui", "format": "cookie", "enable_syno_token": "yes",
    }).encode()
    with urllib.request.urlopen(base + "/webapi/entry.cgi", data, timeout=30) as res:
        body = json.loads(res.read())
    if not body.get("success"):
        raise RuntimeError("DSM login failed: %s" % body)
    return body["data"]["sid"]


def start_firefox(lang):
    profile = tempfile.mkdtemp(prefix="dsm-shots-")
    prefs = {
        "marionette.port": PORT,
        "intl.accept_languages": lang,
        "intl.locale.requested": lang.split(",")[0],
        "layout.css.prefers-color-scheme.content-override": 0,  # 0 = dark
        "ui.systemUsesDarkTheme": 1,
        "layout.css.devPixelsPerPx": "1.0",
        "browser.shell.checkDefaultBrowser": False,
        "datareporting.policy.dataSubmissionEnabled": False,
        "toolkit.telemetry.reportingpolicy.firstRun": False,
    }
    with open(os.path.join(profile, "user.js"), "w") as f:
        for k, v in prefs.items():
            f.write("user_pref(%s, %s);\n" % (json.dumps(k), json.dumps(v)))
    proc = subprocess.Popen(
        ["firefox", "--headless", "--marionette", "--no-remote", "--profile", profile,
         "--window-size=%d,%d" % (WIDTH, HEIGHT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, profile


# Runs in the page: wait until the desktop and Dark Mode are ready, close
# first-run prompts and toasts.
PREPARE = """
const done = arguments[arguments.length - 1];
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const t0 = Date.now();
  while (!(window.SYNO && SYNO.SDS && SYNO.SDS.DarkMode && SYNO.SDS.DarkMode.Theme
           && document.querySelector('.sds-tray-item-darkmode')) && Date.now() - t0 < 45000) await sleep(500);
  await sleep(2500);
  document.querySelectorAll('.v-notification-container').forEach(e => e.style.display = 'none');
  for (const w of document.querySelectorAll('.v-message-box-window')) {
    const b = [...w.querySelectorAll('button')].find(x => /Nein|No thanks|Später|later/i.test(x.textContent));
    if (b) b.click();
  }
  done({ dark: document.documentElement.dataset.dsmTheme, lang: _S('lang') });
})();
"""

# Opens an app, waits, and gives its window a fixed size and position.
OPEN = """
const [app, fn, x, y, w, h, done] = arguments;
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  SYNO.SDS.AppLaunch(app, fn ? { fn: fn } : {});
  await sleep(4500);
  const inst = SYNO.SDS.AppMgr.getByAppName(app)[0];
  const win = inst && inst.window;
  if (win) { win.setSize(w, h); win.setPosition(x, y); }
  await sleep(1500);
  done(!!win);
})();
"""

CLOSE_ALL = """
SYNO.SDS.AppMgr.each(inst => { try { if (inst.window) inst.window.close(); } catch (e) {} });
return true;
"""

# Shows or hides DSM's widget panel with its own taskbar button.
TOGGLE_WIDGETS = """
const [show] = arguments;
const btn = document.querySelector('.tray-item.widget-button');
if (btn && btn.classList.contains('pressed') !== show) btn.click();
return true;
"""

OPEN_TRAY = """
const done = arguments[arguments.length - 1];
const tray = SYNO.SDS.DarkMode.tray;
if (!tray.panel.isVisible()) tray.onClick();
setTimeout(() => {
  const p = tray.panel.el.dom.getBoundingClientRect();
  const b = document.querySelector('.sds-tray-item-darkmode').getBoundingClientRect();
  done([p.left, p.top, p.width, p.height, b.left, b.top]);
}, 800);
"""


def network_load(base, stop):
    """Download a large DSM script repeatedly (traffic for the charts)."""
    url = base + "/scripts/syno-vue-components/syno-vue-components.min.js"
    while not stop.is_set():
        try:
            with urllib.request.urlopen(url + "?_=%f" % time.time(), timeout=10) as res:
                while res.read(1 << 20):
                    pass
        except OSError:
            time.sleep(1)


def shoot(base, sid, lang, suffix, out):
    proc, profile = start_firefox(lang)
    try:
        m = Marionette(PORT)
        m.call("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {"acceptInsecureCerts": True}}})
        m.call("WebDriver:SetWindowRect", {"width": WIDTH, "height": HEIGHT})
        m.call("WebDriver:Navigate", {"url": base + "/"})
        host = urllib.parse.urlparse(base).hostname
        m.call("WebDriver:AddCookie", {"cookie": {"name": "id", "value": sid, "path": "/", "domain": host}})
        m.call("WebDriver:Navigate", {"url": base + "/"})
        info = m.js_async(PREPARE)
        print("desktop ready:", info)

        # Control Panel with the user list; the widgets stay visible on the right.
        m.js(CLOSE_ALL)
        m.js_async(OPEN, "SYNO.SDS.AdminCenter.Application", "SYNO.SDS.AdminCenter.User.Main", 130, 70, 930, 600)
        m.screenshot(os.path.join(out, "desktop-%s.png" % suffix))

        # Resource Monitor with some network load, so the charts show curves.
        m.js(CLOSE_ALL)
        m.js(TOGGLE_WIDGETS, False)
        stop = threading.Event()
        load = threading.Thread(target=network_load, args=(base, stop), daemon=True)
        load.start()
        m.js_async(OPEN, "SYNO.SDS.ResourceMonitor.Instance", None, 130, 70, 1180, 700)
        time.sleep(40)
        m.screenshot(os.path.join(out, "resource-monitor-%s.png" % suffix))
        stop.set()
        m.js(TOGGLE_WIDGETS, True)

        # Appearance menu in the taskbar (cropped).
        m.js(CLOSE_ALL)
        time.sleep(1.5)
        px, py, pw, ph, bx, by = m.js_async(OPEN_TRAY)
        left = int(min(px, bx) - 24)
        top = 0
        right = int(max(px + pw, bx + 40) + 24)
        bottom = int(py + ph + 24)
        m.screenshot(os.path.join(out, "appearance-menu-%s.png" % suffix),
                     clip=(max(0, left), top, min(WIDTH, right) - max(0, left), bottom))
        m.call("WebDriver:DeleteSession")
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", choices=["en", "de", "both"], default="both")
    args = ap.parse_args()
    user, password = os.environ.get("DSM_USER"), os.environ.get("DSM_PASS")
    if not user or not password:
        sys.exit("DSM_USER and DSM_PASS are required")
    os.makedirs(args.out, exist_ok=True)
    langs = {"en": ("en-US, en", "en"), "de": ("de-DE, de", "de")}
    for key in (["en", "de"] if args.lang == "both" else [args.lang]):
        accept, suffix = langs[key]
        shoot(args.url.rstrip("/"), login(args.url.rstrip("/"), user, password), accept, suffix, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
