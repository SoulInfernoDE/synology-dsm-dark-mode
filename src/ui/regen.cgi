#!/bin/sh
# Freshness check and rebuild request for the dark stylesheet. DarkMode.js
# calls this once per desktop load.
#
# Accepts POST requests from logged-in DSM users that carry the header
# "X-DSM-Dark: 1" (browsers cannot add custom headers to cross-site requests,
# which protects against CSRF). The body holds the stylesheets the browser
# loaded, in load order ("all"), and those the current build does not know
# ("sheets"); only plain .css paths are kept. "all" is the fallback list when
# the package cannot fetch DSM's start page. A rebuild also starts when a
# source stylesheet changed on disk while DSM kept its URL (DSM versions module
# stylesheets with a build stamp, not the file time) and while no build exists
# yet. The rebuild runs in the background.

SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
TARGET="$(dirname "$(dirname "$SELF")")"
[ -x "$TARGET/bin/darkmode-regen" ] || TARGET="/var/packages/DarkMode/target"
# The package name differs between the GitHub and the SynoCommunity package.
PKG="$(basename "$(readlink -f "$TARGET")")"
VAR="/var/packages/${PKG}/var"
MANIFEST="$TARGET/ui/manifest.json"
AUTH_CGI="/usr/syno/synoman/webman/modules/authenticate.cgi"
LOGIN_CGI="/usr/syno/synoman/webman/login.cgi"
MIN_INTERVAL=30

respond() {
  printf 'Status: %s\r\nContent-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n\r\n%s' "$1" "$2"
  exit 0
}

[ "$REQUEST_METHOD" = "POST" ] || respond "405 Method Not Allowed" '{"ok":false}'
[ "$HTTP_X_DSM_DARK" = "1" ] || respond "403 Forbidden" '{"ok":false}'

token="${HTTP_X_SYNO_TOKEN:-}"
if [ -z "$token" ]; then
  token="$(REQUEST_METHOD=GET QUERY_STRING="" "$LOGIN_CGI" 2>/dev/null | grep -o '"SynoToken" *: *"[^"]*"' | head -n1 | sed 's/.*"\([^"]*\)"$/\1/')"
fi
user="$(REQUEST_METHOD=GET QUERY_STRING="SynoToken=${token}" HTTP_X_SYNO_TOKEN="$token" "$AUTH_CGI" 2>/dev/null | tr -d '\r\n')"
[ -n "$user" ] || respond "403 Forbidden" '{"ok":false}'

len="${CONTENT_LENGTH:-0}"
[ "$len" -le 262144 ] 2>/dev/null || respond "413 Payload Too Large" '{"ok":false}'
mkdir -p "$VAR"

# Prints "rebuild" or "fresh". Remembers new stylesheets in extra-sheets.txt.
decision="$(head -c "$len" | python3 -I -c '
import json, os, re, sys
extras, manifest_path, page_list, own, root = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], "/usr/syno/synoman"
try:
    body = json.load(sys.stdin)
except ValueError:
    body = {}
sheets = body.get("sheets", []) if isinstance(body, dict) else []
every = body.get("all", []) if isinstance(body, dict) else []
try:
    with open(extras, encoding="utf-8") as f:
        known = [l.strip() for l in f if l.strip()]
except OSError:
    known = []
ok = re.compile(r"^[A-Za-z0-9_./@-]+\.css(\?[A-Za-z0-9=&._-]*)?$")
valid = lambda s: isinstance(s, str) and ok.match(s) and ".." not in s and not s.startswith(own)
if isinstance(every, list):
    page = [s for s in every[:400] if valid(s)]
    if page:
        with open(page_list + ".tmp", "w", encoding="utf-8") as f:
            f.write("\n".join(page) + "\n")
        os.replace(page_list + ".tmp", page_list)
added = False
for s in sheets if isinstance(sheets, list) else []:
    if valid(s):
        base = s.split("?", 1)[0]
        known = [k for k in known if k.split("?", 1)[0] != base]
        known.append(s)
        added = True
if added:
    with open(extras + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(known[-200:]) + "\n")
    os.replace(extras + ".tmp", extras)
changed = False
try:
    with open(manifest_path, encoding="utf-8") as f:
        sources = json.load(f).get("sources", {})
except (OSError, ValueError):
    sources = {}
for path, stamp in sources.items():
    try:
        st = os.stat(os.path.join(root, path))
        if "%d:%d" % (st.st_size, st.st_mtime_ns) != stamp:
            changed = True
            break
    except OSError:
        changed = True
        break
try:
    with open(os.path.join(os.path.dirname(manifest_path), "status.json"), encoding="utf-8") as f:
        state = json.load(f).get("state")
except (OSError, ValueError):
    state = None
print("rebuild" if added or changed or not sources or state in ("waiting", "failed") else "fresh")
' "$VAR/extra-sheets.txt" "$MANIFEST" "$VAR/page-sheets.txt" "webman/3rdparty/${PKG}/")"

[ "$decision" = "rebuild" ] || respond "200 OK" '{"ok":true,"started":false}'

stamp="$VAR/last-request"
now="$(date +%s)"
last="$(cat "$stamp" 2>/dev/null)"
case "$last" in ''|*[!0-9]*) last=0 ;; esac
if [ "$((now - last))" -lt "$MIN_INTERVAL" ]; then
  respond "200 OK" '{"ok":true,"started":false}'
fi
echo "$now" > "$stamp"

if command -v setsid >/dev/null 2>&1; then
  setsid "$TARGET/bin/darkmode-regen" </dev/null >/dev/null 2>&1 &
else
  nohup "$TARGET/bin/darkmode-regen" </dev/null >/dev/null 2>&1 &
fi
respond "200 OK" '{"ok":true,"started":true}'
