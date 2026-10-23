//! مانیتورینگ زنده‌ی ترافیک per-process روی ویندوز.
//!
//! روش کار (همان معماری نسخه‌ی پایتون، بازنویسی‌شده در Rust):
//! - جدول اتصال‌های TCP با مالک PID از GetExtendedTcpTable گرفته می‌شود.
//! - شمارنده‌ی تجمعی بایت هر اتصال با EStats ویندوز خوانده می‌شود
//!   (SetPerTcpConnectionEStats برای فعال‌سازی + GetPerTcpConnectionEStats).
//! - اختلاف دو نمونه‌گیری متوالی تقسیم بر زمان = نرخ لحظه‌ای هر پروسه.
//!
//! مدیریت چرخه‌ی حیات پروسه‌ها:
//! - هر نمونه‌گیری، زنده‌بودن PIDها از اسنپ‌شات پروسه‌های سیستم چک می‌شود.
//! - اتصال‌های متعلق به پروسه‌ی مرده (حتی اگر ردیفشان هنوز در جدول TCP مانده
//!   باشد) از محاسبه‌ی نرخ و از کش نمونه‌گیری حذف می‌شوند تا ترافیک «شبح»
//!   گزارش نشود و کش بی‌نهایت رشد نکند.
//! - PID پروسه‌هایی که از نمونه‌ی قبل تا حالا مرده‌اند در صف خروج نگه داشته
//!   می‌شوند تا لایه‌ی بالاتر (با `take_exited_pids`) نرخ‌های کهنه‌شان را پاک کند.
//!
//! محدودیت شناخته‌شده: EStats فقط TCP است؛ ترافیک UDP اتصال‌محورِ قابل انتساب
//! به پروسه در سطح کاربر شمارنده‌ی بایت ندارد (ابزارهایی مثل GlassWire برای
//! این بخش درایور دارند). برای استریم (RTMP روی TCP) همین پوشش کافی است.

use serde::Serialize;
use std::collections::{HashMap, HashSet};
use std::time::Instant;

/// یک پردازه‌ی زنده‌ی سیستم (برای فهرست «همه‌ی برنامه‌ها»).
#[derive(Serialize, Clone, Debug)]
pub struct ProcInfo {
    pub pid: u32,
    pub name: String,
    /// مسیر کامل فایل اجرایی؛ خالی یعنی قابل‌خواندن نبود (پروسه‌ی سیستمی).
    pub path: String,
}

/// فهرست همه‌ی پردازه‌های زنده با نام و مسیر (بهترین تلاش برای مسیر).
#[cfg(windows)]
pub fn list_processes() -> Vec<ProcInfo> {
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };
    use windows::Win32::System::Threading::{
        OpenProcess, QueryFullProcessImageNameW, PROCESS_NAME_FORMAT,
        PROCESS_QUERY_LIMITED_INFORMATION,
    };
    let mut out = Vec::new();
    unsafe {
        let Ok(snap) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) else {
            return out;
        };
        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };
        if Process32FirstW(snap, &mut entry).is_ok() {
            loop {
                let len = entry
                    .szExeFile
                    .iter()
                    .position(|&c| c == 0)
                    .unwrap_or(entry.szExeFile.len());
                let name = String::from_utf16_lossy(&entry.szExeFile[..len]);
                let pid = entry.th32ProcessID;
                let mut path = String::new();
                if let Ok(h) = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) {
                    let mut buf = [0u16; 1024];
                    let mut size = buf.len() as u32;
                    if QueryFullProcessImageNameW(
                        h,
                        PROCESS_NAME_FORMAT(0),
                        windows::core::PWSTR(buf.as_mut_ptr()),
                        &mut size,
                    )
                    .is_ok()
                    {
                        path = String::from_utf16_lossy(&buf[..size as usize]);
                    }
                    let _ = CloseHandle(h);
                }
                out.push(ProcInfo { pid, name, path });
                if Process32NextW(snap, &mut entry).is_err() {
                    break;
                }
            }
        }
        let _ = CloseHandle(snap);
    }
    out
}

