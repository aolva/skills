"""PPTD -> PPTX OOXML writer (self-developed, stdlib only).

Implements the PPTD v2 rendering pipeline against the OOXML PresentationML
specification: package assembly (content types / rels), theme / master /
layout / notes parts, and per-element rendering (text, shape, line, image,
icon, table, chart, background, transitions, speaker notes).

No external assets are referenced: fonts are declared but not embedded, icons
are generated as inline SVG, charts are native OOXML charts with embedded
workbook data.
"""

from __future__ import annotations

import io
import math
import os
import re
import zipfile
import xml.etree.ElementTree as ET

from . import model
from . import ooxml
from .ooxml import NS, el, px
from .icons import icon_svg

A_NS = NS["a"]
P_NS = NS["p"]
R_NS = NS["r"]

_RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_CT_PRES = "application/vnd.openxmlformats-officedocument.presentationml."


# ---------------------------------------------------------------------------
# package assembly
# ---------------------------------------------------------------------------

class MediaStore:
    def __init__(self):
        self.items = []  # list of (ext, content_type, bytes, key)

    def add(self, data, ext, content_type, key):
        self.items.append((ext, content_type, data, key))
        return len(self.items) - 1

    def key_for(self, data):
        import hashlib

        return hashlib.sha256(data).hexdigest()[:24]


class Package:
    """Minimal OPC package: parts + rels, written as a zip."""

    def __init__(self):
        self.parts = {}  # name -> ET.Element (xml serialized at write time)
        self.rels = {}  # part_name -> list[(rid, type, target, target_mode)]
        self.media = []  # list of (ext, bytes)
        self.charts = []  # list of (chart_root, xlsx_blob)

    def add_part(self, name, root):
        self.parts[name] = root

    def add_rels(self, part_name, rid, rtype, target, mode=None):
        self.rels.setdefault(part_name, []).append((rid, rtype, target, mode))

    def write(self, path):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, root in sorted(self.parts.items(), key=lambda kv: kv[0]):
                if isinstance(root, bytes):
                    zf.writestr(name.lstrip("/"), root)
                else:
                    zf.writestr(name.lstrip("/"), _tostring(root))
            for idx, (ext, data) in enumerate(self.media, start=1):
                zf.writestr(f"ppt/media/image{idx}.{ext}", data)
            for idx, (_croot, blob) in enumerate(self.charts, start=1):
                zf.writestr(f"ppt/embeddings/Microsoft_Excel_Sheet{idx}.xlsx", blob)
            for name, rels in sorted(self.rels.items()):
                root = el("Relationships", xmlns="http://schemas.openxmlformats.org/package/2006/relationships")
                for rid, rtype, target, mode in rels:
                    attrs = {"Id": rid, "Type": rtype, "Target": target}
                    if mode:
                        attrs["TargetMode"] = mode
                    root.append(el("Relationship", **attrs))
                dir_ = name.rsplit("/", 1)[0]
                rels_name = f"{dir_}/_rels/{name.rsplit('/', 1)[-1]}.rels".lstrip("/")
                zf.writestr(rels_name, _tostring(root))


