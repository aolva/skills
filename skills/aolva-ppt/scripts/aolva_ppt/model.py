"""PPTD model loading and theme/style resolution (self-developed).

Loads the .pptd manifest and .page files, resolves theme references
($primary, $title, $default) down the documented priority chains, and
normalizes everything into plain dicts the renderers can consume directly.
"""

from __future__ import annotations

import os
import re
import sys

from . import yaml_mini

_THEME_COLOR_RE = re.compile(r"^\$([A-Za-z0-9_.-]+)$")
_HEX8_RE = re.compile(r"^#([0-9A-Fa-f]{8})$")
_HEX6_RE = re.compile(r"^#([0-9A-Fa-f]{6})$")

EMU_PER_PT = 12700


class PPTDError(Exception):
    pass


class PPTDWarning:
    def __init__(self, message, page=None, element=None):
        self.message = message
        self.page = page
        self.element = element

    def __str__(self):
        where = ""
        if self.page:
            where = f" [{self.page}]"
        if self.element:
            where += f" element={self.element}"
        return f"warning{where}: {self.message}"


# ---------------------------------------------------------------------------
# color / font helpers
# ---------------------------------------------------------------------------

def color_rgb_hex(color):
    """'#RRGGBB' or '#RRGGBBAA' -> (RRGGBB str, alpha float 0..1)."""
    if not isinstance(color, str):
        raise PPTDError(f"invalid color {color!r}")
    m8 = _HEX8_RE.match(color)
    if m8:
        return m8.group(1)[:6], int(m8.group(1)[6:], 16) / 255.0
    m6 = _HEX6_RE.match(color)
    if m6:
        return m6.group(1), 1.0
    raise PPTDError(f"unsupported color {color!r} (expected #RRGGBB or #RRGGBBAA)")


def resolve_color(color, theme_colors, warnings=None, page=None):
    if isinstance(color, str):
        m = _THEME_COLOR_RE.match(color)
        if m:
            key = m.group(1)
            if key not in theme_colors:
                if warnings is not None:
                    warnings.append(
                        PPTDWarning(f"unknown theme color ${key}", page=page)
                    )
                return "#000000", None
            return theme_colors[key], key
        return color, None
    raise PPTDError(f"invalid color {color!r}")


def resolve_font_family(font_family):
    """FontFamily (string or {latin, ea}) -> (latin, ea) tuple."""
    if font_family is None:
        return "MiSans", "MiSans"
    if isinstance(font_family, str):
        return font_family, font_family
    if isinstance(font_family, dict):
        return (
            font_family.get("latin", "MiSans"),
            font_family.get("ea", "MiSans"),
        )
    return "MiSans", "MiSans"


# ---------------------------------------------------------------------------
# text style chains
# ---------------------------------------------------------------------------

TEXT_DEFAULTS = {
    "color": "#000000",
    "fontSize": 18,
    "fontFamily": "MiSans",
    "bold": False,
    "italic": False,
    "lineHeight": 1.0,
    "lineHeightPx": None,
    "letterSpacing": 0,
    "marginTop": 0,
}

STYLE_FIELDS = (
    "color", "fontSize", "fontFamily", "bold", "italic", "backgroundColor",
    "lineHeight", "lineHeightPx", "letterSpacing", "marginTop",
)


def merge_style(base, override):
    """Shallow merge; None values in override are ignored."""
    out = dict(base)
    if override:
        for k in STYLE_FIELDS:
            if k in override and override[k] is not None:
                out[k] = override[k]
    return out


def effective_text_style(content, theme_text_styles, warnings=None, page=None):
    """Element TextContent -> effective text style dict (content > theme > defaults)."""
    style = dict(TEXT_DEFAULTS)
    ref = content.get("style") if isinstance(content, dict) else None
    if ref and isinstance(ref, str):
        key = ref[1:] if ref.startswith("$") else ref
        theme_style = theme_text_styles.get(key) if theme_text_styles else None
        if theme_style is None and warnings is not None:
            warnings.append(PPTDWarning(f"unknown theme textStyle ${key}", page=page))
        if theme_style:
            style = merge_style(style, theme_style)
    if isinstance(content, dict):
        style = merge_style(style, content)
    for k in ("gradient", "shadow"):
        if isinstance(content, dict) and content.get(k) is not None:
            style[k] = content[k]
    return style


