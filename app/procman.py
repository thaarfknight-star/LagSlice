# -*- coding: utf-8 -*-
"""مدیریت پروسس‌ها: شناسایی برنامه‌های اینترنت‌خور، بستن امن با لیست امن.

نکته‌ی صادقانه: روی ویندوز آمار دقیق «مصرف اینترنت هر پروسس» بدون درایور
ممکن نیست؛ پس «کاندیداهای بستن» را با فهرست شناختی (مرورگرها، تورنت،
سینک ابری، لانچرها، آپدیترها) + مصرف CPU/RAM شناسایی می‌کنیم و هرگز به
پروسس‌های سیستمی یا لیست امن دست نمی‌زنیم.
"""
import json
import os
import sys

import psutil

from lang import tr

__version__ = "0.1.0"


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


def iter_processes(safelist):
    """لیست پروسس‌های کاربر؛ هر کدام: pid, name, cpu, mem_mb, kind."""
    out = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            name = (p.info["name"] or "").strip()
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
            mem = p.info["memory_info"]
            hog_key = "hog_" + lname
            out.append({
                "pid": p.info["pid"],
                "name": name,
                "cpu": round(p.info["cpu_percent"] or 0.0, 1),
                "mem_mb": round((mem.rss if mem else 0) / 1024 / 1024, 1),
                "kind": kind,
                "fa": tr(hog_key) if kind == "hog" and tr(hog_key) != hog_key else "",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    out.sort(key=lambda x: ({"hog": 0, "other": 1, "safe": 2}[x["kind"]], -x["mem_mb"]))
    return out


def kill_process(pid):
    """بستن امن یک پروسس؛ برمی‌گرداند (ok, key, param) و main ترجمه می‌کند."""
    try:
        p = psutil.Process(pid)
        name = p.name()
        if classify(name) == "never":
            return False, "kill_system", ""
        p.terminate()
        try:
            p.wait(timeout=3)
        except psutil.TimeoutExpired:
            p.kill()
        return True, "kill_ok", name
    except psutil.NoSuchProcess:
        return False, "kill_gone", ""
    except psutil.AccessDenied:
        return False, "kill_denied", ""
    except Exception as e:
        return False, "kill_err", str(e)


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
