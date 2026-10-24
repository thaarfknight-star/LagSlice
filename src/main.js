// فرانت LagSlice — داده‌ی زنده از هسته‌ی Rust از طریق IPC تائوری می‌آید.
// بیرون از تائوری (پیش‌نمایش مرورگر) داده‌ی نمونه نشان داده می‌شود.
const invoke = window.__TAURI__?.core?.invoke;

let APP_VERSION = "0.9.2";
// نسخه‌ی واقعی از خود برنامه (جلوگیری از کهنه‌ماندن ثابت دستی)
window.__TAURI__?.app?.getVersion?.().then((v) => { if (v) APP_VERSION = v; }).catch(() => {});
const SETTINGS_KEY = "lagslice.settings.v1";

// پیش‌فرض‌ها دقیقاً مثل load_config نسخه‌ی پایتون.
const DEFAULT_SETTINGS = {
  servers: ["8.8.8.8"],
  bitrate_mbps: 8.0,
  lang: "fa",
  ping_enabled: true,
  theme: "lagslice",
  tray: true,
  active: false,
  keepApps: [],
  manualCaps: {},
  closeOthers: true,
  updateMode: "notify",
  mode: "stream",
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (data && typeof data === "object") {
        const cfg = { ...DEFAULT_SETTINGS, ...data };
        // مهاجرت یک‌باره (0.8.0): بستن به سینی پیش‌فرض روشن شد.
        if (!cfg.tray_v2) {
          cfg.tray = true;
          cfg.tray_v2 = true;
        }
        if (!["fa", "en"].includes(cfg.lang)) cfg.lang = "fa";
        if (!["lagslice", "neon_purple", "ice_blue"].includes(cfg.theme)) cfg.theme = "lagslice";
        if (!Array.isArray(cfg.servers) || !cfg.servers.length) cfg.servers = ["8.8.8.8"];
        if (!Array.isArray(cfg.keepApps)) cfg.keepApps = [];
        if (!cfg.manualCaps || typeof cfg.manualCaps !== "object") cfg.manualCaps = {};
        if (typeof cfg.closeOthers !== "boolean") cfg.closeOthers = true;
        return cfg;
      }
    }
  } catch {}
  return { ...DEFAULT_SETTINGS };
}

function saveSettings() {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {}
}

let settings = loadSettings();