def _tostring(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# static parts
# ---------------------------------------------------------------------------

def _content_types(pkg, n_slides, n_notes, has_charts):
    root = el("Types", xmlns=_CT)
    defaults = {
        "rels": "application/vnd.openxmlformats-package.relationships+xml",
        "xml": "application/xml",
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "gif": "image/gif",
        "svg": "image/svg+xml",
    }
    for ext, ctype in defaults.items():
        root.append(el("Default", Extension=ext, ContentType=ctype))
    overrides = {
        "/docProps/core.xml": "application/vnd.openxmlformats-package.core-properties+xml",
        "/docProps/app.xml": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
        "/ppt/presentation.xml": _CT_PRES + "presentation.main+xml",
        "/ppt/presProps.xml": _CT_PRES + "presProps+xml",
        "/ppt/theme/theme1.xml": _CT_PRES + "theme+xml",
        "/ppt/slideMasters/slideMaster1.xml": _CT_PRES + "slideMaster+xml",
        "/ppt/slideLayouts/slideLayout1.xml": _CT_PRES + "slideLayout+xml",
        "/ppt/notesMasters/notesMaster1.xml": _CT_PRES + "notesMaster+xml",
    }
    for i in range(1, n_slides + 1):
        overrides[f"/ppt/slides/slide{i}.xml"] = _CT_PRES + "slide+xml"
    for i in range(1, n_notes + 1):
        overrides[f"/ppt/notesSlides/notesSlide{i}.xml"] = _CT_PRES + "notesSlide+xml"
    n_charts = has_charts if isinstance(has_charts, int) else 0
    if n_charts:
        for i in range(1, n_charts + 1):
            overrides[f"/ppt/embeddings/Microsoft_Excel_Sheet{i}.xlsx"] = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            overrides[f"/ppt/charts/chart{i}.xml"] = (
                "application/vnd.openxmlformats-officedocument.drawingml.chart+xml"
            )
    for name in overrides:
        root.append(el("Override", PartName=name, ContentType=overrides[name]))
    return root


def _core_props(title):
    root = el("cp:coreProperties",
              )
    if title:
        root.append(el("dc:title", text=title))
    root.append(el("dc:creator", text="Aolva PPT Skill"))
    root.append(el("cp:lastModifiedBy", text="Aolva PPT Skill"))
    root.append(el("dcterms:created", **{"xsi:type": "dcterms:W3CDTF"}))
    root[-1].text = "2026-01-01T00:00:00Z"
    root.append(el("dcterms:modified", **{"xsi:type": "dcterms:W3CDTF"}))
    root[-1].text = "2026-01-01T00:00:00Z"
    return root


def _app_props(title):
    root = el("ep:Properties",
              )
    root.append(el("ep:Application", text="Aolva PPT Skill"))
    root.append(el("ep:DocSecurity", text="0"))
    root.append(el("ep:ScaleCrop", text="false"))
    app_info = el("ep:HeadingPairs")
    vec = el("vt:vector", size="2", baseType="variant")
    v1 = el("vt:variant")
    v1.append(el("vt:lpstr", text="TitlesOfParts"))
    v2 = el("vt:variant")
    v2.append(el("vt:i4", text="1"))
    vec.append(v1)
    vec.append(v2)
    app_info.append(vec)
    root.append(app_info)
    titles = el("ep:TitlesOfParts")
    tvec = el("vt:vector", size="1", baseType="lpstr")
    t = el("vt:lpstr", text=title or "Presentation")
    tvec.append(t)
    titles.append(tvec)
    root.append(titles)
    return root


def _theme(doc):
    colors = doc["theme_colors"]
    c = colors or {}

    def accent(i):
        val = c.get(f"accent{i}", "#2563EB" if i == 1 else "#64748B")
        m = re.match(r"^#([0-9A-Fa-f]{6})", val)
        return m.group(1).upper() if m else "2563EB"

    theme = el("a:theme", name="Aolva")
    els = el("a:themeElements")
    scheme = el("a:clrScheme", name="Aolva")
    scheme.append(el("a:dk1"))
    scheme[-1].append(el("a:srgbClr", val="000000"))
    scheme.append(el("a:lt1"))
    scheme[-1].append(el("a:srgbClr", val="FFFFFF"))
    scheme.append(el("a:dk2"))
    scheme[-1].append(el("a:srgbClr", val="44546A"))
    scheme.append(el("a:lt2"))
    scheme[-1].append(el("a:srgbClr", val="E7E6E6"))
    for i in range(1, 7):
        scheme.append(el("a:accent%d" % i))
        scheme[-1].append(el("a:srgbClr", val=accent(i)))
    scheme.append(el("a:hlink"))
    scheme[-1].append(el("a:srgbClr", val="0563C1"))
    scheme.append(el("a:folHlink"))
    scheme[-1].append(el("a:srgbClr", val="954F72"))
    els.append(scheme)

    latin = c.get("latinFont", "MiSans")
    ea = c.get("eaFont", "MiSans")
    fs = el("a:fontScheme", name="Aolva")
    for tag in ("a:majorFont", "a:minorFont"):
        node = el(tag)
        node.append(el("a:latin", typeface=latin))
        node.append(el("a:ea", typeface=ea))
        node.append(el("a:cs", typeface=""))
        fs.append(node)
    els.append(fs)

    fmt = el("a:fmtScheme", name="Aolva")
    fill_lst = el("a:fillStyleLst")
    sf = el("a:solidFill")
    sf.append(el("a:schemeClr", val="phClr"))
    fill_lst.append(sf)
    gf1 = el("a:gradFill", rotWithShape="1")
    g1 = el("a:gsLst")
    for pos, tint, sat in ((0, 50000, 300000), (35000, 37000, 300000), (100000, 15000, 350000)):
        gs = el("a:gs", pos=pos)
        sc = el("a:schemeClr", val="phClr")
        sc.append(el("a:tint", val=tint))
        sc.append(el("a:satMod", val=sat))
        gs.append(sc)
        g1.append(gs)
    gf1.append(g1)
    gf1.append(el("a:lin", ang="16200000", scaled="1"))
    fill_lst.append(gf1)
    gf2 = el("a:gradFill", rotWithShape="1")
    g2 = el("a:gsLst")
    for pos, shade, sat in ((0, 51000, 130000), (80000, 93000, 130000), (100000, 94000, 135000)):
        gs = el("a:gs", pos=pos)
        sc = el("a:schemeClr", val="phClr")
        sc.append(el("a:shade", val=shade))
        sc.append(el("a:satMod", val=sat))
        gs.append(sc)
        g2.append(gs)
    gf2.append(g2)
    gf2.append(el("a:lin", ang="16200000", scaled="0"))
    fill_lst.append(gf2)
    fmt.append(fill_lst)

    ln_lst = el("a:lnStyleLst")
    for w in (9525, 25400, 38100):
        ln = el("a:ln", w=w, cap="flat", cmpd="sng", algn="ctr")
        s = el("a:solidFill")
        sc = el("a:schemeClr", val="phClr")
        if w == 9525:
            sc.append(el("a:shade", val="95000"))
            sc.append(el("a:satMod", val="105000"))
        s.append(sc)
        ln.append(s)
        ln.append(el("a:prstDash", val="solid"))
        ln_lst.append(ln)
    fmt.append(ln_lst)

    eff_lst = el("a:effectStyleLst")
    for _ in range(3):
        e = el("a:effectStyle")
        e.append(el("a:effectLst"))
        eff_lst.append(e)
    fmt.append(eff_lst)

    bg_lst = el("a:bgFillStyleLst")
    s1 = el("a:solidFill")
    s1.append(el("a:schemeClr", val="phClr"))
    bg_lst.append(s1)
    s2 = el("a:solidFill")
    sc2 = el("a:schemeClr", val="phClr")
    sc2.append(el("a:tint", val="95000"))
    sc2.append(el("a:satMod", val="170000"))
    s2.append(sc2)
    bg_lst.append(s2)
    gf3 = el("a:gradFill", rotWithShape="1")
    g3 = el("a:gsLst")
    for pos, ops in ((0, (93000, 150000, 98000, 102000)),
                     (50000, (98000, 130000, 90000, 103000)),
                     (100000, (63000, 120000, None, None))):
        gs = el("a:gs", pos=pos)
        sc = el("a:schemeClr", val="phClr")
        sc.append(el("a:tint", val=ops[0]))
        sc.append(el("a:satMod", val=ops[1]))
        if ops[2] is not None:
            sc.append(el("a:shade", val=ops[2]))
        if ops[3] is not None:
            sc.append(el("a:lumMod", val=ops[3]))
        gs.append(sc)
        g3.append(gs)
    gf3.append(g3)
    gf3.append(el("a:lin", ang="16200000", scaled="0"))
    bg_lst.append(gf3)
    fmt.append(bg_lst)
    els.append(fmt)
    theme.append(els)
    theme.append(el("a:objectDefaults"))
    theme.append(el("a:extraClrSchemeLst"))
    return theme


def _placeholder_sp(id_, name, type_, x, y, cx, cy, geom):
    sp = el("p:sp")
    nv = el("p:nvSpPr")
    cpr = el("p:cNvPr", id=id_, name=name)
    nv.append(cpr)
    nv.append(el("p:cNvSpPr"))
    nv.append(el("p:nvPr"))
    nv[-1].append(el("p:ph", type=type_))
    sp.append(nv)
    sppr = el("p:spPr")
    xf = el("a:xfrm")
    xf.append(el("a:off", x=x, y=y))
    xf.append(el("a:ext", cx=cx, cy=cy))
    sppr.append(xf)
    sppr.append(el("a:prstGeom", prst=geom))
    sppr[-1].append(el("a:avLst"))
    sp.append(sppr)
    return sp


def _sp_tree_with_placeholders(ph_specs):
    sp_tree = el("p:spTree")
    nv = el("p:nvGrpSpPr")
    nv.append(el("p:cNvPr", id="1", name=""))
    nv.append(el("p:cNvGrpSpPr"))
    nv.append(el("p:nvPr"))
    sp_tree.append(nv)
    grp = el("p:grpSpPr")
    xf = el("a:xfrm")
    xf.append(el("a:off", x="0", y="0"))
    xf.append(el("a:ext", cx="0", cy="0"))
    xf.append(el("a:chOff", x="0", y="0"))
    xf.append(el("a:chExt", cx="0", cy="0"))
    grp.append(xf)
    sp_tree.append(grp)
    for spec in ph_specs:
        sp_tree.append(_placeholder_sp(*spec))
    return sp_tree


def _slide_master():
    master = el("p:sldMaster", )
    cld = el("p:cSld")
    bg = el("p:bg")
    bgpr = el("p:bgPr")
    sf = el("a:solidFill")
    sf.append(el("a:srgbClr", val="FFFFFF"))
    bgpr.append(sf)
    bgpr.append(el("a:effectLst"))
    bg.append(bgpr)
    cld.append(bg)
    cld.append(_sp_tree_with_placeholders([
        (2, "Title 1", "title", px(548640), px(0.5), px(9144000), px(2057400), "rect"),
        (3, "Text Placeholder 1", "body", px(548640), px(0.5), px(9144000), px(6858000), "rect"),
    ]))
    master.append(cld)
    master.append(el("p:clrMap", bg1="lt1", tx1="dk1", bg2="lt2", tx2="dk2",
                     accent1="accent1", accent2="accent2", accent3="accent3",
                     accent4="accent4", accent5="accent5", accent6="accent6",
                     hlink="hlink", folHlink="folHlink"))
    id_lst = el("p:sldLayoutIdLst")
    id_lst.append(el("p:sldLayoutId", id="1", **{f"r:id": "rId1"}))
    master.append(id_lst)
    tx = el("p:txStyles")

    def style_block(tag, size, font_marker):
        node = el(tag)
        lvl = el("a:lvl1pPr")
        dpr = el("a:defRPr", sz=size)
        sf = el("a:solidFill")
        sf.append(el("a:schemeClr", val="tx1"))
        dpr.append(sf)
        dpr.append(el("a:latin", typeface=font_marker))
        dpr.append(el("a:ea", typeface=font_marker))
        dpr.append(el("a:cs", typeface=font_marker))
        lvl.append(dpr)
        node.append(lvl)
        return node

    tx.append(style_block("p:titleStyle", "4400", "+mj-lt"))
    tx.append(style_block("p:bodyStyle", "1800", "+mn-lt"))
    tx.append(style_block("p:otherStyle", "1800", "+mn-lt"))
    master.append(tx)
    return master


def _slide_layout():
    layout = el("p:sldLayout", type="blank", preserve="1",
                )
    cld = el("p:cSld")
    cld.set("name", "Blank")
    cld.append(_sp_tree_with_placeholders([]))
    layout.append(cld)
    ovr = el("p:clrMapOvr")
    ovr.append(el("a:masterClrMapping"))
    layout.append(ovr)
    return layout


def _notes_master():
    nm = el("p:notesMaster", )
    cld = el("p:cSld")
    cld.append(_sp_tree_with_placeholders([
        (2, "Slide Image Placeholder 1", "sldImg", 0, 0, px(6858000), px(4114800), "rect"),
        (3, "Notes Placeholder 1", "body", px(914400), px(4724400), px(5943600), px(3987800), "rect"),
    ]))
    nm.append(cld)
    nm.append(el("p:clrMap", bg1="lt1", tx1="dk1", bg2="lt2", tx2="dk2",
                 accent1="accent1", accent2="accent2", accent3="accent3",
                 accent4="accent4", accent5="accent5", accent6="accent6",
                 hlink="hlink", folHlink="folHlink"))
    nm.append(el("p:notesStyle"))
    return nm


def _pres_props():
    return el("p:presentationPr")


def _notes_slide(slide_id, notes_text):
    ns = el("p:notes", )
    cld = el("p:cSld")
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
    sp = _placeholder_sp(2, "Slide Image Placeholder 1", "sldImg", 0, 0, px(6858000), px(4114800), "rect")
    tree.append(sp)
    body = el("p:sp")
    nvb = el("p:nvSpPr")
    nvb.append(el("p:cNvPr", id="3", name="Notes Placeholder 1"))
    nvb.append(el("p:cNvSpPr"))
    nvb.append(el("p:nvPr"))
    nvb[-1].append(el("p:ph", type="body", idx="1"))
    body.append(nvb)
    sppr = el("p:spPr")
    xfb = el("a:xfrm")
    xfb.append(el("a:off", x=px(914400), y=px(4724400)))
    xfb.append(el("a:ext", cx=px(5943600), cy=px(3987800)))
    sppr.append(xfb)
    sppr.append(el("a:prstGeom", prst="rect"))
    sppr[-1].append(el("a:avLst"))
    body.append(sppr)
    txb = el("p:txBody")
    body_pr = el("a:bodyPr", rtlCol="0")
    body_pr.append(el("a:normAutofit"))
    txb.append(body_pr)
    txb.append(el("a:lstStyle"))
    for line in (notes_text or "").split("\n"):
        p = el("a:p")
        r = el("a:r")
        r.append(el("a:rPr", lang="zh-CN", sz="1800", dirty="0"))
        r.append(el("a:t", text=line))
        p.append(r)
        txb.append(p)
    body.append(txb)
    tree.append(body)
    cld.append(tree)
    ns.append(cld)
    ovr = el("p:clrMapOvr")
    ovr.append(el("a:masterClrMapping"))
    ns.append(ovr)
    return ns


def _presentation_xml(slide_ids, width, height):
    pres = el("p:presentation", saveSubsetFonts="1",
              )
    m_id = el("p:sldMasterIdLst")
    m_id.append(el("p:sldMasterId", id="2147483648", **{f"r:id": "rId1"}))
    pres.append(m_id)
    notes = el("p:notesMasterIdLst")
    notes.append(el("p:notesMasterId", **{f"r:id": "rId2"}))
    pres.append(notes)
    s_id = el("p:sldIdLst")
    for i, sid in enumerate(slide_ids, start=1):
        s_id.append(el("p:sldId", id=str(256 + i * 4), **{f"r:id": sid}))
    pres.append(s_id)
    pres.append(el("p:sldSz", cx=px(width), cy=px(height)))
    pres.append(el("p:notesSz", cx="6858000", cy="9144000"))
    dts = el("p:defaultTextStyle")
    for lvl, size in ((1, 4400), (2, 3200), (3, 2600), (4, 2000), (5, 1800)):
        lpr = el("a:lvl%dPPr" % lvl)
        lpr.append(el("a:defRPr", sz=size))
        dts.append(lpr)
    pres.append(dts)
    return pres


# ---------------------------------------------------------------------------
# slide rendering context
# ---------------------------------------------------------------------------

class SlideContext:
    def __init__(self, pkg, doc, slide_index, root_dir):
        self.pkg = pkg
        self.doc = doc
        self.root_dir = root_dir
        self.slide_index = slide_index
        self.next_id = 100
        self.next_rel = 2
        self.warnings = []
        self.chart_seq = []
        self.media_by_key = {}
        self.media_files = {}  # src -> rId
        self.rel_ids = {}  # rtype+target -> rId
        self.slide_xml = None
        self.sp_tree = None

    # -- ids / rels -----------------------------------------------------
    def new_id(self):
        self.next_id += 1
        return self.next_id

    def rel(self, rtype, target, mode=None):
        key = (rtype, target, mode)
        if key in self.rel_ids:
            return self.rel_ids[key]
        rid = f"rId{self.next_rel}"
        self.next_rel += 1
        self.rel_ids[key] = rid
        self.pkg.add_rels(f"/ppt/slides/slide{self.slide_index}.xml", rid, rtype, target, mode)
        return rid

    def media_rel(self, src):
        if src in self.media_files:
            return self.media_files[src]
        path = os.path.normpath(os.path.join(self.root_dir, src))
        if not os.path.isfile(path):
            self.warnings.append(f"media not found: {src}")
            return None
        data = open(path, "rb").read()
        ext = src.rsplit(".", 1)[-1].lower() if "." in src else "png"
        if ext not in ("png", "jpg", "jpeg", "gif", "svg"):
            ext = "png"
        rid = self._store_media(data, ext)
        self.media_files[src] = rid
        return rid

    def svg_media(self, svg_str, key):
        if key in self.media_files:
            return self.media_files[key]
        rid = self._store_media(svg_str.encode("utf-8"), "svg")
        self.media_files[key] = rid
        return rid

    def _store_media(self, data, ext):
        key = hashlib_key(data)
        if key in self.media_by_key:
            idx = self.media_by_key[key]
        else:
            idx = len(self.pkg.media) + 1
            self.pkg.media.append((ext, data))
            self.media_by_key[key] = idx
        target = f"../media/image{idx}.{ext}"
        return self.rel(_RT + "/image", target)

    def hyperlink_rel(self, url):
        return self.rel(_RT + "/hyperlink", url, "External")

    # -- part bookkeeping ----------------------------------------------
    def add_slide_rels(self):
        self.pkg.add_rels(f"/ppt/slides/slide{self.slide_index}.xml", "rId1",
                          _RT + "/slideLayout", "../slideLayouts/slideLayout1.xml")


def hashlib_key(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()[:24]
