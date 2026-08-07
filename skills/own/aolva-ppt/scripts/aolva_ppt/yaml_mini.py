"""Dependency-free YAML subset parser (self-developed).

Parses the YAML 1.2 subset actually used by PPTD decks:
- block mappings (key: value) and block sequences (- item), nested by indentation
- flow collections [a, b] / {k: v} (JSON-like, unquoted strings allowed)
- scalars: plain, single/double quoted, block scalars | and > (with -/+ chomp)
- comments (#) and inline comments
- multi-line plain scalars (continuation lines indented deeper than the key)

Not supported (not produced by the agent workflow): anchors/aliases, tags,
explicit document markers, multi-document streams. When PyYAML is installed it
is preferred for maximum fidelity; this module is the stdlib fallback.
"""

from __future__ import annotations

import re

__all__ = ["yaml_load", "yaml_loads", "has_pyyaml"]


def has_pyyaml() -> bool:
    try:
        import yaml  # type: ignore

        return True
    except ImportError:
        return False


def yaml_loads(text: str):
    try:
        import yaml

        return yaml.safe_load(text)
    except ImportError:
        return _parse(text.splitlines())


def yaml_load(path):
    import io

    with io.open(path, "r", encoding="utf-8-sig") as fh:
        return yaml_loads(fh.read())


# ---------------------------------------------------------------------------
# fallback parser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"^( +)?(- )?(.*)$")

_TRUE = {"true", "True", "TRUE", "yes", "Yes", "on", "On"}
_FALSE = {"false", "False", "FALSE", "no", "No", "off", "Off"}
_NULL = {"null", "Null", "NULL", "~", ""}


def _scan_block_scalar(lines, i, indicator):
    """lines[i] is the 'key: |' line (already stripped). Returns (value, next_i)."""
    prefix = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    header = lines[i].strip()
    chomp = "clip"
    explicit_indent = None
    m = re.search(r"([|>])([+-]?)(\d*)", header)
    style = m.group(1)
    if m.group(2) == "+":
        chomp = "keep"
    elif m.group(2) == "-":
        chomp = "strip"
    if m.group(3):
        explicit_indent = int(m.group(3))
    indent = None
    j = i + 1
    content = []
    while j < len(lines):
        line = lines[j]
        if line.strip() == "":
            content.append("")
            j += 1
            continue
        cur = len(line) - len(line.lstrip())
        if explicit_indent is not None:
            if cur < len(prefix) + explicit_indent:
                break
        else:
            if indent is None:
                indent = cur
            if cur < indent:
                break
        if cur < len(prefix) + 1:
            break
        content.append(line[indent:] if indent is not None else line[len(prefix) + 1 :])
        j += 1
    # strip trailing blank lines for clip/strip chomps
    while chomp in ("clip", "strip") and content and content[-1] == "":
        content.pop()
    if style == ">":
        value = ""
        for k, c in enumerate(content):
            if c == "":
                value += "\n"
            else:
                if k > 0 and value and value[-1] != "\n":
                    value += " "
                value += c
        if chomp == "keep":
            value += "\n" if content and content[-1] == "" else ""
    else:
        value = "\n".join(content)
        if chomp == "keep":
            value += "\n"
    if not content and chomp in ("clip", "strip"):
        value = ""
    return value, j


def _strip_inline_comment(s):
    """Remove a trailing '# comment' that is not inside quotes."""
    quote = None
    for k, ch in enumerate(s):
        if quote:
            if ch == quote and (k == 0 or s[k - 1] != "\\"):
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (k == 0 or s[k - 1] in " \t"):
            return s[:k].rstrip()
    return s.rstrip()


def _split_key_value(line):
    """Split 'key: value' at the first ': ' (or ':' at EOL) outside quotes."""
    quote = None
    depth = 0
    for k, ch in enumerate(line):
        if quote:
            if ch == quote and (k == 0 or line[k - 1] != "\\"):
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            if k + 1 == len(line) or line[k + 1] in " \t":
                return line[:k].rstrip(), line[k + 1 :].lstrip()
    return None, None


def _parse_scalar(s):
    s = s.strip()
    if s == "":
        return None
    if s[0] == '"':
        out = []
        i = 1
        while i < len(s) - 1:
            ch = s[i]
            if ch == "\\" and i + 1 < len(s) - 1:
                nxt = s[i + 1]
                out.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}.get(nxt, nxt))
                i += 2
            else:
                out.append(ch)
                i += 1
        return "".join(out)
    if s[0] == "'":
        return s[1:-1].replace("''", "'")
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    if s in _NULL:
        return None
    if s.startswith("[") or s.startswith("{"):
        return _parse_flow(s)
    # plain scalar: try number
    if re.fullmatch(r"[-+]?\d+", s):
        return int(s)
    if re.fullmatch(r"[-+]?\d+\.\d+([eE][-+]?\d+)?", s):
        return float(s)
    return s