def effective_cell_style(cell, table_style, theme_text_styles, row_index,
                         col_index, n_rows, n_cols, warnings=None, page=None):
    """Cell style chain: cell inline > textStyle ref > row/col category > body > cellStyle > defaults."""
    cell_style = dict(TEXT_DEFAULTS)
    cell_style.update({
        "fill": None, "border": None,
        "align": ["center", "middle"],
        "textAlign": "center", "vertAlign": "middle",
    })
    if table_style:
        base = table_style.get("cellStyle") or {}
        if base.get("fill"):
            cell_style["fill"] = base["fill"]
        if base.get("border"):
            cell_style["border"] = base["border"]
        if base.get("align"):
            cell_style["align"] = base["align"]
        for k in STYLE_FIELDS:
            if k in base and base[k] is not None:
                cell_style[k] = base[k]
        row_over_column = table_style.get("rowOverColumn", True)

        def apply_category(cat, r, c, which):
            if not cat:
                return
            if cat.get("fill"):
                cell_style["fill"] = cat["fill"]
            if cat.get("border"):
                cell_style["border"] = cat["border"]
            if cat.get("align"):
                cell_style["align"] = cat["align"]
            for k in STYLE_FIELDS:
                if k in cat and cat[k] is not None:
                    cell_style[k] = cat[k]

        first_row = table_style.get("firstRowStyle")
        last_row = table_style.get("lastRowStyle")
        first_col = table_style.get("firstColumnStyle")
        last_col = table_style.get("lastColumnStyle")
        body_styles = table_style.get("bodyStyles") or []

        is_row_rule = (row_index == 0 and first_row) or (
            row_index == n_rows - 1 and last_row)
        is_col_rule = (col_index == 0 and first_col) or (
            col_index == n_cols - 1 and last_col)

        if row_over_column:
            if is_row_rule:
                apply_category(
                    first_row if row_index == 0 else last_row, row_index, col_index, "row")
            elif is_col_rule:
                apply_category(
                    first_col if col_index == 0 else last_col, row_index, col_index, "col")
        else:
            if is_col_rule:
                apply_category(
                    first_col if col_index == 0 else last_col, row_index, col_index, "col")
            elif is_row_rule:
                apply_category(
                    first_row if row_index == 0 else last_row, row_index, col_index, "row")

        data_index = row_index - 1
        if 0 <= data_index < n_rows - 2 and body_styles:
            apply_category(
                body_styles[data_index % len(body_styles)], row_index, col_index, "body")

    # textStyle reference
    ref = cell.get("textStyle") if isinstance(cell, dict) else None
    if ref and isinstance(ref, str):
        key = ref[1:] if ref.startswith("$") else ref
        theme_style = theme_text_styles.get(key) if theme_text_styles else None
        if theme_style:
            for k in STYLE_FIELDS:
                if k in theme_style and theme_style[k] is not None:
                    cell_style[k] = theme_style[k]
    # cell inline fields
    if isinstance(cell, dict):
        for k in STYLE_FIELDS:
            if k in cell and cell[k] is not None:
                cell_style[k] = cell[k]
        for k in ("fill", "border", "align"):
            if k in cell and cell[k] is not None:
                cell_style[k] = cell[k]
    if isinstance(cell_style.get("align"), list) and len(cell_style["align"]) == 2:
        cell_style["textAlign"], cell_style["vertAlign"] = cell_style["align"]
    # auto-adapt font size to cell height (spec default)
    return cell_style


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def load_document(manifest_path):
    """Load .pptd manifest. Returns dict with resolved 'pages' data + warnings."""
    warnings = []
    manifest_path = os.path.abspath(manifest_path)
    root_dir = os.path.dirname(manifest_path)
    if not os.path.exists(manifest_path):
        raise PPTDError(f"manifest not found: {manifest_path}")
    try:
        doc = yaml_mini.yaml_load(manifest_path)
    except Exception as e:
        raise PPTDError(f"cannot parse {manifest_path}: {e}")
    if not isinstance(doc, dict):
        raise PPTDError(f"{manifest_path}: manifest must be a mapping")
    if doc.get("version") != "v2":
        warnings.append(PPTDWarning(f"version is {doc.get('version')!r}, expected 'v2'"))

    size = doc.get("size")
    if not (isinstance(size, list) and len(size) == 2):
        raise PPTDError("missing or invalid 'size: [w, h]'")
    width, height = float(size[0]), float(size[1])

    theme = doc.get("theme") or {}
    theme_colors = theme.get("colors") or {}
    theme_text = theme.get("textStyles") or {}
    theme_tables = theme.get("tableStyles") or {}

    pages = []
    raw_pages = doc.get("pages") or []
    for page_path in raw_pages:
        full = os.path.abspath(os.path.normpath(os.path.join(root_dir, page_path)))
        if os.path.commonpath([full, root_dir]) != root_dir:
            raise PPTDError(f"page path escapes project dir: {page_path}")
        if not os.path.exists(full):
            warnings.append(PPTDWarning(f"page file missing: {page_path}"))
            continue
        try:
            data = yaml_mini.yaml_load(full)
        except Exception as e:
            raise PPTDError(f"cannot parse {page_path}: {e}")
        if not isinstance(data, dict):
            raise PPTDError(f"{page_path}: page must be a mapping")
        pages.append(load_page(data, theme, root_dir, page_path, warnings))

    return {
        "title": doc.get("title"),
        "width": width,
        "height": height,
        "theme": theme,
        "theme_colors": theme_colors,
        "theme_text_styles": theme_text,
        "theme_table_styles": theme_tables,
        "manifest_path": manifest_path,
        "root_dir": root_dir,
        "pages": pages,
        "warnings": warnings,
    }