#[cfg(not(windows))]
pub fn list_processes() -> Vec<ProcInfo> {
    Vec::new()
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct AppRate {
    pub pid: u32,
    pub name: String,
    pub up_kbps: f64,
    pub down_kbps: f64,
}

type ConnKey = (u32, u32, u32, u32, u32); // local_ip, local_port, remote_ip, remote_port, pid

pub struct Monitor {
    prev: HashMap<ConnKey, (u64, u64)>, // (bytes_in, bytes_out)
    prev_at: Option<Instant>,
    /// PIDهایی که در آخرین نمونه‌گیری زنده دیده شدند.
    known_pids: HashSet<u32>,
    /// PIDهایی که از آخرین بار خوانده‌شدن مرده‌اند (صف خروج).
    exited_pids: Vec<u32>,
}

impl Monitor {
    pub fn new() -> Self {
        Self {
            prev: HashMap::new(),
            prev_at: None,
            known_pids: HashSet::new(),
            exited_pids: Vec::new(),
        }
    }

    /// یک نمونه‌گیری تازه؛ نرخ‌ها برحسب Kbps برمی‌گردند.
    pub fn sample(&mut self) -> Vec<AppRate> {
        let now = Instant::now();
        let dt = self
            .prev_at
            .map(|t| now.duration_since(t).as_secs_f64())
            .unwrap_or(0.0);
        let current = snapshot_connection_bytes();
        let (names, alive) = process_table();

        let outcome = compute_rates(
            &self.prev,
            &current,
            alive.as_ref(),
            &self.known_pids,
            &names,
            dt,
        );
        self.prev = outcome.cache;
        self.prev_at = Some(now);
        self.known_pids = outcome.live_pids;
        self.exited_pids.extend(outcome.exited_pids);
        outcome.rates
    }

    /// PID پروسه‌هایی که از آخرین فراخوانی مرده‌اند؛ صف خالی می‌شود.
    /// لایه‌ی UI با این لیست می‌تواند نرخ‌های کهنه‌ی پروسه‌های مرده را کنار بگذارد.
    pub fn take_exited_pids(&mut self) -> Vec<u32> {
        std::mem::take(&mut self.exited_pids)
    }

    /// PIDهایی که الان زنده و تحت نظرند (برای تست و دیباگ).
    pub fn live_pids(&self) -> &HashSet<u32> {
        &self.known_pids
    }
}

/// خروجی یک دور محاسبه‌ی نرخ — تابع خالص، جدا از APIهای سیستم.
struct SampleOutcome {
    rates: Vec<AppRate>,
    /// کش نمونه‌ی بعد: فقط اتصال‌های زنده‌ی همین دور.
    cache: HashMap<ConnKey, (u64, u64)>,
    /// PIDهایی که نمونه‌ی قبل زنده بودند و حالا مرده‌اند.
    exited_pids: Vec<u32>,
    /// PIDهای زنده‌ی این دور.
    live_pids: HashSet<u32>,
}

/// محاسبه‌ی نرخ از اختلاف شمارنده‌ها.
///
/// قواعد:
/// - اتصالی که در `prev` نیست، خط مبنایش همان شمارنده‌ی فعلی است (دلتا صفر) —
///   بایت‌های گذشته‌اش به این دور نسبت داده نمی‌شود.
/// - شمارنده‌ای که عقب رفته (ریست EStats یا استفاده‌ی مجدد از همان چهارتایی)
///   دلتای صفر می‌دهد، نه جهش منفی/مثبت کاذب.
/// - اگر `alive` مشخص باشد (Some)، ردیف‌های متعلق به PID مرده — حتی اگر هنوز
///   در اسنپ‌شات TCP باشند — نه در نرخ حساب می‌شوند نه وارد کش می‌شوند.
/// - کش بعدی فقط اتصال‌های همین دور است؛ اتصال بسته‌شده خودبه‌خود هرس می‌شود.
/// - `dt <= 0` (نمونه‌ی اول یا ساعتِ بی‌حرکت) نرخ خالی برمی‌گرداند ولی کش و
///   ردیابی حیات به‌روز می‌شوند.
fn compute_rates(
    prev: &HashMap<ConnKey, (u64, u64)>,
    current: &HashMap<ConnKey, (u64, u64)>,
    alive: Option<&HashSet<u32>>,
    known_pids: &HashSet<u32>,
    names: &HashMap<u32, String>,
    dt: f64,
) -> SampleOutcome {
    // فقط ردیف‌های متعلق به پروسه‌ی زنده می‌مانند.
    let is_live = |pid: u32| alive.map_or(true, |set| set.contains(&pid));
    let live_current: HashMap<ConnKey, (u64, u64)> = current
        .iter()
        .filter(|(key, _)| is_live(key.4))
        .map(|(k, v)| (*k, *v))
        .collect();

    let live_pids: HashSet<u32> = live_current.keys().map(|k| k.4).collect();
    let exited_pids: Vec<u32> = match alive {
        Some(set) => known_pids
            .iter()
            .filter(|pid| !set.contains(pid))
            .copied()
            .collect(),
        None => Vec::new(),
    };

    let mut rates = Vec::new();
    if dt > 0.0 {
        let mut per_pid: HashMap<u32, (u64, u64)> = HashMap::new(); // delta in/out bytes
        for (key, (bin, bout)) in &live_current {
            let (pin, pout) = prev.get(key).copied().unwrap_or((*bin, *bout));
            let entry = per_pid.entry(key.4).or_default();
            entry.0 += bin.saturating_sub(pin);
            entry.1 += bout.saturating_sub(pout);
        }
        rates = per_pid
            .into_iter()
            .filter(|(_, (din, dout))| *din > 0 || *dout > 0)
            .map(|(pid, (din, dout))| AppRate {
                pid,
                name: names
                    .get(&pid)
                    .cloned()
                    .unwrap_or_else(|| format!("pid-{pid}")),
                down_kbps: bytes_to_kbps(din, dt),
                up_kbps: bytes_to_kbps(dout, dt),
            })
            .collect();
        rates.sort_by(|a, b| b.up_kbps.partial_cmp(&a.up_kbps).unwrap());
    }

    SampleOutcome {
        rates,
        cache: live_current,
        exited_pids,
        live_pids,
    }
}

/// تبدیل دلتا بایت در بازه‌ی dt ثانیه به نرخ Kbps.
fn bytes_to_kbps(bytes: u64, dt: f64) -> f64 {
    (bytes as f64 * 8.0 / 1000.0) / dt
}

/// جدول پروسه‌های زنده: (نام هر PID، مجموعه‌ی PIDهای زنده).
/// مجموعه‌ی زنده None یعنی «اطلاعات حیات در دسترس نیست» (خطای اسنپ‌شات یا
/// پلتفرم غیر ویندوز) — در این حالت چیزی بر اساس حیات هرس نمی‌شود.
#[cfg(windows)]
fn process_table() -> (HashMap<u32, String>, Option<HashSet<u32>>) {
    use windows::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
        TH32CS_SNAPPROCESS,
    };
    let mut map = HashMap::new();
    unsafe {
        let Ok(snap) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) else {
            return (map, None);
        };
        let mut entry = PROCESSENTRY32W {
            dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
            ..Default::default()
        };
        if Process32FirstW(snap, &mut entry).is_ok() {
            loop {
                let len = entry
                    .szExeFile
                    .iter()
                    .position(|&c| c == 0)
                    .unwrap_or(entry.szExeFile.len());
                let name = String::from_utf16_lossy(&entry.szExeFile[..len]);
                map.insert(entry.th32ProcessID, name);
                if Process32NextW(snap, &mut entry).is_err() {
                    break;
                }
            }
        }
        let _ = windows::Win32::Foundation::CloseHandle(snap);
    }
    let alive: HashSet<u32> = map.keys().copied().collect();
    (map, Some(alive))
}

