# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""موتور آپدیت خودکار LagSlice (الگو: updater.py در IAS-CMS).

گردش کار:
  ۱) بررسی نسخه: GET روی آخرین ریلیز گیت‌هاب
     (thaarfknight-star/LagSlice/releases/latest) و مقایسه‌ی تگ vX.Y.Z
     با version.txt باندل‌شده.
  ۲) اطلاع‌رسانی: اگر نسخه‌ی جدیدتر بود، دیالوگ «آپدیت جدید» (غیرمسدودکننده)
     با دکمه‌ی «دانلود و نصب».
  ۳) دانلود: فایل LagSlice.exe همان ریلیز با نمایش پیشرفت.
  ۴) نصب: جایگزینی فایل اجرایی در حال اجرا با ترفند rename ویندوز
     (LagSlice.exe → LagSlice.exe.bak)، نوشتن update_applied.json،
     اجرای نسخه‌ی جدید و خروج.
  ۵) در استارت بعدی، پنجره‌ی «به‌روزرسانی انجام شد» تغییرات را از روی
     CHANGELOG_FA.md (تابع changelog_between) نشان می‌دهد.

نکته: دانلود/نصب فقط در نسخه‌ی نصب‌شده (frozen) کار می‌کند؛ در حالت
توسعه فقط بررسی نسخه انجام می‌شود. بدون وابستگی جدید — فقط کتابخانه‌ی
استاندارد پایتون (+ PyQt6 برای دیالوگ‌ها، به‌صورت lazy).
"""

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.error

OWNER = "thaarfknight-star"
REPO = "LagSlice"
API_LATEST = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/latest"
ASSET_NAME = "LagSlice.exe"
USER_AGENT = "LagSlice-updater/1.0"
NOTICE_FILE = "update_applied.json"


# ---------------------------------------------------------- مسیرها ---

def get_install_dir():
    """پوشه‌ی نصب (کنار فایل اجرایی) یا ریشه‌ی مخزن در حالت توسعه."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)  # app/ -> repo root


def _bundled(name):
    """فایل باندل‌شده در exe (_MEIPASS) یا سورس."""
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        p = os.path.join(meipass, name)
        if os.path.isfile(p):
            return p
    p = os.path.join(get_install_dir(), name)
    return p if os.path.isfile(p) else ""


def get_app_version():
    """خواندن نسخه از version.txt (پیش‌فرض 0.0.0)."""
    p = _bundled("version.txt")
    try:
        if p:
            with open(p, encoding="utf-8") as f:
                v = f.read().strip().split()
                return v[0] if v else "0.0.0"
    except OSError:
        pass
    return "0.0.0"


def _ver_tuple(v):
    m = re.search(r"(\d+(?:\.\d+)+)", str(v).strip())
    core = m.group(1) if m else str(v).strip().split("-")[0].split("+")[0]
    parts = []
    for p in core.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


# ---------------------------------------------------------- بررسی ---

