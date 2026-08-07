"""Slide element renderers (self-developed): text / shape / line / image / icon / table.

Implements the PPTD v2 rich-text subset and element semantics on top of
DrawingML. All geometry is written in EMU (1 px == 1 pt in PPTD terms).
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from . import model
from . import ooxml
from .ooxml import NS, el, px
from .icons import icon_svg, normalize as icon_normalize

A_NS = NS["a"]
P_NS = NS["p"]
R_NS = NS["r"]

_PRESET_SHAPES = {
    "rect": "rect", "roundRect": "roundRect", "ellipse": "ellipse",
    "triangle": "triangle", "diamond": "diamond", "homePlate": "homePlate",
    "chevron": "chevron", "donut": "donut", "star5": "star5",
    "rightArrow": "rightArrow", "wedgeRectCallout": "wedgeRectCallout",
    "bracePair": "bracePair", "hexagon": "hexagon", "parallelogram": "parallelogram",
    "trapezoid": "trapezoid", "pentagon": "pentagon", "pentagon1": "homePlate",
    "octagon": "octagon", "arrowLeft": "leftArrow", "leftArrow": "leftArrow",
    "leftRightArrow": "leftRightArrow", "upArrow": "upArrow", "downArrow": "downArrow",
    "doubleArrow": "leftRightArrow", "flowChartProcess": "flowChartProcess",
    "flowChartDecision": "flowChartDecision", "flowChartDocument": "flowChartDocument",
    "cloud": "cloud", "star4": "star4", "star7": "star7", "star8": "star8",
    "pie": "pie", "chord": "chord", "arc": "arc", "lineInv": "lineInv",
    "teardrop": "teardrop", "blockArc": "blockArc", "moon": "moon",
    "halfFrame": "halfFrame", "frame": "frame", "cornerTabs": "cornerTabs",
    "round1Rect": "round1Rect", "round2SameRect": "round2SameRect",
    "round2DiagRect": "round2DiagRect", "snip1Rect": "snip1Rect",
    "snip2SameRect": "snip2SameRect", "snip2DiagRect": "snip2DiagRect",
    "snipRoundRect": "snipRoundRect", "plaque": "plaque", "can": "can",
    "cube": "cube", "bevel": "bevel", "donut": "donut", "noSmoking": "noSmoking",
    "heart": "heart", "lightningBolt": "lightningBolt", "sun": "sun",
    "moon": "moon", "smileyFace": "smileyFace", "irregularSeal1": "irregularSeal1",
    "irregularSeal2": "irregularSeal2", "foldedCorner": "foldedCorner",
    "actionButtonBlank": "actionButtonBlank", "frame": "frame",
    "horizontalScroll": "horizontalScroll", "verticalScroll": "verticalScroll",
    "wave": "wave", "doubleWave": "doubleWave", "upDownArrow": "upDownArrow",
}

_ALIGN = {"left": "l", "center": "ctr", "right": "r", "justify": "just", "distributed": "dist"}
_ANCHOR = {"top": "t", "middle": "ctr", "bottom": "b"}


# ---------------------------------------------------------------------------
# rich text
# ---------------------------------------------------------------------------

class _RichParser(HTMLParser):
    """Parse PPTD rich text into paragraphs: [{pPr, runs: [{text, style, href}]}]."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paras = []
        self.cur = None
        self.span_styles = []
        self.tags = []
        self.hrefs = []
        self.para_style = {}
        self.bullet = None
        self.bullet_stack = []
        self._run = None

    # -- helpers ---------------------------------------------------------
    def _span_style(self, style_attr):
        out = {}
        if not style_attr:
            return out
        for decl in style_attr.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                k, v = k.strip(), v.strip()
                if k == "color":
                    out["color"] = v
                elif k == "font-size":
                    out["fontSize"] = _px_num(v)
                elif k == "font-family":
                    out["fontFamily"] = v.strip("'\"")
                elif k == "background-color":
                    out["backgroundColor"] = v
                elif k == "line-height":
                    if v.endswith("px"):
                        out["lineHeightPx"] = _px_num(v)
                    else:
                        try:
                            out["lineHeight"] = float(v)
                        except ValueError:
                            pass
                elif k == "letter-spacing":
                    out["letterSpacing"] = _px_num(v)
        return out

    def _para_style(self, style_attr):
        out = {}
        if not style_attr:
            return out
        for decl in style_attr.split(";"):
            if ":" in decl:
                k, v = decl.split(":", 1)
                out[k.strip()] = v.strip()
        return out

    def _inline_style(self):
        out = {}
        for s in self.span_styles:
            out.update(s)
        if "strong" in self.tags:
            out["bold"] = True
        if "em" in self.tags:
            out["italic"] = True
        if "u" in self.tags:
            out["underline"] = True
        if "s" in self.tags:
            out["strike"] = True
        if "sup" in self.tags:
            out["baseline"] = 30000
        if "sub" in self.tags:
            out["baseline"] = -25000
        return out

    # -- HTMLParser callbacks -------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("p", "li"):
            self._flush()
            self.para_style = self._para_style(a.get("style"))
            if tag == "li":
                self.bullet_stack.append(self.bullet)
                self.bullet = "ol" if "ol" in self.tags else "ul"
        elif tag == "span":
            self.span_styles.append(self._span_style(a.get("style")))
            self._run = None
        elif tag == "a":
            self.hrefs.append(a.get("href"))
            self._run = None
        elif tag == "br":
            self._add_text("\n")
            return
        else:
            self._run = None
        self.tags.append(tag)

    def handle_endtag(self, tag):
        if tag in ("p", "li"):
            self._flush()
            if tag == "li" and self.bullet_stack:
                self.bullet = self.bullet_stack.pop()
        elif tag in ("span", "a", "strong", "em", "u", "s", "sup", "sub"):
            if tag == "span" and self.span_styles:
                self.span_styles.pop()
            elif tag == "a" and self.hrefs:
                self.hrefs.pop()
            self._run = None
        for i in range(len(self.tags) - 1, -1, -1):
            if self.tags[i] == tag:
                del self.tags[i]
                break

    def handle_data(self, data):
        if not data:
            return
        if data.strip() == "" and not any(t in self.tags for t in ("p", "li")):
            return
        self._add_text(data)

    def _add_text(self, text):
        if self.cur is None:
            self.cur = {"pPr": dict(self.para_style), "runs": [], "bullet": self.bullet}
            self.paras.append(self.cur)
        style = self._inline_style()
        href = self.hrefs[-1] if self.hrefs else None
        sig = (repr(sorted(style.items())), href)
        if self._run is None or self._run["_sig"] != sig:
            self._run = {"text": "", "style": style, "href": href, "_sig": sig}
            self.cur["runs"].append(self._run)
        self._run["text"] += text

    def _flush(self):
        if self.cur is not None:
            self.cur["pPr"] = dict(self.para_style)
            self.cur = None
            self._run = None