// رشته‌های رابط — فارسی از lang.py نسخه‌ی پایتون؛ انگلیسی هم همان‌جا هست.
const STRINGS = {
  fa: {
    subtitle: "مدیریت پهنای‌باند بین گیم و استریم",
    total_up: "آپلود کل",
    ping_label: "پینگ سرور",
    nav_main: "برنامه‌ها",
    nav_scan: "اسکن سرورها",
    nav_relay: "رله‌ی تطبیقی",
    nav_guide: "راهنما",
    nav_settings: "تنظیمات",
    relay_title: "رله‌ی تطبیقی RTMP",
    relay_hint: "وقتی بیت‌ریت شبکه نوسان دارد، ارسال مستقیم Meld به Kick باعث جمع‌شدن صف و رشد تأخیر می‌شود. رله استریم را روی همین سیستم تحویل می‌گیرد، ظرفیت واقعی مسیر تا سرور مقصد را می‌سنجد و بیت‌ریت خروجی را تطبیقی تنظیم می‌کند؛ به‌جای رشد تأخیر، فقط کمی فریم‌ریت کم می‌شود.",
    relay_setup_title: "⚙ راه‌اندازی (یک بار)",
    relay_step1: "از داشبورد Kick آدرس RTMP و کلید استریم را بردار و پایین وارد کن.",
    relay_step2: "دکمه‌ی «شروع رله» را بزن.",
    relay_step3: "در Meld یک خروجی Custom RTMP بساز: آدرس",
    relay_step3b: "و کلید دلخواه (مثلاً",
    relay_step3c: ")",
    relay_step4: "در Meld روی Go Live بزن؛ رله خودش بقیه را انجام می‌دهد.",
    relay_target: "آدرس RTMP مقصد (Kick)",
    relay_target_ph: "rtmp://live-ingest.kick.example/live",
    relay_key: "کلید استریم Kick",
    relay_key_ph: "••••••••",
    relay_top: "سقف بیت‌ریت (Mbps)",
    relay_key_note: "کلید فقط روی همین دستگاه می‌ماند (در حافظه‌ی برنامه و حافظه‌ی محلی مرورگر داخلی)؛ هرگز به سرور یا جایی فرستاده نمی‌شود و در لاگ هم نمی‌آید.",
    relay_start: "▶ شروع رله",
    relay_stop: "⏹ توقف رله",
    relay_status_title: "📊 وضعیت زنده",
    relay_state_label: "وضعیت:",
    relay_rung_label: "بیت‌ریت خروجی فعلی:",
    relay_cap_label: "میانگین نرخ تخلیه:",
    relay_probe_label: "نتیجه‌ی آخرین پروب:",
    relay_stats_label: "ارسال‌شده / GOP حذف‌شده / صف:",
    relay_failsafe: "اگر رله وسط استریم متوقف شود، استریم هم قطع می‌شود؛ برای برگشت فوری، خروجی Meld را به حالت مستقیم Kick برگردان. رله کاملاً اختیاری است و بدون آن هم LagSlice مثل قبل کار می‌کند.",
    guide_title: "📖 راهنمای LagSlice",
    relay_running: "در حال اجرا ✅",
    relay_stopped: "متوقف",
    relay_at_top: "سقف",
    relay_started: "رله شروع شد — حالا در Meld خروجی Custom RTMP را استارت بزن.",
    relay_stopped_msg: "رله متوقف شد.",
    relay_err_url: "آدرس مقصد باید با rtmp:// شروع شود.",
    relay_err_key: "کلید استریم را وارد کن.",
    scan_title: "اسکن سرورهای استریم",
    scan_hint: "سرورها با پینگ و تست اتصال RTMP سنجیده و امتیازدهی می‌شوند؛ امتیاز کمتر یعنی سرور بهتر.",
    scan_name: "نام",
    scan_region: "منطقه",
    scan_host: "هاست",
    scan_port: "پورت",
    scan_add: "افزودن سرور",
    scan_run: "اسکن همه",
    scan_col_server: "سرور",
    scan_col_addr: "آدرس RTMP",
    scan_col_ping: "پینگ (ms)",
    scan_col_loss: "تلفات",
    scan_col_tcp: "اتصال TCP (ms)",
    scan_col_score: "امتیاز",
    scan_col_status: "وضعیت",
    scan_empty: "سروری نیست",
    scanning: "در حال اسکن…",
    scan_ok: "وصل",
    scan_down: "قطع",
    scan_best: "⭐ بهترین سرور: {name} — {url}",
    scan_use: "انتخاب",
    scan_use_done: "سرور پینگ روی {host} تنظیم شد.",
    scan_del: "حذف",
    scan_need_host: "اول هاست سرور را وارد کن.",
    scan_link: "لینک سرور (RTMP)",
    scan_link_ph: "rtmp://host:1935/live",
    scan_bulk: "درون‌ریزی گروهی (هر خط یک لینک)",
    scan_bulk_ph: "rtmp://ir1.example.com/live",
    scan_import: "درون‌ریزی",
    scan_imported: "{count} سرور اضافه شد.",
    scan_pick_best: "⭐ انتخاب بهترین سرور",
    scan_active: "فعال",
    scan_no_best: "هنوز سرور سالمی اسکن نشده است.",
    reserve_title: "رزرو آپلود برای استریم",
    reserve_hint: "مقداری از آپلود را برای Meld Studio رزرو کن؛ بقیه‌ی برنامه‌ها خودکار سقف می‌گیرند تا سهم استریم را نخورند.",
    reserve_label: "رزرو (Mbps)",
    stream_app_label: "برنامه‌ی استریم",
    apply_reserve: "اعمال رزرو",
    clear_caps: "حذف همه‌ی سقف‌ها",
    apps_title: "برنامه‌ها و آپلود زنده",
    col_app: "برنامه",
    col_up: "آپلود (Kbps)",
    col_down: "دانلود (Kbps)",
    col_cap: "سقف آپلود (Kbps)",
    col_kill: "بستن برنامه",
    measuring: "در حال اندازه‌گیری…",
    empty_rates: "هنوز ترافیک آپلودی دیده نشد…",
    cap_placeholder: "بدون سقف",
    cap_apply: "اعمال سقف",
    btn_kill: "بستن",
    kill_ok: "بسته شد",
    kill_err: "بستن ناموفق بود",
    kill_preview: "پیش‌نمایش مرورگر: «{name}» بسته شد (شبیه‌سازی).",
    kill_no_backend: "دستور بستن (kill_process) هنوز در هسته‌ی Rust پیاده نشده است.",
    no_response: "بدون پاسخ",
    reserve_preview: "پیش‌نمایش مرورگر: در نسخه‌ی نهایی رزرو از اینجا اعمال می‌شود.",
    applying: "در حال اعمال…",
    reserve_done: "انجام شد — آپلود کل {total}؛ {count} برنامه سقف گرفتند تا {reserve} برای استریم رزرو بماند.",
    caps_cleared: "همه‌ی سقف‌ها حذف شدند.",
    programs_title: "همه‌ی برنامه‌ها — انتخاب و محدودیت",
    programs_refresh: "بازخوانی فهرست",
    programs_add: "افزودن برنامه از فایل…",
    programs_search_ph: "جست‌وجوی برنامه…",
    close_others: "با فعال‌سازی موتور، برنامه‌های انتخاب‌نشده بسته شوند",
    programs_hint: "برنامه‌های تیک‌خورده «مجاز»اند: باز می‌مانند و می‌شود برایشان سقف آپلود گذاشت. بقیه‌ی برنامه‌های در حال اجرا با فعال‌شدن موتور بسته می‌شوند؛ برنامه‌های سیستمی ویندوز هرگز بسته نمی‌شوند.",
    prog_running: "در حال اجرا",
    prog_not_running: "اجرا نیست",
    prog_traffic: "ترافیک دارد",
    prog_remove: "حذف",
    prog_empty: "برنامه‌ای پیدا نشد.",
    closed_apps: "بسته شد: ",
    error_prefix: "خطا: ",
    set_sec_net: "🌐 سرور پینگ و بیت‌ریت",
    set_server: "سرور پینگ:",
    set_server_ph: "آی‌پی سرور استریم (MasterStream)",
    set_bitrate: "بیت‌ریت استریم (Mbps):",
    ping_hint: "سروری که برنامه برای اندازه‌گیری پینگ و جیتر به آن پینگ می‌زند (پیش‌فرض 8.8.8.8). عدد روی کارت «پینگ سرور» از همین‌جا می‌آید. می‌توانید سرور MasterStream یا هر سرور دیگری بگذارید؛ چند سرور را با ویرگول جدا کنید.",
    set_ping_toggle: "📡 پینگ سرور",
    set_save: "💾 ذخیره تنظیمات",
    set_note: "پینگ به اولین سرور لیست گرفته می‌شود. بیت‌ریت را مطابق تنظیمات MeldStudio بگذار.",
    settings_saved: "💾 تنظیمات ذخیره شد",
    set_sec_lang: "🌍 زبان برنامه",
    lang_label: "زبان / Language:",
    set_sec_theme: "🎨 تم برنامه",
    set_theme: "تم:",
    theme_lagslice: "LagSlice (پیش‌فرض)",
    theme_neon_purple: "بنفش نئونی",
    theme_ice_blue: "آبی یخی",
    set_sec_general: "⚙ عمومی",
    set_tray: "بستن به سینی سیستم (exit to tray)",
    engine_label: "محدودیت‌ها فعال",
    engine_on: "موتور محدودیت فعال شد — سقف‌ها زنده نگه داشته می‌شوند و تثبیت‌کننده‌ی استریم کار می‌کند.",
    engine_armed: "موتور فعال شد — هنوز ترافیکی نیست؛ با شروع آپلود سقف‌ها خودکار اعمال می‌شوند.",
    engine_off: "موتور محدودیت خاموش شد — همه‌ی سقف‌ها حذف شدند.",
    set_sec_contact: "💬 پشتیبانی",
    set_telegram_btn: "باز کردن در تلگرام @tha_arf",
    set_sec_help: "📖 راهنما",
    set_open_guide: "باز کردن راهنمای داخل‌برنامه‌ای",
    set_sec_about: "ℹ درباره / لایسنس",
    set_sec_update: "🔄 به‌روزرسانی",
    set_update_check: "بررسی به‌روزرسانی",
    update_checking: "در حال بررسی…",
    update_latest: "نسخه‌ی شما ({ver}) به‌روز است ✅",
    update_available: "نسخه‌ی تازه موجود است: {ver} — از ریپوی گیت‌هاب بگیرید.",
    update_err: "بررسی به‌روزرسانی ناموفق بود (اتصال/پاسخ گیت‌هاب).",
    upd_mode: "حالت به‌روزرسانی",
    upd_mode_auto: "خودکار (دانلود بی‌صدا)",
    upd_mode_notify: "اطلاع‌رسانی (با تأیید من)",
    upd_mode_off: "خاموش (فقط دستی)",
    upd_pick_file: "بارگذاری فایل آپدیت",
    upd_download: "دانلود آپدیت",
    upd_downloading: "در حال دانلود آپدیت… {pct}٪",
    upd_cancel: "لغو دانلود",
    upd_ready_install: "🔄 آپدیت آماده‌ی نصب است — نصب و راه‌اندازی مجدد",
    upd_available2: "نسخه‌ی تازه موجود است: {ver} ({size})",
    upd_mandatory: "این به‌روزرسانی اجباری است.",
    upd_installing: "در حال نصب… برنامه بسته و دوباره باز می‌شود.",
    upd_applied_ok: "✅ به‌روزرسانی انجام شد: {prev} ← {new}",
    upd_applied_fail: "⚠️ به‌روزرسانی قبلی ناموفق بود: {detail}",
    upd_bad_file: "این فایل بسته‌ی آپدیت معتبر LagSlice نیست.",
  },
  en: {
    subtitle: "Bandwidth management between game and stream",
    total_up: "Total upload",
    ping_label: "Server ping",
    nav_main: "Apps",
    nav_scan: "Server scan",
    nav_relay: "Adaptive relay",
    nav_guide: "Guide",
    nav_settings: "Settings",
    relay_title: "Adaptive RTMP relay",
    relay_hint: "When network bitrate fluctuates, sending directly from Meld to Kick queues frames up and delay grows. The relay takes the stream on this same machine, measures the real path capacity to the destination, and adapts the output bitrate — instead of growing delay, you only lose a little frame rate.",
    relay_setup_title: "⚙ Setup (once)",
    relay_step1: "Copy the RTMP URL and stream key from your Kick dashboard and enter them below.",
    relay_step2: "Press “Start relay”.",
    relay_step3: "In Meld, create a Custom RTMP output with URL",
    relay_step3b: "and any key (e.g.",
    relay_step3c: ")",
    relay_step4: "Press Go Live in Meld; the relay handles the rest.",
    relay_target: "Destination RTMP URL (Kick)",
    relay_target_ph: "rtmp://live-ingest.kick.example/live",
    relay_key: "Kick stream key",
    relay_key_ph: "••••••••",
    relay_top: "Bitrate cap (Mbps)",
    relay_key_note: "The key stays on this machine only (app memory + the embedded browser's local storage); it is never sent anywhere and never logged.",
    relay_start: "▶ Start relay",
    relay_stop: "⏹ Stop relay",
    relay_status_title: "📊 Live status",
    relay_state_label: "Status:",
    relay_rung_label: "Current output bitrate:",
    relay_cap_label: "Avg drain rate:",
    relay_probe_label: "Last probe result:",
    relay_stats_label: "Sent / GOPs dropped / queue:",
    relay_failsafe: "If the relay stops mid-stream, the stream stops too; to recover instantly, switch Meld back to direct Kick output. The relay is fully optional — LagSlice works as before without it.",
    guide_title: "📖 LagSlice guide",
    relay_running: "Running ✅",
    relay_stopped: "Stopped",
    relay_at_top: "cap",
    relay_started: "Relay started — now start the Custom RTMP output in Meld.",
    relay_stopped_msg: "Relay stopped.",
    relay_err_url: "The destination URL must start with rtmp://.",
    relay_err_key: "Enter the stream key.",
    scan_title: "Stream server scan",
    scan_hint: "Servers are measured with ping and an RTMP connection test and scored; a lower score means a better server.",
    scan_name: "Name",
    scan_region: "Region",
    scan_host: "Host",
    scan_port: "Port",
    scan_add: "Add server",
    scan_run: "Scan all",
    scan_col_server: "Server",
    scan_col_addr: "RTMP address",
    scan_col_ping: "Ping (ms)",
    scan_col_loss: "Loss",
    scan_col_tcp: "TCP connect (ms)",
    scan_col_score: "Score",
    scan_col_status: "Status",
    scan_empty: "No servers",
    scanning: "Scanning…",
    scan_ok: "Up",
    scan_down: "Down",
    scan_best: "⭐ Best server: {name} — {url}",
    scan_use: "Use",
    scan_use_done: "Ping server set to {host}.",
    scan_del: "Delete",
    scan_need_host: "Enter the server host first.",
    scan_link: "Server link (RTMP)",
    scan_link_ph: "rtmp://host:1935/live",
    scan_bulk: "Bulk import (one link per line)",
    scan_bulk_ph: "rtmp://ir1.example.com/live",
    scan_import: "Import",
    scan_imported: "{count} servers added.",
    scan_pick_best: "⭐ Pick best server",
    scan_active: "Active",
    scan_no_best: "No healthy server has been scanned yet.",
    reserve_title: "Reserve upload for streaming",
    reserve_hint: "Reserve part of your upload for Meld Studio; other apps get capped automatically so they don't eat the stream's share.",
    reserve_label: "Reserve (Mbps)",
    stream_app_label: "Stream app",
    apply_reserve: "Apply reserve",
    clear_caps: "Clear all caps",
    apps_title: "Apps & live upload",
    col_app: "App",
    col_up: "Upload (Kbps)",
    col_down: "Download (Kbps)",
    col_cap: "Upload cap (Kbps)",
    col_kill: "Close app",
    measuring: "Measuring…",
    empty_rates: "No upload traffic seen yet…",
    cap_placeholder: "No cap",
    cap_apply: "Apply cap",
    btn_kill: "Kill",
    kill_ok: "closed",
    kill_err: "failed to close",
    kill_preview: "Browser preview: “{name}” closed (simulated).",
    kill_no_backend: "The kill command (kill_process) is not implemented in the Rust core yet.",
    no_response: "No response",
    reserve_preview: "Browser preview: in the final build the reserve is applied here.",
    applying: "Applying…",
    reserve_done: "Done — total upload {total}; {count} apps capped so {reserve} stays reserved for the stream.",
    caps_cleared: "All caps cleared.",
    programs_title: "All programs — select & limit",
    programs_refresh: "Refresh list",
    programs_add: "Add program from file…",
    programs_search_ph: "Search programs…",
    close_others: "When the engine activates, close unselected programs",
    programs_hint: "Checked programs are allowed: they stay open and can get an upload cap. Other running programs are closed when the engine activates; Windows system programs are never closed.",
    prog_running: "Running",
    prog_not_running: "Not running",
    prog_traffic: "Has traffic",
    prog_remove: "Remove",
    prog_empty: "No programs found.",
    closed_apps: "Closed: ",
    error_prefix: "Error: ",
    set_sec_net: "🌐 Ping servers & bitrate",
    set_server: "Ping server:",
    set_server_ph: "Stream server IP (MasterStream)",
    set_bitrate: "Stream bitrate (Mbps):",
    ping_hint: "The server the app pings to measure ping/jitter (default 8.8.8.8). The “Server ping” card shows this server's latency. You can set your MasterStream server or any other; separate multiple servers with commas.",
    set_ping_toggle: "📡 Server ping",
    set_save: "💾 Save settings",
    set_note: "Ping uses the first server in the list. Set bitrate to match your MeldStudio settings.",
    settings_saved: "💾 Settings saved",
    set_sec_lang: "🌍 App language",
    lang_label: "Language / زبان:",
    set_sec_theme: "🎨 App theme",
    set_theme: "Theme:",
    theme_lagslice: "LagSlice (default)",
    theme_neon_purple: "Neon Purple",
    theme_ice_blue: "Ice Blue",
    set_sec_general: "⚙ General",
    set_tray: "Close to system tray (exit to tray)",
    engine_label: "Limits active",
    engine_on: "Limits engine is ON — caps stay applied live and the stream stabilizer is working.",
    engine_armed: "Engine is ON — no traffic yet; caps will apply automatically once upload starts.",
    engine_off: "Limits engine is OFF — all caps removed.",
    set_sec_contact: "💬 Support",
    set_telegram_btn: "Open in Telegram @tha_arf",
    set_sec_help: "📖 Guide",
    set_open_guide: "Open in-app guide",
    set_sec_about: "ℹ About / License",
    set_sec_update: "🔄 Updates",
    set_update_check: "Check for updates",
    update_checking: "Checking…",
    update_latest: "You are up to date ({ver}) ✅",
    update_available: "A new version is available: {ver} — get it from the GitHub repo.",
    update_err: "Update check failed (GitHub connection/response).",
    upd_mode: "Update mode",
    upd_mode_auto: "Automatic (silent download)",
    upd_mode_notify: "Notify (with my confirmation)",
    upd_mode_off: "Off (manual only)",
    upd_pick_file: "Load update file",
    upd_download: "Download update",
    upd_downloading: "Downloading update… {pct}%",
    upd_cancel: "Cancel download",
    upd_ready_install: "🔄 Update ready — install & restart",
    upd_available2: "A new version is available: {ver} ({size})",
    upd_mandatory: "This update is mandatory.",
    upd_installing: "Installing… the app will close and reopen.",
    upd_applied_ok: "✅ Updated: {prev} → {new}",
    upd_applied_fail: "⚠️ The previous update failed: {detail}",
    upd_bad_file: "This file is not a valid LagSlice update package.",
  },
};

