# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
# -*- coding: utf-8 -*-
"""سیستم دوزبانه LagSlice: فارسی / انگلیسی با تعویض داخل برنامه.

همه‌ی متن‌های UI از این دیکشنری می‌آیند؛ هیچ رشته‌ی نمایشی
هاردکد در کد UI نیست. جهت چیدمان هم با زبان عوض می‌شود.
"""
import json
import os

LANGS = ("fa", "en")
_current = "fa"

STRINGS = {
    # ---- سربرگ ----
    "app_subtitle": {
        "fa": "بهینه‌ساز استریم — اینترنت ایران",
        "en": "Stream optimizer — for weak connections",
    },
    "status_ready": {"fa": "آماده", "en": "Ready"},
    "status_streaming": {"fa": "🔴 استریم فعال", "en": "🔴 Streaming"},
    "admin_warn": {
        "fa": "⚠ بدون دسترسی ادمین اجرا شدی؛ بستن بعضی برنامه‌ها کار نمی‌کند. با Run as administrator اجرا کن.",
        "en": "⚠ Not running as administrator; closing some apps won't work. Run as administrator.",
    },
    # ---- کارت‌های آمار ----
    "stat_up": {"fa": "آپلود لحظه‌ای", "en": "Upload now"},
    "stat_down": {"fa": "دانلود لحظه‌ای", "en": "Download now"},
    "stat_ping": {"fa": "پینگ سرور", "en": "Server ping"},
    "stat_delay": {"fa": "وضعیت تأخیر ویور (تخمینی)", "en": "Viewer delay (estimated)"},
    "jitter": {"fa": "جیتر", "en": "jitter"},
    "disconnected": {"fa": "قطع", "en": "Down"},
    # ---- وضعیت تأخیر ----
    "delay_good": {"fa": "پایدار", "en": "Stable"},
    "delay_good_d": {
        "fa": "آپلود کافی است؛ تأخیر ویور در محدوده امن",
        "en": "Upload is sufficient; viewer delay is safe",
    },
    "delay_warn": {"fa": "لب مرز", "en": "Borderline"},
    "delay_warn_d": {
        "fa": "آپلود نزدیک به بیت‌ریت است؛ ریسک افزایش تأخیر",
        "en": "Upload is close to bitrate; delay may rise",
    },
    "delay_bad": {"fa": "بحرانی", "en": "Critical"},
    "delay_bad_d": {
        "fa": "آپلود کمتر از بیت‌ریت؛ خطر تأخیر بالای ۲۰ ثانیه",
        "en": "Upload below bitrate; delay may exceed 20s",
    },
    "delay_unknown": {"fa": "نامشخص", "en": "Unknown"},
    "delay_unknown_d": {"fa": "در حال اندازه‌گیری…", "en": "Measuring…"},
    # ---- دکمه استریم ----
    "stream_start": {"fa": "🎬 شروع حالت استریم", "en": "🎬 Start stream mode"},
    "stream_stop": {"fa": "⏹ توقف حالت استریم", "en": "⏹ Stop stream mode"},
    # ---- تب‌ها ----
    "tab_procs": {"fa": "برنامه‌ها", "en": "Apps"},
    "tab_scan": {"fa": "اسکن سرورها", "en": "Server scan"},
    "tab_safe": {"fa": "لیست امن", "en": "Safe list"},
    "tab_settings": {"fa": "تنظیمات", "en": "Settings"},
    "tab_log": {"fa": "لاگ", "en": "Log"},
    "scan_one_tip": {
        "fa": "فقط سرور انتخاب‌شده در جدول اسکن می‌شود",
        "en": "Scans only the selected server in the table",
    },
    "scan_stop_tip": {
        "fa": "توقف اسکن در حال اجرا",
        "en": "Stop the running scan",
    },
    "scan_add_tip": {
        "fa": "افزودن سرور MasterStream جدید به لیست",
        "en": "Add a new MasterStream server to the list",
    },
    "scan_edit_tip": {
        "fa": "ویرایش سرور انتخاب‌شده",
        "en": "Edit the selected server",
    },
    "scan_del_tip": {
        "fa": "حذف سرور انتخاب‌شده از لیست",
        "en": "Delete the selected server from the list",
    },
    "scan_table_tip": {
        "fa": "دابل‌کلیک روی سطر: کپی آدرس RTMP",
        "en": "Double-click a row: copy RTMP address",
    },
    "scan_imported": {"fa": "سرور اضافه شد.", "en": "servers added."},
    "scan_import_none": {"fa": "سرور معتبری پیدا نشد.", "en": "No valid servers found."},
    "scan_srv_name": {"fa": "نام سرور:", "en": "Server name:"},
    "scan_srv_rtmp": {"fa": "آدرس RTMP:", "en": "RTMP address:"},
    "scan_srv_region": {"fa": "منطقه:", "en": "Region:"},
    "scan_srv_note": {"fa": "توضیح:", "en": "Note:"},
    "scan_auto_hint": {
        "fa": "نام و منطقه خودکار از روی لینک حدس زده می‌شوند.",
        "en": "Name and region are auto-detected from the link.",
    },
    "scan_add_title": {"fa": "افزودن سرور", "en": "Add server"},
    "scan_edit_title": {"fa": "ویرایش سرور", "en": "Edit server"},
    "scan_col_server": {"fa": "سرور", "en": "Server"},
    "scan_col_region": {"fa": "منطقه", "en": "Region"},
    "scan_col_ping": {"fa": "پینگ", "en": "Ping"},
    "scan_col_loss": {"fa": "لاست٪", "en": "Loss%"},
    "scan_col_tcp": {"fa": "TCP", "en": "TCP"},
    "scan_col_score": {"fa": "امتیاز", "en": "Score"},
    "scan_up": {"fa": "✅ وصل", "en": "✅ Up"},
    "scan_down": {"fa": "❌ قطع", "en": "❌ Down"},
    "scan_down_tip": {
        "fa": "سرور در دسترس نیست؛ آدرس و پورت را بررسی کن و دوباره اسکن بگیر.",
        "en": "Server is unreachable; check the address and port, then scan again.",
    },
    "scan_of": {"fa": "از", "en": "of"},
    "region_ir": {"fa": "ایران", "en": "Iran"},
    "region_de": {"fa": "آلمان", "en": "Germany"},
    "region_fr": {"fa": "فرانسه", "en": "France"},
    "region_nl": {"fa": "هلند", "en": "Netherlands"},
    "region_uk": {"fa": "انگلیس", "en": "UK"},
    "region_tr": {"fa": "ترکیه", "en": "Turkey"},
    "region_ae": {"fa": "امارات", "en": "UAE"},
    "region_unknown": {"fa": "نامشخص", "en": "Unknown"},
    "tab_scan": {"fa": "اسکن سرورها", "en": "Server scan"},
    "tab_safe": {"fa": "لیست امن", "en": "Safe list"},
    "tab_settings": {"fa": "تنظیمات", "en": "Settings"},
    "tab_log": {"fa": "لاگ", "en": "Log"},
    # ---- تب اسکن سرورها ----
    "scan_hint": {
        "fa": "بهترین سرور MasterStream را برای استریم پیدا کن — با اینترنت خودت تست می‌شود.",
        "en": "Find the best MasterStream server for your stream — tested with your own connection.",
    },
    "scan_all": {"fa": "⚡ اسکن همه", "en": "⚡ Scan all"},
    "scan_one": {"fa": "اسکن انتخاب‌شده", "en": "Scan selected"},
    "scan_stop": {"fa": "⏹ توقف", "en": "⏹ Stop"},
    "scan_scanning": {"fa": "در حال اسکن…", "en": "Scanning…"},
    "scan_add": {"fa": "＋ افزودن", "en": "＋ Add"},
    "scan_edit": {"fa": "✎ ویرایش", "en": "✎ Edit"},
    "scan_del": {"fa": "🗑 حذف", "en": "🗑 Delete"},
    "scan_import": {"fa": "📥 درون‌ریزی", "en": "📥 Import"},
    "scan_copy": {"fa": "📋 کپی آدرس RTMP", "en": "📋 Copy RTMP address"},
    "scan_best": {"fa": "🏆 بهترین سرور", "en": "🏆 Best server"},
    "scan_no_servers": {"fa": "هنوز سروری اضافه نشده", "en": "No servers added yet"},
    "scan_no_servers_hint": {
        "fa": "با «افزودن» یا «درون‌ریزی» اولین سرور MasterStream را اضافه کن",
        "en": "Add your first MasterStream server with “Add” or “Import”",
    },
    "scan_no_results": {
        "fa": "هنوز اسکن نشده — دکمه «اسکن همه» را بزن",
        "en": "Not scanned yet — hit “Scan all”",
    },
    "scan_none_up": {
        "fa": "هیچ سروری وصل نشد. اینترنت یا آدرس‌ها را بررسی کن.",
        "en": "No server is reachable. Check your internet or the addresses.",
    },
    "scan_copied": {"fa": "آدرس RTMP کپی شد — در Meld/OBS وارد کن", "en": "RTMP address copied — paste it into Meld/OBS"},
    "scan_select_first": {"fa": "اول یک سرور را انتخاب کن.", "en": "Select a server first."},
    "scan_del_q": {"fa": "این سرور حذف شود؟", "en": "Delete this server?"},
    "scan_import_title": {"fa": "درون‌ریزی گروهی", "en": "Bulk import"},
    "scan_import_hint": {
        "fa": "هر خط یک سرور — قالب: نام | rtmp://host:port/live",
        "en": "One server per line — format: name | rtmp://host:port/live",
    },
    "scan_one_tip": {
        "fa": "فقط سرور انتخاب‌شده در جدول اسکن می‌شود",
        "en": "Scans only the selected server in the table",
    },
    "scan_stop_tip": {
        "fa": "توقف اسکن در حال اجرا",
        "en": "Stop the running scan",
    },
    "scan_add_tip": {
        "fa": "افزودن سرور MasterStream جدید به لیست",
        "en": "Add a new MasterStream server to the list",
    },
    "scan_edit_tip": {
        "fa": "ویرایش سرور انتخاب‌شده",
        "en": "Edit the selected server",
    },
    "scan_del_tip": {
        "fa": "حذف سرور انتخاب‌شده از لیست",
        "en": "Delete the selected server from the list",
    },
    "scan_table_tip": {
        "fa": "دابل‌کلیک روی سطر: کپی آدرس RTMP",
        "en": "Double-click a row: copy RTMP address",
    },
    "scan_imported": {"fa": "سرور اضافه شد.", "en": "servers added."},
    "scan_import_none": {"fa": "سرور معتبری پیدا نشد.", "en": "No valid servers found."},
    "scan_srv_name": {"fa": "نام سرور:", "en": "Server name:"},
    "scan_srv_rtmp": {"fa": "آدرس RTMP:", "en": "RTMP address:"},
    "scan_srv_region": {"fa": "منطقه:", "en": "Region:"},
    "scan_srv_note": {"fa": "توضیح:", "en": "Note:"},
    "scan_auto_hint": {
        "fa": "نام و منطقه خودکار از روی لینک حدس زده می‌شوند.",
        "en": "Name and region are auto-detected from the link.",
    },
    "scan_add_title": {"fa": "افزودن سرور", "en": "Add server"},
    "scan_edit_title": {"fa": "ویرایش سرور", "en": "Edit server"},
    "scan_col_server": {"fa": "سرور", "en": "Server"},
    "scan_col_region": {"fa": "منطقه", "en": "Region"},
    "scan_col_ping": {"fa": "پینگ", "en": "Ping"},
    "scan_col_loss": {"fa": "لاست٪", "en": "Loss%"},
    "scan_col_tcp": {"fa": "TCP", "en": "TCP"},
    "scan_col_score": {"fa": "امتیاز", "en": "Score"},
    "scan_up": {"fa": "✅ وصل", "en": "✅ Up"},
    "scan_down": {"fa": "❌ قطع", "en": "❌ Down"},
    "scan_down_tip": {
        "fa": "سرور در دسترس نیست؛ آدرس و پورت را بررسی کن و دوباره اسکن بگیر.",
        "en": "Server is unreachable; check the address and port, then scan again.",
    },
    "tab_safe": {"fa": "لیست امن", "en": "Safe list"},
    "tab_settings": {"fa": "تنظیمات", "en": "Settings"},
    "tab_log": {"fa": "لاگ", "en": "Log"},
    # ---- تب برنامه‌ها ----
    "procs_hint": {
        "fa": "برنامه‌های اینترنت‌خور (غیر لیست امن) را می‌توانی ببندی. پروسس‌های سیستمی و لیست امن هرگز نمایش داده نمی‌شوند.",
        "en": "You can close bandwidth-hogging apps (not in safe list). System processes and safe-listed apps are never shown.",
    },
    "col_app": {"fa": "برنامه", "en": "App"},
    "col_pid": {"fa": "PID", "en": "PID"},
    "col_up": {"fa": "آپلود", "en": "Upload"},
    "col_down": {"fa": "دانلود", "en": "Download"},
    "col_cpu": {"fa": "CPU ٪", "en": "CPU %"},
    "col_ram": {"fa": "RAM (MB)", "en": "RAM (MB)"},
    "btn_kill": {"fa": "بستن", "en": "Kill"},
    # ---- تب لیست امن ----
    "safe_hint": {
        "fa": "این برنامه‌ها در «حالت استریم» هرگز بسته نمی‌شوند. با «انتخاب از برنامه‌های در حال اجرا» برنامه‌ها را تیک بزن و اضافه کن.",
        "en": "These apps are never closed in stream mode. Use “Pick from running apps” to tick and add them.",
    },
    "safe_placeholder": {"fa": "مثلاً: myapp.exe", "en": "e.g. myapp.exe"},
    "safe_add": {"fa": "➕ افزودن", "en": "➕ Add"},
    "safe_del": {"fa": "➖ حذف انتخاب‌شده", "en": "➖ Remove selected"},
    # ---- تب تنظیمات ----
    "set_server": {"fa": "سرور پینگ:", "en": "Ping server:"},
    "set_server_ph": {"fa": "آی‌پی سرور استریم (MasterStream)", "en": "Stream server IP (MasterStream)"},
    "set_bitrate": {"fa": "بیت‌ریت استریم (Mbps):", "en": "Stream bitrate (Mbps):"},
    "set_save": {"fa": "💾 ذخیره تنظیمات", "en": "💾 Save settings"},
    "set_note": {
        "fa": "پینگ به اولین سرور لیست گرفته می‌شود. بیت‌ریت را مطابق تنظیمات MeldStudio بگذار.",
        "en": "Ping uses the first server in the list. Set bitrate to match your MeldStudio settings.",
    },
    "lang_label": {"fa": "زبان / Language:", "en": "Language / زبان:"},
    "about_btn": {"fa": "ℹ درباره", "en": "ℹ About"},
    "about_title": {"fa": "درباره‌ی LagSlice", "en": "About LagSlice"},
    # ---- لاگ ----
    "log_ready": {"fa": "LagSlice آماده است ⚡", "en": "LagSlice is ready ⚡"},
    "log_stream_on": {"fa": "🎬 حالت استریم فعال شد؛ بستن برنامه‌های اینترنت‌خور…", "en": "🎬 Stream mode on; closing bandwidth hogs…"},
    "log_nothing": {"fa": "برنامه‌ی اضافی برای بستن پیدا نشد ✅", "en": "No extra apps to close ✅"},
    "log_stream_off": {"fa": "⏹ حالت استریم متوقف شد", "en": "⏹ Stream mode stopped"},
    "log_safe_add": {"fa": "به لیست امن اضافه شد", "en": "added to safe list"},
    "log_safe_del": {"fa": "از لیست امن حذف شد", "en": "removed from safe list"},
    "log_settings_saved": {"fa": "💾 تنظیمات ذخیره شد", "en": "💾 Settings saved"},
    "log_lang_changed": {"fa": "🌐 زبان عوض شد", "en": "🌐 Language changed"},
    "ok": {"fa": "تأیید", "en": "OK"},
    "cancel": {"fa": "انصراف", "en": "Cancel"},
    "help_btn": {"fa": "📖 راهنما", "en": "📖 Help"},
    "help_title": {"fa": "راهنمای LagSlice", "en": "LagSlice Guide"},
    "help_missing": {"fa": "فایل راهنما پیدا نشد.", "en": "Guide file not found."},
    "ping_server_hint": {
        "fa": "سروری که برنامه برای اندازه‌گیری پینگ و جیتر به آن پینگ می‌زند (پیش‌فرض 8.8.8.8). عدد روی کارت «پینگ سرور» از همین‌جا می‌آید. می‌توانید سرور MasterStream یا هر سرور دیگری بگذارید؛ چند سرور را با ویرگول جدا کنید.",
        "en": "The server the app pings to measure ping/jitter (default 8.8.8.8). The “Server ping” card shows this server's latency. You can set your MasterStream server or any other; separate multiple servers with commas.",
    },
    "safe_pick_btn": {"fa": "🔍 انتخاب از برنامه‌های در حال اجرا", "en": "🔍 Pick from running apps"},
    "safe_pick_title": {"fa": "انتخاب برنامه برای لیست امن", "en": "Pick apps for the safe list"},
    "safe_pick_search": {"fa": "جست‌وجو…", "en": "Search…"},
    "safe_pick_add": {"fa": "افزودن انتخاب‌شده‌ها", "en": "Add selected"},
    "safe_pick_cancel": {"fa": "انصراف", "en": "Cancel"},
    "safe_pick_empty": {"fa": "برنامه‌ای پیدا نشد.", "en": "No apps found."},
    "log_safe_pick": {"fa": "به لیست امن اضافه شد", "en": "added to safe list"},
    "stream_confirm_title": {"fa": "تأیید حالت استریم", "en": "Confirm stream mode"},
    "stream_confirm_msg": {
        "fa": "این {n} برنامه‌ی اینترنت‌خور بسته می‌شوند:\n{names}\n\nمطمئنی؟ برنامه‌های لیست امن بسته نمی‌شوند.",
        "en": "These {n} bandwidth-hogging apps will be closed:\n{names}\n\nSure? Safe-listed apps will not be closed.",
    },
    "stream_confirm_yes": {"fa": "ببند و شروع کن", "en": "Close & start"},
    "stream_confirm_no": {"fa": "انصراف", "en": "Cancel"},
    "log_stream_cancel": {"fa": "حالت استریم لغو شد", "en": "Stream mode cancelled"},
    "empty_procs": {
        "fa": "برنامه‌ی اضافی برای بستن نیست؛ همه‌چیز تمیز است ✅",
        "en": "No extra apps to close; all clean ✅",
    },
    "tip_up": {
        "fa": "سرعت آپلود لحظه‌ای کل سیستم. برای استریم پایدار باید از بیت‌ریت بیشتر باشد.",
        "en": "Total system upload speed right now. For stable streaming it should exceed your bitrate.",
    },
    "tip_down": {
        "fa": "سرعت دانلود لحظه‌ای کل سیستم.",
        "en": "Total system download speed right now.",
    },
    "tip_stream": {
        "fa": "همه‌ی برنامه‌های اینترنت‌خور (غیر از لیست امن) را یک‌جا می‌بندد.",
        "en": "Closes all bandwidth-hogging apps at once (except the safe list).",
    },
    # ---- پیام‌های بستن پروسس ----
    "kill_ok": {"fa": "بسته شد", "en": "closed"},
    "kill_gone": {"fa": "پروسس از قبل بسته شده بود", "en": "Process was already closed"},
    "kill_denied": {"fa": "دسترسی کافی نیست؛ با ادمین اجرا کن", "en": "Access denied; run as administrator"},
    "kill_system": {"fa": "پروسس سیستمی است؛ بسته نشد", "en": "System process; not closed"},
    "kill_err": {"fa": "خطا", "en": "Error"},
    # ---- نام‌های فارسی/انگلیسی برنامه‌های اینترنت‌خور ----
    "hog_chrome.exe": {"fa": "مرورگر کروم", "en": "Chrome browser"},
    "hog_firefox.exe": {"fa": "مرورگر فایرفاکس", "en": "Firefox browser"},
    "hog_msedge.exe": {"fa": "مرورگر اج", "en": "Edge browser"},
    "hog_opera.exe": {"fa": "مرورگر اپرا", "en": "Opera browser"},
    "hog_brave.exe": {"fa": "مرورگر بریو", "en": "Brave browser"},
    "hog_vivaldi.exe": {"fa": "مرورگر ویوالدی", "en": "Vivaldi browser"},
    "hog_utorrent.exe": {"fa": "تورنت", "en": "Torrent client"},
    "hog_qbittorrent.exe": {"fa": "تورنت", "en": "Torrent client"},
    "hog_bittorrent.exe": {"fa": "تورنت", "en": "Torrent client"},
    "hog_onedrive.exe": {"fa": "سینک وان‌درایو", "en": "OneDrive sync"},
    "hog_dropbox.exe": {"fa": "سینک دراپ‌باکس", "en": "Dropbox sync"},
    "hog_googledrivesync.exe": {"fa": "سینک گوگل درایو", "en": "Google Drive sync"},
    "hog_googledrivefs.exe": {"fa": "سینک گوگل درایو", "en": "Google Drive sync"},
    "hog_epicgameslauncher.exe": {"fa": "لانچر اپیک", "en": "Epic launcher"},
    "hog_ubisoftconnect.exe": {"fa": "لانچر یوبی‌سافت", "en": "Ubisoft launcher"},
    "hog_eadesktop.exe": {"fa": "لانچر EA", "en": "EA launcher"},
    "hog_battle.net.exe": {"fa": "لانچر بتل‌نت", "en": "Battle.net launcher"},
    "hog_riotclientservices.exe": {"fa": "کلاینت رایوت", "en": "Riot client"},
    "hog_spotify.exe": {"fa": "اسپاتیفای", "en": "Spotify"},
    "hog_telegram.exe": {"fa": "تلگرام دسکتاپ", "en": "Telegram desktop"},
    "hog_whatsapp.exe": {"fa": "واتس‌اپ دسکتاپ", "en": "WhatsApp desktop"},
    "hog_discord.exe": {"fa": "دیسکورد", "en": "Discord"},
    "hog_skype.exe": {"fa": "اسکایپ", "en": "Skype"},
    "hog_zoom.exe": {"fa": "زوم", "en": "Zoom"},
    "hog_teams.exe": {"fa": "تیمز", "en": "Teams"},
    "hog_slack.exe": {"fa": "اسلک", "en": "Slack"},
    # ---- موتور آپدیت ----
    "upd_btn": {"fa": "⬆ بررسی آپدیت", "en": "⬆ Check for updates"},
    "upd_checking": {"fa": "در حال بررسی…", "en": "Checking…"},
    "upd_none": {"fa": "نسخه‌ی فعلی به‌روز است.", "en": "You're up to date."},
    "upd_found_title": {"fa": "آپدیت جدید", "en": "Update available"},
    "upd_later": {"fa": "بعداً", "en": "Later"},
    "upd_download_install": {"fa": "دانلود و نصب", "en": "Download & install"},
    "upd_downloading": {"fa": "در حال دانلود آپدیت…", "en": "Downloading update…"},
    "upd_dev_note": {
        "fa": "نصب خودکار فقط در نسخه‌ی نصب‌شده (exe) کار می‌کند.",
        "en": "Auto-install works only in the installed (exe) build.",
    },
    "upd_restart_note": {
        "fa": "برنامه بسته و با نسخه‌ی جدید اجرا می‌شود.",
        "en": "The app will close and restart with the new version.",
    },
    "upd_done_title": {"fa": "به‌روزرسانی انجام شد", "en": "Update installed"},
    "upd_whatsnew": {"fa": "تغییرات:", "en": "What's new:"},
    "upd_check_failed": {
        "fa": "بررسی آپدیت ناموفق بود؛ اتصال اینترنت را بررسی کن.",
        "en": "Update check failed; check your internet connection.",
    },
}


def set_lang(lang):
    global _current
    if lang in LANGS:
        _current = lang


def get_lang():
    return _current


def tr(key):
    return STRINGS.get(key, {}).get(_current, key)


def fa_digits(s):
    if _current == "fa":
        return str(s).translate(str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫"))
    return str(s)
