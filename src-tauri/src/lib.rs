mod monitor;
mod relay;
mod scanner;
mod updater;

use serde::Serialize;
use std::net::ToSocketAddrs;
use std::sync::Mutex;

struct AppState {
    /// لیست سرورهای استریمِ اسکنر — هنگام استارت از دیسک خوانده می‌شود
    /// (scanner::load_servers) و هر تغییری همان لحظه ذخیره می‌شود.
    servers: Mutex<Vec<scanner::StreamServer>>,
    /// «بستن به سینی سیستم» — فرانت از روی تنظیمات کاربر پرش می‌کند؛
    /// وقتی روشن است، دکمه‌ی بستن پنجره فقط آن را مخفی می‌کند.
    close_to_tray: Mutex<bool>,
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

/// تنظیم «بستن به سینی سیستم» از روی تنظیمات فرانت.
#[tauri::command]
fn set_close_to_tray(state: tauri::State<AppState>, enabled: bool) {
    *state.close_to_tray.lock().unwrap() = enabled;
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // لیست سرورهای اسکنر از دیسک (یا پیش‌فرض).
    let servers = scanner::load_servers();

    // پاک‌سازی فایل‌های ‎.old‎ باقی‌مانده از آپدیت قبلی (موتور آپدیت v2).
    updater::cleanup_old_files();

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(updater::UpdateV2State::default())
        .manage(AppState {
            servers: Mutex::new(servers),
            close_to_tray: Mutex::new(true),
            relay: Mutex::new(relay::RelayRuntime::new()),
        })
        .invoke_handler(tauri::generate_handler![
            ping_host,
            get_servers,
            set_servers,
            scan_servers,
            parse_server_link,
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
        .run(|_, _| {});
}