def _parse_flow(s):
    """Parse a flow [..] or {..} expression (no nesting inside quotes)."""
    s = s.strip()
    if s.startswith("["):
        inner = s[1:-1]
        return [_parse_flow_item(x) for x in _split_flow_items(inner)]
    if s.startswith("{"):
        inner = s[1:-1]
        obj = {}
        for item in _split_flow_items(inner):
            k, v = _split_key_value(item)
            if k is not None:
                obj[_parse_scalar(k)] = _parse_flow_item(v)
        return obj
    return _parse_scalar(s)


def _split_flow_items(inner):
    """Split flow contents on commas that are not inside quotes/nested brackets."""
    items, cur = [], []
    quote, depth = None, 0
    for ch in inner:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch in "[{":
            depth += 1
            cur.append(ch)
        elif ch in "]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        items.append("".join(cur).strip())
    return [x for x in items if x != ""]


def _parse_flow_item(s):
    s = s.strip()
    if s.startswith("[") or s.startswith("{"):
        return _parse_flow(s)
    return _parse_scalar(s)


def _block_scalar_value(lines, i, prefix):
    value, j = _scan_block_scalar(lines, i, None)
    return value, j


def _parse(lines):
    """lines: raw text lines (no newline). Returns the root mapping."""
    # strip blank leading lines, remember per-line indent
    root = {}
    stack = []  # (indent, container)  container = dict or list
    i = 0
    while i < len(lines):
        raw = lines[i]
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = _strip_inline_comment(raw).strip()
        if stripped == "":
            i += 1
            continue

        while stack and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1] if stack else root
        if isinstance(container, list):
            # sequence item
            if not stripped.startswith("-"):
                raise ValueError("bad sequence item at line %d: %r" % (i + 1, stripped))
            rest = stripped[1:].lstrip()
            if rest == "":
                # nested block under the item
                item = {}
                container.append(item)
                stack.append((indent, item))
                i += 1
                continue
            k, v = _split_key_value(rest)
            if k is not None:
                item = {}
                container.append(item)
                stack.append((indent, item))
                if v == "" or v.startswith("|") or v.startswith(">"):
                    if v in ("|", ">"):
                        value, j = _block_scalar_value(lines, i, " " * indent)
                        item[k] = value
                        i = j
                    elif v.startswith("|") or v.startswith(">"):
                        synthesized = rest
                        value, j = _scan_block_scalar(
                            [synthesized, *lines[i + 1 :]], 0, None
                        )
                        item[k] = value
                        i = i + j - 1
                    else:
                        item[k] = _parse_flow_item(v)
                        i += 1
                else:
                    item[k] = _parse_flow_item(v)
                    i += 1
            else:
                # plain scalar or flow collection item
                if rest.startswith("[") or rest.startswith("{"):
                    container.append(_parse_flow(rest))
                else:
                    container.append(_parse_scalar(rest))
                i += 1
            continue

        # mapping line
        k, v = _split_key_value(stripped)
        if k is None:
            raise ValueError("cannot parse line %d: %r" % (i + 1, stripped))
        k = _parse_scalar(k)
        if v in ("|", ">"):
            value, j = _scan_block_scalar(lines, i, None)
            container[k] = value
            i = j
        elif v.startswith("|") or v.startswith(">"):
            header_only = v.split("#")[0].strip()
            if re.fullmatch(r"[|>][+-]?\d*", header_only):
                value, j = _scan_block_scalar([v, *lines[i + 1 :]], 0, None)
                container[k] = value
                i = i + 1 + (j - 1)
            else:
                raise ValueError("bad block scalar header line %d: %r" % (i + 1, v))
        elif v == "":
            # lookahead: an empty value followed by '- item' lines is a list
            j = i + 1
            while j < len(lines) and (lines[j].strip() == "" or lines[j].lstrip().startswith("#")):
                j += 1
            if j < len(lines):
                nxt_indent = len(lines[j]) - len(lines[j].lstrip())
                if nxt_indent > indent and lines[j].strip().startswith("-"):
                    container[k] = []
                    stack.append((indent, container[k]))
                    i += 1
                    continue
            container[k] = {}
            stack.append((indent, container[k]))
            i += 1
        else:
            container[k] = _parse_flow_item(v)
            i += 1
    return root


def v_start_is_block(s):
    return s.startswith("|") or s.startswith(">")
