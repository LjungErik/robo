#!/usr/bin/env python3
"""Robo — a tiny desktop companion robot.

Launcher kept at this path so the autostart entry keeps working; the code
lives in the `robo` package (start with robo/app.py). Same as `python3 -m robo`.

Left-click: pat him (or dismiss the bubble).  Drag: pick him up.
Right-click: menu.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from robo.app import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
