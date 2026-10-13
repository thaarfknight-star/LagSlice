# -*- coding: utf-8 -*-
"""رابط اصلی LagSlice — فارسی، راست‌چین، تم تیره نئونی (بر اساس لوگو)."""
import json
import os
import sys

from PyQt6 import QtCore, QtGui, QtWidgets

from lagslice import __version__
from lagslice.netmon import NetMonitor, delay_health
from lagslice.procman import (
    iter_processes, kill_process, stream_mode_cleanup,
    load_safelist, save_safelist, is_admin,
)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _data_dir():
    """مسیر ذخیره‌ی تنظیمات کاربر: روی ویندوز %APPDATA% (در exe موقت گم نمی‌شود)."""
    try:
        base = os.environ.get("APPDATA")
        if base:
            d = os.path.join(base, "LagSlice")
            os.makedirs(d, exist_ok=True)
            return d
    except Exception:
        pass
    return APP_DIR


CONFIG_PATH = os.path.join(_data_dir(), "lagslice_config.json")


def _find_logo():
    cands = []
    meipass = getattr(sys, "_MEIPASS", None)  # داخل exe باندل‌شده
    if meipass:
        cands.append(os.path.join(meipass, "lagslice-logo.png"))
    cands += [
        os.path.join(APP_DIR, "..", "assets", "lagslice-logo.png"),
        os.path.join(APP_DIR, "..", "logo", "lagslice-logo-transparent.png"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


LOGO_PATH = _find_logo()

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

FA_DIGITS = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")


def fa(s):
    return str(s).translate(FA_DIGITS)


def load_config():
    cfg = {"servers": ["8.8.8.8"], "bitrate_mbps": 8.0}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                cfg.update(data)
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


class StatCard(QtWidgets.QFrame):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        self.name_lbl = QtWidgets.QLabel(name)
        self.name_lbl.setObjectName("StatName")
        self.val_lbl = QtWidgets.QLabel("—")
        self.val_lbl.setObjectName("StatVal")
        lay.addWidget(self.name_lbl)
        lay.addWidget(self.val_lbl)

    def set(self, text, color=None):
        self.val_lbl.setText(text)
        if color:
            self.val_lbl.setStyleSheet(f"color: {color};")


class LagSliceWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LagSlice ⚡ — بهینه‌ساز استریم (نسخه {__version__})")
        self.resize(980, 700)
        self.cfg = load_config()
        self.safelist = load_safelist()
        self.streaming = False

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setSpacing(10)

        # --- سربرگ ---
        head = QtWidgets.QHBoxLayout()
        if LOGO_PATH:
            logo = QtWidgets.QLabel()
            pm = QtGui.QPixmap(LOGO_PATH).scaledToHeight(64, QtCore.Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pm)
            head.addWidget(logo)
        tbox = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("LagSlice ⚡")
        title.setObjectName("Title")
        sub = QtWidgets.QLabel("بهینه‌ساز استریم — اینترنت ایران")
        sub.setObjectName("Sub")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        head.addLayout(tbox)
        head.addStretch(1)
        self.pill = QtWidgets.QLabel("آماده")
        self.pill.setObjectName("Pill")
        self.pill.setStyleSheet(f"background-color: #1B2940; color: {MUTED};")
        head.addWidget(self.pill)
        root.addLayout(head)

        if not is_admin():
            warn = QtWidgets.QLabel("⚠ بدون دسترسی ادمین اجرا شدی؛ بستن بعضی برنامه‌ها کار نمی‌کند. با Run as administrator اجرا کن.")
            warn.setObjectName("Warn")
            warn.setWordWrap(True)
            root.addWidget(warn)

        # --- کارت‌های آمار ---
        stats = QtWidgets.QHBoxLayout()
        self.card_up = StatCard("آپلود لحظه‌ای")
        self.card_down = StatCard("دانلود لحظه‌ای")
        self.card_ping = StatCard("پینگ سرور")
        self.card_delay = StatCard("وضعیت تأخیر ویور (تخمینی)")
        for c in (self.card_up, self.card_down, self.card_ping, self.card_delay):
            stats.addWidget(c)
        root.addLayout(stats)

        # --- دکمه حالت استریم ---
        self.btn_stream = QtWidgets.QPushButton("🎬 شروع حالت استریم")
        self.btn_stream.setObjectName("Go")
        self.btn_stream.clicked.connect(self.toggle_stream)
        root.addWidget(self.btn_stream)

        # --- تب‌ها ---
        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_proc_tab()
        self._build_safe_tab()
        self._build_settings_tab()
        self._build_log_tab()

        # --- مانیتور شبکه ---
        self.netmon = NetMonitor(self._servers, self)
        self.netmon.updated.connect(self._on_net_stats)
        self.netmon.start()

        # رفرش جدول پروسس‌ها هر ۵ ثانیه
        self.proc_timer = QtCore.QTimer(self)
        self.proc_timer.timeout.connect(self.refresh_procs)
        self.proc_timer.start(5000)
        self.refresh_procs()

        self.log("LagSlice آماده است ⚡")

    # ---------- تب برنامه‌ها ----------
    def _build_proc_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        hint = QtWidgets.QLabel("برنامه‌های اینترنت‌خور (غیر لیست امن) را می‌توانی ببندی. پروسس‌های سیستمی و لیست امن هرگز نمایش داده نمی‌شوند.")
        hint.setObjectName("Sub")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.proc_table = QtWidgets.QTableWidget(0, 5)
        self.proc_table.setHorizontalHeaderLabels(["برنامه", "PID", "CPU ٪", "RAM (MB)", ""])
        self.proc_table.horizontalHeader().setStretchLastSection(True)
        self.proc_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.proc_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.proc_table)
        self.tabs.addTab(w, "برنامه‌ها")

    def refresh_procs(self):
        procs = [p for p in iter_processes(self.safelist) if p["kind"] != "safe"]
        self.proc_table.setRowCount(len(procs))
        for r, p in enumerate(procs):
            label = p["name"] + (f" ({p['fa']})" if p["fa"] else "")
            if p["kind"] == "hog":
                label = "🔥 " + label
            self.proc_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label))
            self.proc_table.setItem(r, 1, QtWidgets.QTableWidgetItem(fa(p["pid"])))
            self.proc_table.setItem(r, 2, QtWidgets.QTableWidgetItem(fa(p["cpu"])))
            self.proc_table.setItem(r, 3, QtWidgets.QTableWidgetItem(fa(p["mem_mb"])))
            btn = QtWidgets.QPushButton("بستن")
            btn.setObjectName("Danger")
            btn.clicked.connect(lambda _=False, pid=p["pid"]: self._kill_one(pid))
            self.proc_table.setCellWidget(r, 4, btn)
        self.proc_table.resizeColumnsToContents()

    def _kill_one(self, pid):
        ok, msg = kill_process(pid)
        self.log(("✅ " if ok else "❌ ") + msg)
        self.refresh_procs()

    # ---------- تب لیست امن ----------
    def _build_safe_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        hint = QtWidgets.QLabel("این برنامه‌ها در «حالت استریم» هرگز بسته نمی‌شوند. اسم فایل اجرایی (مثل cs2.exe) را اضافه یا حذف کن.")
        hint.setObjectName("Sub")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.safe_list = QtWidgets.QListWidget()
        self._reload_safe_list()
        lay.addWidget(self.safe_list)
        row = QtWidgets.QHBoxLayout()
        self.safe_input = QtWidgets.QLineEdit()
        self.safe_input.setPlaceholderText("مثلاً: myapp.exe")
        btn_add = QtWidgets.QPushButton("➕ افزودن")
        btn_add.clicked.connect(self._safe_add)
        btn_del = QtWidgets.QPushButton("➖ حذف انتخاب‌شده")
        btn_del.clicked.connect(self._safe_del)
        row.addWidget(self.safe_input)
        row.addWidget(btn_add)
        row.addWidget(btn_del)
        lay.addLayout(row)
        self.tabs.addTab(w, "لیست امن")

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
            self.log(f"➕ {n} به لیست امن اضافه شد")

    def _safe_del(self):
        for it in self.safe_list.selectedItems():
            self.safelist.discard(it.text())
        save_safelist(self.safelist)
        self._reload_safe_list()
        self.log("➖ از لیست امن حذف شد")

    # ---------- تب تنظیمات ----------
    def _build_settings_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QFormLayout(w)
        self.server_edit = QtWidgets.QLineEdit(", ".join(self.cfg["servers"]))
        self.server_edit.setPlaceholderText("آی‌پی سرور استریم (MasterStream)")
        lay.addRow("سرور پینگ:", self.server_edit)
        self.bitrate_spin = QtWidgets.QDoubleSpinBox()
        self.bitrate_spin.setRange(1, 50)
        self.bitrate_spin.setSingleStep(0.5)
        self.bitrate_spin.setValue(float(self.cfg.get("bitrate_mbps", 8.0)))
        lay.addRow("بیت‌ریت استریم (Mbps):", self.bitrate_spin)
        btn = QtWidgets.QPushButton("💾 ذخیره تنظیمات")
        btn.clicked.connect(self._save_settings)
        lay.addRow(btn)
        note = QtWidgets.QLabel("پینگ به اولین سرور لیست گرفته می‌شود. بیت‌ریت را مطابق تنظیمات MeldStudio بگذار.")
        note.setObjectName("Sub")
        note.setWordWrap(True)
        lay.addRow(note)
        self.tabs.addTab(w, "تنظیمات")

    def _save_settings(self):
        servers = [s.strip() for s in self.server_edit.text().split(",") if s.strip()]
        self.cfg["servers"] = servers or ["8.8.8.8"]
        self.cfg["bitrate_mbps"] = float(self.bitrate_spin.value())
        save_config(self.cfg)
        self.log("💾 تنظیمات ذخیره شد")

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
        self.tabs.addTab(w, "لاگ")

    def log(self, msg):
        ts = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        self.log_view.append(f"[{fa(ts)}] {msg}")

    # ---------- شبکه ----------
    def _on_net_stats(self, s):
        self.card_up.set(fa(f'{s["up_mbps"]:.1f}') + " Mbps")
        self.card_down.set(fa(f'{s["down_mbps"]:.1f}') + " Mbps")
        if s["ping_ms"] is not None:
            extra = f' (جیتر {fa(f"{s["jitter_ms"]:.0f}")})' if s["jitter_ms"] is not None else ""
            self.card_ping.set(fa(f'{s["ping_ms"]:.0f}') + " ms" + extra)
        else:
            self.card_ping.set("قطع", RED)
        key, label, desc = delay_health(s["up_mbps"], float(self.cfg.get("bitrate_mbps", 8.0)))
        color = {"good": GREEN, "warn": AMBER, "bad": RED, "unknown": MUTED}[key]
        self.card_delay.set(label, color)
        self.card_delay.setToolTip(desc)

    # ---------- حالت استریم ----------
    def toggle_stream(self):
        if not self.streaming:
            self.log("🎬 حالت استریم فعال شد؛ بستن برنامه‌های اینترنت‌خور…")
            killed, skipped = stream_mode_cleanup(self.safelist)
            for k in killed:
                self.log("🔥 " + k)
            for sk in skipped:
                self.log("⚠ " + sk)
            if not killed:
                self.log("برنامه‌ی اضافی برای بستن پیدا نشد ✅")
            self.streaming = True
            self.btn_stream.setText("⏹ توقف حالت استریم")
            self.btn_stream.setObjectName("Stop")
            self.btn_stream.setStyleSheet("")
            self.pill.setText("🔴 استریم فعال")
            self.pill.setStyleSheet(f"background-color: #3A0F1E; color: {RED};")
        else:
            self.streaming = False
            self.btn_stream.setText("🎬 شروع حالت استریم")
            self.btn_stream.setObjectName("Go")
            self.btn_stream.setStyleSheet("")
            self.pill.setText("آماده")
            self.pill.setStyleSheet(f"background-color: #1B2940; color: {MUTED};")
            self.log("⏹ حالت استریم متوقف شد")

    def closeEvent(self, event):
        self.proc_timer.stop()
        self.netmon.stop()
        self.netmon.wait(2000)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft)
    app.setStyleSheet(QSS)
    win = LagSliceWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
