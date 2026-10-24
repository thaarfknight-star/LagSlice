mod monitor;
mod qos;
mod relay;
mod scanner;
mod updater;

use monitor::{AppRate, Monitor};
use serde::Serialize;
use std::net::ToSocketAddrs;
use std::sync::Mutex;

struct AppState {
    monitor: Mutex<Monitor>,
    /// آخرین نرخ‌های دیده‌شده per exe — مبنای الگوریتم رزرو.
    last_rates: Mutex<Vec<AppRate>>,
    /// لیست سفید برنامه‌ها — هنگام استارت از دیسک خوانده می‌شود
    /// (qos::load_whitelist) و هر تغییری همان لحظه ذخیره می‌شود
    /// (qos::save_whitelist) تا بین اجراها بماند.
    whitelist: Mutex<Vec<String>>,
    /// لیست سرورهای استریمِ اسکنر — هنگام استارت از دیسک خوانده می‌شود
    /// (scanner::load_servers) و هر تغییری همان لحظه ذخیره می‌شود.
    servers: Mutex<Vec<scanner::StreamServer>>,
    /// «بستن به سینی سیستم» — فرانت از روی تنظیمات کاربر پرش می‌کند؛
    /// وقتی روشن است، دکمه‌ی بستن پنجره فقط آن را مخفی می‌کند.
    close_to_tray: Mutex<bool>,
    /// موتور محدودیت (دکمه‌ی فعال‌سازی اصلی): وقتی فعال است، سقف‌ها
    /// زنده نگه داشته می‌شوند و تثبیت‌کننده‌ی استریم کار می‌کند.
    engine: Mutex<EngineState>,
    /// رله‌ی تطبیقی RTMP — وضعیت و نخ پمپ در relay::RelayRuntime است؛
    /// کلید استریم فقط در حافظه‌ی همان ساختار است و هرگز برنمی‌گردد.
    relay: Mutex<relay::RelayRuntime>,
}

/// ردیف وضعیت رله برای فرانت (بدون کلید استریم).
#[derive(Serialize)]
struct RelayStatusRow {
    running: bool,
    target_host: String,
    listen_addr: String,
    current_kbps: u32,
    /// حالت بیت‌ریت ثابت فعال است؟ (۰٫۹٫۱۱)
    fixed_mode: bool,
    capacity_ema_kbps: f64,
    probe_kbps: f64,
    at_top: bool,
    forwarded_bytes: u64,
    forwarded_msgs: u64,
    dropped_gops: u64,
    dropped_bytes: u64,
    queue_bytes: usize,
    queue_age_secs: f64,
    drain_kbps: f64,
    uptime_secs: u64,
    last_error: Option<String>,
    log_path: String,
}

/// شروع رله‌ی تطبیقی: Meld باید با Custom RTMP به 127.0.0.1:1935/live
/// بفرستد؛ مقصد (ingest کیک) و کلیدش از فرانت می‌آیند و کلید فقط در
/// حافظه می‌ماند.
#[tauri::command]
fn relay_start(
    state: tauri::State<AppState>,
    target_url: String,
    stream_key: String,
    top_kbps: u32,
) -> Result<(), String> {
    state.relay.lock().unwrap().start(&target_url, &stream_key, top_kbps)
}

/// توقف رله (نخ پمپ با پرچم توقف تمام می‌شود و join می‌شود).
#[tauri::command]
fn relay_stop(state: tauri::State<AppState>) {
    state.relay.lock().unwrap().stop();
}

/// تغییر حالت رله از پنل (۰٫۹٫۱۱): وسط استریم هم اثر می‌کند،
/// چون پمپ هر تکرار پرچم را می‌خواند؛ فرانت قبل از استارت هم
/// همین را با مقدار انتخاب‌گر صدا می‌زند تا پرچم با انتخاب‌گر
/// هم‌گام شود.
#[tauri::command]
fn relay_set_mode(state: tauri::State<AppState>, fixed: bool) {
    state.relay.lock().unwrap().set_fixed_mode(fixed);
}

