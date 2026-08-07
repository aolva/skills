"""Low-level OOXML helpers (self-developed): namespaces, EMU math, common builders."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from .model import PPTDError, color_rgb_hex, resolve_color

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "asvg": "http://schemas.microsoft.com/office/drawing/2016/SVG/main",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
}

for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)

R_NS = NS["r"]


def el(tag, **attrs):
    """Create an element; tag may carry a prefix like 'a:solidFill'.

    The special kwarg `text=` sets the element's text content instead of an
    attribute; all other kwargs become XML attributes.
    """
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        tag = f"{{{NS[prefix]}}}{local}"
    e = ET.Element(tag)
    body = attrs.pop("text", None)
    for k, v in attrs.items():
        if v is None:
            continue
        if ":" in k and k.split(":", 1)[0] in NS:
            prefix, local = k.split(":", 1)
            e.set(f"{{{NS[prefix]}}}{local}", str(v))
        else:
            e.set(k, str(v))
    if body is not None:
        e.text = str(body)
    return e


def px(value):
    """1px == 1pt in the PPTD spec -> EMU."""
    return int(round(float(value) * 12700))


def color_node(color, alpha=None):
    """<a:srgbClr val=...> with optional <a:alpha>. Handles #RRGGBB / #RRGGBBAA."""
    hex6, a = color_rgb_hex(color)
    node = el("a:srgbClr", val=hex6.upper())
    eff = alpha if alpha is not None else a
    if eff < 1.0:
        node.append(el("a:alpha", val=int(round(max(0.0, min(1.0, eff)) * 100000))))
    return node


def solid_fill(color, alpha=None):
    f = el("a:solidFill")
    f.append(color_node(color, alpha))
    return f


def grad_fill(fill):
    """Fill dict (resolved) -> a:gradFill. linear or radial."""
    g = el("a:gradFill", rotWithShape="1")
    gs_lst = el("a:gsLst")
    for stop in sorted(fill.get("stops") or [], key=lambda s: s.get("position", 0)):
        gs = el("a:gs", pos=int(round(float(stop.get("position", 0)) * 100000)))
        gs.append(color_node(stop["color"]))
        gs_lst.append(gs)
    g.append(gs_lst)
    if fill.get("gradientType") == "radial":
        g.append(
            el(
                "a:path", path="circle",
            )
        )
        # fillToRect must be nested inside a:path
        for child in g:
            if child.tag == f"{{{NS['a']}}}path":
                child.append(el("a:fillToRect", l="50000", t="50000", r="50000", b="50000"))
    else:
        angle = float(fill.get("angle") or 0)
        g.append(el("a:lin", ang=int(round(angle * 60000)) % 36000000, scaled="1"))
    return g


def image_fill(r_embed, src_rect=None):
    bf = el("a:blipFill")
    blip = el("a:blip", **{f"r:embed": r_embed})
    bf.append(blip)
    if src_rect:
        bf.append(el("a:srcRect", l=src_rect[0], t=src_rect[1], r=src_rect[2], b=src_rect[3]))
    stretch = el("a:stretch")
    stretch.append(el("a:fillRect"))
    bf.append(stretch)
    return bf


def fill_element(fill, rel_lookup=None):
    """Build the fill child element(s). ImageFill needs rel_lookup(src)->rId."""
    if fill is None:
        return None
    ftype = fill.get("type", "solid")
    if ftype == "gradient":
        return grad_fill(fill)
    if ftype == "image":
        if not rel_lookup:
            return None
        rid = rel_lookup(fill.get("src"))
        if rid is None:
            return None
        return image_fill(rid)
    return solid_fill(fill.get("color", "#000000"))


def line_style(border, default_width=None):
    """Border dict -> <a:ln> element."""
    if border is None:
        return None
    width = border.get("width")
    if width is None:
        width = default_width if default_width is not None else 1
    ln = el("a:ln", w=int(round(float(width) * 12700)), cap="rnd")
    style = border.get("style", "solid")
    color = border.get("color", "#000000")
    ln.append(solid_fill(color))
    if style == "dash":
        ln.append(el("a:prstDash", val="dash"))
    elif style == "dot":
        ln.append(el("a:prstDash", val="dot"))
    else:
        ln.append(el("a:prstDash", val="solid"))
    return ln


def outer_shadow(shadow):
    """Shadow dict -> <a:effectLst> with outerShdw (offset [x, y], blur, color)."""
    if shadow is None:
        return None
    blur = float(shadow.get("blur", 0))
    color = shadow.get("color", "#00000000")
    off = shadow.get("offset") or [0, 0]
    dx, dy = float(off[0]), float(off[1])
    if dx == 0 and dy == 0:
        dir_val = 0
    else:
        dir_val = int(round(math.degrees(math.atan2(dx, -dy)) * 60000)) % 36000000
    dist = math.hypot(dx, dy)
    sh = el("a:outerShdw", blurRad=int(round(blur * 12700)),
            dist=int(round(dist * 12700)), dir=dir_val, rotWithShape="0")
    # PowerPoint convention: 0 = up, clockwise; offset is drawn along that direction
    hex6, alpha = color_rgb_hex(color)
    c = el("a:srgbClr", val=hex6.upper())
    if alpha < 1.0:
        c.append(el("a:alpha", val=int(round(alpha * 100000))))
    sh.append(c)
    eff = el("a:effectLst")
    eff.append(sh)
    return eff


def xfrm(x, y, w, h, rotation=None, flip_h=None, flip_v=None):
    t = el("a:xfrm")
    if flip_h:
        t.set("flipH", "1")
    if flip_v:
        t.set("flipV", "1")
    if rotation:
        t.set("rot", int(round(float(rotation) * 60000)) % 36000000)
    t.append(el("a:off", x=px(x), y=px(y)))
    t.append(el("a:ext", cx=px(w), cy=px(h)))
    return t
