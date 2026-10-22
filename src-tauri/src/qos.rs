//! موتور رزرو و سقف آپلود per-app با Windows Policy-based QoS.
//!
//! مکانیزم: برای هر برنامه یک پالیسی در
//! `HKLM\SOFTWARE\Policies\Microsoft\Windows\QoS\<LagSlice-{exe}>`
//! نوشته می‌شود (Application Name + Throttle Rate خروجی برحسب KBps).
//! این همان کلیدهایی است که Group Policy Editor می‌نویسد؛ ویندوز آن‌ها را
//! با رفرش پالیسی (gpupdate) اعمال می‌کند.
//!
//! قوانین ایمنی:
//! - فقط ساب‌کی‌هایی با پیشوند «LagSlice-» ساخته/حذف می‌شوند؛ پالیسی‌های
//!   خود کاربر یا سازمان هرگز دست نمی‌خورند.
//! - حذف کامل (clear_all) هنگام خروج برنامه و از دکمه‌ی «حذف همه‌ی سقف‌ها»
//!   در دسترس است تا هیچ پالیسی یتیمی روی سیستم نماند.
//!
//! بازیابی بعد از کرش (همین ماژول):
//! اگر برنامه کرش کند یا سیستم خاموش شود، رویداد Exit اجرا نمی‌شود و
//! پالیسی‌ها روی سیستم می‌مانند. برای همین هنگام هر استارت،
//! [`recover_on_startup`] ریشه‌ی QoS را اسکن می‌کند و هر پالیسی
//! «LagSlice-» به‌جامانده را امن پاک می‌کند؛ شروعِ تمیز یعنی هیچ سقفی
//! از اجرای قبلی فعال نیست. پاک‌سازی تک‌تک انجام می‌شود و خطای یک
//! پالیسی جلوی پاک‌شدن بقیه را نمی‌گیرد — گزارش کامل برمی‌گردد.
//!
//! لیست سفید برنامه‌ها (whitelist):
//! برنامه‌های این لیست هرگز سقف نمی‌گیرند. لیست در فایل JSON کنار فایل
//! اجرایی (`whitelist.json`، هم‌فرمت `safelist.json` نسخه‌ی پایتون)
//! نگه داشته می‌شود تا بین اجراها بماند؛ اگر فایل نباشد یا خراب باشد،
//! لیست پیش‌فرض استفاده می‌شود و برنامه هرگز به‌خاطر آن کرش نمی‌کند.
//!
//! محدودیت فاز اول (صادقانه): این مکانیزم سقف سخت و سراسری per-app است،
//! نه shaping لحظه‌ای per-flow؛ آن بخش درایور کرنل امضاشده می‌خواهد (فاز دو).

use serde::Serialize;
use std::collections::HashSet;
use std::path::{Path, PathBuf};

pub const POLICY_ROOT: &str = r"SOFTWARE\Policies\Microsoft\Windows\QoS";
pub const POLICY_PREFIX: &str = "LagSlice-";

/// محاسبه‌ی سقف هر برنامه برای رزرو استریم — تابع خالص و قابل تست.
///
/// `total_up_kbps`: آپلود کل اندازه‌گیری‌شده، `reserve_kbps`: سهم رزروشده
/// برای استریم، `apps`: برنامه‌های غیرمجاز (exe, مصرف فعلی Kbps).
/// خروجی: برای هر برنامه سقف Kbps متناسب با سهم مصرف فعلی‌اش از بودجه‌ی
/// باقی‌مانده (total − reserve)، با کف ۶۴ Kbps برای هر برنامه.
pub fn compute_caps(
    total_up_kbps: f64,
    reserve_kbps: f64,
    apps: &[(String, f64)],
) -> Vec<(String, f64)> {
    let budget = (total_up_kbps - reserve_kbps).max(0.0);
    let used: f64 = apps.iter().map(|(_, u)| *u).sum();
    apps.iter()
        .map(|(exe, usage)| {
            let share = if used > 0.0 {
                budget * (usage / used)
            } else if apps.is_empty() {
                0.0
            } else {
                budget / apps.len() as f64
            };
            (exe.clone(), share.max(64.0))
        })
        .collect()
}

/// نام امن پالیسی برای یک فایل اجرایی.
pub fn policy_name(exe: &str) -> String {
    let stem = exe
        .trim_end_matches(".exe")
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '-' || c == '_' { c } else { '_' })
        .collect::<String>();
    format!("{POLICY_PREFIX}{stem}")
}