/// وضعیت زنده‌ی رله برای پنل فرانت.
#[tauri::command]
fn relay_status(state: tauri::State<AppState>) -> RelayStatusRow {
    let s = state.relay.lock().unwrap().snapshot();
    RelayStatusRow {
        running: s.running,
        target_host: s.target_host,
        listen_addr: s.listen_addr,
        current_kbps: s.current_kbps,
        fixed_mode: s.fixed_mode,
        capacity_ema_kbps: s.capacity_ema_kbps,
        probe_kbps: s.probe_kbps,
        at_top: s.at_top,
        forwarded_bytes: s.forwarded_bytes,
        forwarded_msgs: s.forwarded_msgs,
        dropped_gops: s.dropped_gops,
        dropped_bytes: s.dropped_bytes,
        queue_bytes: s.queue_bytes,
        queue_age_secs: s.queue_age_secs,
        drain_kbps: s.drain_kbps,
        uptime_secs: s.uptime_secs,
        last_error: s.last_error,
        log_path: s.log_path,
    }
}

/// پارامترها و وضعیت زنده‌ی موتور محدودیت.
struct EngineState {
    active: bool,
    reserve_mbps: f64,
    whitelist: Vec<String>,
    stream_app: String,
    /// بستن خودکار برنامه‌های انتخاب‌نشده هنگام فعال‌بودن موتور.
    close_others: bool,
    /// آخرین جاروی دوره‌ای (در تیک تثبیت‌کننده).
    last_sweep: Option<std::time::Instant>,
    /// نام برنامه‌هایی که جاروی دوره‌ای بسته — فرانت می‌خواند و خالی می‌کند.
    closed_log: Vec<String>,
    last_apply: Option<std::time::Instant>,
    /// بیشینه‌ی مجموع آپلود دیده‌شده در این نشست (مبنای تشخیص اشباع).
    peak_total: f64,
    /// سقف‌هایی که همین حالا روی سیستم اعمال شده‌اند (exe, kbps).
    applied: Vec<(String, f64)>,
}

impl Default for EngineState {
    fn default() -> Self {
        Self {
            active: false,
            reserve_mbps: 6.0,
            whitelist: Vec::new(),
            stream_app: String::new(),
            close_others: false,
            last_sweep: None,
            closed_log: Vec::new(),
            last_apply: None,
            peak_total: 0.0,
            applied: Vec::new(),
        }
    }
}

/// نرخ زنده‌ی آپلود/دانلود هر برنامه (Kbps).
#[tauri::command]
fn get_app_rates(state: tauri::State<AppState>) -> Vec<AppRate> {
    let mut mon = state.monitor.lock().unwrap();
    let rates = mon.sample();
    // پروسه‌هایی که مرده‌اند از نرخ‌های ذخیره‌شده هم پاک شوند تا الگوریتم
    // رزرو روی ترافیک «شبح» حساب نکند.
    let exited = mon.take_exited_pids();
    if !rates.is_empty() {
        *state.last_rates.lock().unwrap() = rates.clone();
    } else if !exited.is_empty() {
        state
            .last_rates
            .lock()
            .unwrap()
            .retain(|r| !exited.contains(&r.pid));
    }
    // تثبیت‌کننده‌ی استریم: وقتی موتور فعال است سقف‌ها را زنده نگه می‌دارد.
    stabilizer_tick(&state);
    rates
}

/// پینگ یک هاست (نام یا IP) — خروجی RTT میلی‌ثانیه.
#[tauri::command]
fn ping_host(host: String) -> Option<u32> {
    let ip = format!("{host}:80")
        .to_socket_addrs()
        .ok()?
        .next()?
        .ip();
    match ip {
        std::net::IpAddr::V4(v4) => monitor::ping_ipv4(v4.octets(), 1000),
        _ => None,
    }
}

/// سقف آپلود دستی برای یک برنامه (Kbps)؛ None یعنی حذف سقف.
#[tauri::command]
fn set_app_cap(exe: String, cap_kbps: Option<f64>) -> Result<(), String> {
    match cap_kbps {
        Some(cap) => {
            qos::set_cap(&exe, cap)?;
        }
        None => {
            qos::remove_cap(&exe)?;
        }
    }
    qos::refresh_policies();
    Ok(())
}

#[derive(Serialize)]
struct ReserveReport {
    total_up_kbps: f64,
    reserve_kbps: f64,
    capped: Vec<(String, f64)>,
}

