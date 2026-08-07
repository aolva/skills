#!/usr/bin/env python3
"""pptd_export.py — self-developed PPTD -> PPTX renderer (no Node, no browser,
no third-party assets; pure Python stdlib).

Usage:
    python3 pptd_export.py <deck.pptd|deck-dir> [--output out.pptx]
                           [--transition fade|none] [--force] [--no-notes]

Exit code 0 on success, 1 on error.
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aolva_ppt import model
from aolva_ppt import ooxml
from aolva_ppt.ooxml import NS, el
from aolva_ppt import elements
from aolva_ppt import charts
from aolva_ppt.pptx_writer import (
    Package, SlideContext, _content_types, _core_props, _app_props,
    _theme, _slide_master, _slide_layout, _notes_master, _pres_props,
    _notes_slide, _presentation_xml, _tostring,
)

A_NS = NS["a"]
P_NS = NS["p"]
R_NS = NS["r"]
_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def build_slide_xml(page, ctx, transition="fade"):
    slide = el("p:sld", )
    cld = el("p:cSld")
    bg = elements.render_background(page.get("background"), ctx)
    if bg is not None:
        cld.append(bg)
    tree = el("p:spTree")
    nv = el("p:nvGrpSpPr")
    nv.append(el("p:cNvPr", id="1", name=""))
    nv.append(el("p:cNvGrpSpPr"))
    nv.append(el("p:nvPr"))
    tree.append(nv)
    grp = el("p:grpSpPr")
    xf = el("a:xfrm")
    xf.append(el("a:off", x="0", y="0"))
    xf.append(el("a:ext", cx="0", cy="0"))
    xf.append(el("a:chOff", x="0", y="0"))
    xf.append(el("a:chExt", cx="0", cy="0"))
    grp.append(xf)
    tree.append(grp)
    for elem in page.get("elements") or []:
        if not isinstance(elem, dict):
            continue
        etype = elem.get("elementType")
        try:
            if etype == "text":
                elements.render_text_box(tree, elem, ctx)
            elif etype == "shape":
                elements.render_shape(tree, elem, ctx)
            elif etype == "line":
                elements.render_line(tree, elem, ctx)
            elif etype == "image":
                elements.render_image(tree, elem, ctx)
            elif etype == "icon":
                elements.render_icon(tree, elem, ctx)
            elif etype == "table":
                elements.render_table(tree, elem, ctx)
            elif etype == "chart":
                charts.render_chart_frame(tree, elem, ctx)
            else:
                ctx.warnings.append(f"unsupported elementType {etype!r}")
        except Exception as exc:  # renderer must never kill the whole deck
            ctx.warnings.append(f"element {elem.get('elementId', '?')} failed: {exc}")
    cld.append(tree)
    slide.append(cld)
    ovr = el("p:clrMapOvr")
    ovr.append(el("a:masterClrMapping"))
    slide.append(ovr)
    if transition == "fade":
        tr = el("p:transition", spd="med")
        tr.append(el("p:fade"))
        slide.append(tr)
    return slide


def export(manifest, output, transition="fade", force=False, no_notes=False):
    doc = model.load_document(manifest)
    for w in doc["warnings"]:
        print(f"[warn] {w}")
    if os.path.exists(output) and not force:
        raise SystemExit(
            f"output exists: {output} (pass --force to overwrite)")
    os.makedirs(os.path.dirname(os.path.abspath(output)) or ".", exist_ok=True)

    pkg = Package()
    pkg.add_rels("/ppt/slideLayouts/slideLayout1.xml", "rId1",
                 _RT + "/slideMaster", "../slideMasters/slideMaster1.xml")
    pkg.add_rels("/ppt/slideMasters/slideMaster1.xml", "rId1",
                 _RT + "/slideLayout", "../slideLayouts/slideLayout1.xml")
    pkg.add_rels("/ppt/slideMasters/slideMaster1.xml", "rId2",
                 _RT + "/theme", "../theme/theme1.xml")
    pkg.add_rels("/ppt/notesMasters/notesMaster1.xml", "rId1",
                 _RT + "/theme", "../theme/theme1.xml")

    slide_xmls = []
    n_notes = 0
    for i, page in enumerate(doc["pages"], start=1):
        ctx = SlideContext(pkg, doc, i, doc["root_dir"])
        ctx.add_slide_rels()
        ctx.page = page.get("src_path")
        slide = build_slide_xml(page, ctx, transition)
        slide_xmls.append(slide)
        pkg.add_part(f"/ppt/slides/slide{i}.xml", slide)
        if page.get("notes") and not no_notes:
            n_notes += 1
            ns = _notes_slide(i, page.get("notes"))
            pkg.add_part(f"/ppt/notesSlides/notesSlide{i}.xml", ns)
            pkg.add_rels(f"/ppt/notesSlides/notesSlide{i}.xml", "rId1",
                         _RT + "/slide", f"../slides/slide{i}.xml")
            ctx.rel(_RT + "/notesSlide", f"../notesSlides/notesSlide{i}.xml")

    for idx, (chart_root, _blob) in enumerate(pkg.charts, start=1):
        pkg.add_part(f"/ppt/charts/chart{idx}.xml", chart_root)

    # static parts
    n_slides = len(slide_xmls)
    pkg.add_part("/ppt/presentation.xml", _presentation_xml(
        [f"rId{3 + i}" for i in range(n_slides)], doc["width"], doc["height"]))
    for i in range(n_slides):
        pkg.add_rels("/ppt/presentation.xml", f"rId{3 + i}",
                     _RT + "/slide", f"slides/slide{i + 1}.xml")
    pkg.add_rels("/ppt/presentation.xml", "rId1", _RT + "/slideMaster", "slideMasters/slideMaster1.xml")
    pkg.add_rels("/ppt/presentation.xml", "rId2", _RT + "/notesMaster", "notesMasters/notesMaster1.xml")
    pkg.add_rels("/ppt/presentation.xml", "rId100", _RT + "/theme", "theme/theme1.xml")
    pkg.add_rels("/ppt/presentation.xml", "rId101", _RT + "/presProps", "presProps.xml")
    pkg.add_part("/ppt/presProps.xml", _pres_props())
    pkg.add_part("/ppt/theme/theme1.xml", _theme(doc))
    pkg.add_part("/ppt/slideMasters/slideMaster1.xml", _slide_master())
    pkg.add_part("/ppt/slideLayouts/slideLayout1.xml", _slide_layout())
    pkg.add_part("/ppt/notesMasters/notesMaster1.xml", _notes_master())
    pkg.add_part("/docProps/core.xml", _core_props(doc["title"]))
    pkg.add_part("/docProps/app.xml", _app_props(doc["title"]))
    pkg.add_part("/_rels/.rels", el("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships"))
    pkg.parts["/_rels/.rels"] = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>'
        b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        b'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        b'</Relationships>'
    )

    ct = _content_types(pkg, n_slides, n_notes, len(pkg.charts))
    pkg.parts["/[Content_Types].xml"] = ct

    pkg.write(output)
    print(f"exported: {output}")
    print(f"slides: {n_slides}, media: {len(pkg.media)}, charts: {len(pkg.charts)}, notes: {n_notes}")
    if ctx.warnings:
        print("[warnings]")
        for w in ctx.warnings:
            print(f"  - {w}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="PPTD -> PPTX (self-developed)")
    ap.add_argument("input", help=".pptd manifest or project directory")
    ap.add_argument("--output", "-o", default=None)
    ap.add_argument("--transition", choices=["fade", "none"], default="fade")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-notes", action="store_true")
    args = ap.parse_args(argv)

    manifest = model.find_pptd_in_dir(args.input)
    if args.output is None:
        base = os.path.splitext(os.path.basename(manifest))[0]
        args.output = os.path.join(os.path.dirname(os.path.abspath(manifest)),
                                   f"{base}.pptx")
    try:
        return export(manifest, args.output, args.transition, args.force, args.no_notes)
    except model.PPTDError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
