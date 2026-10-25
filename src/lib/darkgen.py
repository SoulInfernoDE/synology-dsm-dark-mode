#!/usr/bin/env python3
"""Generate the DSM dark theme stylesheet from the stylesheets DSM itself loads.

DSM 7 has no dark theme and most of its UI (ExtJS based) uses hard-coded
colors. Instead of shipping a hand-written theme that breaks with every DSM
update, this generator reads the stylesheets the DSM desktop actually loads and
writes a "shadow cascade": for every rule that sets a color related property it
emits a copy with the same selector, a dark color and one extra ID of
specificity (":not(#dsmdark)"). Because all copies get the same boost, they win
against every original rule while keeping the original order among themselves.
The light theme stays untouched: the whole output sits in one @media block that
only matches in dark mode (the DSM side script switches it for "always dark" or
"always light").

Only the Python 3.8 standard library is used, so it runs on DSM itself.

Usage:
  darkgen.py --root /usr/syno/synoman --out style.css [--extra curated.css]
             [--list hrefs.txt | --index index.html] [--manifest manifest.json]
"""

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import struct
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import darkimg  # noqa: E402

GENERATOR_VERSION = 2
MEDIA_AUTO = "(prefers-color-scheme: dark)"
BOOST = ":not(#dsmdark)"
OWN_DIR = "webman/3rdparty/DarkMode/"
OWN_PREFIX = "../../../"  # from OWN_DIR back to the DSM web root
IMG_DIR = "dark-img"      # recolored images, relative to the generated file

# --------------------------------------------------------------------------
# Color math (sRGB <-> OKLab / OKLCH)
# --------------------------------------------------------------------------


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _unlin(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def rgb_to_oklch(r, g, b):
    r, g, b = _lin(r / 255), _lin(g / 255), _lin(b / 255)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(A, B), math.atan2(B, A)


def _oklch_to_linear(L, C, h):
    A, B = C * math.cos(h), C * math.sin(h)
    l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3
    m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3
    s = (L - 0.0894841775 * A - 1.2914855480 * B) ** 3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def oklch_to_rgb(L, C, h):
    L = min(1.0, max(0.0, L))
    lo, hi = 0.0, C
    rgb = _oklch_to_linear(L, C, h)
    if not all(-1e-4 <= v <= 1 + 1e-4 for v in rgb):
        # Out of gamut: keep lightness and hue, reduce chroma.
        for _ in range(20):
            mid = (lo + hi) / 2
            if all(-1e-4 <= v <= 1 + 1e-4 for v in _oklch_to_linear(L, mid, h)):
                lo = mid
            else:
                hi = mid
        rgb = _oklch_to_linear(L, lo, h)
    return tuple(int(round(min(1.0, max(0.0, _unlin(min(1.0, max(0.0, v))))) * 255)) for v in rgb)


# --------------------------------------------------------------------------
# Color parsing and formatting
# --------------------------------------------------------------------------

NAMED = {
    "black": "000000", "white": "ffffff", "red": "ff0000", "green": "008000",
    "blue": "0000ff", "yellow": "ffff00", "gray": "808080", "grey": "808080",
    "silver": "c0c0c0", "maroon": "800000", "purple": "800080", "fuchsia": "ff00ff",
    "lime": "00ff00", "olive": "808000", "navy": "000080", "teal": "008080",
    "aqua": "00ffff", "orange": "ffa500", "whitesmoke": "f5f5f5",
    "gainsboro": "dcdcdc", "lightgray": "d3d3d3", "lightgrey": "d3d3d3",
    "darkgray": "a9a9a9", "darkgrey": "a9a9a9", "dimgray": "696969",
    "dimgrey": "696969", "lightslategray": "778899", "slategray": "708090",
    "darkslategray": "2f4f4f", "aliceblue": "f0f8ff", "ghostwhite": "f8f8ff",
    "snow": "fffafa", "ivory": "fffff0", "beige": "f5f5dc", "linen": "faf0e6",
    "lightyellow": "ffffe0", "lightblue": "add8e6", "lightgreen": "90ee90",
    "darkred": "8b0000", "darkblue": "00008b", "darkgreen": "006400",
    "darkorange": "ff8c00", "steelblue": "4682b4", "royalblue": "4169e1",
    "dodgerblue": "1e90ff", "skyblue": "87ceeb", "crimson": "dc143c",
    "tomato": "ff6347", "gold": "ffd700", "pink": "ffc0cb", "brown": "a52a2a",
    "lightcyan": "e0ffff", "honeydew": "f0fff0", "mintcream": "f5fffa",
    "azure": "f0ffff", "lavender": "e6e6fa", "seashell": "fff5ee",
    "floralwhite": "fffaf0", "oldlace": "fdf5e6", "lemonchiffon": "fffacd",
    "cornsilk": "fff8dc", "papayawhip": "ffefd5", "lightpink": "ffb6c1",
}

COLOR_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}(?![0-9a-zA-Z_-])"
    r"|(?:rgba?|hsla?)\([^()]*\)"
    r"|(?<![\w.#-])(?:" + "|".join(sorted(NAMED, key=len, reverse=True)) + r")(?![\w-])",
    re.I,
)


