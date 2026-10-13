# -*- coding: utf-8 -*-
"""نقطه‌ی ورود LagSlice (برای PyInstaller و اجرای مستقیم)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lagslice.main import main

if __name__ == "__main__":
    main()