#[cfg(not(windows))]
fn process_table() -> (HashMap<u32, String>, Option<HashSet<u32>>) {
    (HashMap::new(), None)
}

/// برای هر اتصال TCP فعال: (بایت ورودی تجمعی، بایت خروجی تجمعی) از EStats.
#[cfg(windows)]
fn snapshot_connection_bytes() -> HashMap<ConnKey, (u64, u64)> {
    use windows::Win32::NetworkManagement::IpHelper::{
        GetExtendedTcpTable, GetPerTcpConnectionEStats, SetPerTcpConnectionEStats,
        MIB_TCPROW_LH, TCP_ESTATS_DATA_ROD_v0, TCP_ESTATS_DATA_RW_v0, TCP_TABLE_OWNER_PID_ALL,
    };
    use windows::Win32::Networking::WinSock::AF_INET;

    let mut result = HashMap::new();
    unsafe {
        // اندازه‌ی جدول را می‌گیریم و بعد خود جدول را می‌خوانیم.
        let mut size: u32 = 0;
        let _ = GetExtendedTcpTable(
            None,
            &mut size,
            false,
            AF_INET.0 as u32,
            TCP_TABLE_OWNER_PID_ALL,
            0,
        );
        if size == 0 {
            return result;
        }
        let mut buf = vec![0u8; size as usize];
        let rc = GetExtendedTcpTable(
            Some(buf.as_mut_ptr() as *mut _),
            &mut size,
            false,
            AF_INET.0 as u32,
            TCP_TABLE_OWNER_PID_ALL,
            0,
        );
        if rc != 0 {
            return result;
        }
        let count = *(buf.as_ptr() as *const u32) as usize;
        // MIB_TCPTABLE_OWNER_PID: بعد از dwNumEntries آرایه‌ی MIB_TCPROW_OWNER_PID شروع می‌شود.
        let rows_ptr = buf.as_ptr().add(4) as *const windows::Win32::NetworkManagement::IpHelper::MIB_TCPROW_OWNER_PID;
        for i in 0..count {
            let row = &*rows_ptr.add(i);
            let key: ConnKey = (
                row.dwLocalAddr,
                row.dwLocalPort,
                row.dwRemoteAddr,
                row.dwRemotePort,
                row.dwOwningPid,
            );
            // MIB_TCPROW_LH بیست بایت اول MIB_TCPROW_OWNER_PID است (بدون PID).
            let lh: MIB_TCPROW_LH = std::ptr::read(row as *const _ as *const MIB_TCPROW_LH);
            // فعال‌سازی EStats برای این اتصال (فراخوانی تکراری بی‌ضرر است).
            let rw = TCP_ESTATS_DATA_RW_v0 {
                EnableCollection: windows::Win32::Foundation::BOOLEAN(1),
            };
            let rw_bytes = std::slice::from_raw_parts(
                &rw as *const _ as *const u8,
                std::mem::size_of::<TCP_ESTATS_DATA_RW_v0>(),
            );
            let _ = SetPerTcpConnectionEStats(
                &lh,
                windows::Win32::NetworkManagement::IpHelper::TcpConnectionEstatsData,
                rw_bytes,
                0,
                0,
            );
            let mut rod = TCP_ESTATS_DATA_ROD_v0::default();
            let rod_bytes = std::slice::from_raw_parts_mut(
                &mut rod as *mut _ as *mut u8,
                std::mem::size_of::<TCP_ESTATS_DATA_ROD_v0>(),
            );
            let rc = GetPerTcpConnectionEStats(
                &lh,
                windows::Win32::NetworkManagement::IpHelper::TcpConnectionEstatsData,
                None,
                0,
                None,
                0,
                Some(rod_bytes),
                0,
            );
            if rc == 0 {
                result.insert(key, (rod.DataBytesIn, rod.DataBytesOut));
            }
        }
    }
    result
}

