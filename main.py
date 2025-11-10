"""
Thin CLI wrapper to run the SIMAP export with simple arguments.

Usage examples:
  python main.py --days-back 10 --max-pages 3 --output simap_projects.csv
"""
from __future__ import annotations

import sys

from Simap.simap_projects import run


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))

