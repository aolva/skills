"""Self-developed PPTD -> HTML preview generator.

Renders the deck as a single self-contained HTML file (no JS required, no
network). Written into the deck directory so relative media paths resolve,
and is safe to open in any browser.
"""

from __future__ import annotations

import html
import json
import math
import os
import re

from . import model
from .icons import ICONS, icon_mode, icon_svg, normalize as icon_normalize
from .model import resolve_fill


def _esc(v):
    return html.escape(str(v), quote=True)


def _hex(color):
    if not isinstance(color, str):
        return "#000000"
    if color.startswith("$"):
        return "#000000"
    return color


def _rgba(color, alpha=1.0):
    c = _hex(color).lstrip("#")
    if len(c) >= 8:
        try:
            alpha *= int(c[6:8], 16) / 255
        except ValueError:
            pass
        c = c[:6]
    if len(c) != 6:
        c = "000000"
    r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _fill_css(fill):
    if not fill:
        return ""
    ftype = fill.get("type", "solid")
    if ftype == "gradient":
        stops = fill.get("stops") or []
        if len(stops) < 2:
            return ""
        if fill.get("gradientType") == "radial":
            parts = ", ".join(f"{_rgba(s['color'])} {s.get('position', 0) * 100:.1f}%"
                              for s in stops)
            return f"background: radial-gradient(circle, {parts});"
        angle = fill.get("angle") or 0
        parts = ", ".join(f"{_rgba(s['color'])} {s.get('position', 0) * 100:.1f}%"
                          for s in stops)
        return f"background: linear-gradient({angle}deg, {parts});"
    return f"background: {_rgba(fill.get('color', '#000000'))};"


def _font_css(style):
    parts = []
    if style.get("fontFamily"):
        latin, ea = model.resolve_font_family(style["fontFamily"])
        parts.append(f"font-family: '{latin}', '{ea}', sans-serif;")
    if style.get("fontSize"):
        parts.append(f"font-size: {style['fontSize']}px;")
    if style.get("bold"):
        parts.append("font-weight: 700;")
    if style.get("italic"):
        parts.append("font-style: italic;")
    if style.get("color"):
        parts.append(f"color: {_rgba(style['color'])};")
    if style.get("lineHeight"):
        parts.append(f"line-height: {style['lineHeight']};")
    if style.get("letterSpacing"):
        parts.append(f"letter-spacing: {style['letterSpacing']}px;")
    return " ".join(parts)


def _border_css(border):
    if not border:
        return ""
    style = border.get("style", "solid")
    css_style = {"solid": "solid", "dash": "dashed", "dot": "dotted"}.get(style, "solid")
    width = border.get("width", 1)
    return f"border: {width}px {css_style} {_rgba(border.get('color', '#000000'))};"


def _preview_styles(elem, style):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    out = f"position:absolute; left:{x}px; top:{y}px; width:{w}px; height:{h}px;"
    if elem.get("rotation"):
        out += f" transform: rotate({elem['rotation']}deg); transform-origin: center;"
    if elem.get("flip", [False, False])[0]:
        out += " scaleX(-1);"
    if elem.get("opacity", 1) is not None and float(elem.get("opacity", 1)) < 1:
        out += f" opacity:{elem['opacity']};"
    return out


def _text_html(elem, style):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    content = elem.get("content") or {}
    text = content.get("text") or ""
    align = content.get("align") or ["left", "top"]
    ha = align[0] if isinstance(align, list) else "left"
    va = align[1] if isinstance(align, list) else "top"
    st = _preview_styles(elem, style)
    st += " overflow:hidden;"
    st += f" text-align:{ha}; display:flex; align-items:{'center' if va == 'middle' else ('flex-end' if va == 'bottom' else 'flex-start')};"
    if content.get("textDirection") == "vertical":
        st += " writing-mode:vertical-rl;"
    inner = _rich_text_to_html(text, style)
    return f'<div style="{st}">{inner}</div>'