def parse_rich_text(text):
    """-> list of {pPr: {...}, runs: [{text, style, href}]}."""
    parser = _RichParser()
    try:
        parser.feed(text or "")
        parser.close()
    except Exception:
        return [{"pPr": {}, "runs": [{"text": text or "", "style": {}, "href": None}]}]
    out = []
    for para in parser.paras:
        para = dict(para)
        para["runs"] = [
            {"text": r["text"], "style": r["style"], "href": r["href"]}
            for r in para["runs"]
        ]
        out.append(para)
    if not out:
        return [{"pPr": {}, "runs": [{"text": text or "", "style": {}, "href": None}]}]
    return out


def parse_rich_text(text):
    """-> list of {pPr: {...}, runs: [{text, style, href}]}."""
    parser = _RichParser()
    try:
        parser.feed(text or "")
        parser.close()
    except Exception:
        return [{"pPr": {}, "runs": [{"text": text or "", "style": {}, "href": None}]}]
    if not parser.paras:
        return [{"pPr": {}, "runs": [{"text": text or "", "style": {}, "href": None}]}]
    return parser.paras


# ---------------------------------------------------------------------------
# text box rendering
# ---------------------------------------------------------------------------

def _run_style(rstyle, style, theme_colors):
    """Resolve a run's final properties into OOXML rPr attributes/elements."""
    color = rstyle.get("color", style.get("color", "#000000"))
    color = model.resolve_text_color_inline(color, theme_colors)
    if color.startswith("$"):
        color = "#000000"
    size = rstyle.get("fontSize") or style.get("fontSize", 18)
    latin, ea = model.resolve_font_family(rstyle.get("fontFamily") or style.get("fontFamily", "MiSans"))
    bold = rstyle.get("bold", style.get("bold", False))
    italic = rstyle.get("italic", style.get("italic", False))
    underline = rstyle.get("underline", False)
    strike = rstyle.get("strike", False)
    baseline = rstyle.get("baseline", 0)
    spc = rstyle.get("letterSpacing", style.get("letterSpacing", 0))
    bg = rstyle.get("backgroundColor") or style.get("backgroundColor")
    if bg and bg.startswith("$"):
        bg = theme_colors.get(bg[1:], bg)
    return color, size, latin, ea, bold, italic, underline, strike, baseline, spc, bg


def render_rpr(rpr, rstyle, style, theme_colors, href_rid=None):
    color, size, latin, ea, bold, italic, underline, strike, baseline, spc, bg = \
        _run_style(rstyle, style, theme_colors)
    is_link = href_rid is not None
    attrs = {"lang": "zh-CN", "dirty": "0"}
    if size:
        attrs["sz"] = int(round(float(size) * 100))
    if bold:
        attrs["b"] = "1"
    if italic:
        attrs["i"] = "1"
    if underline or is_link:
        attrs["u"] = "sng"
    if strike:
        attrs["strike"] = "sngStrike"
    if baseline:
        attrs["baseline"] = str(int(baseline))
    if spc:
        attrs["spc"] = int(round(float(spc) * 100))
    rpr = el("a:rPr", **attrs)
    if is_link:
        rpr.set(f"{{{R_NS}}}id", href_rid)
    if is_link:
        rpr.append(el("a:solidFill"))
        rpr[-1].append(el("a:srgbClr", val="0563C1"))
    else:
        if color.startswith("$"):
            color = theme_colors.get(color[1:], "#000000")
        rpr.append(ooxml.solid_fill(color))
    if bg:
        h = el("a:highlight")
        h.append(ooxml.color_node(bg))
        rpr.append(h)
    rpr.append(el("a:latin", typeface=latin))
    rpr.append(el("a:ea", typeface=ea))
    rpr.append(el("a:cs", typeface=""))
    return rpr