/// رزرو آپلود برای استریم: مجموع آپلود اندازه‌گیری می‌شود، سهم استریم
/// کنار گذاشته می‌شود و بقیه‌ی برنامه‌ها (جز لیست سفید) متناسب سقف می‌گیرند.
/// لیست سفیدِ مؤثر = ادغام لیست ذخیره‌شده (منبع اصلی) با لیست ارسالی کالر
/// (سازگاری با فرانت فعلی که برنامه‌ی استریم را همان لحظه می‌فرستد).
/// محاسبه و اعمال سقف‌ها از روی آخرین نرخ‌ها (تجمیع per-exe: چند پردازه‌ی
/// یک برنامه یک سقف می‌گیرند). squeeze=true سقف غیراستریم‌ها را ۱۵٪ تنگ‌تر
/// می‌کند (واکنش تثبیت‌کننده به اشباع لینک).
fn do_apply(state: &AppState, squeeze: bool) -> Result<ReserveReport, String> {
    let (reserve_mbps, extra_wl) = {
        let e = state.engine.lock().unwrap();
        (e.reserve_mbps, e.whitelist.clone())
    };
    let rates = state.last_rates.lock().unwrap().clone();
    let total: f64 = rates.iter().map(|r| r.up_kbps).sum();
    if total <= 0.0 {
        return Err("هنوز ترافیک آپلودی اندازه‌گیری نشده؛ چند ثانیه صبر کن و دوباره بزن.".into());
    }
    let stored = state.whitelist.lock().unwrap().clone();
    let effective = qos::merge_whitelists(&stored, &extra_wl);
    let reserve_kbps = reserve_mbps * 1000.0;
    // تجمیع نرخ پردازه‌های هم‌نام قبل از محاسبه‌ی سقف
    let mut agg: Vec<(String, f64)> = Vec::new();
    for r in &rates {
        if qos::is_whitelisted(&r.name, &effective) {
            continue;
        }
        if let Some(row) = agg.iter_mut().find(|(n, _)| n.eq_ignore_ascii_case(&r.name)) {
            row.1 += r.up_kbps;
        } else {
            agg.push((r.name.clone(), r.up_kbps));
        }
    }
    let mut caps = qos::compute_caps(total, reserve_kbps, &agg);
    if squeeze {
        for (_, cap) in &mut caps {
            *cap = (*cap * 0.85).max(32.0);
        }
    }
    {
        // فقط سقف‌های عوض‌شده را بنویس تا رجیستری بی‌جهت تکان نخورد.
        let mut e = state.engine.lock().unwrap();
        for (exe, cap) in &caps {
            let prev = e
                .applied
                .iter()
                .find(|(n, _)| n.eq_ignore_ascii_case(exe))
                .map(|(_, c)| *c);
            let changed = match prev {
                Some(p) => (p - cap).abs() > (p.max(*cap) * 0.10).max(1.0),
                None => true,
            };
            if changed {
                qos::set_cap(exe, *cap)?;
            }
        }
        // برنامه‌هایی که دیگر ترافیکی ندارند سقف‌شان را بردار.
        let stale: Vec<String> = e
            .applied
            .iter()
            .filter(|(n, _)| !caps.iter().any(|(c, _)| c.eq_ignore_ascii_case(n)))
            .map(|(n, _)| n.clone())
            .collect();
        for exe in &stale {
            let _ = qos::remove_cap(exe);
        }
        e.applied = caps.clone();
        e.last_apply = Some(std::time::Instant::now());
    }
    qos::refresh_policies();
    Ok(ReserveReport {
        total_up_kbps: total,
        reserve_kbps,
        capped: caps,
    })
}

