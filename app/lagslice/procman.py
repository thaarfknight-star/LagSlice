# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""مدیریت پروسس‌ها: شناسایی برنامه‌های اینترنت‌خور، بستن امن با لیست امن.

نکته‌ی صادقانه: روی ویندوز آمار دقیق «مصرف اینترنت هر پروسس» بدون درایور
ممکن نیست؛ پس «کاندیداهای بستن» را با فهرست شناختی (مرورگرها، تورنت،
سینک ابری، لانچرها، آپدیترها) + مصرف CPU/RAM شناسایی می‌کنیم و هرگز به
پروسس‌های سیستمی یا لیست امن دست نمی‌زنیم.
"""
import json
import os

import psutil

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


SAFELIST_PATH = os.path.join(_data_dir(), "safelist.json")

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
# مقدار هر الگو یک کلید i18n است (hog.*) — متن نمایشی از tr() می‌آید
HOG_PATTERNS = {
    "chrome.exe": "hog.chrome",
    "firefox.exe": "hog.firefox",
    "msedge.exe": "hog.msedge",
    "opera.exe": "hog.opera",
    "brave.exe": "hog.brave",
    "vivaldi.exe": "hog.vivaldi",
    "utorrent.exe": "hog.utorrent",
    "qbittorrent.exe": "hog.qbittorrent",
    "bittorrent.exe": "hog.bittorrent",
    "onedrive.exe": "hog.onedrive",
    "dropbox.exe": "hog.dropbox",
    "googledrivesync.exe": "hog.googledrivesync",
    "googledrivefs.exe": "hog.googledrivefs",
    "epicgameslauncher.exe": "hog.epicgameslauncher",
    "ubisoftconnect.exe": "hog.ubisoftconnect",
    "eadesktop.exe": "hog.eadesktop",
    "battle.net.exe": "hog.battlenet",
    "riotclientservices.exe": "hog.riotclientservices",
    "spotify.exe": "hog.spotify",
    "telegram.exe": "hog.telegram",
    "whatsapp.exe": "hog.whatsapp",
    "discord.exe": "hog.discord",
    "skype.exe": "hog.skype",
    "zoom.exe": "hog.zoom",
    "teams.exe": "hog.teams",
    "slack.exe": "hog.slack",
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
            out.append({
                "pid": p.info["pid"],
                "name": name,
                "cpu": round(p.info["cpu_percent"] or 0.0, 1),
                "mem_mb": round((mem.rss if mem else 0) / 1024 / 1024, 1),
                "kind": kind,
                "fa": HOG_PATTERNS.get(lname, ""),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    out.sort(key=lambda x: ({"hog": 0, "other": 1, "safe": 2}[x["kind"]], -x["mem_mb"]))
    return out


def kill_process(pid):
    """بستن امن یک پروسس؛ اول terminate، بعد kill.

    برمی‌گرداند (ok, msg_key, name) — متن نمایشی با tr(msg_key) در لایه‌ی UI.
    """
    try:
        p = psutil.Process(pid)
        name = p.name()
        if classify(name) == "never":
            return False, "kill_sys", name
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


def hog_candidates(safelist):
    """کاندیداهای بستن در حالت استریم: لیستی از (pid, name)."""
    return [(p["pid"], p["name"])
            for p in iter_processes(safelist) if p["kind"] == "hog"]


def stream_mode_cleanup(safelist):
    """بستن همه‌ی کاندیداهای اینترنت‌خور که در لیست امن نیستند.

    برمی‌گرداند لیستی از (ok, name, msg_key) — متن نمایشی با tr در لایه‌ی UI.
    """
    out = []
    for proc in iter_processes(safelist):
        if proc["kind"] != "hog":
            continue
        ok, msg_key, name = kill_process(proc["pid"])
        out.append((ok, name or proc["name"], msg_key))
    return out


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
