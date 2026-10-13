# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
# -*- coding: utf-8 -*-
"""رابط اصلی LagSlice — دوزبانه (فارسی/انگلیسی)، تم تیره نئونی (بر اساس لوگو).

معماری دوزبانه: همه‌ی متن‌های UI از lang.py می‌آیند (تابع tr).
تعویض زبان داخل برنامه با دکمه‌ی سربرگ انجام می‌شود و جهت
چیدمان (راست‌چین/چپ‌چین) هم عوض می‌شود.
"""
import json
import os
import sys
import tempfile
import threading
import time
import traceback


def _crash_log_path():
    """مسیر فایل لاگ کرش: کنار exe، وگرنه APPDATA، وگرنه temp."""
    cands = []
    try:
        exe_dir = os.path.dirname(sys.executable)
        if exe_dir:
            cands.append(os.path.join(exe_dir, "LagSlice-crash.log"))
    except Exception:
        pass
    try:
        base = os.environ.get("APPDATA")
        if base:
            cands.append(os.path.join(base, "LagSlice", "LagSlice-crash.log"))
    except Exception:
        pass
    cands.append(os.path.join(tempfile.gettempdir(), "LagSlice-crash.log"))
    for p in cands:
        try:
            d = os.path.dirname(p)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(p, "a", encoding="utf-8"):
                pass
            return p
        except Exception:
            continue
    return cands[-1]


def _install_crash_hook():
    """هر exception درمان‌نشده (نخ اصلی و نخ‌ها) با traceback در فایل لاگ."""
    def _write(text):
        try:
            with open(_crash_log_path(), "a", encoding="utf-8") as fh:
                fh.write(text)
        except Exception:
            pass

    def _hook(exc_type, exc_value, exc_tb):
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _write(f"\n===== LagSlice crash @ {ts} =====\n{text}")
        except Exception:
            pass
        try:
            from PyQt6 import QtWidgets
            if QtWidgets.QApplication.instance() is not None:
                QtWidgets.QMessageBox.critical(
                    None, "LagSlice",
                    "برنامه با خطای غیرمنتظره‌ای مواجه شد.\n"
                    f"جزئیات در این فایل ذخیره شد:\n{_crash_log_path()}")
        except Exception:
            pass
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass

    def _thread_hook(args):
        _hook(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _hook
    threading.excepthook = _thread_hook


_install_crash_hook()

from PyQt6 import QtCore, QtGui, QtWidgets

from lang import tr, set_lang, get_lang, fa_digits
from netmon import NetMonitor, delay_health
from procman import (
    iter_processes, kill_process, stream_mode_cleanup,
    load_safelist, save_safelist, is_admin, base_dir,
    NEVER_TOUCH, HOG_PATTERNS,
)
from servers import (
    load_servers, add_server as srv_add, update_server as srv_update,
    delete_server as srv_delete, import_rtmp_bulk,
    server_rtmp_url, parse_rtmp, suggest_name, detect_region,
)
from scan import ScanThread
import psutil

REGIONS = ("ir", "de", "fr", "nl", "uk", "tr", "ae", "")


def _fmt_rate(bps):
    """12345678 -> '12.3 Mbps' (digits localized by caller via fa_digits)."""
    try:
        bps = float(bps)
    except Exception:
        return "—"
    if bps >= 1e6:
        return f"{bps / 1e6:.1f} Mbps"
    if bps >= 1e3:
        return f"{bps / 1e3:.0f} Kbps"
    return f"{bps:.0f} bps"

__version__ = "0.2.0"

APP_DIR = base_dir()
CONFIG_PATH = os.path.join(APP_DIR, "lagslice_config.json")


def asset_path(name):
    """مسیر فایل باندل‌شده: اول _MEIPASS (exe بیلدشده)، بعد assets/ سورس."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = os.path.join(meipass, name)
        if os.path.exists(p):
            return p
    p = os.path.join(APP_DIR, "..", "assets", name)
    if os.path.exists(p):
        return p
    return p


LOGO_PATH = asset_path("lagslice-logo.png")


def guide_path():
    """مسیر PDF راهنما: اول _MEIPASS (exe)، بعد docs/ سورس."""
    for name in ("lagslice-help-fa.pdf", "LagSlice-guide-fa.pdf"):
        for p in (
            os.path.join(getattr(sys, "_MEIPASS", ""), "docs", name),
            os.path.join(APP_DIR, "..", "docs", name),
        ):
            if os.path.exists(p):
                return p
    return None


def about_text():
    """متن دیالوگ درباره: از فایل docs باندل‌شده، وگرنه متن داخلی."""
    for p in (
        os.path.join(getattr(sys, "_MEIPASS", ""), "docs", "about-dialog-fa.txt"),
        os.path.join(APP_DIR, "..", "docs", "about-dialog-fa.txt"),
    ):
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            continue
    return "LagSlice ⚡ — " + tr("app_subtitle") + "\nCopyright (C) 2026 Taha Arefi\nAGPL-3.0-only"

CYAN = "#00E5FF"
MAGENTA = "#FF00D4"
BG = "#0B0F17"
CARD = "#101724"
BORDER = "#1E2A3D"
TEXT = "#E8EDF5"
MUTED = "#9AA4B5"
GREEN = "#22E584"
AMBER = "#FFB020"
RED = "#FF4D5E"

QSS = f"""
QWidget {{ background-color: {BG}; color: {TEXT}; font-family: "Vazirmatn", "Segoe UI", Tahoma, sans-serif; font-size: 13px; }}
QLabel#Title {{ font-size: 22px; font-weight: bold; color: {CYAN}; }}
QLabel#Sub {{ font-size: 12px; color: {MUTED}; }}
QLabel#StatVal {{ font-size: 20px; font-weight: bold; color: {TEXT}; }}
QLabel#StatName {{ font-size: 11px; color: {MUTED}; }}
QLabel#Pill {{ border-radius: 12px; padding: 6px 14px; font-weight: bold; }}
QLabel#BestBanner {{ background-color: #0E2A1A; color: #34D399; border: 1px solid #34D399;
    border-radius: 8px; padding: 8px 12px; font-weight: bold; }}
QProgressBar {{ background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 6px;
    text-align: center; color: {MUTED}; }}