def _rich_text_to_html(text, style):
    """Convert the PPTD rich-text subset to HTML (best effort)."""
    if "$" in text:
        text = model.resolve_text_color_inline(text, style.get("_colors") or {})
    s = text
    s = re.sub(r"<span style=\"([^\"]*)\">", lambda m: f"<span style=\"{m.group(1)}\">", s)
    for tag in ("strong", "em", "u", "s", "sup", "sub", "ul", "ol", "li", "a", "p", "br", "span"):
        s = re.sub(rf"<{tag}[^>]*>", lambda m, t=tag: _open_tag(t, m.group(0)), s)
        s = re.sub(rf"</{tag}>", lambda m, t=tag: _close_tag(t), s)
    return s


def _open_tag(tag, raw):
    if tag in ("strong", "em", "u", "s", "sup", "sub"):
        return f"<{tag}>"
    if tag == "br":
        return "<br/>"
    if tag in ("p", "span", "a"):
        return raw
    if tag == "li":
        return "<li style='margin-bottom:4px'>"
    return raw


def _close_tag(tag):
    return f"</{tag}>"


def _shape_html(elem):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    name = elem.get("shapeName", "rect")
    st = _preview_styles(elem, {})
    st += _fill_css(elem.get("fill"))
    st += _border_css(elem.get("border"))
    if name == "ellipse":
        st += " border-radius:50%;"
    elif name == "roundRect":
        adj = (elem.get("adjustments") or [16667])[0]
        st += f" border-radius:{max(1, w * adj / 100000)}px;"
    elif name in ("triangle", "diamond", "chevron", "rightArrow", "star5", "donut", "homePlate", "wedgeRectCallout"):
        st += f" clip-path: polygon(50% 0%, 100% 100%, 0% 100%);" if name == "triangle" else ""
        st += f" clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%);" if name == "diamond" else ""
        st += f" clip-path: polygon(0% 0%, 75% 0%, 100% 50%, 75% 100%, 0% 100%, 25% 50%);" if name == "chevron" else ""
        st += f" clip-path: polygon(0% 0%, 70% 0%, 100% 50%, 70% 100%, 0% 100%, 15% 50%);" if name == "rightArrow" else ""
        st += f" clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%);" if name == "star5" else ""
        st += " border-radius:50%;" if name == "donut" else ""
        if name == "donut":
            inner = max(1, w * 0.25)
            st = st.replace("background", "box-shadow: inset 0 0 0 0; -webkit-mask: radial-gradient(circle, transparent %dpx, black %dpx); background" % (inner, inner))
    if elem.get("shadow"):
        sh = elem["shadow"]
        off = sh.get("offset") or [0, 0]
        st += f" box-shadow: {off[0]}px {off[1]}px {sh.get('blur', 0)}px {_rgba(sh.get('color', '#000000'), 0.5)};"
    return f'<div style="{st}"></div>'


