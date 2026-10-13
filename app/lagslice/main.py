# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""رابط اصلی LagSlice — دوزبانه (فارسی/انگلیسی)، راست‌چین/چپ‌چین، تم تیره نئونی.

معماری دوزبانه (دستور طه): هیچ رشته‌ی نمایشی هاردکد نیست؛ همه از
`tr(key)` در lagslice/i18n.py می‌آیند و با `retranslate_ui()` زنده
تعویض می‌شوند.
"""
import json
import os
import sys

from PyQt6 import QtCore, QtGui, QtWidgets

from lagslice import __version__
from lagslice.i18n import (
    LANG_NAMES,
    get_language,
    is_rtl,
    num,
    set_language,
    tr,
)
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
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: {BG}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px; }}
QTextEdit#Log {{ background-color: #080B11; border: 1px solid {BORDER}; border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; }}
QLabel#Warn {{ background-color: #2A1E08; border: 1px solid {AMBER}; border-radius: 8px; padding: 8px 12px; color: {AMBER}; }}
"""


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
    def __init__(self, name_key, parent=None):
        super().__init__(parent)
        self._name_key = name_key
        self.setObjectName("Card")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        self.name_lbl = QtWidgets.QLabel(tr(name_key))
        self.name_lbl.setObjectName("StatName")
        self.val_lbl = QtWidgets.QLabel("—")
        self.val_lbl.setObjectName("StatVal")
        lay.addWidget(self.name_lbl)
        lay.addWidget(self.val_lbl)

    def set(self, text, color=None):
        self.val_lbl.setText(text)
        if color:
            self.val_lbl.setStyleSheet(f"color: {color};")

    def retranslate(self):
        self.name_lbl.setText(tr(self._name_key))


ABOUT_FALLBACK = """«LagSlice» — بهینه‌ساز استریم
Copyright (C) 2026 Taha Arefi (طه عارفی)

این برنامه نرم‌افزار آزاد است: شما می‌توانید آن را تحت شرایط
«GNU Affero General Public License» نسخه‌ی ۳ (یا هر نسخه‌ی جدیدتر،
به انتخاب شما) بازتوزیع و/یا اصلاح کنید.
متن کامل لایسنس: فایل LICENSE در ریپوی گیت‌هاب + https://www.gnu.org/licenses/agpl-3.0.html
سورس‌کد: https://github.com/thaarfknight-star/LagSlice"""


