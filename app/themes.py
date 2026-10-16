# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""تم‌های LagSlice: پالت رنگ + سازنده‌ی QSS.

تم پیش‌فرض «LagSlice» همان تم نئونی تیره‌ی فعلی است.
هر تم یک دیکشنری رنگ کامل دارد؛ build_qss از روی آن QSS می‌سازد.
"""

THEMES = {
    "lagslice": {
        "label": {"fa": "LagSlice (پیش‌فرض)", "en": "LagSlice (default)"},
        "accent": "#00E5FF",
        "accent2": "#FF00D4",
        "bg": "#0B0F17",
        "card": "#101724",
        "border": "#1E2A3D",
        "text": "#E8EDF5",
        "muted": "#9AA4B5",
        "green": "#22E584",
        "amber": "#FFB020",
        "red": "#FF4D5E",
        "btn_bg": "#16202F",
        "btn_hover": "#1B2940",
        "header_bg": "#141C2B",
        "log_bg": "#080B11",
        "warn_bg": "#2A1E08",
        "banner_bg": "#0E2A1A",
        "banner_fg": "#34D399",
        "disabled_border": "#3A4356",
        "disabled_text": "#5B6577",
        "disabled_bg": "#121826",
    },
    "neon_purple": {
        "label": {"fa": "بنفش نئونی", "en": "Neon Purple"},
        "accent": "#C084FC",
        "accent2": "#F472B6",
        "bg": "#0D0A18",
        "card": "#151028",
        "border": "#2B2145",
        "text": "#EDE9FE",
        "muted": "#A89BC4",
        "green": "#34D399",
        "amber": "#FBBF24",
        "red": "#F87171",
        "btn_bg": "#1B1430",
        "btn_hover": "#241A42",
        "header_bg": "#191231",
        "log_bg": "#0A0714",
        "warn_bg": "#2A1E08",
        "banner_bg": "#0E2A1A",
        "banner_fg": "#34D399",
        "disabled_border": "#3A3356",
        "disabled_text": "#6B5F8A",
        "disabled_bg": "#141021",
    },
    "ice_blue": {
        "label": {"fa": "آبی یخی", "en": "Ice Blue"},
        "accent": "#7DD3FC",
        "accent2": "#22D3EE",
        "bg": "#08111A",
        "card": "#0E1B26",
        "border": "#1C3040",
        "text": "#E8F4FC",
        "muted": "#93A9BC",
        "green": "#2DD4A7",
        "amber": "#FBBF24",
        "red": "#FB7185",
        "btn_bg": "#12242F",
        "btn_hover": "#182E3D",
        "header_bg": "#10202C",
        "log_bg": "#060D13",
        "warn_bg": "#2A1E08",
        "banner_bg": "#0C2A22",
        "banner_fg": "#2DD4A7",
        "disabled_border": "#2A3A48",
        "disabled_text": "#5B7186",
        "disabled_bg": "#0D1620",
    },
}

DEFAULT_THEME = "lagslice"


def theme_keys():
    return list(THEMES.keys())


def theme_label(key, lang="fa"):
    t = THEMES.get(key) or THEMES[DEFAULT_THEME]
    return t["label"].get(lang, t["label"]["en"])


def theme_colors(key):
    return dict(THEMES.get(key) or THEMES[DEFAULT_THEME])


def build_qss(key):
    c = theme_colors(key)
    return f"""
QWidget {{ background-color: {c['bg']}; color: {c['text']}; font-family: "Vazirmatn", "Segoe UI", Tahoma, sans-serif; font-size: 13px; }}
QLabel#Title {{ font-size: 22px; font-weight: bold; color: {c['accent']}; }}
QLabel#Sub {{ font-size: 12px; color: {c['muted']}; }}
QLabel#StatVal {{ font-size: 20px; font-weight: bold; color: {c['text']}; }}
QLabel#StatName {{ font-size: 11px; color: {c['muted']}; }}
QLabel#Pill {{ border-radius: 12px; padding: 6px 14px; font-weight: bold; }}
QLabel#BestBanner {{ background-color: {c['banner_bg']}; color: {c['banner_fg']}; border: 1px solid {c['banner_fg']};
    border-radius: 8px; padding: 8px 12px; font-weight: bold; }}
QLabel#SecHead {{ font-size: 15px; font-weight: bold; color: {c['accent']};
    border-bottom: 1px solid {c['border']}; padding: 8px 2px 6px 2px; margin-top: 6px; }}
QTextEdit#About {{ background-color: {c['card']}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 8px; font-size: 12px; color: {c['muted']}; }}
QProgressBar {{ background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 6px;
    text-align: center; color: {c['muted']}; }}
QProgressBar::chunk {{ background-color: {c['accent']}; border-radius: 6px; }}
QFrame#Card {{ background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QPushButton {{ background-color: {c['btn_bg']}; border: 1px solid {c['accent']}; border-radius: 10px; color: {c['text']}; font-weight: bold; }}
QPushButton:hover {{ background-color: {c['btn_hover']}; }}
QPushButton:disabled {{ border-color: {c['disabled_border']}; color: {c['disabled_text']}; background-color: {c['disabled_bg']}; }}
QPushButton#Go {{ border-color: {c['green']}; font-size: 15px; padding: 14px; }}
QPushButton#Stop {{ border-color: {c['red']}; font-size: 15px; padding: 14px; }}
QPushButton#Danger {{ border-color: {c['accent2']}; }}
QPushButton#Lang {{ border-color: {c['accent2']}; padding: 6px 14px; }}
/* دکمه‌های بیرون جدول: پدینگ (داخل QTableWidget در RTL باگ دارد) */
QDialog QPushButton, QTabWidget QPushButton {{ padding: 10px 18px; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 8px; }}
QTabBar::tab {{ background: {c['card']}; color: {c['muted']}; padding: 8px 18px; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ color: {c['accent']}; border-bottom: 2px solid {c['accent']}; }}
QTableWidget {{ background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px; gridline-color: {c['border']}; }}
QTableWidget::item {{ padding: 4px; }}
QHeaderView::section {{ background-color: {c['header_bg']}; color: {c['muted']}; border: none; padding: 6px; }}
QListWidget {{ background-color: {c['card']}; border: 1px solid {c['border']}; border-radius: 8px; }}
QLineEdit, QSpinBox, QDoubleSpinBox {{ background-color: {c['bg']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 8px; }}
QComboBox {{ background-color: {c['bg']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 8px; }}
QComboBox QAbstractItemView {{ background-color: {c['card']}; border: 1px solid {c['border']}; selection-background-color: {c['btn_hover']}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border; width: 24px; border: none; background: transparent; }}
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover,
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background-color: {c['btn_hover']}; }}
QTextEdit#Log {{ background-color: {c['log_bg']}; border: 1px solid {c['border']}; border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; }}
QLabel#Warn {{ background-color: {c['warn_bg']}; border: 1px solid {c['amber']}; border-radius: 8px; padding: 8px 12px; color: {c['amber']}; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 9px; border: 1px solid {c['accent']}; background: {c['card']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; }}
"""
