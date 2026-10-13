# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""نقطه‌ی ورود LagSlice (برای PyInstaller و اجرای مستقیم)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lagslice.main import main

if __name__ == "__main__":
    main()