def _num(tok, scale):
    tok = tok.strip()
    if tok.endswith("%"):
        return float(tok[:-1]) * scale / 100.0
    return float(tok)


def parse_color(text):
    """Return (r, g, b, a) for a CSS color literal or None."""
    t = text.strip().lower()
    if t in NAMED:
        t = "#" + NAMED[t]
    if t.startswith("#"):
        h = t[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8) or not re.fullmatch(r"[0-9a-f]+", h):
            return None
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a
    m = re.fullmatch(r"(rgba?|hsla?)\((.*)\)", t)
    if not m:
        return None
    parts = re.split(r"\s*[,/]\s*|\s+", m.group(2).strip())
    parts = [p for p in parts if p]
    if len(parts) not in (3, 4):
        return None
    try:
        a = _num(parts[3], 1.0) if len(parts) == 4 else 1.0
        if m.group(1).startswith("rgb"):
            r, g, b = (_num(p, 255) for p in parts[:3])
        else:
            hue = float(parts[0].replace("deg", "")) / 360.0
            s, l = _num(parts[1], 1.0), _num(parts[2], 1.0)
            r, g, b = (v * 255 for v in _hsl_to_rgb(hue, s, l))
    except ValueError:
        return None
    clamp = lambda v: int(round(min(255, max(0, v))))
    return clamp(r), clamp(g), clamp(b), min(1.0, max(0.0, a))


def _hsl_to_rgb(h, s, l):
    if s == 0:
        return l, l, l

    def hue(p, q, t):
        t %= 1.0
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    return hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)


def format_color(r, g, b, a):
    if a >= 0.999:
        return "#%02x%02x%02x" % (r, g, b)
    return "rgba(%d,%d,%d,%s)" % (r, g, b, ("%.3f" % a).rstrip("0").rstrip("."))


# --------------------------------------------------------------------------
# Dark palette: one transform per role
# --------------------------------------------------------------------------
#
# Lightness values are OKLab L (0 = black, 1 = white). "Neutral" colors (the
# blue-grey tones of DSM) get their lightness inverted into a dark range;
# saturated accent colors keep their hue and mostly their lightness so blue
# buttons stay recognisably DSM blue.

NEUTRAL_CHROMA = 0.045
SURFACE_L = 0.235      # window and panel background (light: white)
SURFACE_SPAN = 0.48    # how far darker light colors move up from SURFACE_L
TEXT_L = 0.93          # primary text (light: near black)
TEXT_SPAN = 0.40
BORDER_L = 0.355       # light borders
BORDER_SPAN = 0.45
ACCENT_TEXT_MIN_L = 0.72
INVISIBLE_BORDER_L = 0.97  # neutral borders this light act like the surface