/// آیا این نام ساب‌کی، پالیسی ساخته‌ی LagSlice است؟
/// تنها معیار پاک‌سازی امن: پیشوند دقیق «LagSlice-». هر چیز دیگری —
/// پالیسی کاربر، سازمان یا خود ویندوز — هرگز حذف نمی‌شود.
pub fn is_lagslice_policy(name: &str) -> bool {
    name.starts_with(POLICY_PREFIX)
}

// ---------------------------------------------------------------------------
// بازیابی بعد از کرش
// ---------------------------------------------------------------------------

/// گزارش بازیابی هنگام استارت: چه پیدا شد، چه پاک شد، چه پاک نشد.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct RecoveryReport {
    /// نام همه‌ی پالیسی‌های «LagSlice-» پیدا‌شده در اسکن استارت.
    pub found: Vec<String>,
    /// آن‌هایی که با موفقیت حذف شدند.
    pub removed: Vec<String>,
    /// آن‌هایی که حذفشان خطا داد، به‌صورت «نام: خطا» — یکی‌یکی گزارش
    /// می‌شوند تا خطای یک پالیسی بقیه را قربانی نکند.
    pub failed: Vec<String>,
}

impl RecoveryReport {
    /// آیا چیزی پیدا شد که نیاز به رفرش پالیسی‌های ویندوز داشته باشد؟
    pub fn changed(&self) -> bool {
        !self.removed.is_empty()
    }
}

/// حذف یک پالیسی با نام کامل ساب‌کی — با گارد پیشوند: نامی بدون
/// «LagSlice-» تحت هیچ شرایطی حذف نمی‌شود.
#[cfg(windows)]
fn delete_policy_by_name(name: &str) -> Result<(), String> {
    imp::delete_policy(name)
}

#[cfg(not(windows))]
fn delete_policy_by_name(name: &str) -> Result<(), String> {
    if is_lagslice_policy(name) {
        Ok(())
    } else {
        Err(format!("نام پالیسی بدون پیشوند {POLICY_PREFIX} حذف نمی‌شود: {name}"))
    }
}

/// اسکن ریشه‌ی QoS هنگام استارت و پاک‌سازی امن همه‌ی پالیسی‌های
/// به‌جامانده از اجرای قبلی (کرش، خاموشی سیستم، بسته‌شدن اجباری).
///
/// هرگز panic نمی‌کند و خطا را propagate نمی‌کند: اگر خود اسکن هم خطا
/// بدهد، فقط در `failed` گزارش می‌شود و برنامه عادی بالا می‌آید.
pub fn recover_on_startup() -> RecoveryReport {
    let found = match list_policies() {
        Ok(names) => names,
        Err(e) => {
            return RecoveryReport {
                found: Vec::new(),
                removed: Vec::new(),
                failed: vec![format!("اسکن پالیسی‌ها ناموفق بود: {e}")],
            };
        }
    };
    let mut removed = Vec::new();
    let mut failed = Vec::new();
    for name in &found {
        match delete_policy_by_name(name) {
            Ok(()) => removed.push(name.clone()),
            Err(e) => failed.push(format!("{name}: {e}")),
        }
    }
    RecoveryReport {
        found,
        removed,
        failed,
    }
}

// ---------------------------------------------------------------------------
// لیست سفید برنامه‌ها — ماندگاری (persistence)
// ---------------------------------------------------------------------------

