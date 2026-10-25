"""Dark variants of DSM interface images (PNG and SVG), standard library only.

DSM draws many small interface glyphs (tool buttons, arrows, checkboxes) as
grey PNG or SVG sprites made for a white background. Colored application icons
look fine on dark backgrounds and are left alone. An image counts as a glyph
sprite when nearly all of its visible pixels are neutral grey tones; only then
its neutral pixels are recolored with the same palette as the stylesheet
(dark grey -> light text tone, white -> dark surface), colored pixels stay.
"""

import re
import struct
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"
GLYPH_NEUTRAL_SHARE = 0.92  # share of visible pixels that must be grey
LIGHT_GLYPH_LUM = 0.85     # average grey lightness above this: light image
DARK_SURFACE_LUM = 0.5     # opaque images darker than this are dark already
BG_THRESHOLD = 0.96        # glyphs: only near-white pixels act as surface (fills)
SURFACE_THRESHOLD = 0.6    # opaque background images: light greys are surface
SURFACE_COVERAGE = 0.6     # share of opaque pixels for a background image


class Unsupported(Exception):
    pass


# --------------------------------------------------------------------------
# PNG decoding / encoding (8 bit, non interlaced; palettes up to 8 bit)
# --------------------------------------------------------------------------


def _chunks(data):
    if not data.startswith(PNG_SIG):
        raise Unsupported("not a png")
    i = 8
    while i + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[i:i + 8])
        yield kind, data[i + 8:i + 8 + length]
        i += 12 + length


def _unfilter(raw, width, height, bpp):
    stride = width * bpp
    out = bytearray(height * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ftype == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif ftype == 2:
            row = bytearray((a + b) & 255 for a, b in zip(row, prev))
        elif ftype == 3:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        elif ftype != 0:
            raise Unsupported("bad filter")
        out[y * stride:(y + 1) * stride] = row
        prev = row
    return out


ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _deinterlace(raw, width, height, bpp):
    out = bytearray(width * height * bpp)
    pos = 0
    for x0, y0, dx, dy in ADAM7:
        pw = (width - x0 + dx - 1) // dx
        ph = (height - y0 + dy - 1) // dy
        if pw <= 0 or ph <= 0:
            continue
        size = ph * (1 + pw * bpp)
        sub = _unfilter(raw[pos:pos + size], pw, ph, bpp)
        pos += size
        for j in range(ph):
            y = y0 + j * dy
            for i in range(pw):
                d = (y * width + x0 + i * dx) * bpp
                s = (j * pw + i) * bpp
                out[d:d + bpp] = sub[s:s + bpp]
    return out


def decode_png(data):
    """Return (width, height, kind, payload).

    kind "palette": payload = (palette rgba list, raw chunks for re-encoding)
    kind "rgba": payload = bytearray of RGBA pixels
    """
    ihdr = None
    idat = []
    plte = trns = None
    chunks = []
    for kind, body in _chunks(data):
        chunks.append((kind, body))
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
    if not ihdr:
        raise Unsupported("no header")
    width, height, depth, ctype, _comp, _filt, interlace = ihdr
    if ctype == 3:
        if not plte:
            raise Unsupported("no palette")
        pal = []
        for i in range(len(plte) // 3):
            a = trns[i] if trns and i < len(trns) else 255
            pal.append((plte[3 * i], plte[3 * i + 1], plte[3 * i + 2], a))
        return width, height, "palette", (pal, chunks, depth)
    if depth != 8:
        raise Unsupported("bit depth")
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}.get(ctype)
    if not bpp:
        raise Unsupported("color type")
    raw = zlib.decompress(b"".join(idat))
    px = _deinterlace(raw, width, height, bpp) if interlace else _unfilter(raw, width, height, bpp)
    if ctype == 6:
        return width, height, "rgba", px
    rgba = bytearray(width * height * 4)
    if ctype == 2:
        tr = struct.unpack(">HHH", trns) if trns and len(trns) == 6 else None
        rgba[0::4], rgba[1::4], rgba[2::4] = px[0::3], px[1::3], px[2::3]
        rgba[3::4] = b"\xff" * (width * height)
        if tr:
            for i in range(width * height):
                if (px[3 * i], px[3 * i + 1], px[3 * i + 2]) == tr:
                    rgba[4 * i + 3] = 0
    elif ctype == 0:
        rgba[0::4] = rgba[1::4] = rgba[2::4] = px
        rgba[3::4] = b"\xff" * (width * height)
    else:  # gray + alpha
        rgba[0::4] = rgba[1::4] = rgba[2::4] = px[0::2]
        rgba[3::4] = px[1::2]
    return width, height, "rgba", rgba


def _chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def encode_rgba(width, height, rgba):
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    return (PNG_SIG + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b""))


def encode_palette(chunks, pal):
    out = bytearray(PNG_SIG)
    plte = b"".join(bytes(p[:3]) for p in pal)
    trns = bytes(p[3] for p in pal)
    has_trns = any(p[3] != 255 for p in pal)
    for kind, body in chunks:
        if kind == b"PLTE":
            out += _chunk(b"PLTE", plte)
            if has_trns:
                out += _chunk(b"tRNS", trns.rstrip(b"\xff") or b"\xff")
        elif kind == b"tRNS":
            continue
        elif kind in (b"IHDR", b"IDAT", b"IEND"):
            out += _chunk(kind, body)
    return bytes(out)


# --------------------------------------------------------------------------
# Classification and recoloring
# --------------------------------------------------------------------------


_NEUTRAL = {}