#[cfg(not(windows))]
fn snapshot_connection_bytes() -> HashMap<ConnKey, (u64, u64)> {
    HashMap::new()
}

/// نام اجرایی یک پروسه از روی PID (برای گارد بستن پروسه‌ها).
pub fn process_name(pid: u32) -> Option<String> {
    process_table().0.get(&pid).cloned()
}

/// پینگ ICMP به یک آی‌پی IPv4 — خروجی: RTT به میلی‌ثانیه (None یعنی بدون پاسخ).
#[cfg(windows)]
pub fn ping_ipv4(ip: [u8; 4], timeout_ms: u32) -> Option<u32> {
    use windows::Win32::NetworkManagement::IpHelper::{
        IcmpCreateFile, IcmpSendEcho, ICMP_ECHO_REPLY,
    };
    unsafe {
        let handle = IcmpCreateFile().ok()?;
        let dest = u32::from_ne_bytes(ip);
        let request = [0u8; 32];
        let reply_size = (std::mem::size_of::<ICMP_ECHO_REPLY>() + 32 + 8) as u32;
        let mut reply = vec![0u8; reply_size as usize];
        let n = IcmpSendEcho(
            handle,
            dest,
            request.as_ptr() as *const _,
            request.len() as u16,
            None,
            reply.as_mut_ptr() as *mut _,
            reply_size,
            timeout_ms,
        );
        let _ = windows::Win32::Foundation::CloseHandle(handle);
        if n == 0 {
            return None;
        }
        let r = &*(reply.as_ptr() as *const ICMP_ECHO_REPLY);
        if r.Status == 0 {
            Some(r.RoundTripTime)
        } else {
            None
        }
    }
}