/// تیک تثبیت‌کننده: هر ۵ ثانیه (از مسیر نظرسنجی نرخ‌ها صدا زده می‌شود).
/// وقتی لینک اشباع است و استریم به سهمش نمی‌رسد، بقیه تنگ‌تر می‌شوند.
fn stabilizer_tick(state: &AppState) {
    let should_run = {
        let mut e = state.engine.lock().unwrap();
        if !e.active {
            return;
        }
        // قله‌ی آپلود با فراموشی آرام (پنجره‌ی لغزان تقریبی)
        let total: f64 = state
            .last_rates
            .lock()
            .unwrap()
            .iter()
            .map(|r| r.up_kbps)
            .sum();
        e.peak_total = e.peak_total.max(total * 1.02);
        e.peak_total *= 0.995;
        match e.last_apply {
            Some(t) if t.elapsed() < std::time::Duration::from_secs(5) => false,
            _ => true,
        }
    };
    if !should_run {
        return;
    }
    let (saturated, stream_hungry) = {
        let e = state.engine.lock().unwrap();
        let rates = state.last_rates.lock().unwrap().clone();
        let total: f64 = rates.iter().map(|r| r.up_kbps).sum();
        let stream_up: f64 = rates
            .iter()
            .filter(|r| r.name.eq_ignore_ascii_case(&e.stream_app))
            .map(|r| r.up_kbps)
            .sum();
        let saturated = e.peak_total > 0.0 && total >= 0.95 * e.peak_total;
        let hungry = !e.stream_app.is_empty()
            && stream_up > 0.0
            && stream_up < 0.90 * e.reserve_mbps * 1000.0;
        (saturated, hungry)
    };
    let _ = do_apply(state, saturated && stream_hungry);
    // جاروی دوره‌ای بستن انتخاب‌نشده‌ها: فقط برنامه‌هایی که همین حالا
    // ترافیک دارند (برنامه‌ی بی‌ترافیکی که کاربر وسط استریم باز کند
    // دست نمی‌خورد) — هر ۱۵ ثانیه یک بار.
    let do_sweep = {
        let mut e = state.engine.lock().unwrap();
        if e.active && e.close_others {
            match e.last_sweep {
                Some(t) if t.elapsed() < std::time::Duration::from_secs(15) => false,
                _ => {
                    e.last_sweep = Some(std::time::Instant::now());
                    true
                }
            }
        } else {
            false
        }
    };
    if do_sweep {
        let closed = sweep_unselected(state, true);
        if !closed.is_empty() {
            state.engine.lock().unwrap().closed_log.extend(closed);
        }
    }
}

#[tauri::command]
fn apply_stream_reserve(
    state: tauri::State<AppState>,
    reserve_mbps: f64,
    whitelist: Vec<String>,
) -> Result<ReserveReport, String> {
    {
        let mut e = state.engine.lock().unwrap();
        e.reserve_mbps = reserve_mbps;
        e.whitelist = whitelist.clone();
        e.applied.clear(); // اعمال دستی = بازنویسی کامل
    }
    do_apply(&state, false)
}

/// نتیجه‌ی فعال‌سازی موتور برای فرانت.
#[derive(Serialize)]
struct ActivateResult {
    /// "active" | "armed" | "off"
    status: String,
    /// برنامه‌هایی که همین فعال‌سازی بسته است (حالت بستن انتخاب‌نشده‌ها).
    closed: Vec<String>,
}

/// دکمه‌ی فعال‌سازی اصلی: روشن = سقف‌ها اعمال و زنده نگه داشته می‌شوند +
/// اولویت DSCP برای برنامه‌ی استریم + خاموشی گلوگاه شبکه‌ی ویندوز +
/// (اگر close_others روشن باشد) بستن همه‌ی برنامه‌های انتخاب‌نشده؛
/// خاموش = همه‌ی سقف‌ها حذف و گلوگاه برمی‌گردد.
#[tauri::command]
fn set_engine_active(
    state: tauri::State<AppState>,
    active: bool,
    reserve_mbps: f64,
    whitelist: Vec<String>,
    stream_app: String,
    close_others: bool,
) -> Result<ActivateResult, String> {
    if active {
        {
            let mut e = state.engine.lock().unwrap();
            e.active = true;
            e.reserve_mbps = reserve_mbps;
            e.whitelist = whitelist;
            e.stream_app = stream_app.clone();
            e.close_others = close_others;
            e.applied.clear();
            e.last_apply = None;
            e.last_sweep = None;
        }
        if !stream_app.is_empty() {
            let _ = qos::set_dscp(&stream_app, 46);
        }
        qos::throttle_disable();
        let status = match do_apply(&state, false) {
            Ok(_) => "active",
            Err(_) => "armed", // ترافیک هنوز نیست؛ تیک اول اعمال می‌کند
        };
        let closed = if close_others {
            sweep_unselected(&state, false)
        } else {
            Vec::new()
        };
        Ok(ActivateResult {
            status: status.into(),
            closed,
        })
    } else {
        {
            let mut e = state.engine.lock().unwrap();
            e.active = false;
            e.applied.clear();
        }
        {
            let mut e = state.engine.lock().unwrap();
            e.close_others = false;
        }
        qos::clear_all()?;
        qos::throttle_restore();
        qos::refresh_policies();
        Ok(ActivateResult {
            status: "off".into(),
            closed: Vec::new(),
        })
    }
}