def render_paragraph(para, style, theme_colors, hyperlink_rel=None):
    p = el("a:p")
    ppr = el("a:pPr", rtl="0")
    algn = para["pPr"].get("text-align") or style.get("textAlign") or (
        style.get("align", ["left", "top"])[0] if isinstance(style.get("align"), list) else "left")
    if algn in _ALIGN:
        ppr.set("algn", _ALIGN[algn])
    line_height = style.get("lineHeight", 1)
    line_height_px = style.get("lineHeightPx")
    if para["pPr"].get("line-height"):
        v = para["pPr"]["line-height"]
        if v.endswith("px"):
            line_height_px = _px_num(v)
            line_height = None
        else:
            try:
                line_height = float(v)
                line_height_px = None
            except ValueError:
                pass
    if line_height_px:
        lnspc = el("a:lnSpc")
        lnspc.append(el("a:spcPts", val=int(round(float(line_height_px) * 100))))
        ppr.append(lnspc)
    elif line_height and abs(float(line_height) - 1.0) > 1e-9:
        lnspc = el("a:lnSpc")
        lnspc.append(el("a:spcPct", val=int(round(float(line_height) * 100000))))
        ppr.append(lnspc)
    margin_top = style.get("marginTop", 0)
    if para["pPr"].get("margin-top"):
        margin_top = _px_num(para["pPr"]["margin-top"]) or 0
    if margin_top:
        spc = el("a:spcBef")
        spc.append(el("a:spcPts", val=int(round(float(margin_top) * 100))))
        ppr.append(spc)
    mar_l = _px_num(para["pPr"].get("margin-left")) if para["pPr"].get("margin-left") else None
    mar_r = _px_num(para["pPr"].get("margin-right")) if para["pPr"].get("margin-right") else None
    if mar_l is not None:
        ppr.set("marL", str(px(mar_l)))
    if mar_r is not None:
        ppr.set("marR", str(px(mar_r)))
    bullet = para.get("bullet")
    if bullet == "ul":
        bu = el("a:buFont", typeface="Arial")
        ppr.append(bu)
        ppr.append(el("a:buChar", char="•"))
    elif bullet == "ol":
        bu = el("a:buFont", typeface="Arial")
        ppr.append(bu)
        ppr.append(el("a:buAutoNum", type="arabicPeriod"))
    else:
        ppr.append(el("a:buNone"))
    p.append(ppr)
    for run in para["runs"]:
        rstyle = run["style"] or {}
        rid = None
        if run.get("href"):
            rid = hyperlink_rel(run["href"]) if hyperlink_rel else None
        if run["text"] == "\n":
            p.append(el("a:br"))
            continue
        r = el("a:r")
        rpr = render_rpr(r, rstyle, style, theme_colors, rid)
        r.append(rpr)
        parts = run["text"].split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                r.append(el("a:br"))
            if part:
                t = el("a:t")
                t.text = part
                r.append(t)
        p.append(r)
    return p


def render_text_box(sp_tree, elem, ctx, style=None):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    content = elem.get("content") or {}
    if style is None:
        style = model.effective_text_style(content, ctx.doc["theme_text_styles"],
                                           ctx.warnings, ctx.page)
    theme_colors = ctx.doc["theme_colors"]
    eid = elem.get("elementId", f"el{ctx.new_id()}")

    sp = el("p:sp")
    nv = el("p:nvSpPr")
    cpr = el("p:cNvPr", id=str(ctx.new_id()), name=eid)
    nv.append(cpr)
    nv.append(el("p:cNvSpPr", txBox="1"))
    nv.append(el("p:nvPr"))
    sp.append(nv)
    sppr = el("p:spPr")
    sppr.append(ooxml.xfrm(x, y, w, h,
                           rotation=elem.get("rotation"),
                           flip_h=elem.get("flip", [False, False])[0],
                           flip_v=elem.get("flip", [False, False])[1]))
    prst = el("a:prstGeom", prst="rect")
    prst.append(el("a:avLst"))
    sppr.append(prst)
    sp.append(sppr)

    txb = el("p:txBody")
    align = content.get("align") or style.get("align") or ["left", "top"]
    if isinstance(align, list) and len(align) == 2:
        ha, va = align
    else:
        ha, va = "left", "top"
    wrap = content.get("wrap", True)
    bodypr = el("a:bodyPr", rtlCol="0", anchor=_ANCHOR.get(va, "t"))
    if not wrap:
        bodypr.set("wrap", "none")
    if content.get("textDirection") == "vertical":
        bodypr.set("vert", "vert")
    if va == "middle":
        bodypr.set("anchorCtr", "1")
    for m in ("lIns", "tIns", "rIns", "bIns"):
        bodypr.set(m, "0")
    bodypr.append(el("a:normAutofit"))
    txb.append(bodypr)
    txb.append(el("a:lstStyle"))

    text = content.get("text") or ""
    paras = parse_rich_text(text)
    ha, va = (content.get("align") or style.get("align") or ["left", "top"])
    if isinstance(ha, list):
        ha, va = ha[0], ha[1]
    if not paras:
        paras = [{"pPr": {}, "runs": [{"text": "", "style": {}, "href": None}]}]
    for para in paras:
        if not para["pPr"].get("text-align"):
            para["pPr"]["text-align"] = ha
        txb.append(render_paragraph(para, style, theme_colors, ctx.hyperlink_rel))

    # text-level gradient / shadow
    if style.get("gradient"):
        gf = ooxml.grad_fill(style["gradient"])
        for p in txb.iter(f"{{{A_NS}}}p"):
            for r in p.iter(f"{{{A_NS}}}r"):
                rpr = r.find(f"{{{A_NS}}}rPr")
                if rpr is not None and rpr.find(f"{{{A_NS}}}solidFill") is None:
                    rpr.append(gf)
    if style.get("shadow"):
        eff = ooxml.outer_shadow(style["shadow"])
        if eff is not None:
            for p in txb.iter(f"{{{A_NS}}}p"):
                for r in p.iter(f"{{{A_NS}}}r"):
                    rpr = r.find(f"{{{A_NS}}}rPr")
                    if rpr is not None and rpr.find(f"{{{A_NS}}}effectLst") is None:
                        rpr.append(eff)
    sp.append(txb)
    sp_tree.append(sp)
    return sp


# ---------------------------------------------------------------------------
# shape
# ---------------------------------------------------------------------------

def _adj_avlst(adjustments):
    av = el("a:avLst")
    names = ["adj", "adj1", "adj2", "adj3", "adj4", "adj5"]
    for i, val in enumerate((adjustments or [])[:6]):
        if val is None:
            continue
        av.append(el("a:gd", name=names[i], fmla=f"val {int(round(float(val)))}"))
    return av