const t = (key) => (STRINGS[settings.lang] && STRINGS[settings.lang][key]) || STRINGS.fa[key] || key;
const fill = (tpl, vars) => Object.entries(vars).reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), tpl);

// پروسس‌های سیستمی ویندوز — عین NEVER_TOUCH نسخه‌ی پایتون؛ هرگز در جدول نمی‌آیند و بسته نمی‌شوند.
const NEVER_TOUCH = new Set([
  "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
  "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
  "winlogon.exe", "fontdrvhost.exe", "conhost.exe", "sihost.exe",
  "taskhostw.exe", "runtimebroker.exe", "searchindexer.exe",
  "audiodg.exe", "ctfmon.exe", "dllhost.exe", "wudfhost.exe",
  "idle", "memory compression",
]);

const fmt = (n) => (n >= 1000 ? (n / 1000).toFixed(2) + " Mbps" : n.toFixed(0) + " Kbps");
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// داده‌ی نمونه‌ی پیش‌نمایش مرورگر (قابل‌تغییر تا بستنِ شبیه‌سازی‌شده دیده شود).
let mockRates = [
  { pid: 101, name: "Meld Studio.exe", up_kbps: 5980, down_kbps: 120 },
  { pid: 102, name: "cs2.exe", up_kbps: 210, down_kbps: 480 },
  { pid: 103, name: "chrome.exe", up_kbps: 1450, down_kbps: 3200 },
];