/// پروسه‌هایی که هرگز نباید بسته شوند (همتای NEVER_TOUCH نسخه‌ی پایتون).
/// msedgewebview2.exe موتور نمایش خود برنامه است (زیر Program Files یا
/// AppData، نه SystemRoot) — اگر جارو آن را بکشد، پنجره سفید و بی‌جان
/// می‌ماند (باگ ۰٫۹٫۳). LagSliceUpdater.exe هم هلپر آپدیت خود برنامه است.
const NEVER_TOUCH: &[&str] = &[
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe", "dwm.exe",
    "explorer.exe", "spoolsv.exe", "taskhost.exe", "taskhostw.exe", "conhost.exe",
    "sihost.exe", "ctfmon.exe", "searchindexer.exe", "securityhealthservice.exe",
    "msmpeng.exe", "audiodg.exe",
    "msedgewebview2.exe", "LagSliceUpdater.exe",
];

/// بستن خام یک PID با taskkill (بدون گارد — کالر گاردها را خودش چک می‌کند).
fn kill_pid(pid: u32) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let out = std::process::Command::new("taskkill")
            .args(["/F", "/PID", &pid.to_string()])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .map_err(|e| e.to_string())?;
        if out.status.success() {
            Ok(())
        } else {
            Err(String::from_utf8_lossy(&out.stderr).trim().to_string())
        }
    }
    #[cfg(not(windows))]
    {
        let _ = pid;
        Err("فقط ویندوز".into())
    }
}

/// بستن یک پروسه از روی PID — با گارد پروسه‌های سیستمی و خود برنامه.
#[tauri::command]
fn kill_process(pid: u32) -> Result<(), String> {
    if pid == std::process::id() {
        return Err("پروسه‌ی خود برنامه بسته نمی‌شود.".into());
    }
    if let Some(name) = monitor::process_name(pid) {
        if NEVER_TOUCH.iter().any(|n| n.eq_ignore_ascii_case(&name)) {
            return Err(format!("{name} پروسه‌ی سیستمی است و بسته نمی‌شود."));
        }
    }
    kill_pid(pid)
}

/// یک ردیف از فهرست «همه‌ی برنامه‌ها»: گروه‌بندی‌شده بر اساس نام exe.
#[derive(Serialize)]
struct ProgramRow {
    name: String,
    path: String,
    pid_count: usize,
    /// همین حالا ترافیک شبکه دارد (در آخرین نرخ‌ها دیده شده).
    network: bool,
}

/// فهرست همه‌ی برنامه‌های در حال اجرا (+ وضعیت ترافیک) برای انتخاب کاربر.
#[tauri::command]
fn list_programs(state: tauri::State<AppState>) -> Vec<ProgramRow> {
    let net: std::collections::HashSet<String> = state
        .last_rates
        .lock()
        .unwrap()
        .iter()
        .map(|r| r.name.to_lowercase())
        .collect();
    let mut rows: Vec<ProgramRow> = Vec::new();
    for p in monitor::list_processes() {
        let key = p.name.to_lowercase();
        if let Some(row) = rows.iter_mut().find(|r: &&mut ProgramRow| r.name.to_lowercase() == key) {
            row.pid_count += 1;
            if row.path.is_empty() && !p.path.is_empty() {
                row.path = p.path.clone();
            }
        } else {
            rows.push(ProgramRow {
                network: net.contains(&key),
                name: p.name,
                path: p.path,
                pid_count: 1,
            });
        }
    }
    rows.sort_by(|a, b| a.name.to_lowercase().cmp(&b.name.to_lowercase()));
    rows
}