def _parse_svg_path(path_str, scale_x, scale_y):
    """SVG path -> list of OOXML path ops (moveTo/lnTo/cubicBezTo/close)."""
    tokens = re.findall(r"[MmLlHhVvCcSsQqAaZz]|-?[\d.]+(?:[eE][-+]?\d+)?", path_str)
    ops = []
    x, y = 0.0, 0.0
    start_x, start_y = 0.0, 0.0
    last_cubic = None
    i = 0

    def num():
        nonlocal i
        v = float(tokens[i])
        i += 1
        return v

    def pt(rel=False):
        nonlocal x, y
        dx, dy = num(), num()
        if rel:
            x += dx
            y += dy
        else:
            x, y = dx, dy
        return x, y

    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        rel = cmd.islower()
        cmd = cmd.upper()
        if cmd == "Z":
            ops.append(("close",))
            x, y = start_x, start_y
        elif cmd == "M":
            cx, cy = pt(rel)
            start_x, start_y = cx, cy
            ops.append(("move", cx, cy))
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                cx, cy = pt(rel)
                ops.append(("line", cx, cy))
        elif cmd == "L":
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                cx, cy = pt(rel)
                ops.append(("line", cx, cy))
        elif cmd == "H":
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                if rel:
                    x += num()
                else:
                    x = num()
                ops.append(("line", x, y))
        elif cmd == "V":
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                if rel:
                    y += num()
                else:
                    y = num()
                ops.append(("line", x, y))
        elif cmd == "C":
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                c1x, c1y = pt(rel)
                c2x, c2y = pt(rel)
                ex, ey = pt(rel)
                ops.append(("cubic", c1x, c1y, c2x, c2y, ex, ey))
                last_cubic = (c2x, c2y, ex, ey)
        elif cmd == "S":
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                if last_cubic:
                    rcx, rcy = 2 * last_cubic[2] - last_cubic[0], 2 * last_cubic[3] - last_cubic[1]
                else:
                    rcx, rcy = x, y
                c2x, c2y = pt(rel)
                ex, ey = pt(rel)
                ops.append(("cubic", rcx, rcy, c2x, c2y, ex, ey))
                last_cubic = (c2x, c2y, ex, ey)
        elif cmd == "Q":
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                qx, qy = pt(rel)
                ex, ey = pt(rel)
                c1x = x + 2 / 3 * (qx - x)
                c1y = y + 2 / 3 * (qy - y)
                c2x = ex + 2 / 3 * (qx - ex)
                c2y = ey + 2 / 3 * (qy - ey)
                ops.append(("cubic", c1x, c1y, c2x, c2y, ex, ey))
                last_cubic = (c2x, c2y, ex, ey)
        elif cmd == "A":
            while i < len(tokens) and re.match(r"^[-.]?\d", tokens[i]):
                rx, ry = num(), num()
                rot = num()
                laf = int(num())
                sf = int(num())
                ex, ey = pt(rel)
                for sub in _arc_to_cubics(x, y, rx, ry, rot, laf, sf, ex, ey):
                    ops.append(("cubic", *sub))
                last_cubic = None
        else:
            break
    return ops, (x, y)


def _arc_to_cubics(x0, y0, rx, ry, rot_deg, large_arc, sweep, x1, y1):
    """SVG arc -> cubic bezier segments (endpoint parameterization)."""
    if x0 == x1 and y0 == y1:
        return []
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rot_deg)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    dx, dy = (x0 - x1) / 2, (y0 - y1) / 2
    x1p = cos_p * dx + sin_p * dy
    y1p = -sin_p * dx + cos_p * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s
        ry *= s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    if den == 0:
        return []
    coef = math.sqrt(max(0.0, num / den))
    if large_arc == sweep:
        coef = -coef
    cxp = coef * (rx * y1p / ry)
    cyp = -coef * (ry * x1p / rx)
    cx = cos_p * cxp - sin_p * cyp + (x0 + x1) / 2
    cy = sin_p * cxp + cos_p * cyp + (y0 + y1) / 2

    def angle(ux, uy, vx, vy):
        dot = ux * vx + uy * vy
        length = math.hypot(ux, uy) * math.hypot(vx, vy)
        if length == 0:
            return 0.0
        ang = math.acos(max(-1.0, min(1.0, dot / length)))
        if ux * vy - uy * vx < 0:
            ang = -ang
        return ang

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2 * math.pi
    segments = int(math.ceil(abs(dtheta) / (math.pi / 2)))
    if segments == 0:
        return []
    dtheta /= segments
    out = []
    t = theta1
    for _ in range(segments):
        t2 = t + dtheta
        alpha = 4 / 3 * math.tan(dtheta / 4)
        p0x = cx + rx * math.cos(t) * cos_p - ry * math.sin(t) * sin_p
        p0y = cy + rx * math.cos(t) * sin_p + ry * math.sin(t) * cos_p
        p1x = cx + rx * math.cos(t + dtheta / 2) * cos_p - ry * math.sin(t + dtheta / 2) * sin_p
        p1y = cy + rx * math.cos(t + dtheta / 2) * sin_p + ry * math.sin(t + dtheta / 2) * cos_p
        p2x = cx + rx * math.cos(t2) * cos_p - ry * math.sin(t2) * sin_p
        p2y = cy + rx * math.cos(t2) * sin_p + ry * math.sin(t2) * cos_p
        # arc midpoint + perpendicular derivative at midpoint
        mx = p0x + alpha * (p1x - p0x)
        my = p0y + alpha * (p1y - p0y)
        nx = p2x + alpha * (p1x - p2x)
        ny = p2y + alpha * (p1y - p2y)
        out.append((mx, my, nx, ny, p2x, p2y))
        t = t2
    # translate endpoint to x1,y1 exactly
    out[-1] = (*out[-1][:4], x1, y1)
    return out


def _custom_geom(ops, bounds_w, bounds_h, view_box):
    vw, vh = float(view_box[0]), float(view_box[1])
    sx = px(bounds_w) / vw
    sy = px(bounds_h) / vh

    def sx_(v):
        return int(round(v * sx))

    def sy_(v):
        return int(round(v * sy))

    geom = el("a:custGeom")
    geom.append(el("a:avLst"))
    geom.append(el("a:gdLst"))
    geom.append(el("a:ahLst"))
    geom.append(el("a:cxnLst"))
    geom.append(el("a:rect", l="0", t="0", r=str(px(bounds_w)), b=str(px(bounds_h))))
    path = el("a:path", w=str(px(bounds_w)), h=str(px(bounds_h)))
    for op in ops:
        if op[0] == "move":
            pt = el("a:moveTo")
            pt.append(el("a:pt", x=sx_(op[1]), y=sy_(op[2])))
            path.append(pt)
        elif op[0] == "line":
            ln = el("a:lnTo")
            ln.append(el("a:pt", x=sx_(op[1]), y=sy_(op[2])))
            path.append(ln)
        elif op[0] == "cubic":
            cb = el("a:cubicBezTo")
            cb.append(el("a:pt", x=sx_(op[1]), y=sy_(op[2])))
            cb.append(el("a:pt", x=sx_(op[3]), y=sy_(op[4])))
            cb.append(el("a:pt", x=sx_(op[5]), y=sy_(op[6])))
            path.append(cb)
        elif op[0] == "close":
            path.append(el("a:close"))
    geom.append(el("a:pathLst"))
    geom[-1].append(path)
    return geom