async function refreshRates() {
  let rates = [];
  try {
    if (invoke) {
      rates = await invoke("get_app_rates");
    } else {
      rates = mockRates;
    }
  } catch (e) {
    console.error(e);
  }
  rates = rates.filter((r) => !NEVER_TOUCH.has(String(r.name).toLowerCase()));
  const total = rates.reduce((s, r) => s + r.up_kbps, 0);
  document.getElementById("totalUp").textContent = rates.length ? fmt(total) : "—";

  const body = document.getElementById("appsBody");
  if (!rates.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty">${esc(t("empty_rates"))}</td></tr>`;
    return;
  }
  body.innerHTML = rates
    .map(
      (r) => `<tr>
        <td>${esc(r.name)}</td>
        <td>${fmt(r.up_kbps)}</td>
        <td>${fmt(r.down_kbps)}</td>
        <td><input class="cap-input" type="number" min="64" step="64" placeholder="${esc(t("cap_placeholder"))}" data-exe="${esc(r.name)}" /></td>
        <td><button class="cap-btn" data-exe="${esc(r.name)}">${esc(t("cap_apply"))}</button></td>
        <td><button class="kill-btn" data-pid="${r.pid}" data-exe="${esc(r.name)}">${esc(t("btn_kill"))}</button></td>
      </tr>`
    )
    .join("");
  body.querySelectorAll(".cap-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const exe = btn.dataset.exe;
      const input = body.querySelector(`.cap-input[data-exe="${CSS.escape(exe)}"]`);
      const val = parseFloat(input.value);
      if (!invoke) return;
      await invoke("set_app_cap", { exe, capKbps: isNaN(val) ? null : val });
    });
  });
  body.querySelectorAll(".kill-btn").forEach((btn) => {
    btn.addEventListener("click", () => killApp(btn));
  });
}

// بستن یک برنامه از جدول — معادل _kill_one نسخه‌ی پایتون:
// در تائوری دستور kill_process هسته صدا زده می‌شود؛ در پیش‌نمایش مرورگر شبیه‌سازی می‌شود.
async function killApp(btn) {
  const pid = parseInt(btn.dataset.pid, 10);
  const name = btn.dataset.exe;
  const msg = document.getElementById("procMsg");
  if (NEVER_TOUCH.has(String(name).toLowerCase())) return;
  btn.disabled = true;
  if (!invoke) {
    mockRates = mockRates.filter((r) => r.pid !== pid);
    msg.textContent = "✅ " + fill(t("kill_preview"), { name });
    refreshRates();
    return;
  }
  try {
    await invoke("kill_process", { pid });
    msg.textContent = `✅ ${name} ${t("kill_ok")}`;
  } catch (e) {
    const err = String(e);
    msg.textContent = "❌ " + (/kill_process|command|not found/i.test(err) ? t("kill_no_backend") : `${t("kill_err")}: ${err}`);
    btn.disabled = false;
  }
  refreshRates();
}

async function refreshPing() {
  const stat = document.getElementById("pingStat");
  if (!settings.ping_enabled) {
    stat.classList.add("hidden");
    return;
  }
  stat.classList.remove("hidden");
  const host = (settings.servers && settings.servers[0]) || "8.8.8.8";
  document.getElementById("pingLabel").textContent = `${t("ping_label")} — ${host}`;
  if (!invoke) {
    document.getElementById("pingVal").textContent = "24 ms";
    return;
  }
  try {
    const ms = await invoke("ping_host", { host });
    document.getElementById("pingVal").textContent = ms == null ? t("no_response") : ms + " ms";
  } catch {}
}

function engineParams() {
  const streamApp = document.getElementById("streamExe").value.trim();
  const keep = new Map();
  for (const n of [...(settings.keepApps || []), streamApp, "cs2.exe"]) {
    const v = (n || "").trim();
    if (v) keep.set(v.toLowerCase(), v);
  }
  return {
    reserveMbps: parseFloat(document.getElementById("reserveInput").value) || 0,
    whitelist: [...keep.values()],
    streamApp,
  };
}

async function setEngine(on) {
  const msg = document.getElementById("reserveMsg");
  if (!invoke) return;
  const p = engineParams();
  settings.stream_exe = p.streamApp;
  try {
    const res = await invoke("set_engine_active", {
      active: on,
      reserveMbps: p.reserveMbps,
      whitelist: p.whitelist,
      streamApp: p.streamApp,
      closeOthers: !!settings.closeOthers,
    });
    msg.textContent = on ? t(res.status === "armed" ? "engine_armed" : "engine_on") : t("engine_off");
    if (on && res.closed && res.closed.length) showClosed(res.closed);
    if (on) setTimeout(() => void refreshPrograms(), 1500);
  } catch (e) {
    msg.textContent = t("error_prefix") + e;
  }
}

document.getElementById("engineToggle").addEventListener("change", (e) => {
  settings.active = e.target.checked;
  saveSettings();
  void setEngine(settings.active);
});

document.getElementById("applyReserve").addEventListener("click", async () => {
  const msg = document.getElementById("reserveMsg");
  if (!invoke) {
    msg.textContent = t("reserve_preview");
    return;
  }
  // موتور روشن است؟ اعمال = تازه‌سازی پارامترهای همان موتور.
  if (settings.active) {
    await setEngine(true);
    return;
  }
  const reserveMbps = parseFloat(document.getElementById("reserveInput").value) || 0;
  const streamExe = document.getElementById("streamExe").value.trim();
  msg.textContent = t("applying");
  try {
    const rep = await invoke("apply_stream_reserve", {
      reserveMbps,
      whitelist: engineParams().whitelist,
    });
    msg.textContent = fill(t("reserve_done"), {
      total: fmt(rep.total_up_kbps),
      count: rep.capped.length,
      reserve: fmt(rep.reserve_kbps),
    });
  } catch (e) {
    msg.textContent = t("error_prefix") + e;
  }
});

document.getElementById("clearCaps").addEventListener("click", async () => {
  if (!invoke) return;
  if (settings.active) {
    settings.active = false;
    document.getElementById("engineToggle").checked = false;
    saveSettings();
    await setEngine(false);
    return;
  }
  await invoke("clear_all_caps");
  document.getElementById("reserveMsg").textContent = t("caps_cleared");
});

