mod monitor;
mod qos;

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
#[tauri::command]
fn apply_stream_reserve(
    state: tauri::State<AppState>,
    reserve_mbps: f64,
    whitelist: Vec<String>,
) -> Result<ReserveReport, String> {
    let rates = state.last_rates.lock().unwrap().clone();
    let total: f64 = rates.iter().map(|r| r.up_kbps).sum();
    if total <= 0.0 {
        return Err("هنوز ترافیک آپلودی اندازه‌گیری نشده؛ چند ثانیه صبر کن و دوباره بزن.".into());
    }
    let stored = state.whitelist.lock().unwrap().clone();
    let effective = qos::merge_whitelists(&stored, &whitelist);
    let reserve_kbps = reserve_mbps * 1000.0;
    let targets: Vec<(String, f64)> = rates
        .iter()
        .filter(|r| !qos::is_whitelisted(&r.name, &effective))
        .map(|r| (r.name.clone(), r.up_kbps))
        .collect();
    let caps = qos::compute_caps(total, reserve_kbps, &targets);
    for (exe, cap) in &caps {
        qos::set_cap(exe, *cap)?;
    }
    qos::refresh_policies();
    Ok(ReserveReport {
        total_up_kbps: total,
        reserve_kbps,
        capped: caps,
    })
}

/// پروسه‌هایی که هرگز نباید بسته شوند (همتای NEVER_TOUCH نسخه‌ی پایتون).
const NEVER_TOUCH: &[&str] = &[
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe", "dwm.exe",
    "explorer.exe", "spoolsv.exe", "taskhost.exe", "taskhostw.exe", "conhost.exe",
    "sihost.exe", "ctfmon.exe", "searchindexer.exe", "securityhealthservice.exe",
    "msmpeng.exe", "audiodg.exe",
];

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
    Err("فقط ویندوز".into())
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // بازیابی بعد از کرش — قبل از هر چیز: اگر اجرای قبلی کرش کرده یا
    // سیستم خاموش شده باشد، پالیسی‌های «LagSlice-» روی سیستم مانده‌اند؛
    // اسکن و پاک‌سازی امن آن‌ها یعنی این اجرا با سیستم تمیز شروع می‌شود.
    let recovery = qos::recover_on_startup();
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

    tauri::Builder::default()
        .manage(AppState {
            monitor: Mutex::new(Monitor::new()),
            last_rates: Mutex::new(Vec::new()),
            whitelist: Mutex::new(whitelist),
        })
        .invoke_handler(tauri::generate_handler![
            get_app_rates,
            ping_host,
            set_app_cap,
            apply_stream_reserve,
            clear_all_caps,
            list_active_policies,
            recover_policies,
            get_whitelist,
            set_whitelist,
            add_to_whitelist,
            remove_from_whitelist,
            kill_process
        ])
        .build(tauri::generate_context!())
        .expect("error while building LagSlice")
        .run(|_app, event| {
            // هنگام خروج، هیچ پالیسی یتیمی روی سیستم کاربر نماند.
            if let tauri::RunEvent::Exit = event {
                let _ = qos::clear_all();
            }
        });
}