def _about_text():
    """متن دیالوگ «درباره» — از docs/about-dialog-fa.txt (باندل‌شده در exe)."""
    cands = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(os.path.join(meipass, "docs", "about-dialog-fa.txt"))
    cands.append(os.path.join(APP_DIR, "..", "docs", "about-dialog-fa.txt"))
    for c in cands:
        try:
            with open(c, "r", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            continue
    return ABOUT_FALLBACK


class AboutDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.resize(480, 420)
        layout = QtWidgets.QVBoxLayout(self)
        if LOGO_PATH:
            logo = QtWidgets.QLabel()
            pm = QtGui.QPixmap(LOGO_PATH).scaledToHeight(
                72, QtCore.Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pm)
            logo.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo)
        txt = QtWidgets.QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(_about_text())
        layout.addWidget(txt)
        btn = QtWidgets.QPushButton(tr("about_ok"))
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class LagSliceWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
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
        self.title_lbl = QtWidgets.QLabel("LagSlice ⚡")
        self.title_lbl.setObjectName("Title")
        self.sub_lbl = QtWidgets.QLabel()
        self.sub_lbl.setObjectName("Sub")
        tbox.addWidget(self.title_lbl)
        tbox.addWidget(self.sub_lbl)
        head.addLayout(tbox)
        head.addStretch(1)
        self.pill = QtWidgets.QLabel()
        self.pill.setObjectName("Pill")
        head.addWidget(self.pill)
        self.about_btn = QtWidgets.QPushButton()
        self.about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        head.addWidget(self.about_btn)
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItems([LANG_NAMES["fa"], LANG_NAMES["en"]])
        self.lang_combo.setCurrentText(LANG_NAMES[get_language()])
        self.lang_combo.currentTextChanged.connect(self._on_lang_changed)
        head.addWidget(self.lang_combo)
        root.addLayout(head)

        self.warn_lbl = None
        if not is_admin():
            self.warn_lbl = QtWidgets.QLabel()
            self.warn_lbl.setObjectName("Warn")
            self.warn_lbl.setWordWrap(True)
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

        self.retranslate_ui()
        self.log(tr("log_ready"))

    # ---------- تعویض زبان ----------
    def _on_lang_changed(self, text):
        for code, name in LANG_NAMES.items():
            if name == text and code != get_language():
                set_language(code)
                app = QtWidgets.QApplication.instance()
                if app:
                    app.setLayoutDirection(
                        QtCore.Qt.LayoutDirection.RightToLeft if is_rtl()
                        else QtCore.Qt.LayoutDirection.LeftToRight)
                self.retranslate_ui()
                self.log(tr("log_lang_changed"))
                break

    def retranslate_ui(self):
        """به‌روزرسانی همه‌ی متن‌های UI به زبان فعلی."""
        self.setWindowTitle(tr("window_title").format(v=__version__))
        self.sub_lbl.setText(tr("app_subtitle"))
        self.about_btn.setText(tr("about_btn"))
        if self.warn_lbl:
            self.warn_lbl.setText(tr("warn_no_admin"))
        for c in (self.card_up, self.card_down, self.card_ping, self.card_delay):
            c.retranslate()
        self._paint_pill()
        self._paint_stream_btn()
        self.tabs.setTabText(0, tr("tab_procs"))
        self.tabs.setTabText(1, tr("tab_safe"))
        self.tabs.setTabText(2, tr("tab_settings"))
        self.tabs.setTabText(3, tr("tab_log"))
        self.proc_hint.setText(tr("proc_hint"))
        self.proc_table.setHorizontalHeaderLabels(
            [tr("col_name"), tr("col_pid"), tr("col_cpu"), tr("col_ram"), ""])
        self.safe_hint.setText(tr("safe_hint"))
        self.safe_input.setPlaceholderText(tr("safe_placeholder"))
        self.safe_add_btn.setText(tr("safe_add"))
        self.safe_del_btn.setText(tr("safe_del"))
        self.lbl_server.setText(tr("set_server"))
        self.server_edit.setPlaceholderText(tr("set_server_ph"))
        self.lbl_bitrate.setText(tr("set_bitrate"))
        self.save_btn.setText(tr("set_save"))
        self.set_note.setText(tr("set_note"))
        self.lbl_lang.setText(tr("set_lang"))
        # بازسازی جدول تا توضیحات hog هم ترجمه شوند
        self.refresh_procs()

    def _paint_pill(self):
        if self.streaming:
            self.pill.setText(tr("pill_streaming"))
            self.pill.setStyleSheet(f"background-color: #3A0F1E; color: {RED};")
        else:
            self.pill.setText(tr("pill_ready"))
            self.pill.setStyleSheet(f"background-color: #1B2940; color: {MUTED};")

    def _paint_stream_btn(self):
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
        self.proc_table.horizontalHeader().setStretchLastSection(True)
        self.proc_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.proc_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.proc_table)
        self.tabs.addTab(w, "")

    def refresh_procs(self):
        procs = [p for p in iter_processes(self.safelist) if p["kind"] != "safe"]
        self.proc_table.setRowCount(len(procs))
        for r, p in enumerate(procs):
            desc = tr(p["fa"]) if p["fa"] else ""
            label = p["name"] + (f" ({desc})" if desc else "")
            if p["kind"] == "hog":
                label = "🔥 " + label
            self.proc_table.setItem(r, 0, QtWidgets.QTableWidgetItem(label))
            self.proc_table.setItem(r, 1, QtWidgets.QTableWidgetItem(num(p["pid"])))
            self.proc_table.setItem(r, 2, QtWidgets.QTableWidgetItem(num(p["cpu"])))
            self.proc_table.setItem(r, 3, QtWidgets.QTableWidgetItem(num(p["mem_mb"])))
            btn = QtWidgets.QPushButton(tr("col_close"))
            btn.setObjectName("Danger")
            btn.clicked.connect(lambda _=False, pid=p["pid"]: self._kill_one(pid))
            self.proc_table.setCellWidget(r, 4, btn)
        self.proc_table.resizeColumnsToContents()

    def _kill_one(self, pid):
        ok, msg_key, name = kill_process(pid)
        if msg_key == "kill_ok":
            text = tr(msg_key).format(name=name)
        elif msg_key == "kill_err":
            text = tr(msg_key).format(e=name)
        else:
            text = tr(msg_key)
        self.log(("✅ " if ok else "❌ ") + text)
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
        self.safe_add_btn = QtWidgets.QPushButton()
        self.safe_add_btn.clicked.connect(self._safe_add)
        self.safe_del_btn = QtWidgets.QPushButton()
        self.safe_del_btn.clicked.connect(self._safe_del)
        row.addWidget(self.safe_input)
        row.addWidget(self.safe_add_btn)
        row.addWidget(self.safe_del_btn)
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
            self.log(tr("log_safe_added").format(n=n))

    def _safe_del(self):
        for it in self.safe_list.selectedItems():
            self.safelist.discard(it.text())
        save_safelist(self.safelist)
        self._reload_safe_list()
        self.log(tr("log_safe_removed"))

    # ---------- تب تنظیمات ----------
    def _build_settings_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QFormLayout(w)
        self.lbl_lang = QtWidgets.QLabel()
        self.lang_combo2 = QtWidgets.QComboBox()
        self.lang_combo2.addItems([LANG_NAMES["fa"], LANG_NAMES["en"]])
        self.lang_combo2.setCurrentText(LANG_NAMES[get_language()])
        self.lang_combo2.currentTextChanged.connect(self._on_lang_changed)
        lay.addRow(self.lbl_lang, self.lang_combo2)
        self.lbl_server = QtWidgets.QLabel()
        self.server_edit = QtWidgets.QLineEdit(", ".join(self.cfg["servers"]))
        lay.addRow(self.lbl_server, self.server_edit)
        self.lbl_bitrate = QtWidgets.QLabel()
        self.bitrate_spin = QtWidgets.QDoubleSpinBox()
        self.bitrate_spin.setRange(1, 50)
        self.bitrate_spin.setSingleStep(0.5)
        self.bitrate_spin.setValue(float(self.cfg.get("bitrate_mbps", 8.0)))
        lay.addRow(self.lbl_bitrate, self.bitrate_spin)
        self.save_btn = QtWidgets.QPushButton()
        self.save_btn.clicked.connect(self._save_settings)
        lay.addRow(self.save_btn)
        self.set_note = QtWidgets.QLabel()
        self.set_note.setObjectName("Sub")
        self.set_note.setWordWrap(True)
        lay.addRow(self.set_note)
        self.tabs.addTab(w, "")

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
        self.log_view.append(f"[{num(ts)}] {msg}")

    # ---------- شبکه ----------
    def _on_net_stats(self, s):
        self.card_up.set(num(f'{s["up_mbps"]:.1f}') + " Mbps")
        self.card_down.set(num(f'{s["down_mbps"]:.1f}') + " Mbps")
        if s["ping_ms"] is not None:
            jw = "جیتر" if is_rtl() else "jitter"
            extra = f' ({jw} {num(f"{s["jitter_ms"]:.0f}")})' if s["jitter_ms"] is not None else ""
            self.card_ping.set(num(f'{s["ping_ms"]:.0f}') + " ms" + extra)
        else:
            self.card_ping.set(tr("net_down"), RED)
        key = delay_health(s["up_mbps"], float(self.cfg.get("bitrate_mbps", 8.0)))
        color = {"good": GREEN, "warn": AMBER, "bad": RED, "unknown": MUTED}[key]
        self.card_delay.set(tr("delay_" + key), color)
        self.card_delay.setToolTip(tr("delay_" + key + "_tip"))

    # ---------- حالت استریم ----------
    def toggle_stream(self):
        if not self.streaming:
            self.log(tr("log_stream_on"))
            results = stream_mode_cleanup(self.safelist)
            if not results:
                self.log(tr("log_nothing"))
            for ok, name, msg_key in results:
                if msg_key == "kill_ok":
                    text = tr(msg_key).format(name=name)
                elif msg_key == "kill_err":
                    text = tr(msg_key).format(e=name)
                else:
                    text = f"{name}: {tr(msg_key)}"
                self.log(("🔥 " if ok else "⚠ ") + text)
            self.streaming = True
            self._paint_stream_btn()
            self._paint_pill()
        else:
            self.streaming = False
            self._paint_stream_btn()
            self._paint_pill()
            self.log(tr("log_stream_off"))

    def closeEvent(self, event):
        self.proc_timer.stop()
        self.netmon.stop()
        self.netmon.wait(2000)
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft if is_rtl()
                           else QtCore.Qt.LayoutDirection.LeftToRight)
    app.setStyleSheet(QSS)
    win = LagSliceWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