def render_shape(sp_tree, elem, ctx):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    eid = elem.get("elementId", f"el{ctx.new_id()}")
    theme_colors = ctx.doc["theme_colors"]
    shape_name = elem.get("shapeName", "rect")
    opacity = float(elem.get("opacity", 1))

    sp = el("p:sp")
    nv = el("p:nvSpPr")
    cpr = el("p:cNvPr", id=str(ctx.new_id()), name=eid)
    nv.append(cpr)
    nv.append(el("p:cNvSpPr"))
    nv.append(el("p:nvPr"))
    sp.append(nv)
    sppr = el("p:spPr")
    sppr.append(ooxml.xfrm(x, y, w, h,
                           rotation=elem.get("rotation"),
                           flip_h=elem.get("flip", [False, False])[0],
                           flip_v=elem.get("flip", [False, False])[1]))
    if shape_name == "custom":
        ops, _ = _parse_svg_path(elem.get("path") or "M0,0 L1,1",
                                 w, h)
        vb = elem.get("viewBox") or [w, h]
        sppr.append(_custom_geom(ops, w, h, vb))
    elif shape_name in _PRESET_SHAPES:
        prst = el("a:prstGeom", prst=_PRESET_SHAPES[shape_name])
        prst.append(_adj_avlst(elem.get("adjustments")))
        sppr.append(prst)
    else:
        ctx.warnings.append(f"shape {eid}: unknown preset {shape_name!r}, fallback rect")
        prst = el("a:prstGeom", prst="rect")
        prst.append(el("a:avLst"))
        sppr.append(prst)

    fill = elem.get("fill")
    if fill:
        f = ooxml.fill_element(fill, ctx.media_rel)
        if f is not None:
            if opacity < 1.0 and f.find(f"{{{A_NS}}}srgbClr") is not None:
                c = f.find(f"{{{A_NS}}}srgbClr")
                if c is not None:
                    c.append(el("a:alpha", val=int(round(opacity * 100000))))
            sppr.append(f)
    else:
        sppr.append(el("a:noFill"))
    if elem.get("border"):
        ln = ooxml.line_style(elem["border"])
        if ln is not None:
            if opacity < 1.0:
                c = ln.find(f"{{{A_NS}}}solidFill/{{{A_NS}}}srgbClr")
                if c is not None:
                    c.append(el("a:alpha", val=int(round(opacity * 100000))))
            sppr.append(ln)
    if elem.get("shadow"):
        eff = ooxml.outer_shadow(elem["shadow"])
        if eff is not None:
            sppr.append(eff)
    sp.append(sppr)
    sp_tree.append(sp)
    return sp


# ---------------------------------------------------------------------------
# line (connector)
# ---------------------------------------------------------------------------

def _catmull_rom(points):
    """points: [(x,y)...] -> list of cubic bezier segments [(c1x,c1y,c2x,c2y,ex,ey)]."""
    n = len(points)
    if n < 2:
        return []
    segs = []
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        segs.append((c1[0], c1[1], c2[0], c2[1], p2[0], p2[1]))
    return segs


def render_line(sp_tree, elem, ctx):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    eid = elem.get("elementId", f"el{ctx.new_id()}")
    points = []
    for pair in (elem.get("points") or "").split():
        parts = pair.split(",")
        if len(parts) == 2:
            try:
                points.append((float(parts[0]), float(parts[1])))
            except ValueError:
                pass
    if len(points) < 2:
        ctx.warnings.append(f"line {eid}: need >= 2 points")
        return
    vb = elem.get("viewBox") or [w, h]
    curve = elem.get("curve", "round")

    cxn = el("p:cxnSp")
    nv = el("p:nvCxnSpPr")
    cpr = el("p:cNvPr", id=str(ctx.new_id()), name=eid)
    nv.append(cpr)
    nv.append(el("p:cNvCxnSpPr"))
    nv.append(el("p:nvPr"))
    cxn.append(nv)
    sppr = el("p:spPr")
    sppr.append(ooxml.xfrm(x, y, w, h,
                           rotation=elem.get("rotation"),
                           flip_h=elem.get("flip", [False, False])[0],
                           flip_v=elem.get("flip", [False, False])[1]))

    vw, vh = float(vb[0]), float(vb[1])
    sx_ = px(w) / vw
    sy_ = px(h) / vh
    if curve == "smooth":
        segs = _catmull_rom(points)
        ops = [("move", points[0][0], points[0][1])]
        for seg in segs:
            ops.append(("cubic", *seg))
    else:
        ops = [("move", points[0][0], points[0][1])]
        for pt_ in points[1:]:
            ops.append(("line", pt_[0], pt_[1]))

    geom = el("a:custGeom")
    geom.append(el("a:avLst"))
    geom.append(el("a:gdLst"))
    geom.append(el("a:ahLst"))
    geom.append(el("a:cxnLst"))
    geom.append(el("a:rect", l="0", t="0", r=str(px(w)), b=str(px(h))))
    path = el("a:path", w=str(px(w)), h=str(px(h)))

    def emit(op):
        if op[0] == "move":
            n = el("a:moveTo")
            n.append(el("a:pt", x=int(round(op[1] * sx_)), y=int(round(op[2] * sy_))))
            path.append(n)
        elif op[0] == "line":
            n = el("a:lnTo")
            n.append(el("a:pt", x=int(round(op[1] * sx_)), y=int(round(op[2] * sy_))))
            path.append(n)
        elif op[0] == "cubic":
            n = el("a:cubicBezTo")
            for j in (1, 3, 5):
                n.append(el("a:pt", x=int(round(op[j] * sx_)), y=int(round(op[j + 1] * sy_))))
            path.append(n)

    for op in ops:
        emit(op)
    geom.append(el("a:pathLst"))
    geom[-1].append(path)
    sppr.append(geom)

    border = elem.get("border") or {"style": "solid", "width": 2, "color": "#1F2937"}
    ln = ooxml.line_style(border)
    if ln is not None:
        ln.set("cap", "rnd" if curve == "round" else "sng")
        arrow = elem.get("arrow") or [None, None]
        atypes = {"arrow": "triangle", "stealth": "stealth", "diamond": "diamond", "oval": "oval"}
        if arrow[0] and arrow[0] in atypes:
            ln.append(el("a:headEnd", type=atypes[arrow[0]], w="med", len="med"))
        if arrow[1] and arrow[1] in atypes:
            ln.append(el("a:tailEnd", type=atypes[arrow[1]], w="med", len="med"))
        sppr.append(ln)
    if elem.get("shadow"):
        eff = ooxml.outer_shadow(elem["shadow"])
        if eff is not None:
            sppr.append(eff)
    cxn.append(sppr)
    sp_tree.append(cxn)
    return cxn