def _resolve_refs(node, theme_colors, warnings, page, _in_color=False):
    """Deep-resolve $theme color references in any dict/list structure.

    Only `color` values and gradient `stops` are resolved; `style` / `textStyle`
    references ($title, $body, ...) are left untouched for the style chains.
    """
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "color" and isinstance(v, str) and v.startswith("$"):
                key = v[1:]
                if key in theme_colors:
                    out[k] = theme_colors[key]
                else:
                    if warnings is not None:
                        warnings.append(PPTDWarning(f"unknown theme color ${key}", page=page))
                    out[k] = v
            elif k == "stops" and isinstance(v, list):
                out[k] = [_resolve_refs(s, theme_colors, warnings, page) for s in v]
            else:
                out[k] = _resolve_refs(v, theme_colors, warnings, page)
        return out
    if isinstance(node, list):
        return [_resolve_refs(v, theme_colors, warnings, page) for v in node]
    return node


def load_page(data, theme, root_dir, page_path, warnings):
    page = {
        "pageType": data.get("pageType"),
        "notes": data.get("notes"),
        "elements": data.get("elements") or [],
        "animations": data.get("animations") or [],
        "background": data.get("background"),
        "src_path": page_path,
    }
    page["root_dir"] = root_dir
    theme_colors = (theme.get("colors") or {}) if theme else {}
    bg = page["background"]
    if bg is not None:
        page["background"] = resolve_fill(bg, theme_colors, warnings, page_path)
    elements = []
    for el_data in page["elements"]:
        if isinstance(el_data, dict):
            el_data = _resolve_refs(el_data, theme_colors, warnings, page_path)
        elements.append(el_data)
    page["elements"] = elements
    # element uniqueness
    seen = set()
    for idx, el in enumerate(page["elements"]):
        if not isinstance(el, dict):
            warnings.append(PPTDWarning("element is not a mapping", page=page_path, element=str(idx)))
            continue
        eid = el.get("elementId")
        if eid in seen:
            warnings.append(PPTDWarning(f"duplicate elementId {eid!r}", page=page_path))
        if eid is not None:
            seen.add(eid)
        bounds = el.get("bounds")
        if not (isinstance(bounds, list) and len(bounds) == 4):
            warnings.append(PPTDWarning(
                f"element {eid!r}: invalid bounds {bounds!r}", page=page_path, element=eid))
    return page


def resolve_fill(fill, theme_colors, warnings=None, page=None):
    """Deep-resolve theme colors inside a Fill dict. Returns new dict."""
    if not isinstance(fill, dict):
        return fill
    ftype = fill.get("type")
    if ftype == "gradient":
        out = dict(fill)
        stops = []
        for s in fill.get("stops") or []:
            color, _ = resolve_color(s.get("color"), theme_colors, warnings, page)
            stops.append({"position": s.get("position", 0), "color": color})
        out["stops"] = stops
        return out
    if ftype == "image":
        return dict(fill)
    # solid
    if "color" in fill:
        out = dict(fill)
        color, _ = resolve_color(fill["color"], theme_colors, warnings, page)
        out["color"] = color
        return out
    return dict(fill)


def resolve_text_color_inline(text, theme_colors):
    """Resolve $xxx theme references inside rich-text style attributes."""
    if "$" not in text or not theme_colors:
        return text

    def repl(m):
        key = m.group(1)
        if key in theme_colors:
            return theme_colors[key]
        return m.group(0)

    return re.sub(r"\$([A-Za-z0-9_.-]+)", repl, text)


def find_pptd_in_dir(dir_path):
    """If given a directory, locate its single .pptd manifest."""
    if os.path.isdir(dir_path):
        found = [
            f for f in os.listdir(dir_path)
            if f.lower().endswith(".pptd")
        ]
        if len(found) == 1:
            return os.path.join(dir_path, found[0])
        if len(found) == 0:
            raise PPTDError(f"no .pptd manifest found in {dir_path}")
        raise PPTDError(f"multiple .pptd manifests in {dir_path}: {found}")
    return dir_path