def _line_html(elem):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    vb = elem.get("viewBox") or [w, h]
    vw, vh = float(vb[0]), float(vb[1])
    points = []
    for pair in (elem.get("points") or "").split():
        p = pair.split(",")
        if len(p) == 2:
            points.append((float(p[0]) / vw * w, float(p[1]) / vh * h))
    if len(points) < 2:
        return ""
    border = elem.get("border") or {"color": "#1F2937", "width": 2}
    d = f"M {points[0][0]},{points[0][1]}"
    if elem.get("curve") == "smooth":
        pts = points
        for i in range(len(pts) - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1, p2, p3 = pts[i], pts[i + 1], (pts[i + 2] if i + 2 < len(pts) else pts[i + 1])
            c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
            c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
            d += f" C {c1[0]},{c1[1]} {c2[0]},{c2[1]} {p2[0]},{p2[1]}"
    else:
        for px_, py_ in points[1:]:
            d += f" L {px_},{py_}"
    dash = {"solid": "", "dash": "4 3", "dot": "1 3"}.get(border.get("style", "solid"), "")
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    arrow_attr = ""
    arr = elem.get("arrow") or [None, None]
    if arr[1]:
        arrow_attr += ' marker-end="url(#arr)"'
    if arr[0]:
        arrow_attr += ' marker-start="url(#arr)"'
    st = _preview_styles(elem, {})
    return (f'<svg style="{st}" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}">'
            f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{_hex(border.get("color", "#1F2937"))}"/></marker></defs>'
            f'<path d="{d}" fill="none" stroke="{_hex(border.get("color", "#1F2937"))}" '
            f'stroke-width="{border.get("width", 2)}"{dash_attr}{arrow_attr}/></svg>')


def _image_html(elem, root_dir):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    src = elem.get("src")
    if not src:
        return ""
    fit = (elem.get("fit") or {}).get("mode", "cover")
    st = _preview_styles(elem, {})
    st += f" object-fit: {fit}; border-radius:0;"
    st += _border_css(elem.get("border"))
    if elem.get("cropShape") and elem["cropShape"].get("shapeName") == "roundRect":
        adj = (elem["cropShape"].get("adjustments") or [16667])[0]
        st += f" border-radius:{max(1, w * adj / 100000)}px;"
    if elem.get("cropShape") and elem["cropShape"].get("shapeName") == "ellipse":
        st += " border-radius:50%;"
    if elem.get("shadow"):
        sh = elem["shadow"]
        off = sh.get("offset") or [0, 0]
        st += f" box-shadow: {off[0]}px {off[1]}px {sh.get('blur', 0)}px {_rgba(sh.get('color', '#000000'), 0.5)};"
    return f'<img src="{_esc(src)}" style="{st}"/>'


def _icon_html(elem):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    name = elem.get("iconName", "")
    fill = elem.get("fill") or {"type": "solid", "color": "#1F2937"}
    color = fill.get("color", "#1F2937")
    if color.startswith("$"):
        color = "#1F2937"
    st = _preview_styles(elem, {})
    svg = icon_svg(name, color=color, size=int(max(1, round(min(w, h)))))
    svg = svg.replace("<svg ", f"<svg style='{st}' width='{w}' height='{h}' ", 1)
    return svg


def _table_html(elem):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    rows = elem.get("rows") or []
    cw = elem.get("columnWidths") or []
    st = _preview_styles(elem, {})
    out = [f'<table style="{st}border-collapse:collapse; width:100%; height:100%;">']
    for ri, row in enumerate(rows):
        out.append("<tr>")
        for cell in row:
            if not isinstance(cell, dict):
                cell = {"text": str(cell) if cell is not None else ""}
            cs = "border:1px solid #CBD5E1;"
            if cell.get("fill"):
                cs += _fill_css(cell["fill"])
            if cell.get("bold"):
                cs += "font-weight:700;"
            if cell.get("color"):
                cs += f"color:{_rgba(cell['color'])};"
            if cell.get("fontSize"):
                cs += f"font-size:{cell['fontSize']}px;"
            align = cell.get("align") or ["center", "middle"]
            if isinstance(align, list):
                cs += f"text-align:{align[0]}; vertical-align:{align[1]};"
            span = ""
            if cell.get("colSpan", 1) > 1:
                span += f" colspan={cell['colSpan']}"
            if cell.get("rowSpan", 1) > 1:
                span += f" rowspan={cell['rowSpan']}"
            out.append(f'<td style="{cs}"{span}>')
            out.append(_rich_text_to_html(cell.get("text") or "", {}))
            out.append("</td>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _chart_html(elem):
    x, y, w, h = [float(v) for v in elem["bounds"]]
    st = _preview_styles(elem, {})
    data = elem.get("data") or {}
    cols = data.get("cols") or []
    rows = data.get("rows") or []
    series = elem.get("series") or []
    if not cols or not rows or not series:
        return f'<div style="{st}border:1px dashed #94A3B8;color:#64748B;display:flex;align-items:center;justify-content:center;">图表数据缺失</div>'
    first_type = series[0].get("type", "bar")
    # pick category col (first non-numeric) and numeric cols
    def is_num(col):
        return all(v is None or isinstance(v, (int, float)) or str(v).replace(".", "", 1).lstrip("-").isdigit()
                   for v in (r[cols.index(col)] for r in rows if len(r) > cols.index(col)))
    cat_idx = 0
    for i, c in enumerate(cols):
        if not is_num(c):
            cat_idx = i
            break
    nums = [i for i in range(len(cols)) if is_num(cols[i]) and i != cat_idx]
    if not nums:
        return f'<div style="{st}border:1px dashed #94A3B8;">无数值列</div>'
    cats = [r[cat_idx] if len(r) > cat_idx else "" for r in rows]
    vals = [[r[c] if len(r) > c else None for r in rows] for c in nums]

    palette = ["#2563EB", "#F59E0B", "#10B981", "#EF4444", "#8B5CF6", "#06B6D4"]
    if first_type == "pie":
        total = sum(v for v in vals[0] if v is not None)
        angle = 0
        parts = []
        for i, v in enumerate(vals[0]):
            if v is None:
                continue
            frac = v / total if total else 0
            a2 = angle + frac * 360
            lx, ly = 50 + 40 * math.cos(math.radians(a2)), 50 + 40 * math.sin(math.radians(a2))
            mx, my = 50 + 40 * math.cos(math.radians(angle)), 50 + 40 * math.sin(math.radians(angle))
            large = 1 if frac > 0.5 else 0
            parts.append(f'<path d="M50,50 L{mx},{my} A40,40 0 {large} 1 {lx},{ly} Z" fill="{palette[i % len(palette)]}"/>')
            angle = a2
        return f'<svg style="{st}" viewBox="0 0 100 100">{parts}</svg>'

    # bar / line / area
    pad = 30
    maxv = max((v for col in vals for v in col if v is not None), default=1)
    plot_w, plot_h = w - pad * 2, h - pad * 2
    n = max(len(cats), 1)
    slot = plot_w / n
    svg = []
    for ci, col in enumerate(vals):
        color = palette[ci % len(palette)]
        if first_type == "line":
            pts = []
            for i, v in enumerate(col):
                if v is None:
                    continue
                px_ = pad + slot * (i + 0.5)
                py_ = pad + plot_h - (v / maxv) * plot_h
                pts.append(f"{px_},{py_}")
            svg.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        elif first_type == "area":
            pts = []
            for i, v in enumerate(col):
                if v is None:
                    continue
                px_ = pad + slot * (i + 0.5)
                py_ = pad + plot_h - (v / maxv) * plot_h
                pts.append(f"{px_},{py_}")
            if pts:
                poly = f"M{pts[0]} L{' L'.join(pts[1:])} L{pad + slot * (n - 0.5)},{pad + plot_h} L{pad + slot * 0.5},{pad + plot_h} Z"
                svg.append(f'<path d="{poly}" fill="{color}" opacity="0.35"/>')
        else:
            bw = slot * 0.6
            for i, v in enumerate(col):
                if v is None:
                    continue
                bx = pad + slot * i + (slot - bw) / 2
                bh = (v / maxv) * plot_h
                svg.append(f'<rect x="{bx}" y="{pad + plot_h - bh}" width="{bw}" height="{bh}" fill="{color}"/>')
    # axes + category labels
    svg.append(f'<line x1="{pad}" y1="{pad + plot_h}" x2="{pad + plot_w}" y2="{pad + plot_h}" stroke="#CBD5E1" stroke-width="1"/>')
    for i, c in enumerate(cats):
        svg.append(f'<text x="{pad + slot * (i + 0.5)}" y="{pad + plot_h + 16}" text-anchor="middle" font-size="10" fill="#64748B">{_esc(c)}</text>')
    return f'<svg style="{st}" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{svg}</svg>'


def render_preview(doc, out_path):
    """Write a self-contained HTML preview for the deck."""
    theme = doc["theme"] or {}
    colors = theme.get("colors") or {}
    pages = []
    for pi, page in enumerate(doc["pages"], start=1):
        bg_style = _fill_css(page.get("background")) or "background:#FFFFFF;"
        els = []
        for elem in page.get("elements") or []:
            if not isinstance(elem, dict):
                continue
            try:
                etype = elem.get("elementType")
                if etype == "text":
                    style = model.effective_text_style(elem.get("content") or {}, doc["theme_text_styles"])
                    style["_colors"] = colors
                    els.append(_text_html(elem, style))
                elif etype == "shape":
                    els.append(_shape_html(elem))
                elif etype == "line":
                    els.append(_line_html(elem))
                elif etype == "image":
                    els.append(_image_html(elem, doc["root_dir"]))
                elif etype == "icon":
                    els.append(_icon_html(elem))
                elif etype == "table":
                    els.append(_table_html(elem))
                elif etype == "chart":
                    els.append(_chart_html(elem))
            except Exception:
                els.append(f'<div style="position:absolute;color:#DC2626;font-size:12px;left:{elem.get("bounds",[0,0,0,0])[0]}px;top:{elem.get("bounds",[0,0,0,0])[1]}px;">[渲染失败: {_esc(elem.get("elementType"))}]</div>')
        pages.append(f'<div class="slide" id="s{pi}" style="width:{doc["width"]}px;height:{doc["height"]}px;{bg_style}">{"" .join(els)}</div>')

    title = doc.get("title") or "Deck Preview"
    body = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{_esc(title)} — Aolva PPT 预览</title>
<style>
  body {{ background:#0f172a; margin:0; padding:24px; font-family:system-ui, sans-serif; }}
  .toolbar {{ position:sticky; top:0; z-index:10; background:#1e293b; border-radius:10px;
             padding:10px 16px; margin-bottom:18px; display:flex; gap:12px; align-items:center;
             color:#e2e8f0; box-shadow:0 4px 16px rgba(0,0,0,.4); }}
  .toolbar button {{ background:#3b82f6; color:#fff; border:0; border-radius:6px;
                    padding:6px 14px; cursor:pointer; }}
  .toolbar select {{ background:#0f172a; color:#e2e8f0; border:1px solid #334155; border-radius:6px; padding:6px; }}
  .slide {{ background:#fff; margin:0 auto 24px; box-shadow:0 8px 30px rgba(0,0,0,.5);
           overflow:hidden; position:relative; transform-origin:top center; }}
  .slide img {{ display:block; }}
  table {{ font-size:13px; }}
  td {{ padding:4px 8px; }}
</style>
</head>
<body>
<div class="toolbar">
  <strong>Aolva PPT 预览</strong>
  <span id="pageinfo" style="color:#94a3b8;">1 / {len(pages)} 页</span>
  <select id="pagesel" onchange="gotoPage(this.value)">
    {"".join(f'<option value="{i}">第 {i} 页</option>' for i in range(1, len(pages) + 1))}
  </select>
  <button onclick="zoom(-0.15)">缩小</button>
  <button onclick="zoom(0.15)">放大</button>
  <button onclick="zoom(0)">重置</button>
  <span id="zoomlabel" style="color:#94a3b8;">100%</span>
</div>
{"" .join(pages)}
<script>
  let scale = 1;
  function zoom(d) {{ scale = Math.max(0.2, Math.min(3, scale + d)); applyZoom(); }}
  function applyZoom() {{
    document.querySelectorAll('.slide').forEach(s => s.style.transform = `scale(${{scale}})`);
    document.getElementById('zoomlabel').textContent = Math.round(scale * 100) + '%';
  }}
  function gotoPage(i) {{ document.getElementById('s' + i).scrollIntoView({{behavior:'smooth'}}); }}
</script>
</body>
</html>"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return out_path