// ---------- ناوبری پنج نما: برنامه‌ها / اسکن / رله / راهنما / تنظیمات ----------
function showView(which) {
  document.getElementById("viewMain").classList.toggle("hidden", which !== "main");
  document.getElementById("viewScan").classList.toggle("hidden", which !== "scan");
  document.getElementById("viewRelay").classList.toggle("hidden", which !== "relay");
  document.getElementById("viewGuide").classList.toggle("hidden", which !== "guide");
  document.getElementById("viewSettings").classList.toggle("hidden", which !== "settings");
  document.getElementById("navMain").classList.toggle("active", which === "main");
  document.getElementById("navScan").classList.toggle("active", which === "scan");
  document.getElementById("navRelay").classList.toggle("active", which === "relay");
  document.getElementById("navGuide").classList.toggle("active", which === "guide");
  document.getElementById("navSettings").classList.toggle("active", which === "settings");
}
document.getElementById("navMain").addEventListener("click", () => showView("main"));
document.getElementById("navScan").addEventListener("click", () => showView("scan"));
document.getElementById("navRelay").addEventListener("click", () => showView("relay"));
document.getElementById("navGuide").addEventListener("click", () => showView("guide"));
document.getElementById("navSettings").addEventListener("click", () => showView("settings"));

// ---------- رله‌ی تطبیقی: شروع/توقف + وضعیت زنده (پولینگ ۲ ثانیه‌ای) ----------
const RELAY_TARGET_KEY = "lagslice.relayTarget";
let relayTimer = null;
let relayRunning = false;

function loadRelayTarget() {
  try {
    const raw = localStorage.getItem(RELAY_TARGET_KEY);
    if (raw) {
      const d = JSON.parse(raw);
      if (d && typeof d === "object") {
        if (d.url) document.getElementById("relayTarget").value = d.url;
        if (d.key) document.getElementById("relayKey").value = d.key;
        if (d.top) document.getElementById("relayTop").value = d.top;
      }
    }
  } catch {}
}

function renderRelayStatus(s) {
  const fmtMB = (b) => (b / 1048576).toFixed(1) + " MB";
  document.getElementById("relayState").textContent = s.running
    ? t("relay_running")
    : t("relay_stopped");
  document.getElementById("relayRung").textContent = s.running
    ? s.current_kbps + " Kbps" + (s.at_top ? " (" + t("relay_at_top") + ")" : "")
    : "—";
  document.getElementById("relayCap").textContent = s.running
    ? Math.round(s.capacity_ema_kbps) + " Kbps"
    : "—";
  document.getElementById("relayProbe").textContent = s.running && s.probe_kbps > 0
    ? Math.round(s.probe_kbps) + " Kbps"
    : "—";
  document.getElementById("relayStats").textContent = s.running
    ? fmtMB(s.forwarded_bytes) + " / " + s.dropped_gops + " GOP / " + Math.round(s.queue_bytes / 1024) + " KB"
    : "—";
  document.getElementById("relayError").textContent = s.last_error || "";
  document.getElementById("relayStart").disabled = !!s.running;
  document.getElementById("relayStop").disabled = !s.running;
}

async function pollRelayStatus() {
  try {
    const s = await invoke("relay_status");
    relayRunning = !!s.running;
    renderRelayStatus(s);
    if (!s.running && relayTimer) {
      clearInterval(relayTimer);
      relayTimer = null;
    }
  } catch (e) {
    document.getElementById("relayError").textContent = String(e);
  }
}

document.getElementById("relayStart").addEventListener("click", async () => {
  const url = document.getElementById("relayTarget").value.trim();
  const key = document.getElementById("relayKey").value;
  const topMbps = parseFloat(document.getElementById("relayTop").value);
  if (!url.startsWith("rtmp://")) {
    document.getElementById("relayMsg").textContent = t("relay_err_url");
    return;
  }
  if (!key.trim()) {
    document.getElementById("relayMsg").textContent = t("relay_err_key");
    return;
  }
  const topKbps = Math.round((isNaN(topMbps) ? 8 : topMbps) * 1000);
  try {
    await invoke("relay_start", { targetUrl: url, streamKey: key, topKbps });
    try {
      localStorage.setItem(RELAY_TARGET_KEY, JSON.stringify({ url, key, top: topMbps }));
    } catch {}
    document.getElementById("relayMsg").textContent = t("relay_started");
    relayRunning = true;
    if (relayTimer) clearInterval(relayTimer);
    relayTimer = setInterval(pollRelayStatus, 2000);
    pollRelayStatus();
  } catch (e) {
    document.getElementById("relayMsg").textContent = String(e);
  }
});

document.getElementById("relayStop").addEventListener("click", async () => {
  try {
    await invoke("relay_stop");
  } catch (e) {
    document.getElementById("relayMsg").textContent = String(e);
  }
  relayRunning = false;
  if (relayTimer) {
    clearInterval(relayTimer);
    relayTimer = null;
  }
  document.getElementById("relayMsg").textContent = t("relay_stopped_msg");
  pollRelayStatus();
});

loadRelayTarget();
pollRelayStatus();

// ---------- زبان و تم ----------
function applyLang() {
  document.documentElement.lang = settings.lang;
  document.documentElement.dir = settings.lang === "fa" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPh);
  });
  const themeSel = document.getElementById("setTheme");
  themeSel.options[0].textContent = t("theme_lagslice");
  themeSel.options[1].textContent = t("theme_neon_purple");
  themeSel.options[2].textContent = t("theme_ice_blue");
  document.getElementById("aboutText").style.direction = settings.lang === "fa" ? "rtl" : "ltr";
  refreshPing();
  refreshRates();
  if (scanLoaded) renderScan();
}

function applyTheme() {
  document.body.dataset.theme = settings.theme;
}

// ---------- فرم تنظیمات ----------
function fillSettingsForm() {
  document.getElementById("setServers").value = settings.servers.join(", ");
  document.getElementById("setBitrate").value = settings.bitrate_mbps;
  document.getElementById("setPingEnabled").checked = !!settings.ping_enabled;
  document.getElementById("setLang").value = settings.lang;
  document.getElementById("setTheme").value = settings.theme;
  document.getElementById("setTray").checked = !!settings.tray;
  document.getElementById("reserveInput").value = settings.bitrate_mbps;
}

document.getElementById("saveSettings").addEventListener("click", () => {
  const servers = document
    .getElementById("setServers")
    .value.split(/[,،]/)
    .map((s) => s.trim())
    .filter(Boolean);
  settings.servers = servers.length ? servers : ["8.8.8.8"];
  const bitrate = parseFloat(document.getElementById("setBitrate").value);
  settings.bitrate_mbps = isNaN(bitrate) ? 8.0 : Math.min(50, Math.max(1, bitrate));
  settings.ping_enabled = document.getElementById("setPingEnabled").checked;
  saveSettings();
  document.getElementById("reserveInput").value = settings.bitrate_mbps;
  document.getElementById("settingsMsg").textContent = t("settings_saved");
  refreshPing();
});

document.getElementById("setLang").addEventListener("change", (e) => {
  settings.lang = e.target.value === "en" ? "en" : "fa";
  saveSettings();
  applyLang();
});

document.getElementById("setTheme").addEventListener("change", (e) => {
  settings.theme = e.target.value;
  saveSettings();
  applyTheme();
});

function pushTraySetting() {
  if (invoke) invoke("set_close_to_tray", { enabled: !!settings.tray }).catch(() => {});
}

