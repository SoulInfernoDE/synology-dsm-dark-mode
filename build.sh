#!/bin/bash
# Build the DSM Dark Mode package (noarch SPK for DSM 7.0+).
#
#   ./build.sh            -> dist/DarkMode-<version>-noarch.spk
#
# Requirements: bash, tar, gzip, python3 (build time only: syntax checks and
# the placeholder stylesheet).
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$PWD"
PKG="DarkMode"
VERSION="$(tr -d '[:space:]' < VERSION)"
MAINTAINER="${MAINTAINER:-DSM Dark Mode Project}"
BUILD="$ROOT/build"
STAGE="$BUILD/stage"
OUT="$ROOT/dist"

rm -rf "$BUILD"
mkdir -p "$STAGE/target" "$STAGE/spk" "$OUT"
T="$STAGE/target"

python3 -I -m py_compile src/lib/darkgen.py src/lib/darkimg.py
python3 -I -c "import json, sys; json.load(open(sys.argv[1]))" src/ui/config
for f in src/bin/darkmode-regen src/ui/regen.cgi package/scripts/*; do sh -n "$f"; done

# --- package.tgz contents (installed to /var/packages/DarkMode/target) ---
cp -a src/bin src/lib src/share src/ui "$T/"
find "$T" -name '__pycache__' -prune -exec rm -rf {} +
echo "$VERSION" > "$T/VERSION"
cp LICENSE "$T/LICENSE"

# Placeholder until the NAS has generated the real stylesheet: DSM only links
# style.css into the desktop if it exists when the package is installed.
{
  echo "/* DSM Dark Mode $VERSION - placeholder, rebuilt on the NAS after start. */"
  cat src/share/base.css
  echo "@media (prefers-color-scheme: dark){}"
} > "$T/ui/style.css"
echo '{"generator":0,"signature":"placeholder","generated":0,"hrefs":[],"sheets":[]}' > "$T/ui/manifest.json"
echo '{"state":"pending","time":0}' > "$T/ui/status.json"

# Cache busting. DSM versions style.css with the change time of ui/config and
# DarkMode.js with its own build number; neither changes on package updates by
# itself. Touching config renews the style.css URL, build.json gives the
# loader in DarkMode.js a fresh URL for DarkMode.core.js.
BUILD_ID="${VERSION}-$(date +%s)"
printf '{"version":"%s","build":"%s"}\n' "$VERSION" "$BUILD_ID" > "$T/ui/build.json"
touch "$T/ui/config"

find "$T" -type d -exec chmod 755 {} +
find "$T" -type f -exec chmod 644 {} +
chmod 755 "$T/bin/darkmode-regen" "$T/ui/regen.cgi" "$T/lib/darkgen.py"

tar --owner=0 --group=0 --numeric-owner --sort=name -C "$T" -czf "$STAGE/spk/package.tgz" .

# --- SPK control files ---
cp -a package/conf package/scripts "$STAGE/spk/"
chmod 755 "$STAGE"/spk/scripts/*
cp package/PACKAGE_ICON.PNG package/PACKAGE_ICON_256.PNG "$STAGE/spk/"
cp LICENSE "$STAGE/spk/LICENSE"

CHECKSUM="$(md5sum "$STAGE/spk/package.tgz" | cut -d' ' -f1)"

# Package Center descriptions: package/descriptions/<DSM language code>.txt
DESCRIPTIONS="description=\"$(tr -d '\n"' < package/descriptions/enu.txt)\""
for f in package/descriptions/*.txt; do
  code="$(basename "$f" .txt)"
  DESCRIPTIONS+=$'\n'"description_${code}=\"$(tr -d '\n"' < "$f")\""
done
cat > "$STAGE/spk/INFO" <<INFO
package="$PKG"
version="$VERSION"
os_min_ver="7.0-40000"
displayname="Dark Mode for DSM"
$DESCRIPTIONS
maintainer="$MAINTAINER"
arch="noarch"
thirdparty="yes"
beta="yes"
dsmuidir="ui"
startable="yes"
ctl_stop="yes"
silent_upgrade="yes"
support_center="no"
checksum="$CHECKSUM"
INFO

SPK="$OUT/${PKG}-${VERSION}-noarch.spk"
rm -f "$SPK"
tar --owner=0 --group=0 --numeric-owner -C "$STAGE/spk" -cf "$SPK" \
  INFO package.tgz scripts conf PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG LICENSE
echo "built $SPK ($(du -h "$SPK" | cut -f1))"