/// لیست سفید پیش‌فرض — همان DEFAULT_SAFELIST نسخه‌ی پایتون (گیم و استریم
/// هرگز سقف نمی‌گیرند). وقتی فایل ذخیره‌شده نیست یا خراب است استفاده می‌شود.
pub fn default_whitelist() -> Vec<String> {
    [
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
        "discord.exe",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect()
}

/// پاک‌سازی لیست سفید: trim، حذف خالی‌ها، حذف تکراری‌ها بدون حساسیت به
/// بزرگی/کوچکی حروف (اولین نگارشِ دیده‌شده می‌ماند) و مرتب‌سازی الفبایی
/// بدون حساسیت به حروف تا فایل ذخیره‌شده همیشه خروجی قطعی (deterministic)
/// داشته باشد — دقیقاً مثل `save_safelist` نسخه‌ی پایتون.
pub fn normalize_whitelist<I: IntoIterator<Item = String>>(items: I) -> Vec<String> {
    let mut seen: HashSet<String> = HashSet::new();
    let mut out: Vec<String> = Vec::new();
    for item in items {
        let name = item.trim().to_string();
        if name.is_empty() {
            continue;
        }
        if seen.insert(name.to_lowercase()) {
            out.push(name);
        }
    }
    out.sort_by(|a, b| a.to_lowercase().cmp(&b.to_lowercase()));
    out
}

/// آیا exe در لیست سفید هست؟ (بدون حساسیت به بزرگی/کوچکی حروف)
pub fn is_whitelisted(exe: &str, whitelist: &[String]) -> bool {
    whitelist.iter().any(|w| w.eq_ignore_ascii_case(exe.trim()))
}

/// ادغام دو لیست سفید (مثلاً لیست ذخیره‌شده + لیست ارسالی فرانت) با
/// همان پاک‌سازی [`normalize_whitelist`].
pub fn merge_whitelists(a: &[String], b: &[String]) -> Vec<String> {
    normalize_whitelist(a.iter().chain(b.iter()).cloned())
}

/// مسیر فایل لیست سفید: کنار فایل اجرایی (portable، مثل نسخه‌ی پایتون).
/// با متغیر محیطی `LAGSLICE_WHITELIST_PATH` قابل override است (تست/دیباگ).
pub fn whitelist_path() -> PathBuf {
    if let Ok(p) = std::env::var("LAGSLICE_WHITELIST_PATH") {
        if !p.trim().is_empty() {
            return PathBuf::from(p);
        }
    }
    let dir = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."));
    dir.join("whitelist.json")
}

/// خواندن لیست سفید از یک مسیر مشخص.
/// فایل نیست / خراب است / آرایه‌ی رشته نیست ← لیست پیش‌فرض.
/// آرایه‌ی خالیِ معتبر ← لیست خالی (یعنی کاربر عمداً همه را برداشته).
pub fn load_whitelist_from(path: &Path) -> Vec<String> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return default_whitelist();
    };
    let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) else {
        return default_whitelist();
    };
    let Some(arr) = value.as_array() else {
        return default_whitelist();
    };
    let names: Vec<String> = arr
        .iter()
        .filter_map(|v| v.as_str().map(|s| s.to_string()))
        .collect();
    // آرایه‌ای که هیچ رشته‌ای ندارد ولی معتبر است (مثلاً []) یعنی لیست خالیِ عمدی؛
    // فقط وقتی JSON آرایه نیست یا پارس نمی‌شود سراغ پیش‌فرض می‌رویم.
    normalize_whitelist(names)
}

/// خواندن لیست سفید از مسیر پیش‌فرض؛ اگر `whitelist.json` نبود ولی
/// `safelist.json` نسخه‌ی پایتون در همان پوشه بود، همان خوانده می‌شود
/// تا لیست امن کاربر در مهاجرت گم نشود.
pub fn load_whitelist() -> Vec<String> {
    let path = whitelist_path();
    if !path.exists() {
        if let Some(dir) = path.parent() {
            let legacy = dir.join("safelist.json");
            if legacy.exists() {
                return load_whitelist_from(&legacy);
            }
        }
    }
    load_whitelist_from(&path)
}

/// ذخیره‌ی اتمیک لیست سفید در یک مسیر مشخص: اول در فایل موقتِ کنار همان
/// مسیر نوشته می‌شود و بعد rename می‌شود، تا کرش وسط ذخیره فایل اصلی را
/// خراب نکند. خروجی: لیست پاک‌سازی‌شده‌ای که واقعاً ذخیره شد.
pub fn save_whitelist_to(path: &Path, whitelist: &[String]) -> Result<Vec<String>, String> {
    let clean = normalize_whitelist(whitelist.iter().cloned());
    if let Some(parent) = path.parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("ساخت پوشه‌ی لیست سفید ناموفق بود: {e}"))?;
        }
    }
    let text = serde_json::to_string_pretty(&clean)
        .map_err(|e| format!("ساخت JSON لیست سفید ناموفق بود: {e}"))?;
    let tmp = PathBuf::from(format!("{}.tmp", path.display()));
    std::fs::write(&tmp, text)
        .map_err(|e| format!("نوشتن لیست سفید ناموفق بود: {e}"))?;
    if let Err(e) = std::fs::rename(&tmp, path) {
        // روی ویندوز rename روی فایل موجود خطا می‌دهد؛ مقصد را برمی‌داریم و دوباره.
        let _ = std::fs::remove_file(path);
        std::fs::rename(&tmp, path).map_err(|e2| {
            let _ = std::fs::remove_file(&tmp);
            format!("ذخیره‌ی لیست سفید ناموفق بود: {e} / {e2}")
        })?;
    }
    Ok(clean)
}