def _api_get(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_for_update(timeout=15):
    """بررسی آخرین ریلیز گیت‌هاب.

    خروجی: (True, info) اگر نسخه‌ی جدیدتر موجود است که info شامل
    version/tag/asset_url/size/body/published_at است؛
    (False, None) اگر به‌روز است؛
    (False, "خطا: ...") اگر بررسی ممکن نشد (مثلاً قطعی اینترنت).
    """
    try:
        rel = _api_get(API_LATEST, timeout=timeout)
    except urllib.error.URLError:
        return False, "خطا: اتصال به گیت‌هاب برقرار نشد."
    except Exception as e:
        return False, f"خطا در بررسی آپدیت: {e}"
    try:
        tag = str(rel.get("tag_name", "")).strip()
        new_t = _ver_tuple(tag)
        cur_t = _ver_tuple(get_app_version())
        if not new_t or new_t <= cur_t:
            return False, None
        asset_url, size = "", 0
        for a in rel.get("assets", []):
            if a.get("name") == ASSET_NAME:
                asset_url = a.get("browser_download_url", "")
                size = int(a.get("size", 0) or 0)
                break
        if not asset_url:
            return False, "خطا: فایل اجرایی در ریلیز پیدا نشد."
        return True, {
            "version": tag.lstrip("v"),
            "tag": tag,
            "asset_url": asset_url,
            "size": size,
            "body": rel.get("body", "") or "",
            "published_at": rel.get("published_at", "") or "",
        }
    except Exception as e:
        return False, f"خطا در خواندن اطلاعات ریلیز: {e}"


# ---------------------------------------------------------- دانلود ---

def download_update(url, dest_path, progress_cb=None, timeout=30):
    """دانلود فایل با گزارش پیشرفت (progress_cb: downloaded, total).

    خروجی: (True, "") یا (False, پیام خطای فارسی).
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            total = int(r.headers.get("Content-Length", 0) or 0)
            done = 0
            with open(dest_path, "wb") as f:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        try:
                            progress_cb(done, total)
                        except Exception:
                            pass
        if total and os.path.getsize(dest_path) != total:
            raise IOError("حجم فایل دانلودشده با ریلیز مطابقت ندارد.")
        return True, ""
    except urllib.error.URLError:
        return False, "دانلود ناموفق بود؛ اتصال اینترنت را بررسی کن."
    except Exception as e:
        try:
            if os.path.isfile(dest_path):
                os.remove(dest_path)
        except OSError:
            pass
        return False, f"دانلود ناموفق بود: {e}"


# ---------------------------------------------------------- نصب ---

def apply_update(new_exe_path):
    """جایگزینی فایل اجرایی در حال اجرا با نسخه‌ی جدید (فقط ویندوز/frozen).

    ترفند: rename نسخه‌ی فعلی به .bak (ویندوز اجازه‌ی rename فایل در حال
    اجرا را می‌دهد ولی نه حذف/بازنویسی مستقیم)، انتقال نسخه‌ی جدید به
    جای آن، نوشتن update_applied.json، اجرای نسخه‌ی جدید و خروج.
    خروجی: (True, "") — در صورت موفقیت این تابع برنمی‌گردد (os._exit).
    """
    if not getattr(sys, "frozen", False):
        return False, "نصب خودکار فقط در نسخه‌ی نصب‌شده (exe) کار می‌کند."
    if os.name != "nt":
        return False, "نصب خودکار فقط روی ویندوز پشتیبانی می‌شود."
    install_dir = get_install_dir()
    cur_exe = os.path.abspath(sys.executable)
    bak_exe = cur_exe + ".bak"
    try:
        if not os.path.isfile(new_exe_path):
            return False, "فایل دانلودشده پیدا نشد."
        # بکاپ نسخه‌ی قبلی (فقط یک نسل نگه می‌داریم)
        if os.path.isfile(bak_exe):
            os.remove(bak_exe)
        os.rename(cur_exe, bak_exe)
        shutil.move(new_exe_path, cur_exe)
    except Exception as e:
        return False, f"جایگزینی فایل اجرایی ممکن نشد: {e}"
    # اجرای نسخه‌ی جدید و خروج از نسخه‌ی فعلی
    try:
        if os.name == "nt":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0)
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen([cur_exe], creationflags=flags,
                             close_fds=True,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([cur_exe], close_fds=True,
                             start_new_session=True,
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception as e:
        return False, f"اجرای نسخه‌ی جدید ممکن نشد: {e}"
    os._exit(0)


def write_update_notice(prev_version, new_version):
    """ثبت نشانگر آپدیت موفق (برای پنجره‌ی «به‌روزرسانی انجام شد»)."""
    try:
        with open(os.path.join(get_install_dir(), NOTICE_FILE), "w",
                  encoding="utf-8") as f:
            json.dump({"prev_version": prev_version,
                       "new_version": new_version}, f)
    except OSError:
        pass


def get_update_notice():
    """خواندن نشانگر آپدیت تازه‌اعمال‌شده یا None."""
    try:
        p = os.path.join(get_install_dir(), NOTICE_FILE)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None


def clear_update_notice():
    try:
        p = os.path.join(get_install_dir(), NOTICE_FILE)
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass


# ---------------------------------------------------------- چنج‌لاگ ---

def changelog_between(prev_version, new_version, max_chars=6000):
    """ورودی‌های CHANGELOG_FA.md از بعدِ prev_version تا new_version.

    خروجی: لیستی از (version, date, body) از جدید به قدیم.
    """
    p = _bundled("CHANGELOG_FA.md")
    if not p:
        return []
    try:
        with open(p, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    entries = []
    cur_ver, cur_date, buf = None, None, []
    for line in text.splitlines():
        m = re.match(r"^##\s+(\S+)(?:\s+\(([^)]*)\))?\s*$", line)
        if m:
            if cur_ver:
                entries.append((cur_ver, cur_date, "\n".join(buf).strip()))
            cur_ver, cur_date, buf = m.group(1), m.group(2) or "", []
        elif cur_ver is not None:
            buf.append(line)
    if cur_ver:
        entries.append((cur_ver, cur_date, "\n".join(buf).strip()))
    prev_t = _ver_tuple(prev_version or "0")
    new_t = _ver_tuple(new_version or "0")
    out, total = [], 0
    for ver, date, body in entries:
        vt = _ver_tuple(ver)
        if vt <= prev_t:
            break  # ورودی‌ها از جدید به قدیم‌اند
        if vt > new_t:
            continue
        out.append((ver, date, body))
        total += len(body)
        if total > max_chars:
            break
    return out


# ---------------------------------------------------------- دیالوگ‌ها ---
# (ایمپورت PyQt به‌صورت lazy تا منطق خالص بدون Qt هم قابل تست باشد)

def _qt():
    from PyQt6 import QtWidgets, QtCore, QtGui
    return QtWidgets, QtCore, QtGui


def _tr_fallback(key, lang_dict):
    try:
        from lang import tr
        return tr(key)
    except Exception:
        return lang_dict.get(key, key)


_FA_EN = {
    "upd_btn": ("⬆ بررسی آپدیت", "⬆ Check for updates"),
    "upd_checking": ("در حال بررسی…", "Checking…"),
    "upd_none": ("نسخه‌ی فعلی به‌روز است.", "You're up to date."),
    "upd_found_title": ("آپدیت جدید", "Update available"),
    "upd_later": ("بعداً", "Later"),
    "upd_download_install": ("دانلود و نصب", "Download & install"),
    "upd_downloading": ("در حال دانلود آپدیت…", "Downloading update…"),
    "upd_dev_note": ("نصب خودکار فقط در نسخه‌ی نصب‌شده (exe) کار می‌کند.",
                     "Auto-install works only in the installed (exe) build."),
    "upd_restart_note": ("برنامه بسته و با نسخه‌ی جدید اجرا می‌شود.",
                         "The app will close and restart with the new version."),
    "upd_done_title": ("به‌روزرسانی انجام شد", "Update installed"),
    "upd_whatsnew": ("تغییرات:", "What's new:"),
}


def _t(key):
    try:
        from lang import tr, get_lang
        s = tr(key)
        if s != key:
            return s
    except Exception:
        pass
    try:
        from lang import get_lang
        lang = get_lang()
    except Exception:
        lang = "fa"
    pair = _FA_EN.get(key, (key, key))
    return pair[0] if lang == "fa" else pair[1]


def show_update_available_dialog(parent, info):
    """دیالوگ «آپدیت جدید» با دکمه‌ی دانلود و نصب + نوار پیشرفت."""
    QtWidgets, QtCore, QtGui = _qt()
    from PyQt6.QtCore import Qt
    cur = get_app_version()
    new = info["version"]

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(_t("upd_found_title"))
    from PyQt6.QtCore import Qt
    try:
        from lang import get_lang
        rtl = get_lang() == "fa"
    except Exception:
        rtl = True
    dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl
                           else Qt.LayoutDirection.LeftToRight)
    dlg.setMinimumWidth(460)

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(24, 20, 24, 20)
    root.setSpacing(12)

    title = QtWidgets.QLabel(f"LagSlice ⚡ — {_t('upd_found_title')}")
    title.setStyleSheet("font-size: 18px; font-weight: bold;")
    root.addWidget(title)

    msg = QtWidgets.QLabel(
        f"نسخه‌ی {new} منتشر شده است (نسخه‌ی فعلی: {cur}).\n"
        f"{_t('upd_restart_note')}")
    msg.setWordWrap(True)
    root.addWidget(msg)

    bar = QtWidgets.QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setVisible(False)
    root.addWidget(bar)

    status = QtWidgets.QLabel("")
    status.setWordWrap(True)
    root.addWidget(status)

    btns = QtWidgets.QHBoxLayout()
    btns.addStretch(1)
    later = QtWidgets.QPushButton(_t("upd_later"))
    later.clicked.connect(dlg.reject)
    btns.addWidget(later)
    go = QtWidgets.QPushButton("⬇ " + _t("upd_download_install"))
    btns.addWidget(go)
    root.addLayout(btns)

    def _on_go():
        import tempfile
        import threading
        if not getattr(sys, "frozen", False):
            status.setText("ℹ " + _t("upd_dev_note"))
            return
        go.setEnabled(False)
        later.setEnabled(False)
        bar.setVisible(True)
        status.setText(_t("upd_downloading"))

        def _prog(done, total):
            if total:
                QtCore.QMetaObject.invokeMethod(
                    bar, "setValue", Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(int, int(done * 100 / total)))

        def _work():
            tmp = os.path.join(tempfile.gettempdir(),
                               f"LagSlice-update-{new}.exe")
            ok, err = download_update(info["asset_url"], tmp, _prog)
            if not ok:
                QtCore.QMetaObject.invokeMethod(
                    status, "setText", Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "⚠ " + err))
                QtCore.QMetaObject.invokeMethod(
                    go, "setEnabled", Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(bool, True))
                return
            # ثبت نسخه‌ها برای پنجره‌ی «به‌روزرسانی انجام شد»
            write_update_notice(cur, new)
            ok2, err2 = apply_update(tmp)
            if not ok2:
                QtCore.QMetaObject.invokeMethod(
                    status, "setText", Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(str, "⚠ " + err2))
                QtCore.QMetaObject.invokeMethod(
                    go, "setEnabled", Qt.ConnectionType.QueuedConnection,
                    QtCore.Q_ARG(bool, True))

        threading.Thread(target=_work, daemon=True).start()

    go.clicked.connect(_on_go)
    dlg.exec()


def show_update_done_dialog(parent):
    """پنجره‌ی «به‌روزرسانی انجام شد» — تغییرات از CHANGELOG_FA.md."""
    QtWidgets, QtCore, QtGui = _qt()
    notice = get_update_notice()
    if not notice:
        return
    clear_update_notice()
    prev = notice.get("prev_version", "")
    new = notice.get("new_version", "")
    entries = changelog_between(prev, new)

    try:
        from lang import get_lang
        rtl = get_lang() == "fa"
    except Exception:
        rtl = True

    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle(_t("upd_done_title"))
    from PyQt6.QtCore import Qt
    dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl
                           else Qt.LayoutDirection.LeftToRight)
    dlg.setMinimumSize(520, 380)

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(24, 20, 24, 20)
    root.setSpacing(12)

    title = QtWidgets.QLabel(f"✅ {_t('upd_done_title')} — {prev} ← {new}")
    title.setStyleSheet("font-size: 18px; font-weight: bold;")
    root.addWidget(title)

    if entries:
        sub = QtWidgets.QLabel(_t("upd_whatsnew"))
        sub.setStyleSheet("font-weight: bold;")
        root.addWidget(sub)
        txt = QtWidgets.QTextEdit()
        txt.setReadOnly(True)
        parts = []
        for ver, date, body in entries:
            head = f"## {ver}" + (f" ({date})" if date else "")
            parts.append(head + "\n" + body)
        txt.setPlainText("\n\n".join(parts))
        root.addWidget(txt, 1)
    else:
        lbl = QtWidgets.QLabel(f"LagSlice {new} با موفقیت نصب شد.")
        lbl.setWordWrap(True)
        root.addWidget(lbl, 1)

    ok = QtWidgets.QPushButton("باشه" if rtl else "OK")
    ok.clicked.connect(dlg.accept)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    row.addWidget(ok)
    root.addLayout(row)
    dlg.exec()


def check_in_background(win):
    """بررسی آپدیت در نخ پس‌زمینه؛ اگر نسخه‌ی جدید بود دیالوگ را نشان بده."""
    import threading
    QtWidgets, QtCore, QtGui = _qt()

    def _work():
        try:
            has, info = check_for_update()
        except Exception:
            return
        if not has or not info:
            return
        # نمایش دیالوگ در نخ UI
        QtCore.QMetaObject.invokeMethod(
            win, "_show_update_available",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(object, info))

    threading.Thread(target=_work, daemon=True).start()