/// دیالوگ انتخاب فایل اجرایی یک برنامه (برای افزودن برنامه‌ای که اجرا نیست).
#[tauri::command]
fn pick_program_file(app: tauri::AppHandle) -> Option<String> {
    use tauri_plugin_dialog::{DialogExt, FilePath};
    match app
        .dialog()
        .file()
        .add_filter("برنامه", &["exe"])
        .blocking_pick_file()
    {
        Some(FilePath::Path(p)) => Some(p.to_string_lossy().into_owned()),
        _ => None,
    }
}

/// به‌روزرسانی زنده‌ی فهرست برنامه‌های مجاز (انتخاب‌های کاربر) روی موتور فعال.
#[tauri::command]
fn set_keep_apps(state: tauri::State<AppState>, whitelist: Vec<String>) {
    state.engine.lock().unwrap().whitelist = whitelist;
}

/// خواندن و خالی‌کردن گزارش برنامه‌هایی که جاروی دوره‌ای بسته است.
#[tauri::command]
fn take_closed_log(state: tauri::State<AppState>) -> Vec<String> {
    std::mem::take(&mut state.engine.lock().unwrap().closed_log)
}

/// جاروی بستن برنامه‌های انتخاب‌نشده. گاردها: فهرست NEVER_TOUCH، خود برنامه،
/// هر پردازه‌ای که مسیرش زیر پوشه‌ی ویندوز است، هر پردازه‌ای که نامش شامل
/// webview است (دفاع در عمق برای موتور نمایش، مستقل از نام دقیق فایل)،
/// و برنامه‌های مجاز (whitelist + برنامه‌ی استریم). only_network=true یعنی
/// فقط برنامه‌های دارای ترافیک فعلی.
/// خروجی: نام برنامه‌هایی که بسته شدند (بدون تکرار).
fn sweep_unselected(state: &AppState, only_network: bool) -> Vec<String> {
    let (keep, stream_app) = {
        let e = state.engine.lock().unwrap();
        let mut keep: std::collections::HashSet<String> =
            e.whitelist.iter().map(|w| w.to_lowercase()).collect();
        if !e.stream_app.is_empty() {
            keep.insert(e.stream_app.to_lowercase());
        }
        (keep, e.stream_app.clone())
    };
    let _ = stream_app;
    let net_names: std::collections::HashSet<String> = state
        .last_rates
        .lock()
        .unwrap()
        .iter()
        .map(|r| r.name.to_lowercase())
        .collect();
    let win_dir = std::env::var("SystemRoot")
        .unwrap_or_else(|_| "C:\\Windows".into())
        .to_lowercase();
    let own_pid = std::process::id();
    let mut closed: Vec<String> = Vec::new();
    for p in monitor::list_processes() {
        if p.pid == own_pid || p.pid <= 4 {
            continue;
        }
        let lname = p.name.to_lowercase();
        if lname == "lagslice.exe" || keep.contains(&lname) {
            continue;
        }
        if NEVER_TOUCH.iter().any(|n| n.eq_ignore_ascii_case(&p.name)) {
            continue;
        }
        // دفاع در عمق: هر پردازه‌ای که نامش شامل webview است، موتور نمایش
        // است (خود برنامه یا برنامه‌ی دیگر) و هرگز نباید با جارو کشته شود.
        // lname از قبل lowercase شده است.
        if lname.contains("webview") {
            continue;
        }
        if !p.path.is_empty() && p.path.to_lowercase().starts_with(&win_dir) {
            continue;
        }
        if only_network && !net_names.contains(&lname) {
            continue;
        }
        if kill_pid(p.pid).is_ok() && !closed.iter().any(|c| c.eq_ignore_ascii_case(&p.name)) {
            closed.push(p.name.clone());
        }
    }
    closed
}

/// حذف همه‌ی سقف‌های ساخته‌ی LagSlice.
#[tauri::command]
fn clear_all_caps() -> Result<(), String> {
    qos::clear_all()?;
    qos::refresh_policies();
    Ok(())
}