/// ذخیره‌ی لیست سفید در مسیر پیش‌فرض ([`whitelist_path`]).
pub fn save_whitelist(whitelist: &[String]) -> Result<Vec<String>, String> {
    save_whitelist_to(&whitelist_path(), whitelist)
}

#[cfg(windows)]
mod imp {
    use super::{policy_name, POLICY_PREFIX, POLICY_ROOT};
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::ERROR_SUCCESS;
    use windows::Win32::System::Registry::{
        RegCloseKey, RegCreateKeyExW, RegDeleteTreeW, RegEnumKeyExW, RegOpenKeyExW,
        RegSetValueExW, HKEY, HKEY_LOCAL_MACHINE, KEY_ALL_ACCESS, KEY_READ,
        REG_CREATE_KEY_DISPOSITION, REG_OPTION_NON_VOLATILE, REG_SZ,
    };

    fn wide(s: &str) -> Vec<u16> {
        OsStr::new(s).encode_wide().chain(Some(0)).collect()
    }

    fn set_sz(key: HKEY, name: &str, value: &str) -> Result<(), String> {
        let name_w = wide(name);
        let val_w: Vec<u16> = OsStr::new(value).encode_wide().chain(Some(0)).collect();
        let bytes: &[u8] = unsafe {
            std::slice::from_raw_parts(val_w.as_ptr() as *const u8, val_w.len() * 2)
        };
        let rc = unsafe {
            RegSetValueExW(key, PCWSTR(name_w.as_ptr()), 0, REG_SZ, Some(bytes))
        };
        if rc == ERROR_SUCCESS {
            Ok(())
        } else {
            Err(format!("RegSetValueExW({name}) -> {:?}", rc))
        }
    }

    /// ساخت/به‌روزرسانی پالیسی سقف آپلود برای یک exe. سقف Kbps است و به
    /// KBps (واحد خود ویندوز برای Throttle Rate) تبدیل می‌شود.
    pub fn set_cap(exe: &str, cap_kbps: f64) -> Result<(), String> {
        let path = format!(r"{}\{}", POLICY_ROOT, policy_name(exe));
        let path_w = wide(&path);
        let mut key = HKEY::default();
        let mut disp = REG_CREATE_KEY_DISPOSITION::default();
        let rc = unsafe {
            RegCreateKeyExW(
                HKEY_LOCAL_MACHINE,
                PCWSTR(path_w.as_ptr()),
                0,
                PCWSTR::null(),
                REG_OPTION_NON_VOLATILE,
                KEY_ALL_ACCESS,
                None,
                &mut key,
                Some(&mut disp),
            )
        };
        if rc != ERROR_SUCCESS {
            return Err(format!("RegCreateKeyExW -> {:?} (ادمین لازم است)", rc));
        }
        let kbps = (cap_kbps / 8.0).max(1.0).round() as i64;
        let res = (|| {
            set_sz(key, "Version", "1.0")?;
            set_sz(key, "Application Name", exe)?;
            set_sz(key, "Protocol", "*")?;
            set_sz(key, "Local Port", "*")?;
            set_sz(key, "Local IP", "*")?;
            set_sz(key, "Local IP Prefix Length", "*")?;
            set_sz(key, "Remote Port", "*")?;
            set_sz(key, "Remote IP", "*")?;
            set_sz(key, "Remote IP Prefix Length", "*")?;
            set_sz(key, "DSCP Value", "-1")?;
            set_sz(key, "Throttle Rate", &kbps.to_string())?;
            Ok::<(), String>(())
        })();
        unsafe {
            let _ = RegCloseKey(key);
        }
        res
    }

    /// حذف پالیسی یک exe (اگر باشد).
    pub fn remove_cap(exe: &str) -> Result<(), String> {
        delete_policy(&policy_name(exe))
    }

