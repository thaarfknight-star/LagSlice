# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
# -*- coding: utf-8 -*-
"""مدیریت پروسس‌ها: شناسایی برنامه‌های اینترنت‌خور، بستن امن با لیست امن.

نکته‌ی صادقانه: روی ویندوز آمار دقیق «مصرف اینترنت هر پروسس» بدون درایور
ممکن نیست؛ پس «کاندیداهای بستن» را با فهرست شناختی (مرورگرها، تورنت،
سینک ابری، لانچرها، آپدیترها) + مصرف CPU/RAM شناسایی می‌کنیم و هرگز به
پروسس‌های سیستمی یا لیست امن دست نمی‌زنیم.
"""
import csv
import io
import json
import os
import subprocess
import sys
import time

from lang import tr

__version__ = "0.2.0"


def _hidden_subprocess_kwargs():
    """اجرای مخفی بدون پنجره‌ی cmd (ویندوز)."""
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return dict(startupinfo=si,
                    creationflags=subprocess.CREATE_NO_WINDOW)
    return {}


def base_dir():
    """پوشه‌ی قابل نوشتن برنامه: کنار فایل اجرایی (حالت frozen) یا پوشه‌ی app."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


SAFELIST_PATH = os.path.join(base_dir(), "safelist.json")

# پروسس‌هایی که هرگز نباید بسته شوند (سیستمی/حیاتی ویندوز)
NEVER_TOUCH = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
    "winlogon.exe", "fontdrvhost.exe", "conhost.exe", "sihost.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchindexer.exe",
    "audiodg.exe", "ctfmon.exe", "dllhost.exe", "wudfhost.exe",
    "idle", "memory compression",
}

# الگوهای برنامه‌های معمولاً اینترنت‌خور و غیرضروری حین استریم
# (نام نمایشی دوزبانه از lang.py با کلید hog_<name> خوانده می‌شود)
HOG_PATTERNS = {
    "chrome.exe", "firefox.exe", "msedge.exe", "opera.exe", "brave.exe",
    "vivaldi.exe", "utorrent.exe", "qbittorrent.exe", "bittorrent.exe",
    "onedrive.exe", "dropbox.exe", "googledrivesync.exe", "googledrivefs.exe",
    "epicgameslauncher.exe", "ubisoftconnect.exe", "eadesktop.exe",
    "battle.net.exe", "riotclientservices.exe", "spotify.exe", "telegram.exe",
    "whatsapp.exe", "discord.exe", "skype.exe", "zoom.exe", "teams.exe",
    "slack.exe",
}

DEFAULT_SAFELIST = [
    # بازی و استریم — هرگز بسته نمی‌شوند
    "cs2.exe",
    "meldstudio.exe",
    "meld.exe",
    "obs64.exe",
    "obs32.exe",
    "steam.exe",
    "steamwebhelper.exe",
    "gameoverlayui.exe",
    "lagslice.exe",
    "lagslice_admin.exe",
    # ابزارهای ارتباطی حین استریم (کاربر می‌تواند حذف کند)
    "discord.exe",
]


def default_safelist_path():
    return SAFELIST_PATH


def load_safelist():
    try:
        with open(SAFELIST_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return {s.strip().lower() for s in data if s.strip()}
    except (OSError, ValueError):
        pass
    return {s.lower() for s in DEFAULT_SAFELIST}


def save_safelist(names):
    clean = sorted({n.strip().lower() for n in names if n.strip()})
    with open(SAFELIST_PATH, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=2)
    return clean


def classify(name):
    """برمی‌گرداند: 'never' | 'safe' | 'hog' | 'other'"""
    n = (name or "").lower()
    if n in NEVER_TOUCH:
        return "never"
    return "other"  # safe/hog با توجه به لیست امن و الگوها تعیین می‌شود


_SNAPSHOT = []
_SNAPSHOT_T = 0.0
_SNAPSHOT_TTL = 8.0


def _tasklist_once():
    """یک بار خواندن tasklist؛ برمی‌گرداند لیستی از {pid, name, mem_mb}.

    عمداً بیرون از پروسس اجرا می‌شود: اگر tasklist خودش مشکلی داشته باشد،
    برنامه‌ی اصلی کرش نمی‌کند (برخلاف psutil.process_iter).
    """
    if sys.platform != "win32":
        return []
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=30,
            **_hidden_subprocess_kwargs())
        out = proc.stdout or ""
    except Exception:
        return []
    rows = []
    try:
        for row in csv.reader(io.StringIO(out)):
            if len(row) < 5:
                continue
            name = (row[0] or "").strip()
            try:
                pid = int((row[1] or "").strip())
            except ValueError:
                continue
            mem_raw = (row[4] or "").replace(",", "").upper().replace("K", "").strip()
            try:
                mem_mb = int(mem_raw) / 1024.0
            except ValueError:
                mem_mb = 0.0
            if not name or pid <= 0:
                continue
            rows.append({"pid": pid, "name": name, "mem_mb": mem_mb})
    except Exception:
        return []
    return rows


def snapshot_procs():
    """اسنپ‌شات کش‌شده‌ی پروسس‌ها (حداکثر ۸ ثانیه قدمت)."""
    global _SNAPSHOT, _SNAPSHOT_T
    now = time.monotonic()
    if now - _SNAPSHOT_T > _SNAPSHOT_TTL or not _SNAPSHOT:
        _SNAPSHOT = _tasklist_once()
        _SNAPSHOT_T = now
    return _SNAPSHOT


def pid_to_name(pid):
    """نام پروسس برای pid از روی آخرین اسنپ‌شات؛ "" اگر پیدا نشد."""
    try:
        want = int(pid)
    except (TypeError, ValueError):
        return ""
    for p in snapshot_procs():
        if p["pid"] == want:
            return p["name"]
    return ""


def iter_processes(safelist):
    """لیست پروسس‌های کاربر؛ هر کدام: pid, name, cpu, mem_mb, kind.

    cpu همیشه None است (ستون «—» نشان می‌دهد): خواندن درصد CPU هر پروسس
    با psutil روی بعضی سیستم‌ها کرش native می‌داد، پس کلاً حذف شد.
    """
    out = []
    for p in snapshot_procs():
        try:
            name = (p["name"] or "").strip()
            if not name:
                continue
            lname = name.lower()
            if classify(name) == "never":
                continue
            if lname in safelist:
                kind = "safe"
            elif lname in HOG_PATTERNS:
                kind = "hog"
            else:
                kind = "other"
            hog_key = "hog_" + lname
            out.append({
                "pid": p["pid"],
                "name": name,
                "cpu": None,
                "mem_mb": round(p["mem_mb"], 1),
                "kind": kind,
                "fa": tr(hog_key) if kind == "hog" and tr(hog_key) != hog_key else "",
            })
        except Exception:
            continue
    out.sort(key=lambda x: ({"hog": 0, "other": 1, "safe": 2}[x["kind"]], -x["mem_mb"]))
    return out


def kill_process(pid):
    """بستن امن یک پروسس با taskkill (بدون psutil)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False, "kill_err", ""
    name = pid_to_name(pid)
    if name and classify(name) == "never":
        return False, "kill_system", ""
    if sys.platform != "win32":
        return False, "kill_err", ""
    try:
        proc = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, text=True, errors="replace", timeout=15,
            **_hidden_subprocess_kwargs())
        if proc.returncode == 0:
            return True, "kill_ok", name or str(pid)
        err = ((proc.stderr or "") + " " + (proc.stdout or "")).lower()
        if "not found" in err:
            return False, "kill_gone", ""
        if "access is denied" in err:
            return False, "kill_denied", ""
        return False, "kill_err", (proc.stderr or proc.stdout or "").strip()[:200]
    except Exception as e:
        return False, "kill_err", str(e)[:200]


def stream_mode_cleanup(safelist):
    """بستن همه‌ی کاندیداهای اینترنت‌خور که در لیست امن نیستند.
    برمی‌گرداند لیستی از (name, key, param)."""
    killed, skipped = [], []
    for proc in iter_processes(safelist):
        if proc["kind"] != "hog":
            continue
        ok, key, param = kill_process(proc["pid"])
        (killed if ok else skipped).append((proc["name"], key, param))
    return killed, skipped


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