document.getElementById("setTray").addEventListener("change", (e) => {
  settings.tray = e.target.checked;
  saveSettings();
  pushTraySetting();

// موتور محدودیت: وضعیت سوییچ و برنامه‌ی استریم را برگردان و اگر روشن
// مانده بود، بعد از گرم‌شدن اندازه‌گیری خودش دوباره فعالش کن.
if (settings.stream_exe) document.getElementById("streamExe").value = settings.stream_exe;
document.getElementById("engineToggle").checked = !!settings.active;
if (settings.active && invoke) {
  setTimeout(() => void setEngine(true), 2500);
}
});

document.getElementById("openGuide").addEventListener("click", () => {
  showView("guide");
});

// ---------- همه‌ی برنامه‌ها: انتخاب (مجاز)، سقف و بستن انتخاب‌نشده‌ها ----------
let progRows = [];

function showClosed(names) {
  const el = document.getElementById("closedLog");
  if (!el || !names.length) return;
  const prev = el.textContent ? el.textContent + "‏، " : t("closed_apps");
  el.textContent = prev + names.join("‏، ");
}

function progEntries() {
  const caps = settings.manualCaps || {};
  const live = (progRows || []).map((p) => ({ ...p, running: true }));
  const liveNames = new Set(live.map((p) => p.name.toLowerCase()));
  const saved = [];
  const seen = new Set();
  for (const n of [...(settings.keepApps || []), ...Object.keys(caps)]) {
    const key = String(n).toLowerCase();
    if (liveNames.has(key) || seen.has(key)) continue;
    seen.add(key);
    saved.push({ name: n, path: "", pid_count: 0, network: false, running: false });
  }
  const keep = new Set((settings.keepApps || []).map((x) => String(x).toLowerCase()));
  return [...live, ...saved].sort((a, b) => {
    const ka = keep.has(a.name.toLowerCase()) ? 0 : 1;
    const kb = keep.has(b.name.toLowerCase()) ? 0 : 1;
    if (ka !== kb) return ka - kb;
    if (a.running !== b.running) return a.running ? -1 : 1;
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });
}

function renderPrograms() {
  const list = document.getElementById("progList");
  if (!list) return;
  const q = (document.getElementById("progSearch").value || "").trim().toLowerCase();
  const keep = new Set((settings.keepApps || []).map((x) => String(x).toLowerCase()));
  const caps = settings.manualCaps || {};
  const all = progEntries().filter(
    (r) => !q || r.name.toLowerCase().includes(q) || (r.path || "").toLowerCase().includes(q)
  );
  if (!all.length) {
    list.innerHTML = `<p class="hint">${esc(t("prog_empty"))}</p>`;
    return;
  }
  list.innerHTML = all
    .map((r) => {
      const key = r.name.toLowerCase();
      const checked = keep.has(key) ? "checked" : "";
      const capVal = caps[r.name] ?? caps[key] ?? "";
      const badges = [
        `<span class="badge ${r.running ? "run" : "off"}">${esc(t(r.running ? "prog_running" : "prog_not_running"))}</span>`,
        r.network ? `<span class="badge net">${esc(t("prog_traffic"))}</span>` : "",
      ].join(" ");
      const removeBtn = r.running
        ? ""
        : `<button data-act="remove" data-exe="${esc(r.name)}">${esc(t("prog_remove"))}</button>`;
      return `<div class="prog-row">
        <label><input type="checkbox" data-act="keep" data-exe="${esc(r.name)}" ${checked}> <span class="prog-name">${esc(r.name)}</span></label>
        ${badges}
        <span class="prog-path">${esc(r.path || "")}</span>
        <input class="cap-input" type="number" min="64" step="64" placeholder="Kbps" data-exe="${esc(r.name)}" value="${esc(String(capVal))}">
        <button data-act="cap" data-exe="${esc(r.name)}">${esc(t("cap_apply"))}</button>
        ${removeBtn}
      </div>`;
    })
    .join("");
}

async function pushKeepApps() {
  if (!invoke || !settings.active) return;
  try {
    await invoke("set_keep_apps", { whitelist: engineParams().whitelist });
  } catch {}
}

async function refreshPrograms() {
  if (invoke) {
    try {
      progRows = await invoke("list_programs");
    } catch {}
  }
  // وسط تایپ کاربر در پنل، رندر را نگه دار تا فوکوس نپرد.
  const list = document.getElementById("progList");
  if (list && list.contains(document.activeElement) && document.activeElement.classList.contains("cap-input")) return;
  renderPrograms();
}

document.getElementById("progList").addEventListener("change", async (e) => {
  const el = e.target;
  if (el.dataset.act !== "keep") return;
  const exe = el.dataset.exe;
  const key = exe.toLowerCase();
  settings.keepApps = (settings.keepApps || []).filter((x) => String(x).toLowerCase() !== key);
  if (el.checked) settings.keepApps.push(exe);
  saveSettings();
  await pushKeepApps();
  renderPrograms();
});

document.getElementById("progList").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const exe = btn.dataset.exe;
  const key = exe.toLowerCase();
  if (btn.dataset.act === "cap") {
    const input = document.querySelector(`.prog-row .cap-input[data-exe="${CSS.escape(exe)}"]`);
    const val = parseFloat(input ? input.value : "");
    if (!settings.manualCaps) settings.manualCaps = {};
    if (isNaN(val)) delete settings.manualCaps[exe];
    else settings.manualCaps[exe] = val;
    saveSettings();
    if (invoke) await invoke("set_app_cap", { exe, capKbps: isNaN(val) ? null : val }).catch(() => {});
  } else if (btn.dataset.act === "remove") {
    settings.keepApps = (settings.keepApps || []).filter((x) => String(x).toLowerCase() !== key);
    if (settings.manualCaps) delete settings.manualCaps[exe];
    saveSettings();
    if (invoke) await invoke("set_app_cap", { exe, capKbps: null }).catch(() => {});
    await pushKeepApps();
    renderPrograms();
  }
});

document.getElementById("progSearch").addEventListener("input", renderPrograms);
document.getElementById("progRefresh").addEventListener("click", () => void refreshPrograms());
document.getElementById("progAdd").addEventListener("click", async () => {
  if (!invoke) return;
  const path = await invoke("pick_program_file").catch(() => null);
  if (!path) return;
  const name = String(path).split(/[\\/]/).pop();
  if (!name) return;
  const key = name.toLowerCase();
  if (!(settings.keepApps || []).some((x) => String(x).toLowerCase() === key)) {
    settings.keepApps = [...(settings.keepApps || []), name];
    saveSettings();
  }
  await pushKeepApps();
  await refreshPrograms();
});

const closeOthersEl = document.getElementById("closeOthers");
closeOthersEl.checked = !!settings.closeOthers;
closeOthersEl.addEventListener("change", () => {
  settings.closeOthers = closeOthersEl.checked;
  saveSettings();
});

setInterval(() => void refreshPrograms(), 15000);
// گزارش بستن‌های دوره‌ای موتور (جارو) — هر ۵ ثانیه خوانده می‌شود.
setInterval(async () => {
  if (!invoke || !settings.active) return;
  const names = await invoke("take_closed_log").catch(() => null);
  if (names && names.length) showClosed(names);
}, 5000);
void refreshPrograms();


// ---------- موتور آپدیت v2 (فید ثابت + دانلود قابل‌ادامه + هلپر نصب) ----------
// دقیقاً مدل شیرین‌حساب: check_update2 ← download_update2 (رویداد پیشرفت
// update-progress2، کنسل با نگه‌داشتن ‎.part‎) ← apply_update2 (هلپر + ری‌استارت).
const tauriEvent = window.__TAURI__?.event;
let updInfo = null;
let updDownloading = false;

