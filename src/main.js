// فرانت LagSlice — داده‌ی زنده از هسته‌ی Rust از طریق IPC تائوری می‌آید.
// بیرون از تائوری (پیش‌نمایش مرورگر) داده‌ی نمونه نشان داده می‌شود.
const invoke = window.__TAURI__?.core?.invoke;

const APP_VERSION = "0.5.0";
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
    nav_scan: "اسکن سرورها",
    nav_settings: "تنظیمات",
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
    nav_scan: "Server scan",
    nav_settings: "Settings",
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

// ---------- ناوبری سه نما: برنامه‌ها / اسکن سرورها / تنظیمات ----------
function showView(which) {
  document.getElementById("viewMain").classList.toggle("hidden", which !== "main");
  document.getElementById("viewScan").classList.toggle("hidden", which !== "scan");
  document.getElementById("viewSettings").classList.toggle("hidden", which !== "settings");
  document.getElementById("navMain").classList.toggle("active", which === "main");
  document.getElementById("navScan").classList.toggle("active", which === "scan");
  document.getElementById("navSettings").classList.toggle("active", which === "settings");
}
document.getElementById("navMain").addEventListener("click", () => showView("main"));
document.getElementById("navScan").addEventListener("click", () => showView("scan"));
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
    const latest = String(rel.tag_name || "").replace(/^lagslice-rs-v/, "").replace(/^v/, "");
    if (!latest) throw new Error("no tag");
    msg.textContent =
      latest === APP_VERSION
        ? fill(t("update_latest"), { ver: APP_VERSION })
        : fill(t("update_available"), { ver: latest });
  } catch {
    msg.textContent = t("update_err");
  }
});

// ---------- اسکنر سرورهای استریم (StreamScanner) ----------
let scanList = [];
let scanResults = {};
let scanLoaded = false;
const SERVERS_PREVIEW_KEY = "lagslice.servers.preview";

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
        <td>${esc(s.name || "—")}${s.region ? ` <span class="dim">(${esc(s.region)})</span>` : ""}</td>
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
  const host = document.getElementById("scanHost").value.trim();
  const msg = document.getElementById("scanMsg");
  if (!host) {
    msg.textContent = t("scan_need_host");
    return;
  }
  const port = parseInt(document.getElementById("scanPort").value, 10);
  scanList.push({
    id: "s" + Date.now().toString(36),
    name: document.getElementById("scanName").value.trim() || host,
    region: document.getElementById("scanRegion").value.trim(),
    host,
    port: isNaN(port) ? 1935 : Math.min(65535, Math.max(1, port)),
  });
  document.getElementById("scanHost").value = "";
  msg.textContent = "";
  await persistScanServers();
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
loadScanServers();
refreshRates();
refreshPing();
setInterval(refreshRates, 1000);
setInterval(refreshPing, 5000);