/// نام پالیسی‌های LagSlice که همین حالا روی سیستم فعال‌اند
/// (اسکن زنده‌ی ریشه‌ی QoS؛ برای نمایش و دیباگ).
#[tauri::command]
fn list_active_policies() -> Result<Vec<String>, String> {
    qos::list_policies()
}

/// اجرای دستی بازیابی: اسکن و پاک‌سازی پالیسی‌های به‌جامانده.
/// همان کاری که هنگام استارت خودکار انجام می‌شود.
#[tauri::command]
fn recover_policies() -> qos::RecoveryReport {
    let report = qos::recover_on_startup();
    if report.changed() {
        qos::refresh_policies();
    }
    report
}

/// لیست سفید فعلی (از حافظه‌ی برنامه که هنگام استارت از دیسک پر شده).
#[tauri::command]
fn get_whitelist(state: tauri::State<AppState>) -> Vec<String> {
    state.whitelist.lock().unwrap().clone()
}

/// جایگزینی کامل لیست سفید + ذخیره‌ی فوری روی دیسک.
/// خروجی: لیست پاک‌سازی‌شده‌ای که ذخیره شد.
#[tauri::command]
fn set_whitelist(
    state: tauri::State<AppState>,
    whitelist: Vec<String>,
) -> Result<Vec<String>, String> {
    let saved = qos::save_whitelist(&whitelist)?;
    *state.whitelist.lock().unwrap() = saved.clone();
    Ok(saved)
}

/// افزودن یک برنامه به لیست سفید + ذخیره‌ی فوری.
#[tauri::command]
fn add_to_whitelist(
    state: tauri::State<AppState>,
    exe: String,
) -> Result<Vec<String>, String> {
    let current = state.whitelist.lock().unwrap().clone();
    let merged = qos::merge_whitelists(&current, &[exe]);
    let saved = qos::save_whitelist(&merged)?;
    *state.whitelist.lock().unwrap() = saved.clone();
    Ok(saved)
}

/// حذف یک برنامه از لیست سفید + ذخیره‌ی فوری.
#[tauri::command]
fn remove_from_whitelist(
    state: tauri::State<AppState>,
    exe: String,
) -> Result<Vec<String>, String> {
    let current = state.whitelist.lock().unwrap().clone();
    let kept: Vec<String> = current
        .into_iter()
        .filter(|w| !w.eq_ignore_ascii_case(exe.trim()))
        .collect();
    let saved = qos::save_whitelist(&kept)?;
    *state.whitelist.lock().unwrap() = saved.clone();
    Ok(saved)
}

/// لیست سرورهای استریم (از حافظه‌ای که هنگام استارت از دیسک پر شده).
#[tauri::command]
fn get_servers(state: tauri::State<AppState>) -> Vec<scanner::StreamServer> {
    state.servers.lock().unwrap().clone()
}

/// جایگزینی کامل لیست سرورها + ذخیره‌ی فوری روی دیسک.
#[tauri::command]
fn set_servers(
    state: tauri::State<AppState>,
    servers: Vec<scanner::StreamServer>,
) -> Result<Vec<scanner::StreamServer>, String> {
    let saved = scanner::save_servers(&servers)?;
    *state.servers.lock().unwrap() = saved.clone();
    Ok(saved)
}

/// اسکن موازی سرورها (پینگ + TCP + امتیاز) — روی نخ جدا اجرا می‌شود
/// تا رابط کاربری در طول اسکن فریز نشود.
#[tauri::command]
async fn scan_servers(servers: Vec<scanner::StreamServer>) -> Vec<scanner::ProbeResult> {
    tauri::async_runtime::spawn_blocking(move || scanner::scan_all(&servers))
        .await
        .unwrap_or_default()
}

/// ساخت سرور از روی لینک RTMP: نام و منطقه و هاست و پورت خودکار
/// پر می‌شوند (مثل پروژه‌ی StreamScanner).
#[tauri::command]
fn parse_server_link(text: String) -> scanner::StreamServer {
    scanner::import_rtmp(&text, "", "")
}

/// درون‌ریزی گروهی لینک‌های RTMP (هر خط یک لینک) با حذف تکراری‌ها.
#[tauri::command]
fn import_server_links(
    text: String,
    existing: Vec<scanner::StreamServer>,
) -> scanner::ImportOutcome {
    scanner::import_rtmp_bulk(&text, &existing)
}