const updMsg = () => document.getElementById("updateMsg");
const updEl = (id) => document.getElementById(id);

function updSize(bytes) {
  if (!bytes) return "";
  return bytes >= 1048576 ? (bytes / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1024)) + " KB";
}

function updShowReady() {
  updEl("downloadUpdate").classList.add("hidden");
  updEl("cancelDownload").classList.add("hidden");
  updEl("applyUpdate").classList.remove("hidden");
  updEl("updateProgress").classList.add("hidden");
}

async function updDownload() {
  if (!invoke || updDownloading) return;
  updDownloading = true;
  updEl("downloadUpdate").classList.add("hidden");
  updEl("applyUpdate").classList.add("hidden");
  updEl("cancelDownload").classList.remove("hidden");
  updEl("updateProgress").classList.remove("hidden");
  updMsg().textContent = fill(t("upd_downloading"), { pct: 0 });
  try {
    await invoke("download_update2");
    updShowReady();
  } catch (e) {
    updMsg().textContent = t("error_prefix") + e;
    updEl("cancelDownload").classList.add("hidden");
    updEl("updateProgress").classList.add("hidden");
    if (updInfo) updEl("downloadUpdate").classList.remove("hidden");
  } finally {
    updDownloading = false;
  }
}

async function updCheck(manual) {
  if (!invoke) return;
  if (manual) updMsg().textContent = t("update_checking");
  try {
    const info = await invoke("check_update2");
    if (!info) {
      if (manual) updMsg().textContent = fill(t("update_latest"), { ver: APP_VERSION });
      return;
    }
    updInfo = info;
    updMsg().textContent =
      fill(t("upd_available2"), { ver: info.version, size: updSize(info.size) }) +
      (info.mandatory ? " " + t("upd_mandatory") : "");
    const notes = updEl("updateNotes");
    if (info.notes_fa) {
      notes.textContent = info.notes_fa;
      notes.classList.remove("hidden");
    }
    if (settings.updateMode === "auto" && !manual) {
      updDownload();
    } else {
      updEl("downloadUpdate").classList.remove("hidden");
    }
  } catch {
    if (manual) updMsg().textContent = t("update_err");
  }
}

document.getElementById("checkUpdate").addEventListener("click", () => updCheck(true));

document.getElementById("downloadUpdate").addEventListener("click", updDownload);

document.getElementById("cancelDownload").addEventListener("click", async () => {
  if (invoke) await invoke("cancel_update_download2").catch(() => {});
});

document.getElementById("applyUpdate").addEventListener("click", async () => {
  if (!invoke) return;
  updMsg().textContent = t("upd_installing");
  try {
    await invoke("apply_update2");
  } catch (e) {
    updMsg().textContent = t("error_prefix") + e;
  }
});

document.getElementById("pickUpdateFile").addEventListener("click", async () => {
  if (!invoke) return;
  try {
    const path = await invoke("open_update_file_dialog");
    if (!path) return;
    updMsg().textContent = t("upd_installing");
    await invoke("apply_local_update", { path });
  } catch (e) {
    updMsg().textContent = t("error_prefix") + e;
  }
});

document.getElementById("updateMode").addEventListener("change", (e) => {
  settings.updateMode = e.target.value;
  saveSettings();
});

if (tauriEvent?.listen) {
  tauriEvent.listen("update-progress2", (ev) => {
    const p = ev.payload || {};
    const bar = updEl("updateProgress");
    if (bar) {
      bar.classList.remove("hidden");
      bar.firstElementChild.style.width = (p.percent || 0) + "%";
    }
    if (updDownloading) updMsg().textContent = fill(t("upd_downloading"), { pct: p.percent || 0 });
  });
}

// گزارش آپدیت قبلی + چک خودکار بر اساس حالت انتخابی (۱۵ ثانیه بعد از اجرا؛
// حالت auto هر ۶ ساعت دوباره و دانلود بی‌صدا).
async function updStartup() {
  if (!invoke) return;
  updEl("updateMode").value = settings.updateMode || "notify";
  try {
    const report = await invoke("get_update_report");
    if (report?.status === "ok") {
      updMsg().textContent = fill(t("upd_applied_ok"), { prev: report.prev_version, new: report.new_version });
      if (report.changelog) {
        const notes = updEl("updateNotes");
        notes.textContent = report.changelog;
        notes.classList.remove("hidden");
      }
    } else if (report && report.status !== "ok") {
      updMsg().textContent = fill(t("upd_applied_fail"), { detail: report.detail || report.status });
    }
  } catch {}
  if (settings.updateMode === "off") return;
  setTimeout(() => updCheck(false), 15000);
  if (settings.updateMode === "auto") setInterval(() => updCheck(false), 6 * 3600 * 1000);
}

// ---------- اسکنر سرورهای استریم (StreamScanner) ----------
let scanList = [];
let scanResults = {};
let scanLoaded = false;
let activeServerId = localStorage.getItem("lagslice.activeServerId") || "";
const SERVERS_PREVIEW_KEY = "lagslice.servers.preview";

