# -*- coding: utf-8 -*-
"""لانچر LagSlice — اجرا با: python main.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

from lagslice.main import main

if __name__ == "__main__":
    main()