# ---------------------------------------------------------------------------
# image
# ---------------------------------------------------------------------------

def _image_geometry(bounds, img_w, img_h, fit_mode, crop):
    """Compute (off_x, off_y, ext_w, ext_h, src_rect) honoring crop+fit.

    crop: {left, top, right, bottom} proportions applied to the source.
    fit: 'fill' stretch to bounds; 'cover' center-crop; 'contain' fit inside.
    Returns src_rect percentages (l,t,r,b as 0..1 values) and dst ext/off px.
    """
    bw, bh = bounds[2], bounds[3]
    l = float(crop.get("left", 0) or 0)
    t = float(crop.get("top", 0) or 0)
    r = float(crop.get("right", 0) or 0)
    b = float(crop.get("bottom", 0) or 0)
    # source rect after crop (proportional to full image)
    sl = l
    st = t
    sr = 1.0 - r
    sb = 1.0 - b
    if sr <= sl or sb <= st:
        return None
    src_w = sr - sl
    src_h = sb - st
    ratio_img = (img_w * src_w) / (img_h * src_h)
    ratio_box = bw / bh

    mode = (fit_mode or "cover")
    if mode == "fill":
        return (0, 0, bw, bh, (sl, st, r, b))
    if mode == "contain":
        if ratio_img > ratio_box:
            dw = bw
            dh = bh * ratio_box / ratio_img
        else:
            dh = bh
            dw = bw * ratio_img / ratio_box
        ox = (bw - dw) / 2
        oy = (bh - dh) / 2
        return (ox, oy, dw, dh, (sl, st, r, b))
    # cover: crop the source to the box aspect ratio (keeps full dst size)
    if ratio_img > ratio_box:
        # source too wide: crop left/right of the cropped source
        keep = ratio_box / ratio_img
        extra = (1.0 - keep) / 2
        l2 = sl + src_w * extra
        r2 = r + src_w * extra
        return (0, 0, bw, bh, (l2, st, r2, b))
    else:
        keep = ratio_img / ratio_box
        extra = (1.0 - keep) / 2
        t2 = st + src_h * extra
        b2 = b + src_h * extra
        return (0, 0, bw, bh, (sl, t2, r, b2))


def render_image(sp_tree, elem, ctx):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    eid = elem.get("elementId", f"el{ctx.new_id()}")
    src = elem.get("src")
    if not src:
        ctx.warnings.append(f"image {eid}: missing src")
        return
    fit = (elem.get("fit") or {}).get("mode", "cover")
    crop = elem.get("crop") or {}

    rid = ctx.media_rel(src)
    if rid is None:
        return
    # probe image natural size (only for local files)
    img_w, img_h = (None, None)
    if not src.startswith(("http://", "https://", "data:")):
        img_w, img_h = _image_natural_size(os.path.join(ctx.root_dir, src))
    if img_w is None:
        img_w, img_h = w, h

    geom = _image_geometry([x, y, w, h], img_w, img_h, fit, crop)
    if geom is None:
        ctx.warnings.append(f"image {eid}: invalid crop")
        return
    ox, oy, ew, eh, src_rect = geom

    pic = el("p:pic")
    nv = el("p:nvPicPr")
    cpr = el("p:cNvPr", id=str(ctx.new_id()), name=eid)
    nv.append(cpr)
    nv.append(el("p:cNvPicPr"))
    nv[-1].append(el("a:picLocks", noChangeAspect="1"))
    nv.append(el("p:nvPr"))
    pic.append(nv)

    blipfill = el("p:blipFill")
    blip = el("a:blip", **{f"r:embed": rid})
    if float(elem.get("opacity", 1)) < 1.0:
        blip.append(el("a:alphaModFix", val=int(round(float(elem.get("opacity", 1)) * 100000))))
    blipfill.append(blip)
    if any(abs(v) > 1e-9 for v in src_rect):
        blipfill.append(el("a:srcRect",
                           l=int(round(src_rect[0] * 100000)),
                           t=int(round(src_rect[1] * 100000)),
                           r=int(round(src_rect[2] * 100000)),
                           b=int(round(src_rect[3] * 100000))))
    stretch = el("a:stretch")
    stretch.append(el("a:fillRect"))
    blipfill.append(stretch)
    pic.append(blipfill)

    sppr = el("p:spPr")
    sppr.append(ooxml.xfrm(x + ox, y + oy, ew, eh,
                           rotation=elem.get("rotation"),
                           flip_h=elem.get("flip", [False, False])[0],
                           flip_v=elem.get("flip", [False, False])[1]))
    crop_shape = elem.get("cropShape") or {}
    cs_name = crop_shape.get("shapeName")
    if cs_name == "custom":
        ops, _ = _parse_svg_path(crop_shape.get("path") or "M0,0 L1,1", ew, eh)
        sppr.append(_custom_geom(ops, ew, eh, crop_shape.get("viewBox") or [ew, eh]))
    elif cs_name and cs_name in _PRESET_SHAPES:
        prst = el("a:prstGeom", prst=_PRESET_SHAPES[cs_name])
        prst.append(_adj_avlst(crop_shape.get("adjustments")))
        sppr.append(prst)
    else:
        prst = el("a:prstGeom", prst="rect")
        prst.append(el("a:avLst"))
        sppr.append(prst)
    if elem.get("border"):
        ln = ooxml.line_style(elem["border"])
        if ln is not None:
            sppr.append(ln)
    if elem.get("shadow"):
        eff = ooxml.outer_shadow(elem["shadow"])
        if eff is not None:
            sppr.append(eff)
    pic.append(sppr)
    sp_tree.append(pic)
    return pic


