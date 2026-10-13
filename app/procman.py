# -*- coding: utf-8 -*-
"""مدیریت پردازش‌ها و لیست امن LagSlice.

- فهرست پردازش‌های قابل‌بستن (پردازش‌های سیستمی حیاتی حذف می‌شوند)
- «اینترنت‌خورهای شناخته‌شده»: مرورگرها، پیام‌رسان‌ها، سینک ابری، لانچرها
- لیست امن: نام exeهایی که هرگز بسته نمی‌شوند (پیش‌فرض: CS2، استیم، MeldStudio)
"""

import json
import os

try:
    import psutil
    _PSUTIL_OK = True
except Exception:
    psutil = None
    _PSUTIL_OK = False

# پردازش‌های سیستمی که هرگز نمایش/بسته نمی‌شوند
SYSTEM_PROC = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe",
    "dwm.exe", "sihost.exe", "taskhostw.exe", "ctfmon.exe",
    "conhost.exe", "fontdrvhost.exe", "lsaiso.exe",
}

# اینترنت‌خورهای شناخته‌شده: exe -> توضیح فارسی
KNOWN_HOGS = {
    "chrome.exe": "مرورگر کروم",
    "msedge.exe": "مرورگر اج",
    "firefox.exe": "فایرفاکس",
    "opera.exe": "مرورگر اپرا",
    "brave.exe": "مرورگر بریو",
    "vivaldi.exe": "مرورگر ویوالدی",
    "discord.exe": "دیسکورد",
    "telegram.exe": "تلگرام",
    "whatsapp.exe": "واتس‌اپ",
    "onedrive.exe": "وان‌درایو",
    "dropbox.exe": "دراپ‌باکس",
    "googledrivefs.exe": "گوگل درایو",
    "spotify.exe": "اسپاتیفای",
    "epicgameslauncher.exe": "لانچر اپیک",
    "gog galaxy.exe": "لانچر GOG",
    "ubisoftconnect.exe": "یوبی‌سافت کانکت",
    "eadesktop.exe": "اپ EA",
    "battle.net.exe": "بتل‌نت",
    "qbittorrent.exe": "تورنت",
    "utorrent.exe": "تورنت",
    "zoom.exe": "زوم",
    "skype.exe": "اسکایپ",
    "teams.exe": "تیمز",
}

# پیش‌فرض لیست امن: این‌ها هرگز بسته نمی‌شوند
DEFAULT_SAFE = [
    "cs2.exe",
    "steam.exe",
    "steamwebhelper.exe",
    "gameoverlayui.exe",
    "meldstudio.exe",
    "explorer.exe",
]


def get_config_dir():
    appdata = os.environ.get("APPDATA")
    base = os.path.join(appdata, "LagSlice") if appdata else os.path.join(os.path.expanduser("~"), ".config", "LagSlice")
    os.makedirs(base, exist_ok=True)
    return base


def _safelist_path():
    return os.path.join(get_config_dir(), "safelist.json")


def load_safelist():
    try:
        with open(_safelist_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return [str(x).lower() for x in data]
    except (OSError, ValueError):
        pass
    return list(DEFAULT_SAFE)


def save_safelist(items):
    items = sorted({str(x).strip().lower() for x in items if str(x).strip()})
    with open(_safelist_path(), "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
    return items


def psutil_available():
    return _PSUTIL_OK


def list_processes():
    """فهرست پردازش‌های کاربر (بدون سیستمی‌ها)."""
    out = []
    if not _PSUTIL_OK:
        return out
    safe = set(load_safelist())
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            name = (p.info.get("name") or "").strip()
            if not name:
                continue
            lname = name.lower()
            if lname in SYSTEM_PROC or lname in safe:
                continue
            mem = p.info.get("memory_info")
            mem_mb = round((mem.rss if mem else 0) / (1024 * 1024), 1)
            out.append({
                "pid": p.info["pid"],
                "name": name,
                "mem_mb": mem_mb,
                "is_hog": lname in KNOWN_HOGS,
                "hog_desc": KNOWN_HOGS.get(lname, ""),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    out.sort(key=lambda d: (not d["is_hog"], -d["mem_mb"]))
    return out


def kill_process(pid):
    if not _PSUTIL_OK:
        return False, "psutil در دسترس نیست"
    try:
        p = psutil.Process(pid)
        name = p.name()
        p.kill()
        return True, name
    except psutil.NoSuchProcess:
        return False, "پردازش از قبل بسته شده"
    except psutil.AccessDenied:
        return False, "دسترسی ندارید (با ادمین اجرا کنید)"
    except Exception as exc:
        return False, str(exc)
