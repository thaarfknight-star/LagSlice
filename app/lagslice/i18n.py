# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""معماری دوزبانه‌ی LagSlice.

قانون طه: همه‌ی متن‌های UI از اول دوزبانه‌اند — هیچ رشته‌ی نمایشی
هاردکد فارسی/انگلیسی در کد UI نیست؛ همه از `tr(key)` می‌آیند.

- `tr(key)`: متن به زبان فعلی («fa» یا «en»)
- `num(value)`: ارقام فارسی فقط در حالت فارسی
- `set_language(code)`: تعویض زبان + ذخیره در کانفیگ (lagslice_config.json)
- `is_rtl()`: جهت چیدمان پنجره
"""

import json
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_path():
    try:
        base = os.environ.get("APPDATA")
        if base:
            d = os.path.join(base, "LagSlice")
            os.makedirs(d, exist_ok=True)
            return os.path.join(d, "lagslice_config.json")
    except Exception:
        pass
    return os.path.join(APP_DIR, "lagslice_config.json")


CONFIG_PATH = _config_path()

LANGS = ("fa", "en")
LANG_NAMES = {"fa": "فارسی", "en": "English"}

STRINGS = {
    "fa": {
        "app_subtitle": "بهینه‌ساز استریم — اینترنت ایران",
        "window_title": "LagSlice ⚡ — بهینه‌ساز استریم (نسخه {v})",
        "pill_ready": "آماده",
        "pill_streaming": "🔴 استریم فعال",
        "about_btn": "ℹ درباره",
        "about_title": "درباره‌ی LagSlice",
        "about_ok": "باشه",
        "warn_no_admin": "⚠ بدون دسترسی ادمین اجرا شدی؛ بستن بعضی برنامه‌ها کار نمی‌کند. با Run as administrator اجرا کن.",
        "stat_up": "آپلود لحظه‌ای",
        "stat_down": "دانلود لحظه‌ای",
        "stat_ping": "پینگ سرور",
        "stat_delay": "وضعیت تأخیر ویور (تخمینی)",
        "stream_start": "🎬 شروع حالت استریم",
        "stream_stop": "⏹ توقف حالت استریم",
        "tab_procs": "برنامه‌ها",
        "tab_safe": "لیست امن",
        "tab_settings": "تنظیمات",
        "tab_log": "لاگ",
        "proc_hint": "برنامه‌های اینترنت‌خور (غیر لیست امن) را می‌توانی ببندی. پروسس‌های سیستمی و لیست امن هرگز نمایش داده نمی‌شوند.",
        "col_name": "برنامه",
        "col_pid": "PID",
        "col_cpu": "CPU ٪",
        "col_ram": "RAM (MB)",
        "col_close": "بستن",
        "safe_hint": "این برنامه‌ها در «حالت استریم» هرگز بسته نمی‌شوند. اسم فایل اجرایی (مثل cs2.exe) را اضافه یا حذف کن.",
        "safe_placeholder": "مثلاً: myapp.exe",
        "safe_add": "➕ افزودن",
        "safe_del": "➖ حذف انتخاب‌شده",
        "set_server": "سرور پینگ:",
        "set_server_ph": "آی‌پی سرور استریم (MasterStream)",
        "set_bitrate": "بیت‌ریت استریم (Mbps):",
        "set_save": "💾 ذخیره تنظیمات",
        "set_note": "پینگ به اولین سرور لیست گرفته می‌شود. بیت‌ریت را مطابق تنظیمات MeldStudio بگذار.",
        "set_lang": "زبان / Language:",
        "log_ready": "LagSlice آماده است ⚡",
        "log_stream_on": "🎬 حالت استریم فعال شد؛ بستن برنامه‌های اینترنت‌خور…",
        "log_stream_off": "⏹ حالت استریم متوقف شد",
        "log_nothing": "برنامه‌ی اضافی برای بستن پیدا نشد ✅",
        "log_safe_added": "➕ {n} به لیست امن اضافه شد",
        "log_safe_removed": "➖ از لیست امن حذف شد",
        "log_settings_saved": "💾 تنظیمات ذخیره شد",
        "log_lang_changed": "🌐 زبان تغییر کرد",
        "delay_unknown": "نامشخص",
        "delay_unknown_tip": "در حال اندازه‌گیری…",
        "delay_good": "پایدار",
        "delay_good_tip": "آپلود کافی است؛ تأخیر ویور در محدوده امن",
        "delay_warn": "لب مرز",
        "delay_warn_tip": "آپلود نزدیک به بیت‌ریت است؛ ریسک افزایش تأخیر",
        "delay_bad": "بحرانی",
        "delay_bad_tip": "آپلود کمتر از بیت‌ریت؛ خطر تأخیر بالای ۲۰ ثانیه",
        "kill_sys": "پروسس سیستمی است؛ بسته نشد",
        "kill_gone": "پروسس از قبل بسته شده بود",
        "kill_denied": "دسترسی کافی نیست؛ با ادمین اجرا کن",
        "kill_err": "خطا: {e}",
        "kill_ok": "{name} بسته شد",
        "net_down": "قطع",
        "hog.chrome": "مرورگر کروم",
        "hog.firefox": "مرورگر فایرفاکس",
        "hog.msedge": "مرورگر اج",
        "hog.opera": "مرورگر اپرا",
        "hog.brave": "مرورگر بریو",
        "hog.vivaldi": "مرورگر ویوالدی",
        "hog.utorrent": "تورنت",
        "hog.qbittorrent": "تورنت",
        "hog.bittorrent": "تورنت",
        "hog.onedrive": "سینک وان‌درایو",
        "hog.dropbox": "سینک دراپ‌باکس",
        "hog.googledrivesync": "سینک گوگل درایو",
        "hog.googledrivefs": "سینک گوگل درایو",
        "hog.epicgameslauncher": "لانچر اپیک",
        "hog.ubisoftconnect": "لانچر یوبی‌سافت",
        "hog.eadesktop": "لانچر EA",
        "hog.battlenet": "لانچر بتل‌نت",
        "hog.riotclientservices": "کلاینت رایوت",
        "hog.spotify": "اسپاتیفای",
        "hog.telegram": "تلگرام دسکتاپ",
        "hog.whatsapp": "واتس‌اپ دسکتاپ",
        "hog.discord": "دیسکورد",
        "hog.skype": "اسکایپ",
        "hog.zoom": "زوم",
        "hog.teams": "تیمز",
        "hog.slack": "اسلک",
    },
    "en": {
        "app_subtitle": "Stream optimizer — for Iranian internet",
        "window_title": "LagSlice ⚡ — Stream Optimizer (v{v})",
        "pill_ready": "Ready",
        "pill_streaming": "🔴 Streaming",
        "about_btn": "ℹ About",
        "about_title": "About LagSlice",
        "about_ok": "OK",
        "warn_no_admin": "⚠ Not running as admin; closing some apps won't work. Run as administrator.",
        "stat_up": "Upload now",
        "stat_down": "Download now",
        "stat_ping": "Server ping",
        "stat_delay": "Viewer delay (estimated)",
        "stream_start": "🎬 Start stream mode",
        "stream_stop": "⏹ Stop stream mode",
        "tab_procs": "Apps",
        "tab_safe": "Safe list",
        "tab_settings": "Settings",
        "tab_log": "Log",
        "proc_hint": "You can close bandwidth-hogging apps (not on the safe list). System processes and safe-listed apps are never shown.",
        "col_name": "App",
        "col_pid": "PID",
        "col_cpu": "CPU %",
        "col_ram": "RAM (MB)",
        "col_close": "Close",
        "safe_hint": "These apps are never closed in stream mode. Add or remove executable names (e.g. cs2.exe).",
        "safe_placeholder": "e.g. myapp.exe",
        "safe_add": "➕ Add",
        "safe_del": "➖ Remove selected",
        "set_server": "Ping server:",
        "set_server_ph": "Stream server IP (MasterStream)",
        "set_bitrate": "Stream bitrate (Mbps):",
        "set_save": "💾 Save settings",
        "set_note": "Ping is taken from the first server in the list. Set the bitrate to match your MeldStudio settings.",
        "set_lang": "Language / زبان:",
        "log_ready": "LagSlice is ready ⚡",
        "log_stream_on": "🎬 Stream mode on; closing bandwidth hogs…",
        "log_stream_off": "⏹ Stream mode off",
        "log_nothing": "No extra apps to close ✅",
        "log_safe_added": "➕ {n} added to safe list",
        "log_safe_removed": "➖ Removed from safe list",
        "log_settings_saved": "💾 Settings saved",
        "log_lang_changed": "🌐 Language changed",
        "delay_unknown": "Unknown",
        "delay_unknown_tip": "Measuring…",
        "delay_good": "Stable",
        "delay_good_tip": "Upload is sufficient; viewer delay is safe",
        "delay_warn": "Borderline",
        "delay_warn_tip": "Upload is close to bitrate; delay may rise",
        "delay_bad": "Critical",
        "delay_bad_tip": "Upload below bitrate; risk of 20s+ delay",
        "kill_sys": "System process; not closed",
        "kill_gone": "Process was already closed",
        "kill_denied": "Access denied; run as admin",
        "kill_err": "Error: {e}",
        "kill_ok": "{name} closed",
        "net_down": "Down",
        "hog.chrome": "Chrome browser",
        "hog.firefox": "Firefox browser",
        "hog.msedge": "Edge browser",
        "hog.opera": "Opera browser",
        "hog.brave": "Brave browser",
        "hog.vivaldi": "Vivaldi browser",
        "hog.utorrent": "Torrent",
        "hog.qbittorrent": "Torrent",
        "hog.bittorrent": "Torrent",
        "hog.onedrive": "OneDrive sync",
        "hog.dropbox": "Dropbox sync",
        "hog.googledrivesync": "Google Drive sync",
        "hog.googledrivefs": "Google Drive sync",
        "hog.epicgameslauncher": "Epic launcher",
        "hog.ubisoftconnect": "Ubisoft Connect",
        "hog.eadesktop": "EA app",
        "hog.battlenet": "Battle.net",
        "hog.riotclientservices": "Riot client",
        "hog.spotify": "Spotify",
        "hog.telegram": "Telegram Desktop",
        "hog.whatsapp": "WhatsApp Desktop",
        "hog.discord": "Discord",
        "hog.skype": "Skype",
        "hog.zoom": "Zoom",
        "hog.teams": "Teams",
        "hog.slack": "Slack",
    },
}

_lang = None


def get_language():
    """زبان فعلی (پیش‌فرض: fa)."""
    global _lang
    if _lang is None:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict) and data.get("lang") in LANGS:
                    _lang = data["lang"]
                    return _lang
        except (OSError, ValueError):
            pass
        _lang = "fa"
    return _lang


def set_language(code):
    """تعویض زبان + ذخیره در کانفیگ (بدون پاک کردن بقیه‌ی تنظیمات)."""
    global _lang
    if code not in LANGS:
        return
    _lang = code
    try:
        data = {}
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                d = json.load(fh)
                if isinstance(d, dict):
                    data = d
        except (OSError, ValueError):
            pass
        data["lang"] = code
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def tr(key):
    """متن کلید به زبان فعلی (fallback: فارسی، بعد خود کلید)."""
    lang = get_language()
    return STRINGS.get(lang, {}).get(key, STRINGS["fa"].get(key, key))


_FA_DIGITS = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")


def num(value):
    """عدد/رشته؛ ارقام فارسی فقط در حالت فارسی."""
    s = str(value)
    return s.translate(_FA_DIGITS) if get_language() == "fa" else s


def is_rtl():
    return get_language() == "fa"