// تجزیه‌ی لینک RTMP در پیش‌نمایش مرورگر (در برنامه از هسته‌ی Rust می‌آید).
function parseLinkPreview(text) {
  const m = String(text || "").trim().replace(/^rtmps?:\/\//i, "");
  const authority = m.split("/")[0];
  const [host, port] = authority.split(":");
  return { host: (host || "").toLowerCase(), port: parseInt(port, 10) || 1935 };
}

async function parseServerLink(text) {
  if (invoke) {
    try {
      return await invoke("parse_server_link", { text });
    } catch {}
  }
  const { host, port } = parseLinkPreview(text);
  return { id: "s" + Date.now().toString(36), name: host ? host.split(".")[0].toUpperCase() : "", region: "", host, port };
}

// با وارد کردن لینک، نام و منطقه و هاست و پورت خودکار پر می‌شوند.
let linkTimer = null;
document.getElementById("scanLink").addEventListener("input", (e) => {
  clearTimeout(linkTimer);
  const text = e.target.value.trim();
  if (!text) return;
  linkTimer = setTimeout(async () => {
    const s = await parseServerLink(text);
    if (!s.host) return;
    document.getElementById("scanHost").value = s.host;
    document.getElementById("scanPort").value = s.port || 1935;
    if (s.name) document.getElementById("scanName").value = s.name;
    if (s.region) document.getElementById("scanRegion").value = s.region;
  }, 350);
});

async function loadScanServers() {
  try {
    if (invoke) {
      scanList = await invoke("get_servers");
    } else {
      const raw = localStorage.getItem(SERVERS_PREVIEW_KEY);
      scanList = raw ? JSON.parse(raw) : [{ id: "ms1", name: "MasterStream 1", region: "ir", host: "", port: 1935 }];
    }
  } catch {}
  if (!Array.isArray(scanList)) scanList = [];
  scanLoaded = true;
  renderScan();
}

async function persistScanServers() {
  try {
    if (invoke) {
      scanList = await invoke("set_servers", { servers: scanList });
    } else {
      localStorage.setItem(SERVERS_PREVIEW_KEY, JSON.stringify(scanList));
    }
  } catch (e) {
    document.getElementById("scanMsg").textContent = t("error_prefix") + e;
  }
  renderScan();
}

function renderScan() {
  const body = document.getElementById("scanBody");
  if (!body) return;
  const banner = document.getElementById("bestBanner");
  if (!scanList.length) {
    body.innerHTML = `<tr><td colspan="9" class="empty">${esc(t("scan_empty"))}</td></tr>`;
    banner.textContent = "";
    return;
  }
  const rows = scanList.map((s) => ({ s, r: scanResults[s.id] || null }));
  rows.sort((a, b) => (a.r ? a.r.score : Infinity) - (b.r ? b.r.score : Infinity));
  const best = rows.find((x) => x.r && x.r.ok);
  body.innerHTML = rows
    .map(({ s, r }) => {
      const url = s.host ? `rtmp://${s.host}:${s.port || 1935}/live` : "—";
      const isBest = !!(best && r && r.id === best.r.id);
      return `<tr${isBest ? ' class="best-row"' : ""}>
        <td>${esc(s.name || "—")}${s.region ? ` <span class="dim">(${esc(s.region)})</span>` : ""}${s.id === activeServerId ? ` <span class="active-badge">⭐ ${esc(t("scan_active"))}</span>` : ""}</td>
        <td dir="ltr">${esc(url)}</td>
        <td>${r && r.ping_ms != null ? r.ping_ms.toFixed(0) : "—"}</td>
        <td>${r ? r.loss.toFixed(0) + "%" : "—"}</td>
        <td>${r && r.tcp_ms != null ? r.tcp_ms.toFixed(0) : "—"}</td>
        <td>${r && r.ok ? r.score.toFixed(0) : "—"}</td>
        <td>${r ? (r.ok ? `<span class="status-ok">${esc(t("scan_ok"))}</span>` : `<span class="status-down">${esc(t("scan_down"))}</span>`) : "—"}</td>
        <td><button class="use-btn" data-id="${esc(s.id)}">${esc(t("scan_use"))}</button></td>
        <td><button class="del-btn" data-id="${esc(s.id)}">${esc(t("scan_del"))}</button></td>
      </tr>`;
    })
    .join("");
  banner.textContent = best
    ? fill(t("scan_best"), { name: best.s.name || best.s.host, url: `rtmp://${best.s.host}:${best.s.port || 1935}/live` })
    : "";
  body.querySelectorAll(".del-btn").forEach((btn) =>
    btn.addEventListener("click", async () => {
      scanList = scanList.filter((x) => x.id !== btn.dataset.id);
      delete scanResults[btn.dataset.id];
      await persistScanServers();
    })
  );
  body.querySelectorAll(".use-btn").forEach((btn) =>
    btn.addEventListener("click", () => {
      const s = scanList.find((x) => x.id === btn.dataset.id);
      if (!s || !s.host) return;
      settings.servers = [s.host];
      saveSettings();
      fillSettingsForm();
      refreshPing();
      document.getElementById("scanMsg").textContent = fill(t("scan_use_done"), { host: s.host });
    })
  );
}

document.getElementById("addServer").addEventListener("click", async () => {
  const msg = document.getElementById("scanMsg");
  const link = document.getElementById("scanLink").value.trim();
  let host = document.getElementById("scanHost").value.trim();
  let name = document.getElementById("scanName").value.trim();
  let region = document.getElementById("scanRegion").value.trim();
  let port = parseInt(document.getElementById("scanPort").value, 10);
  let id = "s" + Date.now().toString(36);
  // اگر لینک داده شده، مشخصات از روی لینک کامل می‌شوند (نام/منطقه خودکار).
  if (link) {
    const s = await parseServerLink(link);
    if (s.host) {
      host = s.host;
      port = s.port || 1935;
      id = s.id || id;
      if (!name) name = s.name;
      if (!region) region = s.region;
    }
  }
  if (!host) {
    msg.textContent = t("scan_need_host");
    return;
  }
  scanList.push({
    id,
    name: name || host,
    region,
    host,
    port: isNaN(port) ? 1935 : Math.min(65535, Math.max(1, port)),
  });
  document.getElementById("scanHost").value = "";
  document.getElementById("scanLink").value = "";
  msg.textContent = "";
  await persistScanServers();
});

document.getElementById("importBulk").addEventListener("click", async () => {
  const text = document.getElementById("scanBulk").value;
  const msg = document.getElementById("scanMsg");
  if (!text.trim()) return;
  try {
    let outcome;
    if (invoke) {
      outcome = await invoke("import_server_links", { text, existing: scanList });
    } else {
      const seen = new Set(scanList.map((s) => `${s.host.toLowerCase()}:${s.port}`));
      const added = [];
      for (const line of text.split(/\n+/)) {
        const p = parseLinkPreview(line.includes("|") ? line.split("|")[1] : line);
        if (!p.host || seen.has(`${p.host}:${p.port}`)) continue;
        seen.add(`${p.host}:${p.port}`);
        added.push({ id: "s" + Date.now().toString(36) + added.length, name: (line.includes("|") ? line.split("|")[0].trim() : "") || p.host, region: "", host: p.host, port: p.port });
      }
      outcome = { added, count: added.length };
    }
    if (outcome.added.length) {
      scanList = scanList.concat(outcome.added);
      await persistScanServers();
    }
    msg.textContent = fill(t("scan_imported"), { count: outcome.count });
    document.getElementById("scanBulk").value = "";
  } catch (e) {
    msg.textContent = t("error_prefix") + e;
  }
});

// انتخاب بهترین سرور: بهترین نتیجه‌ی اسکن (کمترین امتیازِ سالم) سرور
// فعال می‌شود و به‌عنوان سرور پینگ/استریم برنامه تنظیم می‌گردد.
document.getElementById("pickBest").addEventListener("click", () => {
  const msg = document.getElementById("scanMsg");
  const rows = scanList
    .map((s) => ({ s, r: scanResults[s.id] }))
    .filter((x) => x.r && x.r.ok)
    .sort((a, b) => a.r.score - b.r.score);
  if (!rows.length) {
    msg.textContent = t("scan_no_best");
    return;
  }
  const best = rows[0].s;
  activeServerId = best.id;
  localStorage.setItem("lagslice.activeServerId", activeServerId);
  settings.servers = [best.host];
  saveSettings();
  fillSettingsForm();
  refreshPing();
  msg.textContent = fill(t("scan_best"), { name: best.name || best.host, url: `rtmp://${best.host}:${best.port || 1935}/live` });
  renderScan();
});

document.getElementById("runScan").addEventListener("click", async () => {
  const btn = document.getElementById("runScan");
  const msg = document.getElementById("scanMsg");
  if (!scanList.length) return;
  btn.disabled = true;
  msg.textContent = t("scanning");
  try {
    let results;
    if (invoke) {
      results = await invoke("scan_servers", { servers: scanList });
    } else {
      results = scanList.map((s) => {
        const ping = 20 + Math.random() * 40;
        const tcp = 30 + Math.random() * 60;
        const ok = !!s.host;
        return { id: s.id, ping_ms: ping, loss: 0, tcp_ms: tcp, ok, score: ok ? tcp + ping * 0.3 : 1000000 };
      });
    }
    scanResults = {};
    for (const r of results) scanResults[r.id] = r;
    msg.textContent = "";
  } catch (e) {
    msg.textContent = t("error_prefix") + e;
  }
  btn.disabled = false;
  renderScan();
});

// ---------- شروع ----------
fillSettingsForm();
applyTheme();
applyLang();
pushTraySetting();
updStartup();
loadScanServers();
refreshRates();
refreshPing();
setInterval(refreshRates, 1000);
setInterval(refreshPing, 5000);
