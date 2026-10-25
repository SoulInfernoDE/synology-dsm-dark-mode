#!/bin/sh
# Inventory of everything DSM Dark Mode depends on, for comparing DSM versions.
#
# Run on the NAS (as an administrator, sudo for the cache directory):
#   sh dsm-inventory.sh > inventory-<version>.txt
# then diff two inventories. Sections start with "## ".

ROOT=/usr/syno/synoman
PORT="$(sed -n 's/^admin_port="\{0,1\}\([0-9]*\)"\{0,1\}$/\1/p' /etc/synoinfo.conf 2>/dev/null | head -n1)"
[ -n "$PORT" ] || PORT=5000

echo "## version"
. /etc.defaults/VERSION 2>/dev/null
echo "productversion=$productversion buildnumber=$buildnumber smallfixnumber=$smallfixnumber"

echo "## tools"
for t in python3 curl sed find setsid; do
  printf '%s=%s\n' "$t" "$(command -v "$t" >/dev/null 2>&1 && echo yes || echo no)"
done
python3 --version 2>&1

echo "## login and auth helpers"
for f in "$ROOT/webman/modules/authenticate.cgi" "$ROOT/webman/login.cgi"; do
  printf '%s=%s\n' "$f" "$([ -x "$f" ] && echo yes || echo no)"
done

echo "## stylesheets on the start page (load order, without version)"
curl -fsSkL --max-time 20 "http://127.0.0.1:${PORT}/" \
  | grep -o '<link[^>]*rel="stylesheet"[^>]*>' | grep -o 'href="[^"]*"' \
  | sed 's/href="//; s/"$//; s/?.*//'

echo "## 3rdparty style.css hook (dirs with config + style.css)"
for d in "$ROOT"/webman/3rdparty/*/; do
  [ -f "$d/config" ] && [ -f "$d/style.css" ] && basename "$d"
done

echo "## js config cache"
ls -d /var/cache/js_config_parser 2>/dev/null || echo "missing"

echo "## root css tokens (syno-vue-components)"
f="$ROOT/scripts/syno-vue-components/style/syno-vue-components.css"
if [ -f "$f" ]; then
  grep -o ':root{[^}]*}' "$f" | tr ';{' '\n\n' | grep '^--' | sort
else
  echo "missing: $f"
fi

echo "## stylesheet sizes (bytes, colors, var uses, urls)"
curl -fsSkL --max-time 20 "http://127.0.0.1:${PORT}/" \
  | grep -o '<link[^>]*rel="stylesheet"[^>]*>' | grep -o 'href="[^"]*"' \
  | sed 's/href="//; s/"$//; s/?.*//' | grep -v '3rdparty/DarkMode/' \
  | while read -r p; do
      [ -f "$ROOT/$p" ] || { echo "$p missing"; continue; }
      printf '%s %s colors=%s vars=%s urls=%s\n' "$p" "$(wc -c < "$ROOT/$p")" \
        "$(grep -oiE '#[0-9a-f]{3,8}\b|rgba?\(' "$ROOT/$p" | wc -l)" \
        "$(grep -o 'var(--' "$ROOT/$p" | wc -l)" \
        "$(grep -o 'url(' "$ROOT/$p" | wc -l)"
    done

echo "## desktop APIs used by DarkMode.js (occurrences in DSM bundles)"
for sym in "SYNO.SDS.Tray.ArrowTray" "SYNO.SDS.Tray.Panel" "SYNO.SDS.AppTrayItem" \
           "SYNO.SDS.UserSettings" "getProperty" "setProperty" "syncSave" \
           "autoLaunch" "addTray" "SYNO.ux.Radio" "_TT=" "SynoToken"; do
  n=$(cat "$ROOT"/synoSDSjslib/dist/*.js "$ROOT"/webman/sds/dist/*.js "$ROOT"/webman/desktop/dist/*.js \
        "$ROOT"/webman/taskbar/dist/*.js 2>/dev/null | grep -o "$sym" | wc -l)
  printf '%s=%s\n' "$sym" "$n"
done

echo "## echarts"
for f in $(find "$ROOT" -name '*.js' -size +100k 2>/dev/null | xargs grep -l 'echarts' 2>/dev/null | head -n 5); do
  printf '%s %s\n' "${f#$ROOT/}" "$(grep -oE 'version:"[0-9]+\.[0-9]+\.[0-9]+"|version="[0-9]+\.[0-9]+\.[0-9]+"' "$f" | head -n1)"
done

echo "## tray icon size (system tray css)"
grep -oE '\.tray-item[^{]*\{[^}]*(width|height)[^}]*\}' "$ROOT/webman/taskbar/dist/style.css" 2>/dev/null | head -n 5