    /// حذف یک ساب‌کی پالیسی با نام کامل — با گارد پیشوند: هر نامی که با
    /// «LagSlice-» شروع نشود رد می‌شود، حتی اگر کالر اشتباه کرده باشد.
    pub fn delete_policy(name: &str) -> Result<(), String> {
        if !name.starts_with(POLICY_PREFIX) {
            return Err(format!(
                "نام پالیسی بدون پیشوند {POLICY_PREFIX} حذف نمی‌شود: {name}"
            ));
        }
        let root_w = wide(POLICY_ROOT);
        let name_w = wide(name);
        let mut root = HKEY::default();
        let rc = unsafe {
            RegOpenKeyExW(
                HKEY_LOCAL_MACHINE,
                PCWSTR(root_w.as_ptr()),
                0,
                KEY_ALL_ACCESS,
                &mut root,
            )
        };
        if rc != ERROR_SUCCESS {
            return Ok(()); // ریشه اصلاً نیست یعنی پالیسی‌ای هم نیست
        }
        let rc = unsafe { RegDeleteTreeW(root, PCWSTR(name_w.as_ptr())) };
        unsafe {
            let _ = RegCloseKey(root);
        }
        if rc == ERROR_SUCCESS || rc.0 == 2 {
            Ok(())
        } else {
            Err(format!("RegDeleteTreeW({name}) -> {:?}", rc))
        }
    }

    /// اسکن ریشه‌ی QoS و برگرداندن نام همه‌ی ساب‌کی‌های «LagSlice-»
    /// (مرتب‌شده). پالیسی‌های بقیه نه برگردانده می‌شوند نه دست می‌خورند.
    /// ریشه وجود نداشته باشد یعنی هیچ پالیسی‌ای نیست: لیست خالی، بدون خطا.
    pub fn list_policies() -> Result<Vec<String>, String> {
        let root_w = wide(POLICY_ROOT);
        let mut root = HKEY::default();
        let rc = unsafe {
            RegOpenKeyExW(
                HKEY_LOCAL_MACHINE,
                PCWSTR(root_w.as_ptr()),
                0,
                KEY_READ,
                &mut root,
            )
        };
        if rc != ERROR_SUCCESS {
            return Ok(Vec::new());
        }
        let mut names: Vec<String> = Vec::new();
        let mut idx = 0u32;
        loop {
            let mut buf = [0u16; 256];
            let mut len = buf.len() as u32;
            let rc = unsafe {
                RegEnumKeyExW(root, idx, windows::core::PWSTR(buf.as_mut_ptr()), &mut len, None, windows::core::PWSTR(std::ptr::null_mut()), None, None)
            };
            if rc != ERROR_SUCCESS {
                break;
            }
            let name = String::from_utf16_lossy(&buf[..len as usize]);
            if name.starts_with(POLICY_PREFIX) {
                names.push(name);
            }
            idx += 1;
        }
        unsafe {
            let _ = RegCloseKey(root);
        }
        names.sort();
        Ok(names)
    }

    /// حذف همه‌ی پالیسی‌های ساخته‌ی LagSlice (پیشوند LagSlice-).
    pub fn clear_all() -> Result<(), String> {
        for n in list_policies()? {
            delete_policy(&n)?;
        }
        Ok(())
    }

    /// رفرش پالیسی‌های گروهی تا ویندوز سقف‌ها را اعمال کند.
    pub fn refresh_policies() {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = std::process::Command::new("gpupdate")
            .args(["/target:computer", "/force"])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn();
    }
}

#[cfg(windows)]
pub use imp::{clear_all, list_policies, refresh_policies, remove_cap, set_cap};