/// تنظیم «بستن به سینی سیستم» از روی تنظیمات فرانت.
#[tauri::command]
fn set_close_to_tray(state: tauri::State<AppState>, enabled: bool) {
    *state.close_to_tray.lock().unwrap() = enabled;
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // بازیابی بعد از کرش — قبل از هر چیز: اگر اجرای قبلی کرش کرده یا
    // سیستم خاموش شده باشد، پالیسی‌های «LagSlice-» روی سیستم مانده‌اند؛
    // اسکن و پاک‌سازی امن آن‌ها یعنی این اجرا با سیستم تمیز شروع می‌شود.
    let recovery = qos::recover_on_startup();
    // اگر اجرای قبلی وسط کار مرده بود، گلوگاه شبکه را هم برگردان.
    qos::throttle_restore();
    if !recovery.found.is_empty() {
        eprintln!(
            "[LagSlice] بازیابی هنگام استارت: {} پالیسی به‌جامانده پیدا شد، {} حذف شد، {} ناموفق ماند.",
            recovery.found.len(),
            recovery.removed.len(),
            recovery.failed.len()
        );
        for f in &recovery.failed {
            eprintln!("[LagSlice] بازیابی ناموفق: {f}");
        }
        if recovery.changed() {
            qos::refresh_policies();
        }
    }

    // لیست سفید از دیسک (یا پیش‌فرض) — ماندگار بین اجراها.
    let whitelist = qos::load_whitelist();

    // لیست سرورهای اسکنر از دیسک (یا پیش‌فرض).
    let servers = scanner::load_servers();

    // پاک‌سازی فایل‌های ‎.old‎ باقی‌مانده از آپدیت قبلی (موتور آپدیت v2).
    updater::cleanup_old_files();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(updater::UpdateV2State::default())
        .manage(AppState {
            monitor: Mutex::new(Monitor::new()),
            last_rates: Mutex::new(Vec::new()),
            whitelist: Mutex::new(whitelist),
            servers: Mutex::new(servers),
            close_to_tray: Mutex::new(true),
            engine: Mutex::new(EngineState::default()),
            relay: Mutex::new(relay::RelayRuntime::new()),
        })
        .invoke_handler(tauri::generate_handler![
            get_app_rates,
            ping_host,
            set_app_cap,
            apply_stream_reserve,
            set_engine_active,
            clear_all_caps,
            list_active_policies,
            recover_policies,
            get_whitelist,
            set_whitelist,
            add_to_whitelist,
            remove_from_whitelist,
            kill_process,
            list_programs,
            pick_program_file,
            set_keep_apps,
            take_closed_log,
            get_servers,
            set_servers,
            scan_servers,
            parse_server_link,
            import_server_links,
            set_close_to_tray,
            relay_start,
            relay_stop,
            relay_set_mode,
            relay_status,
            updater::check_update2,
            updater::download_update2,
            updater::cancel_update_download2,
            updater::apply_update2,
            updater::open_update_file_dialog,
            updater::apply_local_update,
            updater::get_update_report
        ])
        .setup(|app| {
            // آیکن سینی سیستم با منوی «نمایش / خروج»؛ خروج واقعی از همین
            // منو (یا وقتی حالت سینی خاموش است، با بستن پنجره) انجام می‌شود.
            use tauri::menu::{Menu, MenuItem};
            use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
            use tauri::Manager;
            let show_item = MenuItem::with_id(app, "show", "نمایش LagSlice", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "خروج", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &quit_item])?;
            let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/icon.png"))?;
            TrayIconBuilder::with_id("main-tray")
                .icon(icon)
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // بستن به سینی: اگر تنظیم روشن است، بستن پنجره فقط مخفی‌اش
            // می‌کند و برنامه در سینی به کارش ادامه می‌دهد.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                use tauri::Manager;
                let state = window.state::<AppState>();
                if *state.close_to_tray.lock().unwrap() {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building LagSlice")
        .run(|_app, event| {
            // هنگام خروج، هیچ پالیسی یتیمی روی سیستم کاربر نماند.
            if let tauri::RunEvent::Exit = event {
                let _ = qos::clear_all();
                qos::throttle_restore();
            }
        });
}
