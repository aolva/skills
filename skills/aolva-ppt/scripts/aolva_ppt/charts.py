"""Native OOXML charts (self-developed): bar / line / area / pie.

Implements PPTD v2 chart elements as editable PowerPoint charts with an
embedded worksheet. Other chart types (scatter, radar, treemap, sankey, ...)
are not yet supported and are skipped with a warning.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import ooxml
from .ooxml import NS, el
from . import model

A_NS = NS["a"]
C_NS = NS["c"]
R_NS = NS["r"]
S_NS = NS["s"]

_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

SUPPORTED = {"bar", "line", "area", "pie"}

_NUMFMT = {
    "0": "0",
    "0.0": "0.0",
    "0%": "0%",
    "0.0%": "0.0%",
    "#,##0": "#,##0",
    "0.0E+00": "0.00E+00",
}


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _is_numeric_col(rows, idx):
    for row in rows:
        if len(row) > idx and row[idx] is not None:
            if _num(row[idx]) is None:
                return False
    return True


def _series_specs(elem, data):
    """Normalize series: list of (type, name, col_index, fill, dataLabels)."""
    out = []
    cols = data.get("cols") or []
    rows = data.get("rows") or []
    series = elem.get("series") or []
    defaults = elem.get("seriesDefaults") or {}
    cat_idx = 0
    for i, c in enumerate(cols):
        if not _is_numeric_col(rows, i):
            cat_idx = i
            break
    numeric_idxs = [i for i in range(len(cols)) if _is_numeric_col(rows, i) and i != cat_idx]
    for si, s in enumerate(series):
        stype = s.get("type", "bar")
        if stype not in SUPPORTED:
            continue
        enc = s.get("encode") or {}
        col_idx = None
        for key in ("value", "y", "flow", "close"):
            ref = enc.get(key) if isinstance(enc, dict) else None
            if ref and ref in cols:
                col_idx = cols.index(ref)
                break
        if col_idx is None:
            # map through encode names
            if isinstance(enc, dict):
                for v in enc.values():
                    if v in cols and v not in (cols[cat_idx] if cols else None):
                        col_idx = cols.index(v)
                        break
        if col_idx is None:
            used = len(out)
            if used < len(numeric_idxs):
                col_idx = numeric_idxs[used]
        if col_idx is None:
            continue
        sname = cols[col_idx] if col_idx < len(cols) else f"系列{si + 1}"
        fill = s.get("fill")
        if fill is None:
            d = defaults.get(stype) or {}
            fill = d.get("fill")
        dl = s.get("dataLabels") or elem.get("dataLabels")
        out.append({
            "type": stype,
            "name": sname,
            "col": col_idx,
            "cat": cat_idx,
            "fill": fill,
            "dataLabels": dl,
        })
    return out


def _theme_color_cycle(theme_colors):
    order = []
    keys = [k for k in theme_colors.keys() if k not in ("latinFont", "eaFont")]
    for key in keys:
        order.append(theme_colors[key])
    order += ["#2563EB", "#F59E0B", "#10B981", "#EF4444", "#8B5CF6",
              "#06B6D4", "#F97316", "#EC4899", "#84CC16", "#6366F1"]
    return order


def _fill_hex(fill, cycle, theme_colors):
    if isinstance(fill, str):
        if fill.startswith("$"):
            return theme_colors.get(fill[1:], "#2563EB")
        return fill
    if isinstance(fill, dict) and fill.get("type", "solid") == "solid":
        c = fill.get("color", "#2563EB")
        if c.startswith("$"):
            return theme_colors.get(c[1:], "#2563EB")
        return c
    return cycle[0]


def build_worksheet(specs, data):
    """Return xlsx part bytes + (header_col_names, row_values) for chart refs."""
    rows = data.get("rows") or []
    cat = specs[0]["cat"] if specs else 0
    headers = [data.get("cols") or []]
    hdr = [headers[0][cat] if cat < len(headers[0]) else "分类"]
    for s in specs:
        hdr.append(s["name"])
    col_letter = lambda i: _col_letter(i + 1)
    sheet_rows = [hdr]
    for row in rows:
        vals = []
        vals.append(row[cat] if cat < len(row) else "")
        for s in specs:
            v = row[s["col"]] if s["col"] < len(row) else None
            vals.append(_num(v))
        sheet_rows.append(vals)
    n_rows = len(sheet_rows)

    # --- worksheet xml ---
    root = el("s:worksheet")
    dim = el("s:dimension", ref=f"A1:{_col_letter(len(hdr))}{n_rows}")
    root.append(dim)
    sd = el("s:sheetData")
    for ri, row in enumerate(sheet_rows, start=1):
        r = el("s:row", r=ri)
        for ci, val in enumerate(row, start=1):
            cell = el("s:c", r=f"{_col_letter(ci)}{ri}")
            if isinstance(val, (int, float)):
                cell.append(el("s:v", text=_fmt_num(val)))
            elif val is None:
                pass
            else:
                cell.set("t", "inlineStr")
                is_ = el("s:is")
                is_.append(el("s:t", text=str(val)))
                cell.append(is_)
            r.append(cell)
        sd.append(r)
    root.append(sd)
    ws_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    # --- workbook package ---
    ct = el("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
    ct.append(el("Default", Extension="rels",
                 ContentType="application/vnd.openxmlformats-package.relationships+xml"))
    ct.append(el("Default", Extension="xml", ContentType="application/xml"))
    ct.append(el("Override", PartName="/xl/workbook.xml",
                 ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"))
    ct.append(el("Override", PartName="/xl/worksheets/sheet1.xml",
                 ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"))
    ct.append(el("Override", PartName="/xl/styles.xml",
                 ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"))
    ct_xml = ET.tostring(ct, encoding="utf-8", xml_declaration=True)

    wb = el("s:workbook")
    sheets = el("s:sheets")
    sheets.append(el("s:sheet", name="Sheet1", sheetId="1", **{f"r:id": "rId1"}))
    wb.append(sheets)
    wb.append(el("s:calcPr", calcId="191029", fullCalcOnLoad="1"))
    wb_xml = ET.tostring(wb, encoding="utf-8", xml_declaration=True)

    wb_rels = el("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
    wb_rels.append(el("Relationship", Id="rId1",
                      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                      Target="worksheets/sheet1.xml"))
    wb_rels.append(el("Relationship", Id="rId2",
                      Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
                      Target="styles.xml"))
    wb_rels_xml = ET.tostring(wb_rels, encoding="utf-8", xml_declaration=True)

    styles = el("s:styleSheet")
    fonts = el("s:fonts", count="1")
    f = el("s:font")
    f.append(el("s:sz", val="11"))
    f.append(el("s:name", val="Calibri"))
    fonts.append(f)
    styles.append(fonts)
    fills = el("s:fills", count="1")
    fills.append(el("s:fill"))
    fills[-1].append(el("s:patternFill", patternType="none"))
    styles.append(fills)
    borders = el("s:borders", count="1")
    borders.append(el("s:border"))
    styles.append(borders)
    xfs = el("s:cellStyleXfs", count="1")
    xfs.append(el("s:xf", numFmtId="0", fontId="0", fillId="0", borderId="0"))
    styles.append(xfs)
    cellxfs = el("s:cellXfs", count="1")
    cellxfs.append(el("s:xf", numFmtId="0", fontId="0", fillId="0", borderId="0", xfId="0"))
    styles.append(cellxfs)
    styles_xml = ET.tostring(styles, encoding="utf-8", xml_declaration=True)

    parts = {
        "[Content_Types].xml": ct_xml,
        "xl/workbook.xml": wb_xml,
        "xl/_rels/workbook.xml.rels": wb_rels_xml,
        "xl/worksheets/sheet1.xml": ws_xml,
        "xl/styles.xml": styles_xml,
    }
    return parts, hdr, n_rows


def _col_letter(i):
    s = ""
    while i:
        i, rem = divmod(i - 1, 26)
        s = chr(65 + rem) + s
    return s


def _fmt_num(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return repr(v)


def _str_ref(f, values, is_num=False):
    """cat/val reference element with inline cache."""
    if is_num:
        ref = el("c:numRef")
        ref.append(el("c:f", text=f))
        cache = el("c:numCache")
        cache.append(el("c:formatCode", text="General"))
        cache.append(el("c:ptCount", val=len(values)))
        for i, v in enumerate(values):
            if v is None:
                continue
            pt = el("c:pt", idx=i)
            pt.append(el("c:v", text=_fmt_num(v)))
            cache.append(pt)
        ref.append(cache)
    else:
        ref = el("c:strRef")
        ref.append(el("c:f", text=f))
        cache = el("c:strCache")
        cache.append(el("c:ptCount", val=len(values)))
        for i, v in enumerate(values):
            if v is None:
                continue
            pt = el("c:pt", idx=i)
            pt.append(el("c:v", text=str(v)))
            cache.append(pt)
        ref.append(cache)
    return ref


def _ser_tx(name):
    tx = el("c:tx")
    ref = el("c:strRef")
    ref.append(el("c:f", text="Sheet1!$B$1"))
    cache = el("c:strCache")
    cache.append(el("c:ptCount", val="1"))
    pt = el("c:pt", idx="0")
    pt.append(el("c:v", text=name))
    cache.append(pt)
    ref.append(cache)
    tx.append(ref)
    return tx


def _datalabels(dl, chart_type, numfmt=None):
    dls = el("c:dLbls")
    dls.append(el("c:numFmt", formatCode=numfmt or "General", sourceLinked="0"))
    show_val = bool(dl) if dl is not None else False
    if isinstance(dl, dict):
        show_val = dl.get("show", False)
    if chart_type == "pie":
        dls.append(el("c:showPercent", val="1" if show_val else "0"))
        dls.append(el("c:showVal", val="0"))
        dls.append(el("c:showCategoryName", val="0"))
        dls.append(el("c:showLegendKey", val="0"))
    else:
        dls.append(el("c:showVal", val="1" if show_val else "0"))
        dls.append(el("c:showPercent", val="0"))
        dls.append(el("c:showCategoryName", val="0"))
        dls.append(el("c:showLegendKey", val="0"))
    dls.append(el("c:showLeaderLines", val="0"))
    return dls


def render_chart_frame(sp_tree, elem, ctx):
    """Render a chart element into the slide spTree."""
    x, y, w, h = [float(v) for v in elem["bounds"]]
    eid = elem.get("elementId", f"el{ctx.new_id()}")
    data = elem.get("data") or {}
    specs = _series_specs(elem, data)
    if not specs:
        ctx.warnings.append(f"chart {eid}: no supported series (bar/line/area/pie)")
        return
    rows = data.get("rows") or []
    cycle = _theme_color_cycle(ctx.doc["theme_colors"])
    theme_colors = ctx.doc["theme_colors"]

    ws_parts, hdr, n_rows = build_worksheet(specs, data)
    blob = _zip_bytes(ws_parts)
    chart_root = _chart_xml(elem, specs, hdr, n_rows, cycle, theme_colors, ctx)
    chart_idx = len(ctx.pkg.charts) + 1
    ctx.pkg.charts.append((chart_root, blob))

    chart_name = f"/ppt/charts/chart{chart_idx}.xml"
    slide_rid = ctx.rel(_RT + "/chart", f"../charts/chart{chart_idx}.xml")
    ctx.pkg.add_rels(chart_name, "rId1",
                     "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package",
                     f"../embeddings/Microsoft_Excel_Sheet{chart_idx}.xlsx")

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
    gd = el("a:graphicData", uri="http://schemas.openxmlformats.org/drawingml/2006/chart")
    chart_ref = el("c:chart", **{f"r:id": slide_rid})
    gd.append(chart_ref)
    graphic.append(gd)
    gf.append(graphic)
    sp_tree.append(gf)
    return gf


def _zip_bytes(parts):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _chart_xml(elem, specs, hdr, n_rows, cycle, theme_colors, ctx):
    space = el("c:chartSpace", )
    space.append(el("c:lang", val="zh-CN"))
    chart = el("c:chart")
    title = elem.get("title")
    if isinstance(title, dict):
        title = title.get("text")
    if title:
        t = el("c:title")
        tx = el("c:tx")
        rich = el("c:rich")
        rich.append(el("a:bodyPr"))
        rich.append(el("a:lstStyle"))
        p = el("a:p")
        r = el("a:r")
        r.append(el("a:rPr", lang="zh-CN", sz="1400", b="1"))
        r.append(el("a:t", text=str(title)))
        p.append(r)
        rich.append(p)
        tx.append(rich)
        t.append(tx)
        t.append(el("c:overlay", val="0"))
        chart.append(t)
    chart.append(el("c:autoTitleDeleted", val="0"))
    plot = el("c:plotArea")
    plot.append(el("c:layout"))

    data_dict = elem.get("data") or {}
    rows_data = data_dict.get("rows") or []

    first_type = specs[0]["type"]
    if first_type == "pie":
        pie = el("c:pieChart")
        pie.append(el("c:varyColors", val="1"))
        for i, s in enumerate(specs):
            ser = _ser(s, i, specs, hdr, n_rows, cycle, theme_colors, rows_data)
            pie.append(ser)
        if any(s["dataLabels"] for s in specs):
            pie.append(_datalabels(specs[0]["dataLabels"], "pie",
                                   _numfmt_of(specs[0]["dataLabels"])))
        plot.append(pie)
    else:
        for s in specs:
            s_type = s["type"]
            if s_type == "bar":
                node = el("c:barChart")
                node.append(el("c:barDir", val="col"))
                node.append(el("c:grouping", val="clustered"))
                node.append(el("c:varyColors", val="0"))
            elif s_type == "line":
                node = el("c:lineChart")
                node.append(el("c:grouping", val="standard"))
                node.append(el("c:varyColors", val="0"))
            else:
                node = el("c:areaChart")
                node.append(el("c:grouping", val="standard"))
                node.append(el("c:varyColors", val="0"))
            node.append(_ser(s, specs.index(s), specs, hdr, n_rows, cycle, theme_colors, rows_data))
            if s["dataLabels"]:
                node.append(_datalabels(s["dataLabels"], s_type, _numfmt_of(s["dataLabels"])))
            if s_type == "line":
                pass
            plot.append(node)
        cat_ax = el("c:catAx")
        cat_ax.append(el("c:axId", val="111111111"))
        sc = el("c:scaling")
        sc.append(el("c:orientation", val="minMax"))
        cat_ax.append(sc)
        cat_ax.append(el("c:delete", val="0"))
        cat_ax.append(el("c:axPos", val="b"))
        cat_ax.append(el("c:crossAx", val="222222222"))
        cat_ax.append(el("c:crosses", val="autoZero"))
        cat_ax.append(el("c:majorTickMark", val="out"))
        cat_ax.append(el("c:minorTickMark", val="none"))
        cat_ax.append(el("c:tickLblPos", val="nextTo"))
        cat_ax.append(_tx_pr())
        plot.append(cat_ax)
        val_ax = el("c:valAx")
        val_ax.append(el("c:axId", val="222222222"))
        sc = el("c:scaling")
        sc.append(el("c:orientation", val="minMax"))
        val_ax.append(sc)
        val_ax.append(el("c:delete", val="0"))
        val_ax.append(el("c:axPos", val="l"))
        val_ax.append(el("c:crossAx", val="111111111"))
        val_ax.append(el("c:crosses", val="autoZero"))
        val_ax.append(el("c:majorTickMark", val="out"))
        val_ax.append(el("c:minorTickMark", val="none"))
        val_ax.append(el("c:tickLblPos", val="nextTo"))
        val_ax.append(_tx_pr())
        plot.append(val_ax)
    chart.append(plot)

    legend = elem.get("legend")
    if legend is None or legend is True or (isinstance(legend, dict) and legend.get("show", True)):
        lg = el("c:legend")
        if isinstance(legend, dict):
            lg.append(el("c:legendPos", val=legend.get("position", "bottom")))
        else:
            lg.append(el("c:legendPos", val="bottom"))
        lg.append(el("c:overlay", val="0"))
        chart.append(lg)
    elif isinstance(legend, dict) and legend.get("show", True):
        lg = el("c:legend")
        lg.append(el("c:legendPos", val=legend.get("position", "bottom")))
        lg.append(el("c:overlay", val="0"))
        chart.append(lg)
    chart.append(el("c:plotVisOnly", val="1"))
    chart.append(el("c:dispBlanksAs", val="gap"))
    space.append(chart)
    if elem.get("fill") or elem.get("border"):
        sppr = el("c:spPr")
        if elem.get("fill"):
            f = ooxml.fill_element(elem["fill"])
            if f is not None:
                sppr.append(f)
        if elem.get("border"):
            ln = ooxml.line_style(elem["border"])
            if ln is not None:
                sppr.append(ln)
        space.append(sppr)
    return space


def _tx_pr():
    tx = el("c:txPr")
    tx.append(el("a:bodyPr", rot="0", spcFirstLastPara="0"))
    tx.append(el("a:lstStyle"))
    p = el("a:p")
    ppr = el("a:pPr")
    ppr.append(el("a:defRPr", sz="1000"))
    p.append(ppr)
    tx.append(p)
    return tx


def _numfmt_of(dl):
    if isinstance(dl, dict) and dl.get("numberFormat"):
        return _NUMFMT.get(dl["numberFormat"], "General")
    return "General"


def _ser(s, idx, specs, hdr, n_rows, cycle, theme_colors, rows_data):
    ser = el("c:ser")
    ser.append(el("c:idx", val=idx))
    ser.append(el("c:order", val=idx))
    tx = el("c:tx")
    ref = el("c:strRef")
    col = _col_letter(idx + 2)
    ref.append(el("c:f", text=f"Sheet1!${col}$1"))
    cache = el("c:strCache")
    cache.append(el("c:ptCount", val="1"))
    pt = el("c:pt", idx="0")
    pt.append(el("c:v", text=s["name"]))
    cache.append(pt)
    ref.append(cache)
    tx.append(ref)
    ser.append(tx)

    fill = _fill_hex(s["fill"], cycle, theme_colors)
    sppr = el("c:spPr")
    sppr.append(ooxml.solid_fill(fill))
    if s["type"] == "line":
        ln = el("a:ln", w="28575")
        ln.append(ooxml.solid_fill(fill))
        sppr.append(ln)
    ser.append(sppr)
    if s["type"] == "line":
        m = el("c:marker")
        m.append(el("c:symbol", val="circle"))
        m.append(el("c:size", val="5"))
        ser.append(m)

    cat_col = s["cat"]
    cat_values = []
    for row in rows_data:
        cat_values.append(row[cat_col] if cat_col < len(row) else "")
    ser.append(_str_ref(f"Sheet1!$A$2:$A${n_rows}", cat_values))

    col = _col_letter(idx + 2)
    val_values = []
    for row in rows_data:
        v = row[s["col"]] if s["col"] < len(row) else None
        val_values.append(_num(v))
    ser.append(_str_ref(f"Sheet1!${col}$2:${col}${n_rows}", val_values, is_num=True))
    return ser
