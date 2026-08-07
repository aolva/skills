#!/usr/bin/env python3
"""export_pptx.py — upstream-compatible wrapper around the self-developed
PPTD -> PPTX exporter.

Usage (same shape as the old open-kimi-ppt-skill interface):
    python3 export_pptx.py <deck.pptd|deck-dir> [--output deck.pptx]
                           [--transition fade|none] [--force]
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pptd_export import main

if __name__ == "__main__":
    sys.exit(main())