def _is_neutral(r, g, b):
    """Grey tones, including the slightly blue greys of DSM (OKLCH chroma)."""
    key = (r, g, b)
    if key not in _NEUTRAL:
        from darkgen import rgb_to_oklch, NEUTRAL_CHROMA
        _NEUTRAL[key] = rgb_to_oklch(r, g, b)[1] < NEUTRAL_CHROMA
    return _NEUTRAL[key]


def _classify(colors, total=None):
    """Decide how to treat an image.

    colors: iterable of (r, g, b, a, weight); total: pixel count (None if
    unknown). Returns None (leave alone), "glyph" (grey icons for white
    backgrounds) or "surface" (opaque light background images).
    """
    visible = neutral = 0
    lum_sum = 0.0
    for r, g, b, a, w in colors:
        if a < 40:
            continue
        visible += w
        if _is_neutral(r, g, b):
            neutral += w
            lum_sum += w * (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    if not visible or neutral / visible < GLYPH_NEUTRAL_SHARE:
        return None
    coverage = visible / total if total else 0.0
    mean = lum_sum / neutral
    if coverage >= SURFACE_COVERAGE and mean < DARK_SURFACE_LUM:
        return None
    if mean < LIGHT_GLYPH_LUM:
        return "surface" if coverage >= SURFACE_COVERAGE else "glyph"
    # Light images: opaque ones are backgrounds, transparent ones are white
    # glyphs made for dark or colored backgrounds and stay as they are.
    return "surface" if coverage >= SURFACE_COVERAGE else None


def _recolor_fn(transform, mode):
    cache = {}
    threshold = BG_THRESHOLD if mode == "glyph" else SURFACE_THRESHOLD

    def recolor(r, g, b, a):
        key = (r, g, b)
        if key not in cache:
            if not _is_neutral(r, g, b):
                cache[key] = key
            else:
                lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
                role = "bg" if lum >= threshold else "text"
                cache[key] = transform((r, g, b, 1.0), role)[:3]
        return cache[key]
    return recolor


def _palette_counts(payload, width, height):
    pal, chunks, depth = payload
    raw = zlib.decompress(b"".join(b for k, b in chunks if k == b"IDAT"))
    row_bytes = (width * depth + 7) // 8
    data = _unfilter(raw, row_bytes, height, 1)
    counts = [0] * len(pal)
    per_byte = 8 // depth
    mask = (1 << depth) - 1
    for y in range(height):
        row = data[y * row_bytes:(y + 1) * row_bytes]
        if depth == 8:
            for v in row:
                if v < len(counts):
                    counts[v] += 1
            continue
        n = 0
        for v in row:
            for k in range(per_byte):
                if n >= width:
                    break
                idx = (v >> (8 - depth * (k + 1))) & mask
                if idx < len(counts):
                    counts[idx] += 1
                n += 1
    return counts


def dark_png(data, transform):
    """Return the dark PNG bytes, or None if the image should stay as is."""
    width, height, kind, payload = decode_png(data)
    if kind == "palette":
        pal, chunks, _depth = payload
        if not any(k == b"IHDR" for k, _ in chunks) or _interlaced(chunks):
            counts = [1] * len(pal)
            total = None
        else:
            counts = _palette_counts(payload, width, height)
            total = width * height
        mode = _classify(((r, g, b, a, c) for (r, g, b, a), c in zip(pal, counts)), total)
        if not mode:
            return None
        recolor = _recolor_fn(transform, mode)
        return encode_palette(chunks, [recolor(r, g, b, a) + (a,) for r, g, b, a in pal])
    px = payload
    counts = {}
    for i in range(0, len(px), 4):
        if px[i + 3] >= 40:
            k = (px[i], px[i + 1], px[i + 2])
            counts[k] = counts.get(k, 0) + 1
    mode = _classify(((r, g, b, 255, w) for (r, g, b), w in counts.items()), width * height)
    if not mode:
        return None
    recolor = _recolor_fn(transform, mode)
    for i in range(0, len(px), 4):
        if px[i + 3]:
            px[i], px[i + 1], px[i + 2] = recolor(px[i], px[i + 1], px[i + 2], px[i + 3])
    return encode_rgba(width, height, px)


def _interlaced(chunks):
    for kind, body in chunks:
        if kind == b"IHDR":
            return body[12] == 1
    return False


SVG_PAINT_RE = re.compile(r"""((?:fill|stroke|stop-color|flood-color)\s*[=:]\s*["']?)(#[0-9a-fA-F]{3,8}\b|rgba?\([^()]*\))""")


def dark_svg(text, parse_color, transform):
    """Recolor a grey glyph SVG; returns None for colorful or white SVGs.

    Paint is recolored by attribute: neutral strokes become borders, white
    fills become surfaces and other grey fills become text tones.
    """
    paints = [(m.group(1), parse_color(m.group(2))) for m in SVG_PAINT_RE.finditer(text)]
    paints = [(k, c) for k, c in paints if c]
    if not paints:
        return None
    grey = [c for _k, c in paints if _is_neutral(*c[:3])]
    if len(grey) / len(paints) < 0.5:
        return None
    if all((0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255 >= LIGHT_GLYPH_LUM for c in grey):
        return None

    def sub(m):
        c = parse_color(m.group(2))
        if not c or not _is_neutral(*c[:3]):
            return m.group(0)
        lum = (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255
        if m.group(1).lstrip().startswith("stroke"):
            role = "border"
        else:
            role = "bg" if lum >= BG_THRESHOLD else "text"
        r, g, b, _a = transform((c[0], c[1], c[2], 1.0), role)
        return m.group(1) + "#%02x%02x%02x" % (r, g, b)
    return SVG_PAINT_RE.sub(sub, text)
