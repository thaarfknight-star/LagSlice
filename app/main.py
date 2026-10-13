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

from PyQt6 import QtCore, QtGui, QtWidgets

from lang import tr, set_lang, get_lang, fa_digits
from netmon import NetMonitor, delay_health
from procman import (
    iter_processes, kill_process, stream_mode_cleanup,
    load_safelist, save_safelist, is_admin, base_dir,
    NEVER_TOUCH, HOG_PATTERNS,
)
import psutil


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
QWidget {{ background-color: {BG}; color: {TEXT}; font-family: "Segoe UI", Tahoma, sans-serif; font-size: 13px; }}
QLabel#Title {{ font-size: 22px; font-weight: bold; color: {CYAN}; }}
QLabel#Sub {{ font-size: 12px; color: {MUTED}; }}
QLabel#StatVal {{ font-size: 20px; font-weight: bold; color: {TEXT}; }}
QLabel#StatName {{ font-size: 11px; color: {MUTED}; }}
QLabel#Pill {{ border-radius: 12px; padding: 6px 14px; font-weight: bold; }}
QFrame#Card {{ background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QPushButton {{ background-color: #16202F; border: 1px solid {CYAN}; border-radius: 10px; padding: 10px 18px; color: {TEXT}; font-weight: bold; }}
QPushButton:hover {{ background-color: #1B2940; }}
QPushButton:disabled {{ border-color: #3A4356; color: #5B6577; background-color: #121826; }}
QPushButton#Go {{ border-color: {GREEN}; font-size: 15px; padding: 14px; }}
QPushButton#Stop {{ border-color: {RED}; font-size: 15px; padding: 14px; }}
QPushButton#Danger {{ border-color: {MAGENTA}; }}
QPushButton#Lang {{ border-color: {MAGENTA}; padding: 6px 14px; }}
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

    def set(self, text, color=None):
        self.val_lbl.setText(text)
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
        btn = QtWidgets.QPushButton("OK")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)


class LagSliceWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        set_lang(self.cfg.get("lang", "fa"))
        self.safelist = load_safelist()
        self.streaming = False
        self._last_delay_key = "unknown"

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
        self.sub_lbl.setText(tr("app_subtitle"))
        self.btn_lang.setText("EN" if get_lang() == "fa" else "فا")
        self.btn_about.setText(tr("about_btn"))
        self.warn_lbl.setText(tr("admin_warn"))
        for c in (self.card_up, self.card_down, self.card_ping, self.card_delay):
            c.retranslate()
        self._refresh_pill()
        self._refresh_stream_btn()
        self.tabs.setTabText(0, tr("tab_procs"))
        self.tabs.setTabText(1, tr("tab_safe"))
        self.tabs.setTabText(2, tr("tab_settings"))
        self.tabs.setTabText(3, tr("tab_log"))
        self.proc_hint.setText(tr("procs_hint"))
        self.proc_table.setHorizontalHeaderLabels(
            [tr("col_app"), tr("col_pid"), tr("col_cpu"), tr("col_ram"), ""])
        self.safe_hint.setText(tr("safe_hint"))
        self.safe_input.setPlaceholderText(tr("safe_placeholder"))
        self.btn_safe_add.setText(tr("safe_add"))
        self.btn_safe_del.setText(tr("safe_del"))
        self.lbl_server.setText(tr("set_server"))
        self.server_edit.setPlaceholderText(tr("set_server_ph"))
        self.lbl_bitrate.setText(tr("set_bitrate"))
        self.btn_save.setText(tr("set_save"))
        self.set_note.setText(tr("set_note"))
        self.lbl_lang.setText(tr("lang_label"))
        self._update_delay_card()
        self.refresh_procs()

    def show_about(self):
        AboutDialog(self).exec()

    def _refresh_pill(self):
        if self.streaming:
            self.pill.setText(tr("status_streaming"))
            self.pill.setStyleSheet(f"background-color: #3A0F1E; color: {RED};")
        else:
            self.pill.setText(tr("status_ready"))
            self.pill.setStyleSheet(f"background-color: #1B2940; color: {MUTED};")

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
        lay.addWidget(self.proc_table)
        self.tabs.addTab(w, "")

    def refresh_procs(self):
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
            self.proc_table.setRowCount(len(rows))
            for r, p in enumerate(rows):
                label = p["name"] + (f" ({p['fa']})" if p["fa"] else "")
                if p["kind"] == "hog":
                    label = "🔥 " + label
                self.proc_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label))
                self.proc_table.setItem(
                    r, 1, QtWidgets.QTableWidgetItem(fa_digits(_fmt_rate(p["up"]))))
                self.proc_table.setItem(
                    r, 2, QtWidgets.QTableWidgetItem(fa_digits(_fmt_rate(p["down"]))))
                self.proc_table.setItem(
                    r, 3, QtWidgets.QTableWidgetItem(fa_digits(p["pid"])))
                btn = QtWidgets.QPushButton(tr("btn_kill"))
                btn.setObjectName("Danger")
                btn.clicked.connect(lambda _=False, pid=p["pid"]: self._kill_one(pid))
                self.proc_table.setCellWidget(r, 4, btn)
            self.proc_table.resizeColumnsToContents()
            return
        procs = [p for p in iter_processes(self.safelist) if p["kind"] != "safe"]
        self.proc_table.setHorizontalHeaderLabels(
            [tr("col_app"), tr("col_pid"), tr("col_cpu"), tr("col_ram"), ""])
        self.proc_table.setRowCount(len(procs))
        for r, p in enumerate(procs):
            label = p["name"] + (f" ({p['fa']})" if p["fa"] else "")
            if p["kind"] == "hog":
                label = "🔥 " + label
            self.proc_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label))
            self.proc_table.setItem(r, 1, QtWidgets.QTableWidgetItem(fa_digits(p["pid"])))
            self.proc_table.setItem(r, 2, QtWidgets.QTableWidgetItem(fa_digits(p["cpu"])))
            self.proc_table.setItem(r, 3, QtWidgets.QTableWidgetItem(fa_digits(p["mem_mb"])))
            btn = QtWidgets.QPushButton(tr("btn_kill"))
            btn.setObjectName("Danger")
            btn.clicked.connect(lambda _=False, pid=p["pid"]: self._kill_one(pid))
            self.proc_table.setCellWidget(r, 4, btn)
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
        self.safe_input = QtWidgets.QLineEdit()
        self.btn_safe_add = QtWidgets.QPushButton()
        self.btn_safe_add.clicked.connect(self._safe_add)
        self.btn_safe_del = QtWidgets.QPushButton()
        self.btn_safe_del.clicked.connect(self._safe_del)
        row.addWidget(self.safe_input)
        row.addWidget(self.btn_safe_add)
        row.addWidget(self.btn_safe_del)
        lay.addLayout(row)
        self.tabs.addTab(w, "")

    def _reload_safe_list(self):
        self.safe_list.clear()
        for n in sorted(self.safelist):
            self.safe_list.addItem(n)

    def _safe_add(self):
        n = self.safe_input.text().strip().lower()
        if n:
            self.safelist.add(n)
            save_safelist(self.safelist)
            self._reload_safe_list()
            self.safe_input.clear()
            self.log(f"➕ {n} {tr('log_safe_add')}")

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
        lay.addRow(self.lbl_server, self.server_edit)
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
            extra = f' ({tr("jitter")} {fa_digits(f"{s["jitter_ms"]:.0f}")})' if s["jitter_ms"] is not None else ""
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
        self.proc_timer.stop()
        self.netmon.stop()
        self.netmon.wait(2000)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
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
