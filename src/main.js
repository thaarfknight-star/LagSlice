// فرانت LagSlice — داده‌ی زنده از هسته‌ی Rust از طریق IPC تائوری می‌آید.
// بیرون از تائوری (پیش‌نمایش مرورگر) داده‌ی نمونه نشان داده می‌شود.
const invoke = window.__TAURI__?.core?.invoke;

const APP_VERSION = "0.4.0";
const SETTINGS_KEY = "lagslice.settings.v1";

// پیش‌فرض‌ها دقیقاً مثل load_config نسخه‌ی پایتون.
const DEFAULT_SETTINGS = {
  servers: ["8.8.8.8"],
  bitrate_mbps: 8.0,
  lang: "fa",
  ping_enabled: true,
  theme: "lagslice",
  tray: false,
  mode: "stream",
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const data = JSON.parse(raw);
      if (data && typeof data === "object") {
        const cfg = { ...DEFAULT_SETTINGS, ...data };
        if (!["fa", "en"].includes(cfg.lang)) cfg.lang = "fa";
        if (!["lagslice", "neon_purple", "ice_blue"].includes(cfg.theme)) cfg.theme = "lagslice";
        if (!Array.isArray(cfg.servers) || !cfg.servers.length) cfg.servers = ["8.8.8.8"];
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
    nav_settings: "تنظیمات",
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
    set_sec_contact: "💬 پشتیبانی",
    set_telegram_btn: "باز کردن در تلگرام @tha_arf",
    set_sec_help: "📖 راهنما",
    set_open_guide: "باز کردن فایل راهنما",
    guide_missing: "فایل راهنما (LagSlice-guide-fa.pdf) هنوز به نسخه‌ی Rust اضافه نشده است.",
    set_sec_about: "ℹ درباره / لایسنس",
    set_sec_update: "🔄 به‌روزرسانی",
    set_update_check: "بررسی به‌روزرسانی",
    update_checking: "در حال بررسی…",
    update_latest: "نسخه‌ی شما ({ver}) به‌روز است ✅",
    update_available: "نسخه‌ی تازه موجود است: {ver} — از ریپوی گیت‌هاب بگیرید.",
    update_err: "بررسی به‌روزرسانی ناموفق بود (اتصال/پاسخ گیت‌هاب).",
  },
  en: {
    subtitle: "Bandwidth management between game and stream",
    total_up: "Total upload",
    ping_label: "Server ping",
    nav_main: "Apps",
    nav_settings: "Settings",
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
    set_sec_contact: "💬 Support",
    set_telegram_btn: "Open in Telegram @tha_arf",
    set_sec_help: "📖 Guide",
    set_open_guide: "Open guide file",
    guide_missing: "The guide file (LagSlice-guide-fa.pdf) has not been added to the Rust build yet.",
    set_sec_about: "ℹ About / License",
    set_sec_update: "🔄 Updates",
    set_update_check: "Check for updates",
    update_checking: "Checking…",
    update_latest: "You are up to date ({ver}) ✅",
    update_available: "A new version is available: {ver} — get it from the GitHub repo.",
    update_err: "Update check failed (GitHub connection/response).",
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

document.getElementById("applyReserve").addEventListener("click", async () => {
  const msg = document.getElementById("reserveMsg");
  if (!invoke) {
    msg.textContent = t("reserve_preview");
    return;
  }
  const reserveMbps = parseFloat(document.getElementById("reserveInput").value) || 0;
  const streamExe = document.getElementById("streamExe").value.trim();
  msg.textContent = t("applying");
  try {
    const rep = await invoke("apply_stream_reserve", {
      reserveMbps,
      whitelist: [streamExe, "cs2.exe"],
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
  await invoke("clear_all_caps");
  document.getElementById("reserveMsg").textContent = t("caps_cleared");
});

// ---------- ناوبری دو نما: برنامه‌ها / تنظیمات ----------
function showView(which) {
  document.getElementById("viewMain").classList.toggle("hidden", which !== "main");
  document.getElementById("viewSettings").classList.toggle("hidden", which !== "settings");
  document.getElementById("navMain").classList.toggle("active", which === "main");
  document.getElementById("navSettings").classList.toggle("active", which === "settings");
}
document.getElementById("navMain").addEventListener("click", () => showView("main"));
document.getElementById("navSettings").addEventListener("click", () => showView("settings"));

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

document.getElementById("setTray").addEventListener("change", (e) => {
  settings.tray = e.target.checked;
  saveSettings();
});

document.getElementById("openGuide").addEventListener("click", () => {
  document.getElementById("guideMsg").textContent = t("guide_missing");
});

// بررسی دستی به‌روزرسانی از ریلیزهای گیت‌هاب (مثل show_update نسخه‌ی پایتون).
document.getElementById("checkUpdate").addEventListener("click", async () => {
  const msg = document.getElementById("updateMsg");
  msg.textContent = t("update_checking");
  try {
    const res = await fetch("https://api.github.com/repos/thaarfknight-star/LagSlice/releases/latest", {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!res.ok) throw new Error(String(res.status));
    const rel = await res.json();
    const latest = String(rel.tag_name || "").replace(/^v/, "");
    if (!latest) throw new Error("no tag");
    msg.textContent =
      latest === APP_VERSION
        ? fill(t("update_latest"), { ver: APP_VERSION })
        : fill(t("update_available"), { ver: latest });
  } catch {
    msg.textContent = t("update_err");
  }
});

// ---------- شروع ----------
fillSettingsForm();
applyTheme();
applyLang();
refreshRates();
refreshPing();
setInterval(refreshRates, 1000);
setInterval(refreshPing, 5000);
