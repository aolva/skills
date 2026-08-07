#!/usr/bin/env python3
"""pptd_preview.py — self-developed PPTD -> HTML preview (no browser engine needed).

Usage:
    python3 pptd_preview.py <deck.pptd|deck-dir> [--output preview.html]
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aolva_ppt import model
from aolva_ppt.preview import render_preview


def main(argv=None):
    ap = argparse.ArgumentParser(description="PPTD -> HTML preview")
    ap.add_argument("input", help=".pptd manifest or project directory")
    ap.add_argument("--output", "-o", default=None)
    args = ap.parse_args(argv)
    manifest = model.find_pptd_in_dir(args.input)
    doc = model.load_document(manifest)
    for w in doc["warnings"]:
        print(f"[warn] {w}")
    if args.output is None:
        preview_dir = os.path.join(doc["root_dir"], ".preview")
        base = os.path.splitext(os.path.basename(manifest))[0]
        args.output = os.path.join(preview_dir, f"{base}-preview.html")
    out = render_preview(doc, args.output)
    print(f"preview: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