#[cfg(not(windows))]
pub fn set_cap(_exe: &str, _cap_kbps: f64) -> Result<(), String> {
    Err("فقط ویندوز".into())
}
#[cfg(not(windows))]
pub fn remove_cap(_exe: &str) -> Result<(), String> {
    Err("فقط ویندوز".into())
}
#[cfg(not(windows))]
pub fn clear_all() -> Result<(), String> {
    Ok(())
}
#[cfg(not(windows))]
pub fn list_policies() -> Result<Vec<String>, String> {
    Ok(Vec::new())
}
#[cfg(not(windows))]
pub fn refresh_policies() {}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_whitelist_path(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "lagslice-qos-test-{}-{tag}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir.join("whitelist.json")
    }

    #[test]
    fn policy_name_sanitizes_and_prefixes() {
        assert_eq!(policy_name("chrome.exe"), "LagSlice-chrome");
        assert_eq!(policy_name("Meld Studio.exe"), "LagSlice-Meld_Studio");
        assert!(is_lagslice_policy(&policy_name("cs2.exe")));
    }

    #[test]
    fn only_lagslice_prefix_is_ours() {
        assert!(is_lagslice_policy("LagSlice-chrome"));
        assert!(!is_lagslice_policy("MyCompany-VPN"));
        assert!(!is_lagslice_policy("LagSliceX-chrome"));
        assert!(!is_lagslice_policy(""));
    }

    #[test]
    fn delete_guard_rejects_foreign_names() {
        // روی غیر-ویندوز هم گارد باید قبل از هر کاری جلوی نام خارجی را بگیرد.
        assert!(delete_policy_by_name("SomeOtherPolicy").is_err());
        assert!(delete_policy_by_name("LagSlice-chrome").is_ok());
    }

    #[test]
    fn recovery_on_clean_system_is_empty_and_safe() {
        // روی لینوکس (CI) رجیستری نیست: اسکن خالی، بدون failed جعلی.
        let report = recover_on_startup();
        assert!(report.found.is_empty());
        assert!(report.removed.is_empty());
        assert!(!report.changed());
        assert_eq!(list_policies().unwrap(), Vec::<String>::new());
    }

    #[test]
    fn compute_caps_keeps_floor_and_budget_proportions() {
        let apps = vec![
            ("a.exe".to_string(), 300.0),
            ("b.exe".to_string(), 100.0),
        ];
        let caps = compute_caps(1000.0, 200.0, &apps);
        assert_eq!(caps[0].1, 600.0);
        assert_eq!(caps[1].1, 200.0);
        let tiny = compute_caps(100.0, 99.0, &apps);
        assert!(tiny.iter().all(|(_, c)| *c >= 64.0));
    }

    #[test]
    fn normalize_dedups_case_insensitively_trims_and_sorts() {
        let out = normalize_whitelist(vec![
            "  Chrome.exe ".to_string(),
            "chrome.EXE".to_string(),
            "".to_string(),
            "   ".to_string(),
            "cs2.exe".to_string(),
        ]);
        assert_eq!(out, vec!["Chrome.exe".to_string(), "cs2.exe".to_string()]);
    }

    #[test]
    fn whitelist_matching_is_case_insensitive() {
        let wl = vec!["CS2.exe".to_string(), "meld.exe".to_string()];
        assert!(is_whitelisted("cs2.EXE", &wl));
        assert!(is_whitelisted(" Meld.exe ", &wl));
        assert!(!is_whitelisted("chrome.exe", &wl));
    }

    #[test]
    fn merge_whitelists_unions_without_duplicates() {
        let merged = merge_whitelists(
            &["cs2.exe".to_string()],
            &["CS2.exe".to_string(), "obs64.exe".to_string()],
        );
        assert_eq!(merged, vec!["cs2.exe".to_string(), "obs64.exe".to_string()]);
    }

    #[test]
    fn whitelist_roundtrip_through_disk() {
        let path = temp_whitelist_path("roundtrip");
        let saved = save_whitelist_to(
            &path,
            &["CS2.exe".to_string(), " cs2.exe ".to_string(), "obs64.exe".to_string()],
        )
        .unwrap();
        assert_eq!(saved, vec!["CS2.exe".to_string(), "obs64.exe".to_string()]);
        assert_eq!(load_whitelist_from(&path), saved);
        // فایل موقتِ اتمیک نباید جا بماند.
        assert!(!PathBuf::from(format!("{}.tmp", path.display())).exists());
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn whitelist_missing_or_corrupt_falls_back_to_defaults() {
        let dir = std::env::temp_dir().join(format!(
            "lagslice-qos-test-{}-fallback",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let missing = dir.join("nope.json");
        assert_eq!(load_whitelist_from(&missing), default_whitelist());

        let corrupt = dir.join("whitelist.json");
        std::fs::write(&corrupt, "{not json").unwrap();
        assert_eq!(load_whitelist_from(&corrupt), default_whitelist());

        std::fs::write(&corrupt, "{\"exe\": 1}").unwrap();
        assert_eq!(load_whitelist_from(&corrupt), default_whitelist());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn whitelist_empty_array_is_an_intentional_empty_list() {
        let path = temp_whitelist_path("empty");
        std::fs::write(&path, "[]").unwrap();
        assert_eq!(load_whitelist_from(&path), Vec::<String>::new());
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn default_whitelist_covers_game_and_stream() {
        let d = default_whitelist();
        assert!(is_whitelisted("cs2.exe", &d));
        assert!(is_whitelisted("meldstudio.exe", &d));
        assert!(is_whitelisted("obs64.exe", &d));
        assert!(!is_whitelisted("chrome.exe", &d));
    }
}