def _dark_bg(L, C, h, a):
    if C < NEUTRAL_CHROMA or L > 0.9:
        if L >= 0.5:
            L2 = SURFACE_L + (1.0 - L) * SURFACE_SPAN
            C2 = min(C, 0.03) * 0.6
        else:
            # Already dark (tooltips, overlays): keep, slightly lifted.
            L2 = max(L, 0.16)
            C2 = C
        return L2, C2
    if L > 0.8:
        # Pastel tints (selection, info boxes) become dark tints.
        return SURFACE_L + (1.0 - L) * SURFACE_SPAN + 0.04, min(C, 0.06)
    # Accent surfaces (buttons, badges): keep but tame very bright ones.
    return min(L, 0.68), C


def _dark_text(L, C, h, a):
    if C < NEUTRAL_CHROMA:
        if L > 0.9:
            return L, C           # white text on accents stays white
        return min(TEXT_L, 1.0 - L * TEXT_SPAN), C * 0.5
    return max(L, ACCENT_TEXT_MIN_L), C


def _dark_border(L, C, h, a):
    if C < NEUTRAL_CHROMA:
        if L >= INVISIBLE_BORDER_L:
            # White borders mostly sit on white surfaces in DSM (invisible
            # spacers): keep them blending in with the surface.
            return _dark_bg(L, C, h, a)
        if L >= 0.5:
            return BORDER_L + (1.0 - L) * BORDER_SPAN * 0.5, min(C, 0.02)
        return max(0.45, 1.0 - L * 0.9), C * 0.5
    return max(L, 0.55), C


def transform(rgba, role):
    r, g, b, a = rgba
    if a == 0:
        return rgba
    L, C, h = rgb_to_oklch(r, g, b)
    if role == "shadow":
        if L > 0.6:
            # Light emboss shadows look like glow on dark backgrounds.
            return 0, 0, 0, round(a * 0.5, 3)
        return r, g, b, min(1.0, a * 1.6)
    fn = {"bg": _dark_bg, "text": _dark_text, "border": _dark_border}[role]
    L2, C2 = fn(L, C, h, a)
    r2, g2, b2 = oklch_to_rgb(L2, C2, h)
    return r2, g2, b2, a


# --------------------------------------------------------------------------
# CSS reading helpers
# --------------------------------------------------------------------------


def strip_comments(css):
    out, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if c in "\"'":
            j = i + 1
            while j < n and css[j] != c:
                j += 2 if css[j] == "\\" else 1
            out.append(css[i:j + 1])
            i = j + 1
        elif css.startswith("/*", i):
            j = css.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _skip_string(s, i):
    q = s[i]
    j = i + 1
    while j < len(s) and s[j] != q:
        j += 2 if s[j] == "\\" else 1
    return j + 1


def _skip_url(s, i):
    # i points at "url(" (unquoted urls may contain characters like ; or {).
    j = i + 4
    while j < len(s) and s[j] in " \t\r\n":
        j += 1
    if j < len(s) and s[j] in "\"'":
        j = _skip_string(s, j)
    end = s.find(")", j)
    return len(s) if end < 0 else end + 1


