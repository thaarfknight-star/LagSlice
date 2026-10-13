# -*- coding: utf-8 -*-
"""LagSlice — پنجره‌ی اصلی.

بهینه‌ساز استریم برای اینترنت ایران:
- بستن برنامه‌های اینترنت‌خور (با لیست امن قابل‌ادیت)
- پایش پینگ سرور استریم و سرعت لحظه‌ای شبکه
- هدف: نگه داشتن تأخیر ویور زیر ۲۰ ثانیه
"""

import datetime
import os
import sys

from PyQt6 import QtCore, QtGui, QtWidgets

from app import __version__
from app.netmon import NetSpeed, get_ingest_host, ping_host, quality_fa, set_ingest_host
from app.procman import (
    DEFAULT_SAFE,
    kill_process,
    list_processes,
    load_safelist,
    psutil_available,
    save_safelist,
)

_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa(s):
    return str(s).translate(_FA)


def asset_path(name):
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", name)


QSS = """
QWidget { background-color: #0a0e14; color: #e8edf5; font-family: "Segoe UI", "Vazirmatn", sans-serif; font-size: 13px; }
QLabel#Title { font-size: 22px; font-weight: bold; color: #00e5ff; }
QLabel#Sub { color: #9aa4b5; font-size: 12px; }
QLabel#Muted { color: #9aa4b5; }
QGroupBox { border: 1px solid #1e2a3d; border-radius: 10px; margin-top: 12px; background: #101724; }
QGroupBox::title { subcontrol-origin: margin; right: 12px; padding: 0 8px; color: #ff2fb3; }
QLabel#Card { background: #101724; border: 1px solid #1e2a3d; border-radius: 10px; padding: 10px; }
QLabel#CardVal { font-size: 20px; font-weight: bold; }
QPushButton { background: #16202f; border: 1px solid #00e5ff; border-radius: 8px; padding: 9px 16px; color: #e8edf5; }
QPushButton:hover { background: #1b2940; }
QPushButton:disabled { border-color: #3a4356; color: #5b6577; background: #121826; }
QPushButton#Go { border-color: #00e5ff; font-weight: bold; font-size: 14px; }
QPushButton#Danger { border-color: #ff2fb3; }
QTableWidget { background: #0b0f17; border: 1px solid #1e2a3d; border-radius: 8px; gridline-color: #1e2a3d; }
QTableWidget::item { padding: 4px; }
QHeaderView::section { background: #141b29; color: #00e5ff; border: none; padding: 6px; }
QTextEdit#Log { background: #080b11; border: 1px solid #1e2a3d; border-radius: 8px; font-family: "Consolas", monospace; font-size: 12px; }
QLineEdit { background: #0b0f17; border: 1px solid #1e2a3d; border-radius: 8px; padding: 8px; }
QListWidget { background: #0b0f17; border: 1px solid #1e2a3d; border-radius: 8px; }
QCheckBox { spacing: 6px; }
"""


class _Worker(QtCore.QObject):
    done = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    @QtCore.pyqtSlot()
    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


def run_in_thread(owner, fn, on_done, on_failed):
    thread = QtCore.QThread(owner)
    worker = _Worker(fn)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.done.connect(on_done)
    worker.failed.connect(on_failed)
    worker.done.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    owner._threads.append(thread)
    thread.finished.connect(lambda: owner._threads.remove(thread) if thread in owner._threads else None)
    thread.start()


class SafeListDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🛡 لیست امن")
        self.resize(380, 420)
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel("برنامه‌های این لیست هرگز بسته نمی‌شوند.\nنام فایل اجرایی را بنویسید (مثلاً cs2.exe).")
        info.setWordWrap(True)
        info.setObjectName("Muted")
        layout.addWidget(info)
        self.lst = QtWidgets.QListWidget()
        layout.addWidget(self.lst)
        row = QtWidgets.QHBoxLayout()
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("نام exe…")
        add_btn = QtWidgets.QPushButton("➕ افزودن")
        del_btn = QtWidgets.QPushButton("🗑 حذف")
        row.addWidget(self.edit, 1)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        layout.addLayout(row)
        ok = QtWidgets.QPushButton("💾 ذخیره و بستن")
        layout.addWidget(ok)
        add_btn.clicked.connect(self._add)
        del_btn.clicked.connect(self._del)
        ok.clicked.connect(self._save)
        self._items = load_safelist()
        self._refresh()

    def _refresh(self):
        self.lst.clear()
        for it in sorted(self._items):
            QtWidgets.QListWidgetItem(it, self.lst)

    def _add(self):
        v = self.edit.text().strip().lower()
        if v and v not in self._items:
            self._items.append(v)
            self.edit.clear()
            self._refresh()

    def _del(self):
        for it in self.lst.selectedItems():
            if it.text() in self._items:
                self._items.remove(it.text())
        self._refresh()

    def _save(self):
        save_safelist(self._items)
        self.accept()


class ServerDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ سرور استریم")
        self.resize(380, 180)
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel("آدرس سرور ingest استریم (MasterStream) برای پایش پینگ:")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("مثلاً: ingest.masterstream.tv")
        self.edit.setText(get_ingest_host())
        layout.addWidget(self.edit)
        ok = QtWidgets.QPushButton("💾 ذخیره")
        layout.addWidget(ok)
        ok.clicked.connect(self._save)

    def _save(self):
        set_ingest_host(self.edit.text())
        self.accept()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LagSlice ⚡ v{__version__}")
        self.resize(880, 700)
        self._threads = []
        self._net = NetSpeed()
        self._procs = []

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setSpacing(8)

        # سربرگ
        header = QtWidgets.QHBoxLayout()
        logo = QtWidgets.QLabel()
        lp = asset_path("lagslice-logo.png")
        if os.path.exists(lp):
            pm = QtGui.QPixmap(lp).scaled(56, 56, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                          QtCore.Qt.TransformationMode.SmoothTransformation)
            logo.setPixmap(pm)
        header.addWidget(logo)
        tbox = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("LagSlice ⚡")
        title.setObjectName("Title")
        sub = QtWidgets.QLabel("بهینه‌ساز استریم — تأخیر ویور زیر ۲۰ ثانیه")
        sub.setObjectName("Sub")
        tbox.addWidget(title)
        tbox.addWidget(sub)
        header.addLayout(tbox)
        header.addStretch(1)
        self.verLabel = QtWidgets.QLabel(f"v{fa(__version__)}")
        self.verLabel.setObjectName("Muted")
        header.addWidget(self.verLabel)
        root.addLayout(header)

        # کارت‌های وضعیت
        cards = QtWidgets.QHBoxLayout()
        self.pingCard = self._make_card("پینگ سرور استریم", "—")
        self.netCard = self._make_card("سرعت شبکه (آپلود/دانلود)", "—")
        self.targetCard = self._make_card("هدف تأخیر ویور", f"زیر {fa(20)} ثانیه")
        for c in (self.pingCard, self.netCard, self.targetCard):
            cards.addWidget(c[0])
        root.addLayout(cards)
        self.pingVal = self.pingCard[1]
        self.netVal = self.netCard[1]

        # دکمه‌ها
        btns = QtWidgets.QHBoxLayout()
        self.optBtn = QtWidgets.QPushButton("⚡ بهینه‌سازی خودکار")
        self.optBtn.setObjectName("Go")
        self.refreshBtn = QtWidgets.QPushButton("🔄 تازه‌سازی لیست")
        self.safeBtn = QtWidgets.QPushButton("🛡 لیست امن")
        self.srvBtn = QtWidgets.QPushButton("⚙ سرور استریم")
        for b in (self.optBtn, self.refreshBtn, self.safeBtn, self.srvBtn):
            btns.addWidget(b)
        btns.addStretch(1)
        root.addLayout(btns)
        self.optBtn.clicked.connect(self._optimize)
        self.refreshBtn.clicked.connect(self._refresh_procs)
        self.safeBtn.clicked.connect(lambda: SafeListDialog(self).exec())
        self.srvBtn.clicked.connect(self._open_server)

        # جدول پردازش‌ها
        root.addWidget(QtWidgets.QLabel("💻 پردازش‌های در حال اجرا (غیرسیستمی)"))
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["✓", "نام پردازش", "PID", "حافظه (MB)", "توضیح"])
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        root.addWidget(self.table, 1)

        # لاگ
        root.addWidget(QtWidgets.QLabel("📋 لاگ"))
        self.logView = QtWidgets.QTextEdit()
        self.logView.setObjectName("Log")
        self.logView.setReadOnly(True)
        self.logView.setMaximumHeight(120)
        root.addWidget(self.logView)

        # تایمرها
        self._speed_timer = QtCore.QTimer(self)
        self._speed_timer.timeout.connect(self._tick_speed)
        self._speed_timer.start(1000)
        self._ping_timer = QtCore.QTimer(self)
        self._ping_timer.timeout.connect(self._tick_ping)
        self._ping_timer.start(15000)

        if not psutil_available():
            self.log("⚠ psutil نصب نیست؛ مدیریت پردازش غیرفعال است.")
            self.optBtn.setEnabled(False)
            self.refreshBtn.setEnabled(False)
        else:
            self._refresh_procs()
        self._tick_ping()
        self.log("LagSlice شروع شد. برای تست: سرور استریم را تنظیم و بهینه‌سازی را بزنید.")

    def _make_card(self, title, val):
        box = QtWidgets.QLabel()
        box.setObjectName("Card")
        lay = QtWidgets.QVBoxLayout(box)
        t = QtWidgets.QLabel(title)
        t.setObjectName("Muted")
        v = QtWidgets.QLabel(val)
        v.setObjectName("CardVal")
        v.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        lay.addWidget(v)
        return box, v

    def log(self, text):
        ts = fa(datetime.datetime.now().strftime("%H:%M:%S"))
        self.logView.append(f'<span style="color:#5b6577">[{ts}]</span> {text}')

    # ---------- پردازش‌ها ----------
    def _refresh_procs(self):
        def _load():
            return list_processes()
        run_in_thread(self, _load, self._on_procs, lambda m: self.log(f"❌ خطا: {m}"))

    def _on_procs(self, procs):
        self._procs = procs
        self.table.setRowCount(0)
        for p in procs:
            r = self.table.rowCount()
            self.table.insertRow(r)
            chk = QtWidgets.QCheckBox()
            chk.setChecked(p["is_hog"])
            self.table.setCellWidget(r, 0, chk)
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(p["name"]))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(fa(p["pid"])))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(fa(p["mem_mb"])))
            desc = ("🌐 اینترنت‌خور: " + p["hog_desc"]) if p["is_hog"] else "—"
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(desc))
        self.log(f"فهرست به‌روز شد: {fa(len(procs))} پردازش.")

    def _checked_pids(self):
        out = []
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w and w.isChecked():
                try:
                    out.append(int(self.table.item(r, 2).text().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))))
                except (ValueError, AttributeError):
                    pass
        return out

    def _optimize(self):
        pids = self._checked_pids()
        if not pids:
            QtWidgets.QMessageBox.information(self, "بهینه‌سازی", "هیچ پردازشی انتخاب نشده است.")
            return
        ans = QtWidgets.QMessageBox.question(
            self, "تأیید بهینه‌سازی",
            f"{fa(len(pids))} پردازش انتخاب‌شده بسته شود؟\n(اعضای لیست امن هرگز در فهرست نیستند)",
        )
        if ans != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        ok_count = 0
        for pid in pids:
            ok, msg = kill_process(pid)
            if ok:
                ok_count += 1
                self.log(f"✅ بسته شد: {msg}")
            else:
                self.log(f"❌ {msg} (PID {fa(pid)})")
        self.log(f"تمام شد: {fa(ok_count)} از {fa(len(pids))} پردازش بسته شد.")
        self._refresh_procs()

    # ---------- شبکه ----------
    def _tick_speed(self):
        up, down = self._net.sample()
        if up is None:
            return
        self.netVal.setText(f"↑ {fa(round(up,1))} / ↓ {fa(round(down,1))} kbps")

    def _tick_ping(self):
        host = get_ingest_host()
        if not host:
            self.pingVal.setText("تنظیم نشده")
            self.pingVal.setStyleSheet("font-size: 20px; font-weight: bold; color: #8b93a3;")
            return
        self.pingVal.setText("…")
        run_in_thread(self, lambda: ping_host(host), self._on_ping, lambda m: None)

    def _on_ping(self, ms):
        label, color = quality_fa(ms)
        self.pingVal.setText(f"{fa(ms) + ' ms — ' + label if ms is not None else 'بدون پاسخ'}")
        self.pingVal.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {color};")
        if ms is not None:
            self.log(f"پینگ {get_ingest_host()}: {fa(ms)}ms ({label})")

    def _open_server(self):
        ServerDialog(self).exec()
        self._tick_ping()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setLayoutDirection(QtCore.Qt.LayoutDirection.RightToLeft)
    app.setApplicationName("LagSlice")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