def _image_natural_size(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
            import struct

            w, h = struct.unpack(">II", head[16:24])
            return w, h
        if head[:3] == b"\xff\xd8\xff":
            # parse SOF markers
            with open(path, "rb") as fh:
                data = fh.read(262144)
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h = (data[i + 5] << 8) | data[i + 6]
                    w = (data[i + 7] << 8) | data[i + 8]
                    return w, h
                length = (data[i + 2] << 8) | data[i + 3]
                i += 2 + length
            return None, None
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return int.from_bytes(head[6:8], "little"), int.from_bytes(head[8:10], "little")
    except OSError:
        return None, None
    return None, None


# ---------------------------------------------------------------------------
# icon
# ---------------------------------------------------------------------------

def render_icon(sp_tree, elem, ctx):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    eid = elem.get("elementId", f"el{ctx.new_id()}")
    icon_name = elem.get("iconName", "")
    fill = elem.get("fill") or {"type": "solid", "color": "#1F2937"}
    color = fill.get("color", "#1F2937") if fill.get("type") in (None, "solid") else "#1F2937"
    if color.startswith("$"):
        color = ctx.doc["theme_colors"].get(color[1:], "#1F2937")
    if not icon_normalize(icon_name):
        ctx.warnings.append(f"icon {eid}: unknown icon {icon_name!r}, using neutral dot")
    svg = icon_svg(icon_name, color=color, size=int(max(1, round(min(w, h)))))
    rid = ctx.svg_media(svg, f"icon-{eid}")
    if rid is None:
        return

    pic = el("p:pic")
    nv = el("p:nvPicPr")
    cpr = el("p:cNvPr", id=str(ctx.new_id()), name=eid)
    nv.append(cpr)
    nv.append(el("p:cNvPicPr"))
    nv[-1].append(el("a:picLocks", noChangeAspect="1"))
    nv.append(el("p:nvPr"))
    pic.append(nv)

    blipfill = el("p:blipFill")
    blip = el("a:blip", **{f"r:embed": rid})
    ext = el("a:extLst")
    ext2 = el("a:ext", uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}")
    svg_blip = el("asvg:svgBlip", **{f"r:embed": rid})
    ext2.append(svg_blip)
    ext.append(ext2)
    blip.append(ext)
    blipfill.append(blip)
    stretch = el("a:stretch")
    stretch.append(el("a:fillRect"))
    blipfill.append(stretch)
    pic.append(blipfill)

    sppr = el("p:spPr")
    sppr.append(ooxml.xfrm(x, y, w, h,
                           rotation=elem.get("rotation"),
                           flip_h=elem.get("flip", [False, False])[0],
                           flip_v=elem.get("flip", [False, False])[1]))
    prst = el("a:prstGeom", prst="rect")
    prst.append(el("a:avLst"))
    sppr.append(prst)
    if elem.get("border"):
        ln = ooxml.line_style(elem["border"])
        if ln is not None:
            sppr.append(ln)
    if elem.get("shadow"):
        eff = ooxml.outer_shadow(elem["shadow"])
        if eff is not None:
            sppr.append(eff)
    pic.append(sppr)
    sp_tree.append(pic)
    return pic


# ---------------------------------------------------------------------------
# table
# ---------------------------------------------------------------------------

def _cell_border_spec(border):
    """BorderSpec -> (top, right, bottom, left) Border|None."""
    if border is None:
        return (None, None, None, None)
    if isinstance(border, list):
        if len(border) == 2:
            tb, lr = border
            return (tb, lr, tb, lr)
        if len(border) == 4:
            t, r, b, l = border
            return (t, r, b, l)
        return (border[0], border[0], border[0], border[0])
    return (border, border, border, border)


def render_table(sp_tree, elem, ctx):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    eid = elem.get("elementId", f"el{ctx.new_id()}")
    theme_colors = ctx.doc["theme_colors"]
    col_widths = [float(v) for v in (elem.get("columnWidths") or [])]
    row_heights = [float(v) for v in (elem.get("rowHeights") or [])]
    rows = elem.get("rows") or []
    if not col_widths:
        n = max((len(r) for r in rows), default=1)
        col_widths = [1.0 / n] * n
    if not row_heights:
        row_heights = [1.0 / len(rows)] * len(rows)
    if abs(sum(col_widths) - 1.0) > 0.01:
        s = sum(col_widths)
        col_widths = [v / s for v in col_widths]
    if abs(sum(row_heights) - 1.0) > 0.01 and row_heights:
        s = sum(row_heights)
        row_heights = [v / s for v in row_heights]

    style = elem.get("style")
    table_style = None
    if isinstance(style, str):
        key = style[1:] if style.startswith("$") else style
        table_style = ctx.doc["theme_table_styles"].get(key)
        if table_style is None:
            ctx.warnings.append(f"table {eid}: unknown theme tableStyle ${key}")
    elif isinstance(style, dict):
        table_style = style

    tbl = el("a:tbl")
    tblpr = el("a:tblPr", firstRow="0", bandRow="0")
    tblpr.append(el("a:tableStyleId"))
    tblpr[-1].text = "{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"
    tbl.append(tblpr)
    grid = el("a:tblGrid")
    for cw in col_widths:
        grid.append(el("a:gridCol", w=px(w * cw)))
    tbl.append(grid)

    n_rows = len(rows)
    n_cols = len(col_widths)
    # occupied grid tracking for merges
    occupied = [[False] * n_cols for _ in range(n_rows)]
    grid_map = [[None] * n_cols for _ in range(n_rows)]

    for ri, row in enumerate(rows):
        ci = 0
        for cell in row:
            while ci < n_cols and occupied[ri][ci]:
                ci += 1
            if ci >= n_cols:
                break
            if not isinstance(cell, dict):
                cell = {"text": str(cell) if cell is not None else ""}
            row_span = int(cell.get("rowSpan", 1) or 1)
            col_span = int(cell.get("colSpan", 1) or 1)
            for r2 in range(ri, min(ri + row_span, n_rows)):
                for c2 in range(ci, min(ci + col_span, n_cols)):
                    occupied[r2][c2] = True
            grid_map[ri][ci] = (row_span, col_span, cell)
            ci += col_span

    # continuation cells for vertical merges
    for ri in range(n_rows):
        ci = 0
        while ci < n_cols:
            if occupied[ri][ci] and grid_map[ri][ci] is None:
                grid_map[ri][ci] = (1, 1, None)
            ci += 1

    for ri, row in enumerate(rows):
        tr = el("a:tr", h=px(h * row_heights[min(ri, len(row_heights) - 1)]))
        ci = 0
        while ci < n_cols:
            info = grid_map[ri][ci]
            if info is None:
                ci += 1
                continue
            row_span, col_span, cell = info
            if cell is None:
                tc = el("a:tc")
                tcb = el("a:txBody")
                tcb.append(el("a:bodyPr", rtlCol="0"))
                tcb.append(el("a:lstStyle"))
                tcb.append(el("a:p"))
                tc.append(tcb)
                tcpr = el("a:tcPr", vMerge="1")
                tc.append(tcpr)
                tr.append(tc)
                ci += 1
                continue
            tc = el("a:tc")
            eff = model.effective_cell_style(
                cell, table_style, ctx.doc["theme_text_styles"],
                ri, ci, n_rows, n_cols, ctx.warnings, ctx.page)
            # auto font size adaption
            cell_h_px = h * row_heights[min(ri, len(row_heights) - 1)]
            if eff.get("fontSize") is None:
                eff["fontSize"] = max(8, min(18, cell_h_px * 0.34))
            txb = el("a:txBody")
            bpr = el("a:bodyPr", rtlCol="0", anchor=_ANCHOR.get(eff.get("vertAlign", "middle"), "ctr"))
            bpr.set("lIns", str(px(0)))
            bpr.set("tIns", str(px(0)))
            bpr.set("rIns", str(px(0)))
            bpr.set("bIns", str(px(0)))
            bpr.append(el("a:normAutofit"))
            txb.append(bpr)
            txb.append(el("a:lstStyle"))
            eff["textAlign"] = eff.get("textAlign", "center")
            paras = parse_rich_text(cell.get("text") or "")
            for para in paras:
                if not para["pPr"].get("text-align"):
                    para["pPr"]["text-align"] = eff.get("textAlign")
                txb.append(render_paragraph(para, eff, theme_colors, ctx.hyperlink_rel))
            tc.append(txb)
            tcpr = el("a:tcPr")
            if col_span > 1:
                tcpr.set("gridSpan", str(col_span))
            if row_span > 1:
                tcpr.set("rowSpan", str(row_span))
            # borders
            border = eff.get("border")
            t_b, r_b, b_b, l_b = _cell_border_spec(border)
            for side, key in (("lnT", t_b), ("lnR", r_b), ("lnB", b_b), ("lnL", l_b)):
                if key is None:
                    continue
                ln = ooxml.line_style(key)
                if ln is not None:
                    tcpr.append(ln)
            # fill
            fill = eff.get("fill")
            if fill:
                f = ooxml.fill_element(fill, ctx.media_rel)
                if f is not None:
                    tcpr.append(f)
            tc.append(tcpr)
            tr.append(tc)
            ci += 1
        tbl.append(tr)

    # table-level frame: wrap in a graphicFrame? Tables are a:tbl inside a
    # graphicFrame with graphicData uri table.
    gf = el("p:graphicFrame")
    nv = el("p:nvGraphicFramePr")
    cpr = el("p:cNvPr", id=str(ctx.new_id()), name=eid)
    nv.append(cpr)
    nv.append(el("p:cNvGraphicFramePr"))
    nv.append(el("p:nvPr"))
    gf.append(nv)
    gf.append(ooxml.xfrm(x, y, w, h,
                         rotation=elem.get("rotation"),
                         flip_h=elem.get("flip", [False, False])[0],
                         flip_v=elem.get("flip", [False, False])[1]))
    graphic = el("a:graphic")
    gd = el("a:graphicData", uri="http://schemas.openxmlformats.org/drawingml/2006/table")
    gd.append(tbl)
    graphic.append(gd)
    gf.append(graphic)
    sp_tree.append(gf)
    return gf


# ---------------------------------------------------------------------------
# background
# ---------------------------------------------------------------------------

def render_background(bg, ctx):
    """Build the <p:bg> element (inserted as the first child of cSld)."""
    if bg is None:
        return None
    b = el("p:bg")
    bpr = el("p:bgPr")
    ftype = bg.get("type", "solid")
    if ftype == "image":
        rid = ctx.media_rel(bg.get("src"))
        if rid is not None:
            blipfill = el("a:blipFill")
            blip = el("a:blip", **{f"r:embed": rid})
            if float(bg.get("opacity", 1)) < 1.0:
                blip.append(el("a:alphaModFix", val=int(round(float(bg.get("opacity", 1)) * 100000))))
            blipfill.append(blip)
            stretch = el("a:stretch")
            stretch.append(el("a:fillRect"))
            blipfill.append(stretch)
            bpr.append(blipfill)
    else:
        f = ooxml.fill_element(bg)
        if f is not None:
            bpr.append(f)
    bpr.append(el("a:effectLst"))
    b.append(bpr)
    return b