def split_top(s, seps):
    """Split s at top-level characters in seps (outside (), [], strings)."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(s):
        c = s[i]
        if c in "\"'":
            i = _skip_string(s, i)
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and c in seps:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return parts


def parse_blocks(css):
    """Yield (prelude, body) for top level blocks; body is None for statements."""
    i, n = 0, len(css)
    while i < n:
        start = i
        depth = 0
        while i < n:
            c = css[i]
            if c in "\"'":
                i = _skip_string(css, i)
                continue
            if css.startswith("url(", i):
                i = _skip_url(css, i)
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == ";" and depth <= 0:
                yield css[start:i].strip(), None
                i += 1
                break
            elif c == "{" and depth <= 0:
                prelude = css[start:i].strip()
                j, level = i + 1, 1
                while j < n and level:
                    d = css[j]
                    if d in "\"'":
                        j = _skip_string(css, j)
                        continue
                    if css.startswith("url(", j):
                        j = _skip_url(css, j)
                        continue
                    if d == "{":
                        level += 1
                    elif d == "}":
                        level -= 1
                    j += 1
                yield prelude, css[i + 1:j - 1]
                i = j
                break
            elif c == "}":
                # Stray closing brace: skip it.
                i += 1
                break
            i += 1
        else:
            return


# --------------------------------------------------------------------------
# Selectors
# --------------------------------------------------------------------------

LEGACY_PSEUDO_ELEMENTS = (
    "before", "after", "first-line", "first-letter", "selection",
    "-moz-selection", "-moz-placeholder", "-ms-input-placeholder",
    "-webkit-input-placeholder", "-ms-clear", "-ms-expand", "-ms-reveal",
)


def boost_selector(sel):
    """Insert BOOST into the subject compound of a complex selector."""
    sel = sel.strip()
    if not sel:
        return sel
    # Find the start of the last compound selector.
    depth, i, last = 0, 0, 0
    while i < len(sel):
        c = sel[i]
        if c in "\"'":
            i = _skip_string(sel, i)
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and c in " \t\n>+~":
            last = i + 1
        i += 1
    compound = sel[last:]
    # Insert before the first pseudo-element of that compound.
    depth, i, cut = 0, 0, len(compound)
    while i < len(compound):
        c = compound[i]
        if c in "\"'":
            i = _skip_string(compound, i)
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and c == ":":
            if compound.startswith("::", i):
                cut = i
                break
            name = re.match(r":([-\w]+)", compound[i:])
            if name and name.group(1).lower() in LEGACY_PSEUDO_ELEMENTS:
                cut = i
                break
        i += 1
    return sel[:last] + compound[:cut] + BOOST + compound[cut:]


def boost_selector_list(prelude):
    return ",".join(boost_selector(s) for s in split_top(prelude, ","))


# --------------------------------------------------------------------------
# Declarations
# --------------------------------------------------------------------------

TEXT_PROPS = {
    "color", "caret-color", "column-rule-color", "text-decoration-color",
    "-webkit-text-fill-color", "-webkit-text-stroke-color", "fill", "stroke",
    "text-emphasis-color",
}
BORDER_PROPS = {
    "border-color", "border-top-color", "border-right-color",
    "border-bottom-color", "border-left-color", "outline-color",
    "border-block-color", "border-inline-color",
}
BORDER_SHORTHANDS = {
    "border": "border-color", "border-top": "border-top-color",
    "border-right": "border-right-color", "border-bottom": "border-bottom-color",
    "border-left": "border-left-color", "outline": "outline-color",
}
SHADOW_PROPS = {"box-shadow", "text-shadow", "-webkit-box-shadow"}
URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
IMAGE_RE = re.compile(r"url\(|(?:-[a-z]+-)?(?:repeating-)?(?:linear|radial|conic)-gradient\(|-webkit-gradient\(", re.I)
VAR_RE = re.compile(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\)[^()]*)*))?\)")
KEYWORD_COLORS = {"transparent", "currentcolor", "inherit", "initial", "unset", "revert", "none"}


def custom_prop_role(name):
    # Synology names tokens "--v-<component>-<property>__<part>", so words such
    # as "mask" may belong to the component (--v-info-mask-color__content is
    # a text color). Only property words decide the role.
    n = name.lower().split("__", 1)[0]
    if "shadow" in n:
        return "shadow"
    if re.search(r"bkg|(?<![a-z])bg|background", n):
        return "bg"
    if re.search(r"border|outline|divider|split|separator|stroke", n):
        return "border"
    return "text"


class Context:
    def __init__(self, root_vars):
        self.root_vars = root_vars

    def resolve_var(self, name, seen=None):
        """Resolve a global custom property to a single color literal."""
        seen = seen or set()
        if name in seen or name not in self.root_vars:
            return None
        seen.add(name)
        value = self.root_vars[name].strip()
        m = VAR_RE.fullmatch(value)
        if m:
            return self.resolve_var(m.group(1), seen) or (m.group(2) and parse_color(m.group(2)) and m.group(2))
        return value if parse_color(value) else None


def transform_colors(value, role, ctx):
    """Replace every color literal (and resolvable global var) in value."""
    if ctx is not None:
        def sub_var(m):
            lit = ctx.resolve_var(m.group(1))
            return lit if lit else m.group(0)
        value = VAR_RE.sub(sub_var, value)
    # Keep url(...) contents untouched.
    pieces = re.split(r"(url\([^)]*\))", value, flags=re.I)
    out = []
    for p in pieces:
        if p.lower().startswith("url("):
            out.append(p)
            continue

        def sub(m):
            c = parse_color(m.group(0))
            return format_color(*transform(c, role)) if c else m.group(0)
        out.append(COLOR_RE.sub(sub, p))
    return "".join(out)


class Images:
    """Dark variants of referenced interface images, written next to the CSS."""

    def __init__(self, root, out_dir, cache_dir=None):
        self.root = root
        self.out_dir = out_dir
        self.cache_dir = cache_dir
        self.used = set()
        self.done = {}
        self.stats = {"images": 0, "recolored": 0}
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            for f in os.listdir(out_dir):
                os.remove(os.path.join(out_dir, f))
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def variant(self, web):
        """Return the published name of the dark variant of web path, or None."""
        if not self.out_dir:
            return None
        if web in self.done:
            return self.done[web]
        self.done[web] = None
        ext = os.path.splitext(web)[1].lower()
        if ext not in (".png", ".svg"):
            return None
        full = resolve(self.root, web)
        if full is None:
            return None
        self.stats["images"] += 1
        name = hashlib.sha1(web.encode()).hexdigest()[:16] + ext
        cached = self._cache_path(full, ext)
        if cached and os.path.exists(cached):
            self.done[web] = self._publish(name, cached)
            return self.done[web]
        if cached and os.path.exists(cached + ".none"):
            return None
        data = read_file(self.root, web)
        if data is None:
            return None
        try:
            if ext == ".png":
                new = darkimg.dark_png(data, transform)
            else:
                text = darkimg.dark_svg(data.decode("utf-8", "replace"), parse_color, transform)
                new = text.encode("utf-8") if text else None
        except (darkimg.Unsupported, zlib.error, ValueError, IndexError, struct.error):
            new = None
        if not new:
            if cached:
                open(cached + ".none", "wb").close()
            return None
        if cached:
            with open(cached, "wb") as f:
                f.write(new)
            self.done[web] = self._publish(name, cached)
            return self.done[web]
        with open(os.path.join(self.out_dir, name), "wb") as f:
            f.write(new)
        self.stats["recolored"] += 1
        self.done[web] = name
        return name

    def _cache_path(self, full, ext):
        if not self.cache_dir:
            return None
        try:
            st = os.stat(full)
        except OSError:
            return None
        key = "%s|%d|%d|%d" % (full, st.st_size, st.st_mtime_ns, GENERATOR_VERSION)
        name = hashlib.sha1(key.encode()).hexdigest() + ext
        self.used.update((name, name + ".none"))
        return os.path.join(self.cache_dir, name)

    def prune(self):
        """Drop cache entries of images that are gone or changed."""
        if not self.cache_dir:
            return
        for f in os.listdir(self.cache_dir):
            if f not in self.used:
                try:
                    os.remove(os.path.join(self.cache_dir, f))
                except OSError:
                    pass

    def _publish(self, name, cached):
        dest = os.path.join(self.out_dir, name)
        with open(cached, "rb") as src, open(dest, "wb") as f:
            f.write(src.read())
        self.stats["recolored"] += 1
        return name


def absolutize_urls(value, base_dir, images=None):
    def sub(m):
        url = m.group(2).strip()
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|/|#)", url, re.I):
            return m.group(0)
        clean = url.split("?", 1)[0].split("#", 1)[0]
        full = os.path.normpath(os.path.join(base_dir, clean)).replace(os.sep, "/").lstrip("/")
        dark = images.variant(full) if images else None
        if dark:
            return 'url("%s/%s")' % (IMG_DIR, dark)
        # Relative to the generated file, so DSM behind a path prefix still works.
        return 'url("%s%s")' % (OWN_PREFIX, full.replace('"', "%22"))
    return URL_RE.sub(sub, value)


def split_background(value):
    """Return (image_layers_or_None, color_or_None) of a background shorthand."""
    layers = split_top(value, ",")
    images = []
    color = None
    for idx, layer in enumerate(layers):
        tokens = []
        i, s = 0, layer.strip()
        # Tokenize at top level whitespace, keeping functions together.
        depth, start = 0, 0
        while i < len(s):
            c = s[i]
            if c in "\"'":
                i = _skip_string(s, i)
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif depth == 0 and c in " \t\n":
                if i > start:
                    tokens.append(s[start:i])
                start = i + 1
            i += 1
        if start < len(s):
            tokens.append(s[start:])
        img = "none"
        for t in tokens:
            if IMAGE_RE.match(t):
                img = t
            elif idx == len(layers) - 1 and (parse_color(t) or t.lower() in ("transparent", "currentcolor") or t.lower().startswith("var(")):
                color = t
        images.append(img)
    return images, color


def _opaque_var(value, ctx):
    """True if value uses a variable that is not a plain global color.

    Such a variable may hold a whole shorthand ("1px solid #fff"), so the
    declaration cannot be split into longhands.
    """
    for m in VAR_RE.finditer(value):
        if not (ctx and ctx.resolve_var(m.group(1))):
            return True
    return False


class Generator:
    def __init__(self, ctx, images=None):
        self.ctx = ctx
        self.images = images
        self.stats = {"rules": 0, "decls": 0, "files": 0}

    def convert_decls(self, body, base_dir):
        out = []
        for raw in split_top(body, ";"):
            if ":" not in raw:
                continue
            prop, _, value = raw.partition(":")
            prop = prop.strip().lower()
            value = value.strip()
            if not prop or not value or prop.startswith("*") or prop.startswith("_"):
                continue
            important = ""
            m = re.search(r"!\s*important\s*$", value, re.I)
            if m:
                important = " !important"
                value = value[:m.start()].strip()
            for p, v in self.convert_one(prop, value, base_dir):
                out.append("%s:%s%s" % (p, v, important))
        return out

    def convert_one(self, prop, value, base_dir):
        ctx = self.ctx
        if prop.startswith("--"):
            if COLOR_RE.search(value) or VAR_RE.search(value):
                role = custom_prop_role(prop)
                new = transform_colors(value, role, ctx)
                if new != value or COLOR_RE.search(value):
                    return [(prop, absolutize_urls(new, base_dir, self.images))]
            return []
        if prop in TEXT_PROPS:
            return [(prop, transform_colors(value, "text", ctx))]
        if prop == "background-color":
            return [(prop, transform_colors(value, "bg", ctx))]
        if prop == "background-image":
            return [(prop, absolutize_urls(transform_colors(value, "bg", ctx), base_dir, self.images))]
        if prop == "background":
            if _opaque_var(value, ctx):
                # The whole shorthand comes from a variable: copy it as it is,
                # the variable itself gets a dark value where it is defined.
                return [(prop, value)]
            images, color = split_background(value)
            res = [("background-color", transform_colors(color, "bg", ctx) if color else "transparent")]
            res.append(("background-image", absolutize_urls(transform_colors(", ".join(images), "bg", ctx), base_dir, self.images)))
            return res
        if prop in BORDER_PROPS:
            return [(prop, transform_colors(value, "border", ctx))]
        if prop in BORDER_SHORTHANDS:
            longhand = BORDER_SHORTHANDS[prop]
            if value.strip().lower() in ("inherit", "initial", "unset", "revert"):
                return [(longhand, value)]
            if _opaque_var(value, ctx):
                return [(prop, transform_colors(value, "border", ctx))]
            colors = [t for t in split_top(value, " ") if t and (parse_color(t) or t.lower().startswith("var(") or t.lower() in ("transparent", "currentcolor"))]
            if prop == "outline" and not colors:
                return [(longhand, "currentcolor")]
            return [(longhand, transform_colors(colors[-1], "border", ctx) if colors else "currentcolor")]
        if prop in SHADOW_PROPS:
            return [(prop, transform_colors(value, "shadow", ctx))]
        return []

    def convert_sheet(self, css, web_path, out):
        base_dir = os.path.dirname(web_path)
        self._walk(strip_comments(css), base_dir, out, 0)

    def _walk(self, css, base_dir, out, depth):
        for prelude, body in parse_blocks(css):
            if body is None or not prelude:
                continue
            low = prelude.lower()
            if low.startswith("@media") or low.startswith("@supports") or low.startswith("@layer") or low.startswith("@container"):
                inner = []
                self._walk(body, base_dir, inner, depth + 1)
                if inner:
                    out.append(prelude + "{" + "".join(inner) + "}")
                continue
            if re.match(r"@(-[a-z]+-)?keyframes", low):
                frames, has_color = [], False
                for fp, fb in parse_blocks(body):
                    if fb is None:
                        continue
                    decls = []
                    for raw in split_top(fb, ";"):
                        if ":" not in raw:
                            continue
                        p, _, v = raw.partition(":")
                        conv = self.convert_one(p.strip().lower(), v.strip(), base_dir)
                        if conv:
                            has_color = True
                            decls.extend("%s:%s" % c for c in conv)
                        else:
                            decls.append(raw.strip())
                    frames.append(fp + "{" + ";".join(decls) + "}")
                if has_color:
                    out.append(prelude + "{" + "".join(frames) + "}")
                continue
            if low.startswith("@"):
                continue
            if "{" in body:
                continue
            decls = self.convert_decls(body, base_dir)
            if decls:
                self.stats["rules"] += 1
                self.stats["decls"] += len(decls)
                out.append(boost_selector_list(prelude) + "{" + ";".join(decls) + "}")


def collect_root_vars(sheets):
    root = {}
    for css in sheets:
        for prelude, body in parse_blocks(strip_comments(css)):
            if body is None:
                continue
            if prelude.strip() in (":root", "html", ":root,html", "html,:root"):
                for raw in split_top(body, ";"):
                    p, _, v = raw.partition(":")
                    p = p.strip()
                    if p.startswith("--") and v.strip():
                        root[p] = v.strip()
    return root


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

LINK_RE = re.compile(r'<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"', re.I)


def hrefs_from_index(html):
    return [h for h in LINK_RE.findall(html)]


def web_path(href):
    """Normalise an href ("webman/x.css?v=1", "/webman/x.css", full url) to a path."""
    h = re.sub(r"^[a-z]+://[^/]+", "", href.strip(), flags=re.I)
    h = h.split("?", 1)[0].split("#", 1)[0].lstrip("/")
    h = os.path.normpath(h).replace(os.sep, "/")
    if h.startswith("..") or not h.endswith(".css"):
        return None
    return h


def resolve(root, path):
    """Real path of a file below the DSM web root, or None.

    Package UIs are symlinks into /var/packages (and from there to @appstore
    on a volume); anything else outside the web root is refused.
    """
    full = os.path.realpath(os.path.join(root, path))
    allowed = (os.path.realpath(root) + os.sep, "/var/packages/", "/volume")
    if not full.startswith(allowed) and "/@appstore/" not in full:
        return None
    return full if os.path.isfile(full) else None


def read_file(root, path):
    full = resolve(root, path)
    if full is None:
        return None
    try:
        with open(full, "rb") as f:
            return f.read()
    except OSError:
        return None


def fingerprints(root, paths):
    """Size and change time of each source stylesheet, to notice changed files
    whose URL (DSM's version parameter) stayed the same."""
    out = {}
    for p in paths:
        full = resolve(root, p)
        if full:
            st = os.stat(full)
            out[p] = "%d:%d" % (st.st_size, st.st_mtime_ns)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default="/usr/syno/synoman", help="DSM web root")
    ap.add_argument("--out", required=True, help="output stylesheet")
    ap.add_argument("--base", action="append", default=[], help="CSS placed before the dark block (always active)")
    ap.add_argument("--extra", action="append", default=[], help="hand-written CSS appended to the dark block")
    ap.add_argument("--index", help="saved DSM index HTML to read the stylesheet list from")
    ap.add_argument("--list", help="file with more stylesheet hrefs (one per line), appended after the index ones")
    ap.add_argument("--cache", help="directory to cache recolored images between runs")
    ap.add_argument("--manifest", help="write the list of processed stylesheets as JSON")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    hrefs = []
    if args.index:
        with open(args.index, encoding="utf-8", errors="replace") as f:
            hrefs += hrefs_from_index(f.read())
    if args.list and os.path.exists(args.list):
        with open(args.list, encoding="utf-8") as f:
            hrefs += [l.strip() for l in f if l.strip()]
    if not hrefs:
        ap.error("no stylesheets: pass --index and/or --list")

    paths, seen = [], set()
    for h in hrefs:
        p = web_path(h)
        if p and p not in seen and not p.startswith(OWN_DIR):
            seen.add(p)
            paths.append(p)

    sheets = []
    for p in paths:
        data = read_file(args.root, p)
        if data is not None:
            sheets.append((p, data.decode("utf-8", "replace")))

    started = time.time()
    images = Images(args.root, os.path.join(os.path.dirname(os.path.abspath(args.out)), IMG_DIR), args.cache)
    gen = Generator(Context(collect_root_vars([c for _, c in sheets])), images)
    body = []
    for p, css in sheets:
        chunk = []
        gen.convert_sheet(css, p, chunk)
        if chunk:
            body.append("/* %s */\n%s" % (p, "\n".join(chunk)))
        gen.stats["files"] += 1

    images.prune()

    def read_all(files):
        parts = []
        for name in files:
            with open(name, encoding="utf-8") as f:
                parts.append(f.read())
        return "\n".join(parts)

    digest = hashlib.sha1(("\n".join(hrefs) + "|%d|%d" % (GENERATOR_VERSION, time.time())).encode()).hexdigest()[:12]
    out = [
        "/* DSM Dark Mode - generated by darkgen.py v%d from %d stylesheets. Do not edit. */" % (GENERATOR_VERSION, gen.stats["files"]),
        read_all(args.base),
        "@media %s{" % MEDIA_AUTO,
        ":root{color-scheme:dark;--dsm-dark-signature:%s}" % digest,
        "\n".join(body),
        "/* hand-written */",
        read_all(args.extra),
        "}",
        "",
    ]
    data = "\n".join(out).encode("utf-8")
    tmp = args.out + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, args.out)
    with gzip.open(args.out + ".gz.tmp", "wb", 9) as f:
        f.write(data)
    os.replace(args.out + ".gz.tmp", args.out + ".gz")

    if args.manifest:
        tmp = args.manifest + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"generator": GENERATOR_VERSION, "signature": digest,
                       "generated": int(time.time()),
                       "hrefs": list(dict.fromkeys(re.sub(r"^(\./|/)+", "", h.strip()) for h in hrefs)),
                       "sheets": paths,
                       "sources": fingerprints(args.root, paths)}, f)
        os.replace(tmp, args.manifest)

    if not args.quiet:
        sys.stderr.write("darkgen: %d files, %d rules, %d declarations, %d bytes, %d/%d images recolored, %.2fs\n" % (
            gen.stats["files"], gen.stats["rules"], gen.stats["decls"], len(data),
            images.stats["recolored"], images.stats["images"], time.time() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