#[cfg(not(windows))]
pub fn ping_ipv4(_ip: [u8; 4], _timeout_ms: u32) -> Option<u32> {
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(pid: u32, local_port: u32) -> ConnKey {
        (0x0100007f, local_port, 0x0200007f, 443, pid)
    }

    fn names(pairs: &[(u32, &str)]) -> HashMap<u32, String> {
        pairs.iter().map(|(p, n)| (*p, n.to_string())).collect()
    }

    fn no_known() -> HashSet<u32> {
        HashSet::new()
    }

    /// ۱۲۵٬۰۰۰ بایت در یک ثانیه = ۱٬۰۰۰ Kbps دانلود؛ ۲۵۰٬۰۰۰ بایت = ۲٬۰۰۰ Kbps آپلود.
    #[test]
    fn rate_math_basic() {
        let prev = HashMap::from([(key(10, 5000), (1_000, 2_000))]);
        let current = HashMap::from([(key(10, 5000), (126_000, 252_000))]);
        let out = compute_rates(&prev, &current, None, &no_known(), &names(&[(10, "game.exe")]), 1.0);
        assert_eq!(out.rates.len(), 1);
        let r = &out.rates[0];
        assert_eq!(r.pid, 10);
        assert_eq!(r.name, "game.exe");
        assert!((r.down_kbps - 1000.0).abs() < 1e-9, "down={}", r.down_kbps);
        assert!((r.up_kbps - 2000.0).abs() < 1e-9, "up={}", r.up_kbps);
    }

    /// نصف‌شدن بازه‌ی زمانی، نرخ را دو برابر می‌کند.
    #[test]
    fn rate_math_scales_with_dt() {
        let prev = HashMap::from([(key(10, 5000), (0, 0))]);
        let current = HashMap::from([(key(10, 5000), (125_000, 0))]);
        let out = compute_rates(&prev, &current, None, &no_known(), &HashMap::new(), 0.5);
        assert_eq!(out.rates.len(), 1);
        assert!((out.rates[0].down_kbps - 2000.0).abs() < 1e-9);
    }

    /// دو اتصال از یک پروسه با هم جمع می‌شوند.
    #[test]
    fn rate_aggregates_connections_of_same_pid() {
        let prev = HashMap::from([
            (key(10, 5000), (0, 0)),
            (key(10, 5001), (0, 0)),
            (key(20, 5002), (0, 0)),
        ]);
        let current = HashMap::from([
            (key(10, 5000), (62_500, 125_000)),
            (key(10, 5001), (62_500, 125_000)),
            (key(20, 5002), (125_000, 0)),
        ]);
        let out = compute_rates(&prev, &current, None, &no_known(), &HashMap::new(), 1.0);
        assert_eq!(out.rates.len(), 2);
        let ten = out.rates.iter().find(|r| r.pid == 10).unwrap();
        assert!((ten.down_kbps - 1000.0).abs() < 1e-9);
        assert!((ten.up_kbps - 2000.0).abs() < 1e-9);
        // مرتب‌سازی بر اساس آپلود نزولی: pid 10 اول است.
        assert_eq!(out.rates[0].pid, 10);
    }

    /// اتصال تازه‌وارد خط مبنایش خودش است؛ ترافیک گذشته‌اش شمرده نمی‌شود.
    #[test]
    fn new_connection_has_zero_baseline() {
        let prev = HashMap::new();
        let current = HashMap::from([(key(10, 5000), (999_999, 999_999))]);
        let out = compute_rates(&prev, &current, None, &no_known(), &HashMap::new(), 1.0);
        assert!(out.rates.is_empty());
        // ولی وارد کش می‌شود تا دور بعد دلتا داشته باشد.
        assert_eq!(out.cache.len(), 1);
    }

    /// اتصالی که بسته شده از کش هرس می‌شود و کش رشد نمی‌کند.
    #[test]
    fn closed_connection_pruned_from_cache() {
        let prev = HashMap::from([
            (key(10, 5000), (100, 100)),
            (key(10, 5001), (100, 100)),
        ]);
        let current = HashMap::from([(key(10, 5000), (100, 100))]);
        let out = compute_rates(&prev, &current, None, &no_known(), &HashMap::new(), 1.0);
        assert_eq!(out.cache.len(), 1);
        assert!(out.cache.contains_key(&key(10, 5000)));
    }

    /// پروسه‌ی مرده: ردیفش حتی اگر در اسنپ‌شات TCP مانده باشد نه نرخ می‌گیرد
    /// نه وارد کش می‌شود؛ و در لیست خروج گزارش می‌شود.
    #[test]
    fn dead_pid_rows_dropped_and_reported() {
        let prev = HashMap::from([
            (key(10, 5000), (0, 0)),
            (key(99, 5001), (0, 0)),
        ]);
        let current = HashMap::from([
            (key(10, 5000), (125_000, 0)),
            (key(99, 5001), (125_000, 0)), // ردیف یتیم پروسه‌ی مرده
        ]);
        let alive: HashSet<u32> = [10].into_iter().collect();
        let known: HashSet<u32> = [10, 99].into_iter().collect();
        let out = compute_rates(&prev, &current, Some(&alive), &known, &HashMap::new(), 1.0);
        assert_eq!(out.rates.len(), 1);
        assert_eq!(out.rates[0].pid, 10);
        assert!(!out.cache.keys().any(|k| k.4 == 99));
        assert_eq!(out.exited_pids, vec![99]);
        assert!(!out.live_pids.contains(&99));
    }

    /// شمارنده‌ی عقب‌رفته (ریست EStats) جهش کاذب نمی‌سازد.
    #[test]
    fn counter_reset_gives_zero_delta() {
        let prev = HashMap::from([(key(10, 5000), (500_000, 500_000))]);
        let current = HashMap::from([(key(10, 5000), (100, 100))]);
        let out = compute_rates(&prev, &current, None, &no_known(), &HashMap::new(), 1.0);
        assert!(out.rates.is_empty());
    }

    /// dt صفر (نمونه‌ی اول) نرخ خالی می‌دهد ولی کش به‌روز می‌شود.
    #[test]
    fn zero_dt_yields_no_rates_but_updates_cache() {
        let prev = HashMap::new();
        let current = HashMap::from([(key(10, 5000), (100, 100))]);
        let out = compute_rates(&prev, &current, None, &no_known(), &HashMap::new(), 0.0);
        assert!(out.rates.is_empty());
        assert_eq!(out.cache.len(), 1);
        assert!(out.live_pids.contains(&10));
    }

    /// بدون اطلاعات حیات (None) هیچ پروسه‌ای مرده فرض نمی‌شود.
    #[test]
    fn unknown_liveness_keeps_everything() {
        let prev = HashMap::from([(key(99, 5001), (0, 0))]);
        let current = HashMap::from([(key(99, 5001), (125_000, 0))]);
        let known: HashSet<u32> = [99].into_iter().collect();
        let out = compute_rates(&prev, &current, None, &known, &HashMap::new(), 1.0);
        assert_eq!(out.rates.len(), 1);
        assert!(out.exited_pids.is_empty());
    }

    /// نام نامشخص با pid- پیشوند می‌خورد.
    #[test]
    fn missing_name_falls_back_to_pid_label() {
        let prev = HashMap::from([(key(42, 5000), (0, 0))]);
        let current = HashMap::from([(key(42, 5000), (125_000, 0))]);
        let out = compute_rates(&prev, &current, None, &no_known(), &HashMap::new(), 1.0);
        assert_eq!(out.rates[0].name, "pid-42");
    }
}