QProgressBar::chunk {{ background-color: {CYAN}; border-radius: 6px; }}
QFrame#Card {{ background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QPushButton {{ background-color: #16202F; border: 1px solid {CYAN}; border-radius: 10px; color: {TEXT}; font-weight: bold; }}
QPushButton:hover {{ background-color: #1B2940; }}
QPushButton:disabled {{ border-color: #3A4356; color: #5B6577; background-color: #121826; }}
QPushButton#Go {{ border-color: {GREEN}; font-size: 15px; padding: 14px; }}
QPushButton#Stop {{ border-color: {RED}; font-size: 15px; padding: 14px; }}
QPushButton#Danger {{ border-color: {MAGENTA}; }}
QPushButton#Lang {{ border-color: {MAGENTA}; padding: 6px 14px; }}
/* دکمه‌های بیرون جدول: پدینگ (داخل QTableWidget در RTL باگ دارد) */
QDialog QPushButton, QTabWidget QPushButton {{ padding: 10px 18px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; }}
QTabBar::tab {{ background: {CARD}; color: {MUTED}; padding: 8px 18px; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
QTabBar::tab:selected {{ color: {CYAN}; border-bottom: 2px solid {CYAN}; }}
QTableWidget {{ background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {BORDER}; }}
QTableWidget::item {{ padding: 4px; }}
QHeaderView::section {{ background-color: #141C2B; color: {MUTED}; border: none; padding: 6px; }}
QListWidget {{ background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QLineEdit, QSpinBox, QDoubleSpinBox {{ background-color: {BG}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px; }}
QTextEdit#Log {{ background-color: #080B11; border: 1px solid {BORDER}; border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; }}
QLabel#Warn {{ background-color: #2A1E08; border: 1px solid {AMBER}; border-radius: 8px; padding: 8px 12px; color: {AMBER}; }}
"""


def load_config():
    cfg = {"servers": ["8.8.8.8"], "bitrate_mbps": 8.0, "lang": "fa"}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                cfg.update(data)
    except (OSError, ValueError):
        pass
    if cfg.get("lang") not in ("fa", "en"):
        cfg["lang"] = "fa"
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


class StatCard(QtWidgets.QFrame):
    def __init__(self, name_key, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._name_key = name_key
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        self.name_lbl = QtWidgets.QLabel()
        self.name_lbl.setObjectName("StatName")
        self.val_lbl = QtWidgets.QLabel("—")
        self.val_lbl.setObjectName("StatVal")
        lay.addWidget(self.name_lbl)
        lay.addWidget(self.val_lbl)
        self.retranslate()

    def retranslate(self):
        self.name_lbl.setText(tr(self._name_key))
        # حسابرسی RTL: لیبل فارسی راست‌چین؛ مقدار عددی همیشه چپ‌چین/LTR
        rtl = get_lang() == "fa"
        self.name_lbl.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight if rtl
            else QtCore.Qt.AlignmentFlag.AlignLeft)
        self.val_lbl.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.val_lbl.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight if rtl
            else QtCore.Qt.AlignmentFlag.AlignLeft)

    def set(self, text, color=None):
        self.val_lbl.setText(text)
        # مقادیر عددی (ms/Mbps/IP/—) همیشه چپ‌چین/LTR؛ وضعیت‌های متنی با جهت زبان
        import re as _re
        is_numeric = bool(_re.search(r"[0-9۰-۹٫.]|ms|Mbps|Kbps|bps|—|-", str(text)))
        if is_numeric:
            self.val_lbl.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
            self.val_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft
                                      | QtCore.Qt.AlignmentFlag.AlignVCenter)
        else:
            if get_lang() == "fa":
                self.val_lbl.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft)
                self.val_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight
                                          | QtCore.Qt.AlignmentFlag.AlignVCenter)
            else:
                self.val_lbl.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
                self.val_lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft
                                          | QtCore.Qt.AlignmentFlag.AlignVCenter)
        if color:
            self.val_lbl.setStyleSheet(f"color: {color};")


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.resize(480, 400)
        lay = QtWidgets.QVBoxLayout(self)
        if os.path.exists(LOGO_PATH):
            logo = QtWidgets.QLabel()
            pm = QtGui.QPixmap(LOGO_PATH).scaledToHeight(72, QtCore.Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pm)
            logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(logo)
        txt = QtWidgets.QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(about_text())
        lay.addWidget(txt)
        btn = QtWidgets.QPushButton(tr("ok"))
        btn.clicked.connect(self.accept)
        lay.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)


class ServerEditDialog(QtWidgets.QDialog):
    """افزودن/ویرایش سرور استریم — نام و منطقه خودکار از روی لینک حدس زده می‌شوند."""

    def __init__(self, parent=None, server=None):
        super().__init__(parent)
        s = server or {}
        self.setWindowTitle(tr("scan_edit_title") if server else tr("scan_add_title"))
        lay = QtWidgets.QFormLayout(self)
        self.name_edit = QtWidgets.QLineEdit(s.get("name", ""))
        self.name_edit.setPlaceholderText("IR1")
        self.rtmp_edit = QtWidgets.QLineEdit(server_rtmp_url(s) if server else "")
        self.rtmp_edit.setPlaceholderText("rtmp://host:1935/live")
        self.rtmp_edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.rtmp_edit.setLayoutDirection(QtCore.Qt.LayoutDirection.LeftToRight)
        self.rtmp_edit.textChanged.connect(self._auto_fill)
        self.region_combo = QtWidgets.QComboBox()
        for r in REGIONS:
            self.region_combo.addItem(tr("region_" + (r or "unknown")), r)
        cur = s.get("region", "unknown")
        idx = self.region_combo.findData(cur)
        self.region_combo.setCurrentIndex(idx if idx >= 0 else 0)
        lay.addRow(tr("scan_srv_name"), self.name_edit)
        lay.addRow(tr("scan_srv_rtmp"), self.rtmp_edit)
        lay.addRow(tr("scan_srv_region"), self.region_combo)
        hint = QtWidgets.QLabel(tr("scan_auto_hint"))
        hint.setObjectName("Sub")
        hint.setWordWrap(True)
        lay.addRow(hint)
        row = QtWidgets.QHBoxLayout()
        ok_btn = QtWidgets.QPushButton(tr("ok"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QtWidgets.QPushButton(tr("cancel"))
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        lay.addRow(row)

    def _auto_fill(self, text):
        host, _port = parse_rtmp(text)
        if host and not self.name_edit.text().strip():
            self.name_edit.setText(suggest_name(host))
        if host:
            idx = self.region_combo.findData(detect_region(host))
            if idx >= 0:
                self.region_combo.setCurrentIndex(idx)

    def values(self):
        host, port = parse_rtmp(self.rtmp_edit.text())
        return {
            "name": self.name_edit.text().strip(),
            "host": host,
            "port": port,
            "region": self.region_combo.currentData(),
        }


class SafePickDialog(QtWidgets.QDialog):
    """افزودن به لیست امن با انتخاب از برنامه‌های در حال اجرا (جست‌وجو + تیک)."""

    def __init__(self, safelist, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("safe_pick_title"))
        self.resize(420, 480)
        lay = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(tr("safe_pick_search"))
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QtWidgets.QListWidget()
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        lay.addWidget(self.list)
        self._names = []
        seen = set()
        for p in psutil.process_iter(["name"]):
            try:
                n = (p.info.get("name") or "").strip().lower()
            except Exception:
                continue
            if not n or n in seen or n in NEVER_TOUCH or n in safelist:
                continue
            seen.add(n)
            self._names.append(n)
        for n in sorted(self._names):
            it = QtWidgets.QListWidgetItem(n)
            it.setFlags(it.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.list.addItem(it)
        if not self._names:
            self.list.addItem(tr("safe_pick_empty"))
        row = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton(tr("safe_pick_add"))
        add_btn.clicked.connect(self.accept)
        cancel_btn = QtWidgets.QPushButton(tr("safe_pick_cancel"))
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(add_btn)
        row.addWidget(cancel_btn)
        lay.addLayout(row)

    def _filter(self, text):
        q = text.strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(q) and q not in it.text().lower())

    def selected(self):
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == QtCore.Qt.CheckState.Checked:
                out.append(it.text())
        return out


class LagSliceWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        set_lang(self.cfg.get("lang", "fa"))
        self.safelist = load_safelist()
        self.servers = load_servers()
        self.streaming = False
        self._last_delay_key = "unknown"
        self._scan_thread = None
        self._scanning = False
        self._scan_results = {}

        self.setWindowTitle(f"LagSlice ⚡ (v{__version__})")
        self.resize(980, 700)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setSpacing(10)

        # --- سربرگ ---
        head = QtWidgets.QHBoxLayout()
        if os.path.exists(LOGO_PATH):
            logo = QtWidgets.QLabel()
            pm = QtGui.QPixmap(LOGO_PATH).scaledToHeight(64, QtCore.Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pm)
            head.addWidget(logo)
        tbox = QtWidgets.QVBoxLayout()
        self.title_lbl = QtWidgets.QLabel("LagSlice ⚡")
        self.title_lbl.setObjectName("Title")
        self.sub_lbl = QtWidgets.QLabel()
        self.sub_lbl.setObjectName("Sub")
        tbox.addWidget(self.title_lbl)
        tbox.addWidget(self.sub_lbl)
        head.addLayout(tbox)
        head.addStretch(1)
        self.btn_lang = QtWidgets.QPushButton()
        self.btn_lang.setObjectName("Lang")
        self.btn_lang.clicked.connect(self.toggle_lang)
        head.addWidget(self.btn_lang)
        self.btn_about = QtWidgets.QPushButton()
        self.btn_about.setObjectName("Lang")
        self.btn_about.clicked.connect(self.show_about)
        head.addWidget(self.btn_about)
        self.btn_help = QtWidgets.QPushButton()
        self.btn_help.setObjectName("Lang")
        self.btn_help.clicked.connect(self.show_help)
        head.addWidget(self.btn_help)
        self.pill = QtWidgets.QLabel()
        self.pill.setObjectName("Pill")
        head.addWidget(self.pill)
        root.addLayout(head)

        self.warn_lbl = QtWidgets.QLabel()
        self.warn_lbl.setObjectName("Warn")
        self.warn_lbl.setWordWrap(True)
        self.warn_lbl.setVisible(not is_admin())
        root.addWidget(self.warn_lbl)

        # --- کارت‌های آمار ---
        stats = QtWidgets.QHBoxLayout()
        self.card_up = StatCard("stat_up")
        self.card_down = StatCard("stat_down")
        self.card_ping = StatCard("stat_ping")
        self.card_delay = StatCard("stat_delay")
        for c in (self.card_up, self.card_down, self.card_ping, self.card_delay):
            stats.addWidget(c)
        root.addLayout(stats)

        # --- دکمه حالت استریم ---
        self.btn_stream = QtWidgets.QPushButton()
        self.btn_stream.clicked.connect(self.toggle_stream)
        root.addWidget(self.btn_stream)

        # --- تب‌ها ---
        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_proc_tab()
        self._build_scan_tab()
        self._build_safe_tab()
        self._build_settings_tab()
        self._build_log_tab()

        self.apply_language()
        self._refresh_pill()
        self._refresh_stream_btn()

        # --- مانیتور شبکه ---
        self.netmon = NetMonitor(self._servers, self)
        self.netmon.updated.connect(self._on_net_stats)
        self.netmon.start()

        self.proc_timer = QtCore.QTimer(self)
        self.proc_timer.timeout.connect(self.refresh_procs)
        self.proc_timer.start(5000)
        self.refresh_procs()

        self.log(tr("log_ready"))

    # ============ دوزبانه‌سازی ============
    def toggle_lang(self):
        new = "en" if get_lang() == "fa" else "fa"
        set_lang(new)
        self.cfg["lang"] = new
        save_config(self.cfg)
        direction = (QtCore.Qt.LayoutDirection.RightToLeft if new == "fa"
                     else QtCore.Qt.LayoutDirection.LeftToRight)
        QtWidgets.QApplication.instance().setLayoutDirection(direction)
        self.setLayoutDirection(direction)
        self.apply_language()
        # سینک کامبوباکس تنظیمات بدون لوپ (سیگنالش خودش چک می‌کند)
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(0 if new == "fa" else 1)
        self.lang_combo.blockSignals(False)
        self.refresh_procs()
        self.log(tr("log_lang_changed"))

    def apply_language(self):
        rtl = get_lang() == "fa"
        align = (QtCore.Qt.AlignmentFlag.AlignRight if rtl
                 else QtCore.Qt.AlignmentFlag.AlignLeft)
        self.sub_lbl.setText(tr("app_subtitle"))
        self.btn_lang.setText("EN" if rtl else "فا")
        self.btn_about.setText(tr("about_btn"))
        self.btn_help.setText(tr("help_btn"))
        self.warn_lbl.setText(tr("admin_warn"))
        self.warn_lbl.setAlignment(align)
        for c in (self.card_up, self.card_down, self.card_ping, self.card_delay):
            c.retranslate()
        self.card_ping.setToolTip(tr("ping_server_hint"))
        self.card_up.setToolTip(tr("tip_up"))
        self.card_down.setToolTip(tr("tip_down"))
        self.btn_stream.setToolTip(tr("tip_stream"))
        self.proc_hint.setAlignment(align)
        self.safe_hint.setAlignment(align)
        self.set_note.setAlignment(align)
        self.ping_hint.setAlignment(align)
        self._refresh_pill()
        self._refresh_stream_btn()
        self.tabs.setTabText(0, tr("tab_procs"))
        self.tabs.setTabText(1, tr("tab_scan"))
        self.tabs.setTabText(2, tr("tab_safe"))
        self.tabs.setTabText(3, tr("tab_settings"))
        self.tabs.setTabText(4, tr("tab_log"))
        self.proc_hint.setText(tr("procs_hint"))
        self.proc_table.setHorizontalHeaderLabels(
            [tr("col_app"), tr("col_pid"), tr("col_cpu"), tr("col_ram"), ""])
        self.safe_hint.setText(tr("safe_hint"))
        self.btn_safe_pick.setText(tr("safe_pick_btn"))
        self.btn_safe_del.setText(tr("safe_del"))
        self.lbl_server.setText(tr("set_server"))
        self.server_edit.setPlaceholderText(tr("set_server_ph"))
        self.lbl_bitrate.setText(tr("set_bitrate"))
        self.btn_save.setText(tr("set_save"))
        self.set_note.setText(tr("set_note"))
        self.lbl_lang.setText(tr("lang_label"))
        self._retranslate_scan()
        self._update_delay_card()
        self.refresh_procs()

    def show_about(self):
        AboutDialog(self).exec()

    def show_help(self):
        p = guide_path()
        if not p:
            QtWidgets.QMessageBox.warning(self, tr("help_title"), tr("help_missing"))
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(p))

    def _refresh_pill(self):
        if self.streaming:
            self.pill.setText(tr("status_streaming"))
            self.pill.setStyleSheet(f"background-color: #3A0F1E; color: {RED};")
        else:
            self.pill.setText(tr("status_ready"))
            self.pill.setStyleSheet(f"background-color: #1B2940; color: {MUTED};")
        # انیمیشن نرم تغییر وضعیت
        eff = QtWidgets.QGraphicsOpacityEffect(self.pill)
        self.pill.setGraphicsEffect(eff)
        anim = QtCore.QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(350)
        anim.setStartValue(0.25)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        anim.start()
        self._pill_anim = anim

    def _refresh_stream_btn(self):
        if self.streaming:
            self.btn_stream.setText(tr("stream_stop"))
            self.btn_stream.setObjectName("Stop")
        else:
            self.btn_stream.setText(tr("stream_start"))
            self.btn_stream.setObjectName("Go")
        self.btn_stream.setStyleSheet("")

    # ---------- تب برنامه‌ها ----------
    def _build_proc_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.proc_hint = QtWidgets.QLabel()
        self.proc_hint.setObjectName("Sub")
        self.proc_hint.setWordWrap(True)
        lay.addWidget(self.proc_hint)
        self.proc_table = QtWidgets.QTableWidget(0, 5)
        self.proc_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.proc_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.proc_table.verticalHeader().setVisible(False)
        self._kill_btn_pool = []
        # ستون نام برنامه کش می‌آید تا جدول تمام‌عرض شود (راست‌چین)
        hh = self.proc_table.horizontalHeader()
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for i in range(1, 5):
            hh.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.proc_table)
        self.tabs.addTab(w, "")

    def _tcell(self, text, numeric=False):
        """سلول جدول: متنی با جهت زبان، عددی همیشه چپ‌چین/LTR."""
        it = QtWidgets.QTableWidgetItem(text)
        fa = get_lang() == "fa"
        if numeric:
            it.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignLeft
                                | QtCore.Qt.AlignmentFlag.AlignVCenter)
        else:
            it.setTextAlignment(
                (QtCore.Qt.AlignmentFlag.AlignRight if fa else QtCore.Qt.AlignmentFlag.AlignLeft)
                | QtCore.Qt.AlignmentFlag.AlignVCenter)
        return it

    def _pool_button(self, r):
        """دکمه‌ی pool برای سطر r — اگر حذف شده بود، از نو ساخته می‌شود."""
        btn = None
        if r < len(self._kill_btn_pool):
            cand = self._kill_btn_pool[r]
            if cand is not None:
                try:
                    cand.setText(cand.text())  # تست زنده‌بودن
                    btn = cand
                except RuntimeError:
                    btn = None
        if btn is None:
            btn = QtWidgets.QPushButton()
            btn.setObjectName("Danger")
            if r < len(self._kill_btn_pool):
                self._kill_btn_pool[r] = btn
            else:
                while len(self._kill_btn_pool) < r:
                    self._kill_btn_pool.append(None)
                self._kill_btn_pool.append(btn)
        return btn

    def _set_kill_button(self, r, pid):
        """دکمه‌ی بستن سطر r — استفاده‌ی مجدد از pool تا ویجت‌ها نشت نکنند."""
        btn = self._pool_button(r)
        btn.setText(tr("btn_kill"))
        try:
            btn.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        btn.clicked.connect(lambda _=False, pid=pid: self._kill_one(pid))
        self.proc_table.setCellWidget(r, 4, btn)
        btn.setVisible(True)

    def _show_table_empty(self):
        """حالت خالیِ گویا: به‌جای جدول خالی، یک سطر پیام."""
        t = self.proc_table
        t.setRowCount(1)
        msg = self._tcell(tr("empty_procs"))
        msg.setFlags(msg.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable
                     & ~QtCore.Qt.ItemFlag.ItemIsEnabled)
        t.setItem(0, 0, msg)
        t.setSpan(0, 0, 1, t.columnCount())

    def refresh_procs(self):
        # جدا کردن دکمه‌های pool از سلول‌های قدیمی برای استفاده‌ی مجدد
        self.proc_table.clearSpans()
        for r in range(self.proc_table.rowCount()):
            try:
                w = self.proc_table.cellWidget(r, 4)
                if w is None:
                    continue
                w.isVisible()  # تست زنده‌بودن
            except RuntimeError:
                continue
            if w in self._kill_btn_pool:
                self.proc_table.removeCellWidget(r, 4)
                try:
                    w.setVisible(False)
                except RuntimeError:
                    pass
        per_proc = (getattr(self, "_last_stats", None) or {}).get("per_proc") or {}
        if per_proc:
            # حالت شبکه: آپلود/دانلود واقعی هر برنامه (EStats، بدون درایور)
            rows = []
            for pid, e in per_proc.items():
                try:
                    name = psutil.Process(int(pid)).name() or ""
                except Exception:
                    continue
                lname = name.lower()
                if lname in NEVER_TOUCH or lname in self.safelist:
                    continue
                kind = "hog" if lname in HOG_PATTERNS else "other"
                hog_key = "hog_" + lname
                rows.append({
                    "pid": int(pid), "name": name,
                    "up": e.get("up_bps", 0.0), "down": e.get("down_bps", 0.0),
                    "kind": kind,
                    "fa": tr(hog_key) if kind == "hog" and tr(hog_key) != hog_key else "",
                })
            rows.sort(key=lambda x: x["up"], reverse=True)
            self.proc_table.setHorizontalHeaderLabels(
                [tr("col_app"), tr("col_up"), tr("col_down"), tr("col_pid"), ""])
            if not rows:
                self._show_table_empty()
                return
            self.proc_table.setRowCount(len(rows))
            for r, p in enumerate(rows):
                label = p["name"] + (f" ({p['fa']})" if p["fa"] else "")
                if p["kind"] == "hog":
                    label = "🔥 " + label
                self.proc_table.setItem(r, 0, self._tcell(label))
                self.proc_table.setItem(
                    r, 1, self._tcell(fa_digits(_fmt_rate(p["up"])), numeric=True))
                self.proc_table.setItem(
                    r, 2, self._tcell(fa_digits(_fmt_rate(p["down"])), numeric=True))
                self.proc_table.setItem(
                    r, 3, self._tcell(fa_digits(p["pid"]), numeric=True))
                self._set_kill_button(r, p["pid"])
            return
        procs = [p for p in iter_processes(self.safelist) if p["kind"] != "safe"]
        self.proc_table.setHorizontalHeaderLabels(
            [tr("col_app"), tr("col_pid"), tr("col_cpu"), tr("col_ram"), ""])
        if not procs:
            self._show_table_empty()
            return
        self.proc_table.setRowCount(len(procs))
        for r, p in enumerate(procs):
            label = p["name"] + (f" ({p['fa']})" if p["fa"] else "")
            if p["kind"] == "hog":
                label = "🔥 " + label
            self.proc_table.setItem(r, 0, self._tcell(label))
            self.proc_table.setItem(r, 1, self._tcell(fa_digits(p["pid"]), numeric=True))
            self.proc_table.setItem(r, 2, self._tcell(fa_digits(p["cpu"]), numeric=True))
            self.proc_table.setItem(r, 3, self._tcell(fa_digits(p["mem_mb"]), numeric=True))
            self._set_kill_button(r, p["pid"])
        self.proc_table.resizeColumnsToContents()

    def _kill_one(self, pid):
        ok, key, param = kill_process(pid)
        if key == "kill_ok":
            msg = f"{param} {tr(key)}"
        elif key == "kill_err":
            msg = f'{tr(key)}: {param}'
        else:
            msg = tr(key)
        self.log(("✅ " if ok else "❌ ") + msg)
        self.refresh_procs()

    # ---------- تب اسکن سرورها ----------
    def _build_scan_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.scan_hint = QtWidgets.QLabel()
        self.scan_hint.setObjectName("Sub")
        self.scan_hint.setWordWrap(True)
        lay.addWidget(self.scan_hint)

        # بنر بهترین سرور
        self.scan_best = QtWidgets.QLabel()
        self.scan_best.setObjectName("BestBanner")
        self.scan_best.setWordWrap(True)
        self.scan_best.setVisible(False)
        lay.addWidget(self.scan_best)

        # پروگرس اسکن
        prow = QtWidgets.QHBoxLayout()
        self.scan_bar = QtWidgets.QProgressBar()
        self.scan_bar.setVisible(False)
        self.scan_bar.setTextVisible(True)
        self.scan_lbl = QtWidgets.QLabel()
        self.scan_lbl.setVisible(False)
        prow.addWidget(self.scan_bar, 1)
        prow.addWidget(self.scan_lbl)
        lay.addLayout(prow)

        # دکمه‌های اسکن
        srow = QtWidgets.QHBoxLayout()
        self.btn_scan_all = QtWidgets.QPushButton()
        self.btn_scan_all.setObjectName("Go")
        self.btn_scan_all.clicked.connect(self._scan_all)
        self.btn_scan_one = QtWidgets.QPushButton()
        self.btn_scan_one.clicked.connect(self._scan_selected)
        self.btn_scan_stop = QtWidgets.QPushButton()
        self.btn_scan_stop.setObjectName("Stop")
        self.btn_scan_stop.clicked.connect(self._scan_stop)
        self.btn_scan_stop.setEnabled(False)
        srow.addWidget(self.btn_scan_all)
        srow.addWidget(self.btn_scan_one)
        srow.addWidget(self.btn_scan_stop)
        srow.addStretch(1)
        lay.addLayout(srow)

        # جدول نتایج
        self.scan_table = QtWidgets.QTableWidget(0, 6)
        self.scan_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.scan_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.scan_table.verticalHeader().setVisible(False)
        shh = self.scan_table.horizontalHeader()
        shh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for i in range(1, 6):
            shh.setSectionResizeMode(i, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.scan_table.itemDoubleClicked.connect(lambda _i: self._scan_copy_rtmp())
        lay.addWidget(self.scan_table, 1)

        # دکمه‌های مدیریت سرور
        mrow = QtWidgets.QHBoxLayout()
        self.btn_srv_add = QtWidgets.QPushButton()
        self.btn_srv_add.clicked.connect(self._scan_add)
        self.btn_srv_edit = QtWidgets.QPushButton()
        self.btn_srv_edit.clicked.connect(self._scan_edit)
        self.btn_srv_del = QtWidgets.QPushButton()
        self.btn_srv_del.setObjectName("Danger")
        self.btn_srv_del.clicked.connect(self._scan_del)
        self.btn_srv_import = QtWidgets.QPushButton()
        self.btn_srv_import.clicked.connect(self._scan_import)
        self.btn_srv_copy = QtWidgets.QPushButton()
        self.btn_srv_copy.clicked.connect(self._scan_copy_rtmp)
        mrow.addWidget(self.btn_srv_add)
        mrow.addWidget(self.btn_srv_edit)
        mrow.addWidget(self.btn_srv_del)
        mrow.addWidget(self.btn_srv_import)
        mrow.addStretch(1)
        mrow.addWidget(self.btn_srv_copy)
        lay.addLayout(mrow)

        self.tabs.addTab(w, "")

    def _retranslate_scan(self):
        rtl = get_lang() == "fa"
        align = (QtCore.Qt.AlignmentFlag.AlignRight if rtl
                 else QtCore.Qt.AlignmentFlag.AlignLeft)
        self.scan_hint.setText(tr("scan_hint"))
        self.scan_hint.setAlignment(align)
        self.scan_best.setAlignment(align)
        self.btn_scan_all.setText(tr("scan_all"))
        self.btn_scan_all.setToolTip(tr("scan_hint"))
        self.btn_scan_one.setText(tr("scan_one"))
        self.btn_scan_one.setToolTip(tr("scan_one_tip"))
        self.btn_scan_stop.setText(tr("scan_stop"))
        self.btn_scan_stop.setToolTip(tr("scan_stop_tip"))
        self.btn_srv_add.setText(tr("scan_add"))
        self.btn_srv_add.setToolTip(tr("scan_add_tip"))
        self.btn_srv_edit.setText(tr("scan_edit"))
        self.btn_srv_edit.setToolTip(tr("scan_edit_tip"))
        self.btn_srv_del.setText(tr("scan_del"))
        self.btn_srv_del.setToolTip(tr("scan_del_tip"))
        self.btn_srv_import.setText(tr("scan_import"))
        self.btn_srv_import.setToolTip(tr("scan_import_hint"))
        self.btn_srv_copy.setText(tr("scan_copy"))
        self.btn_srv_copy.setToolTip(tr("scan_copied"))
        self.scan_table.setToolTip(tr("scan_table_tip"))
        self.scan_table.setHorizontalHeaderLabels(
            [tr("scan_col_server"), tr("scan_col_region"), tr("scan_col_ping"),
             tr("scan_col_loss"), tr("scan_col_tcp"), tr("scan_col_score")])
        for i in range(6):
            item = self.scan_table.horizontalHeaderItem(i)
            if item is not None:
                item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
                    if i else (align | QtCore.Qt.AlignmentFlag.AlignVCenter))
        self._refresh_scan_table()

    def _selected_server(self):
        rows = self.scan_table.selectionModel().selectedRows()
        if not rows:
            return None
        sid = self.scan_table.item(rows[0].row(), 0)
        if sid is None:
            return None
        sid = sid.data(QtCore.Qt.ItemDataRole.UserRole)
        for s in self.servers:
            if s.get("id") == sid:
                return s
        return None

    def _fill_scan_row(self, i, s, r):
        """پر کردن سطر i جدول اسکن (برای رفرش کامل یا آپدیت درجا)."""
        fa = get_lang() == "fa"
        it0 = self._tcell(s.get("name", ""))
        it0.setData(QtCore.Qt.ItemDataRole.UserRole, s.get("id"))
        self.scan_table.setItem(i, 0, it0)
        self.scan_table.setItem(
            i, 1, self._tcell(tr("region_" + (s.get("region") or "unknown"))))
        if r is None:
            for c in range(2, 6):
                self.scan_table.setItem(i, c, self._tcell("—", numeric=True))
        elif not r["ok"]:
            for c in (2, 3, 4):
                self.scan_table.setItem(i, c, self._tcell("—", numeric=True))
            down = self._tcell(tr("scan_down"))
            down.setToolTip(tr("scan_down_tip"))
            self.scan_table.setItem(i, 5, down)
            it0.setToolTip(tr("scan_down_tip"))
        else:
            ping = f"{r['ping_ms']:.0f} ms" if r["ping_ms"] is not None else "—"
            loss = f"{r['loss']:.0f}٪" if fa else f"{r['loss']:.0f}%"
            tcp = f"{r['tcp_ms']:.0f} ms"
            self.scan_table.setItem(i, 2, self._tcell(fa_digits(ping), numeric=True))
            self.scan_table.setItem(i, 3, self._tcell(fa_digits(loss), numeric=True))
            self.scan_table.setItem(i, 4, self._tcell(fa_digits(tcp), numeric=True))
            self.scan_table.setItem(i, 5, self._tcell(
                fa_digits(f"{r['score']:.0f}"), numeric=True))

    def _scan_row_for(self, sid):
        """پیدا کردن سطر جدول برای id سرور (آپدیت درجا، بدون پرش)."""
        for i in range(self.scan_table.rowCount()):
            it = self.scan_table.item(i, 0)
            if it is not None and it.data(QtCore.Qt.ItemDataRole.UserRole) == sid:
                return i
        return -1

    def _refresh_scan_table(self):
        """جدول سرورها مرتب بر اساس امتیاز (بهترین اول)."""
        if not self.servers:
            self.scan_table.setRowCount(0)
            self.scan_hint.setText(tr("scan_no_servers_hint"))
            self.scan_best.setVisible(False)
            return
        self.scan_hint.setText(tr("scan_hint"))
        rows = []
        for s in self.servers:
            r = self._scan_results.get(s.get("id"))
            rows.append((r["score"] if r else float("inf"), s, r))
        rows.sort(key=lambda x: x[0])
        self.scan_table.setRowCount(len(rows))
        for i, (_sc, s, r) in enumerate(rows):
            self._fill_scan_row(i, s, r)
        self._update_best_banner()

    def _update_best_banner(self):
        best = None
        for s in self.servers:
            r = self._scan_results.get(s.get("id"))
            if r and r["ok"] and (best is None or r["score"] < best[1]["score"]):
                best = (s, r)
        if best is None:
            self.scan_best.setVisible(False)
            return
        s, r = best
        url = server_rtmp_url(s)
        txt = f"{tr('scan_best')}: {s.get('name')}"
        if url:
            txt += f" — {url}"
        self.scan_best.setText(txt)
        self.scan_best.setVisible(True)

    # ----- اجرای اسکن -----
    def _scan_all(self):
        if self._scanning:
            return
        if not self.servers:
            QtWidgets.QMessageBox.information(
                self, tr("tab_scan"), tr("scan_no_servers_hint"))
            return
        self._start_scan(list(self.servers))

    def _scan_selected(self):
        if self._scanning:
            return
        s = self._selected_server()
        if s is None:
            QtWidgets.QMessageBox.information(
                self, tr("tab_scan"), tr("scan_select_first"))
            return
        self._start_scan([s])

    def _start_scan(self, servers):
        self._scanning = True
        self.scan_bar.setVisible(True)
        self.scan_lbl.setVisible(True)
        self.scan_bar.setRange(0, len(servers))
        self.scan_bar.setValue(0)
        self.btn_scan_all.setEnabled(False)
        self.btn_scan_one.setEnabled(False)
        self.btn_scan_stop.setEnabled(True)
        self.scan_lbl.setText(tr("scan_scanning"))
        self._scan_thread = ScanThread(servers, parent=self)
        self._scan_thread.progress.connect(self._on_scan_progress)
        self._scan_thread.result_ready.connect(self._on_scan_result)
        self._scan_thread.finished_all.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_progress(self, done, total):
        self.scan_bar.setValue(done)
        self.scan_lbl.setText(f"{tr('scan_scanning')} {fa_digits(done)} {tr('scan_of')} {fa_digits(total)}")

    def _on_scan_result(self, r):
        # آپدیت درجا بدون مرتب‌سازی مجدد تا جدول حین اسکن نپرد
        if r.get("id"):
            self._scan_results[r["id"]] = r
            i = self._scan_row_for(r["id"])
            if i >= 0:
                s = next((x for x in self.servers if x.get("id") == r["id"]), None)
                if s is not None:
                    self._fill_scan_row(i, s, r)

    def _on_scan_done(self, results):
        self._scanning = False
        self.scan_bar.setVisible(False)
        self.scan_lbl.setVisible(False)
        self.btn_scan_all.setEnabled(True)
        self.btn_scan_one.setEnabled(True)
        self.btn_scan_stop.setEnabled(False)
        self._scan_thread = None
        ups = [r for r in results if r.get("ok")]
        self._refresh_scan_table()
        if not ups:
            self.log("❌ " + tr("scan_none_up"))
            QtWidgets.QMessageBox.warning(self, tr("tab_scan"), tr("scan_none_up"))
        else:
            self.log(f"⚡ {len(ups)} {tr('scan_up')}")

    def _scan_stop(self):
        if self._scan_thread is not None:
            self._scan_thread.stop()

    # ----- مدیریت سرورها -----
    def _scan_add(self):
        dlg = ServerEditDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            v = dlg.values()
            self.servers, s = srv_add(v["name"], v["host"], v["port"], v["region"])
            self._refresh_scan_table()
            self.log(f"➕ {s['name']}")

    def _scan_edit(self):
        s = self._selected_server()
        if s is None:
            QtWidgets.QMessageBox.information(
                self, tr("tab_scan"), tr("scan_select_first"))
            return
        dlg = ServerEditDialog(self, s)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            v = dlg.values()
            self.servers = srv_update(
                s["id"], name=v["name"], host=v["host"],
                port=v["port"], region=v["region"])
            self._refresh_scan_table()

    def _scan_del(self):
        s = self._selected_server()
        if s is None:
            QtWidgets.QMessageBox.information(
                self, tr("tab_scan"), tr("scan_select_first"))
            return
        ans = QtWidgets.QMessageBox.question(
            self, tr("scan_del"), f"{s.get('name')}\n{tr('scan_del_q')}")
        if ans == QtWidgets.QMessageBox.StandardButton.Yes:
            self.servers = srv_delete(s["id"])
            self._scan_results.pop(s["id"], None)
            self._refresh_scan_table()
            self.log(f"➖ {s.get('name')}")

    def _scan_import(self):
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, tr("scan_import_title"), tr("scan_import_hint"))
        if ok and text.strip():
            n = import_rtmp_bulk(text)
            self.servers = load_servers()
            self._refresh_scan_table()
            self.log(f"📥 {fa_digits(n)} {tr('scan_imported')}" if n
                     else f"📥 {tr('scan_import_none')}")

    def _scan_copy_rtmp(self):
        s = self._selected_server()
        if s is None:
            QtWidgets.QMessageBox.information(
                self, tr("tab_scan"), tr("scan_select_first"))
            return
        url = server_rtmp_url(s)
        QtWidgets.QApplication.clipboard().setText(url)
        self.log(f"📋 {tr('scan_copied')}: {url}")
        QtWidgets.QMessageBox.information(self, tr("scan_copy"), url)

    # ---------- تب لیست امن ----------
    def _build_safe_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.safe_hint = QtWidgets.QLabel()
        self.safe_hint.setObjectName("Sub")
        self.safe_hint.setWordWrap(True)
        lay.addWidget(self.safe_hint)
        self.safe_list = QtWidgets.QListWidget()
        self._reload_safe_list()
        lay.addWidget(self.safe_list)
        row = QtWidgets.QHBoxLayout()
        self.btn_safe_pick = QtWidgets.QPushButton()
        self.btn_safe_pick.clicked.connect(self._safe_pick)
        self.btn_safe_del = QtWidgets.QPushButton()
        self.btn_safe_del.clicked.connect(self._safe_del)
        row.addWidget(self.btn_safe_pick)
        row.addWidget(self.btn_safe_del)
        lay.addLayout(row)
        self.tabs.addTab(w, "")

    def _safe_pick(self):
        dlg = SafePickDialog(self.safelist, self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            added = 0
            for n in dlg.selected():
                if n not in self.safelist:
                    self.safelist.add(n)
                    added += 1
            if added:
                save_safelist(self.safelist)
                self._reload_safe_list()
                self.log(f"➕ {added} {tr('log_safe_pick')}")

    def _reload_safe_list(self):
        self.safe_list.clear()
        for n in sorted(self.safelist):
            self.safe_list.addItem(n)

    def _safe_del(self):
        for it in self.safe_list.selectedItems():
            self.safelist.discard(it.text())
        save_safelist(self.safelist)
        self._reload_safe_list()
        self.log(f"➖ {tr('log_safe_del')}")

    # ---------- تب تنظیمات ----------
    def _build_settings_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QFormLayout(w)
        self.lbl_server = QtWidgets.QLabel()
        self.server_edit = QtWidgets.QLineEdit(", ".join(self.cfg["servers"]))
        self.server_edit.setToolTip(tr("ping_server_hint"))
        lay.addRow(self.lbl_server, self.server_edit)
        self.ping_hint = QtWidgets.QLabel(tr("ping_server_hint"))
        self.ping_hint.setObjectName("Sub")
        self.ping_hint.setWordWrap(True)
        lay.addRow(self.ping_hint)
        self.lbl_bitrate = QtWidgets.QLabel()
        self.bitrate_spin = QtWidgets.QDoubleSpinBox()
        self.bitrate_spin.setRange(1, 50)
        self.bitrate_spin.setSingleStep(0.5)
        self.bitrate_spin.setValue(float(self.cfg.get("bitrate_mbps", 8.0)))
        lay.addRow(self.lbl_bitrate, self.bitrate_spin)
        self.lbl_lang = QtWidgets.QLabel()
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItems(["فارسی", "English"])
        self.lang_combo.setCurrentIndex(0 if get_lang() == "fa" else 1)
        self.lang_combo.currentIndexChanged.connect(self._lang_combo_changed)
        lay.addRow(self.lbl_lang, self.lang_combo)
        self.btn_save = QtWidgets.QPushButton()
        self.btn_save.clicked.connect(self._save_settings)
        lay.addRow(self.btn_save)
        self.set_note = QtWidgets.QLabel()
        self.set_note.setObjectName("Sub")
        self.set_note.setWordWrap(True)
        lay.addRow(self.set_note)
        self.tabs.addTab(w, "")

    def _lang_combo_changed(self, idx):
        new = "fa" if idx == 0 else "en"
        if new != get_lang():
            self.toggle_lang()
            self.lang_combo.setCurrentIndex(0 if new == "fa" else 1)

    def _save_settings(self):
        servers = [s.strip() for s in self.server_edit.text().split(",") if s.strip()]
        self.cfg["servers"] = servers or ["8.8.8.8"]
        self.cfg["bitrate_mbps"] = float(self.bitrate_spin.value())
        save_config(self.cfg)
        self.log(tr("log_settings_saved"))

    def _servers(self):
        return self.cfg.get("servers", ["8.8.8.8"])

    # ---------- تب لاگ ----------
    def _build_log_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setObjectName("Log")
        self.log_view.setReadOnly(True)
        lay.addWidget(self.log_view)
        self.tabs.addTab(w, "")

    def log(self, msg):
        ts = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.log_view.append(f"[{fa_digits(ts)}] {msg}")

    # ---------- شبکه ----------
    def _on_net_stats(self, s):
        self._last_stats = s
        self.card_up.set(fa_digits(f'{s["up_mbps"]:.1f}') + " Mbps")
        self.card_down.set(fa_digits(f'{s["down_mbps"]:.1f}') + " Mbps")
        if s["ping_ms"] is not None:
            if s["jitter_ms"] is not None:
                jm = "%d" % round(s["jitter_ms"])
                extra = " (" + tr("jitter") + " " + fa_digits(jm) + ")"
            else:
                extra = ""
            self.card_ping.set(fa_digits(f'{s["ping_ms"]:.0f}') + " ms" + extra)
        else:
            self.card_ping.set(tr("disconnected"), RED)
        self._last_delay_key = delay_health(s["up_mbps"], float(self.cfg.get("bitrate_mbps", 8.0)))
        self._update_delay_card()

    def _update_delay_card(self):
        key = self._last_delay_key
        color = {"good": GREEN, "warn": AMBER, "bad": RED, "unknown": MUTED}[key]
        self.card_delay.set(tr("delay_" + key), color)
        self.card_delay.setToolTip(tr("delay_" + key + "_d"))

    # ---------- حالت استریم ----------
    def toggle_stream(self):
        if not self.streaming:
            # تأیید قبل از کار خطرناک: بستن دسته‌جمعی برنامه‌ها
            victims = [p for p in iter_processes(self.safelist) if p["kind"] == "hog"]
            if victims:
                names = ", ".join(p["name"] for p in victims[:8])
                if len(victims) > 8:
                    names += f" (+{fa_digits(len(victims) - 8)})"
                box = QtWidgets.QMessageBox(self)
                box.setWindowTitle(tr("stream_confirm_title"))
                box.setText(tr("stream_confirm_msg").format(
                    n=fa_digits(len(victims)), names=names))
                box.setStandardButtons(
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No)
                box.button(QtWidgets.QMessageBox.StandardButton.Yes).setText(
                    tr("stream_confirm_yes"))
                box.button(QtWidgets.QMessageBox.StandardButton.No).setText(
                    tr("stream_confirm_no"))
                box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
                if box.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
                    self.log(tr("log_stream_cancel"))
                    return
            self.log(tr("log_stream_on"))
            killed, skipped = stream_mode_cleanup(self.safelist)
            for name, key, param in killed:
                self.log("🔥 " + self._fmt_kill(name, key, param))
            for name, key, param in skipped:
                self.log("⚠ " + self._fmt_kill(name, key, param))
            if not killed:
                self.log(tr("log_nothing"))
            self.streaming = True
            self._refresh_stream_btn()
            self._refresh_pill()
        else:
            self.streaming = False
            self._refresh_stream_btn()
            self._refresh_pill()
            self.log(tr("log_stream_off"))

    @staticmethod
    def _fmt_kill(name, key, param):
        if key == "kill_ok":
            return f"{name} {tr(key)}"
        if key == "kill_err":
            return f"{name}: {tr(key)}: {param}"
        return f"{name}: {tr(key)}"

    def closeEvent(self, event):
        if self._scan_thread is not None:
            self._scan_thread.stop()
            self._scan_thread.wait(3000)
        self.proc_timer.stop()
        self.netmon.stop()
        self.netmon.wait(2000)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    # فونت وزیرمتن (باندل‌شده در exe؛ OFL)
    for _f in ("fonts/Vazirmatn-Regular.ttf", "fonts/Vazirmatn-Bold.ttf"):
        _p = asset_path(_f)
        if os.path.exists(_p):
            QtGui.QFontDatabase.addApplicationFont(_p)
    # جهت اولیه از کانفیگ
    cfg_lang = load_config().get("lang", "fa")
    app.setLayoutDirection(
        QtCore.Qt.LayoutDirection.RightToLeft if cfg_lang == "fa"
        else QtCore.Qt.LayoutDirection.LeftToRight)
    app.setStyleSheet(QSS)
    win = LagSliceWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
