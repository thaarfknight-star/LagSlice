//! اسکنر سرورهای استریم (StreamScanner) — پورت Rust از نسخه‌ی پایتون.
//!
//! تست موازی سرورها: پینگ ICMP + اتصال TCP به پورت RTMP + امتیازدهی.
//! امتیاز کمتر = بهتر؛ فرمول اثبات‌شده‌ی StreamScanner:
//!     score = tcp_ms + ping_ms * 0.3 + loss * 20
//! سرور قطع (TCP ناموفق): score = 1_000_000 (DOWN_SCORE)
//!
//! لیست سرورها در servers.json کنار exe نگه‌داری می‌شود (همان الگوی
//! whitelist.json) تا بین اجراها بماند.

use serde::{Deserialize, Serialize};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

pub const DEFAULT_RTMP_PORT: u16 = 1935;
pub const DOWN_SCORE: f64 = 1_000_000.0;
const PING_COUNT: usize = 4;
const PING_TIMEOUT_MS: u32 = 1000;
const TCP_TIMEOUT: Duration = Duration::from_secs(3);

/// یک سرور استریم در لیست اسکنر.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StreamServer {
    pub id: String,
    pub name: String,
    pub region: String,
    pub host: String,
    pub port: u16,
}

/// نتیجه‌ی پروب کامل یک سرور.
#[derive(Debug, Clone, Serialize)]
pub struct ProbeResult {
    pub id: String,
    pub name: String,
    pub region: String,
    pub host: String,
    pub port: u16,
    /// میانگین پینگ موفق‌ها (ms)؛ None یعنی هیچ پینگی جواب نداد.
    pub ping_ms: Option<f64>,
    /// درصد تلفات پینگ (۰ تا ۱۰۰).
    pub loss: f64,
    /// زمان اتصال TCP (ms)؛ None یعنی اتصال ناموفق.
    pub tcp_ms: Option<f64>,
    pub ok: bool,
    pub score: f64,
}

impl StreamServer {
    /// آدرس RTMP کامل: rtmp://host:port/live
    pub fn rtmp_url(&self) -> String {
        if self.host.trim().is_empty() {
            return String::new();
        }
        format!("rtmp://{}:{}/live", self.host.trim(), self.port)
    }

    /// پاک‌سازی یک ردیف ورودی: برش فاصله‌ها و پورت پیش‌فرض.
    fn cleaned(mut self) -> Self {
        self.name = self.name.trim().to_string();
        self.region = self.region.trim().to_string();
        self.host = self.host.trim().to_string();
        if self.port == 0 {
            self.port = DEFAULT_RTMP_PORT;
        }
        self
    }
}

/// لیست پیش‌فرض وقتی هیچ فایلی نیست — نمونه‌ی اولیه؛ هاست واقعی را
/// کاربر خودش وارد می‌کند (عین نسخه‌ی پایتون).
pub fn default_servers() -> Vec<StreamServer> {
    vec![StreamServer {
        id: "ms1".into(),
        name: "MasterStream 1".into(),
        region: "ir".into(),
        host: String::new(),
        port: DEFAULT_RTMP_PORT,
    }]
}

/// مسیر فایل لیست سرورها: کنار exe (یا override با متغیر محیطی).
pub fn servers_path() -> PathBuf {
    if let Ok(p) = std::env::var("LAGSLICE_SERVERS_PATH") {
        if !p.trim().is_empty() {
            return PathBuf::from(p);
        }
    }
    let dir = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."));
    dir.join("servers.json")
}

/// خواندن لیست از یک مسیر مشخص. فایل نیست/خراب است ← لیست پیش‌فرض.
pub fn load_servers_from(path: &Path) -> Vec<StreamServer> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return default_servers();
    };
    match serde_json::from_str::<Vec<StreamServer>>(&text) {
        Ok(list) => list.into_iter().map(|s| s.cleaned()).collect(),
        Err(_) => default_servers(),
    }
}

pub fn load_servers() -> Vec<StreamServer> {
    load_servers_from(&servers_path())
}

/// ذخیره‌ی اتمیک لیست در یک مسیر مشخص (tmp + rename)؛ خروجی همان
/// لیست پاک‌سازی‌شده‌ای است که ذخیره شد.
pub fn save_servers_to(path: &Path, servers: &[StreamServer]) -> Result<Vec<StreamServer>, String> {
    let clean: Vec<StreamServer> = servers.iter().cloned().map(|s| s.cleaned()).collect();
    let text = serde_json::to_string_pretty(&clean).map_err(|e| e.to_string())?;
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, text).map_err(|e| e.to_string())?;
    std::fs::rename(&tmp, path).map_err(|e| e.to_string())?;
    Ok(clean)
}

pub fn save_servers(servers: &[StreamServer]) -> Result<Vec<StreamServer>, String> {
    save_servers_to(&servers_path(), servers)
}

/// فرمول امتیاز — خالص و قابل تست. عین StreamScanner:
/// موفق = tcp + ping*0.3 + loss*20 (اگر پینگ باشد)؛ ناموفق = DOWN_SCORE.
pub fn compute_score(ok: bool, tcp_ms: Option<f64>, ping_ms: Option<f64>, loss: f64) -> f64 {
    if !ok {
        return DOWN_SCORE;
    }
    let mut score = tcp_ms.unwrap_or(0.0);
    if let Some(ping) = ping_ms {
        score += ping * 0.3 + loss * 20.0;
    }
    score
}

/// پروب کامل یک سرور: TCP به پورت RTMP + پینگ ICMP (چهار تلاش).
/// روی هر سکویی کار می‌کند؛ پینگ واقعی ICMP فقط روی ویندوز پیاده شده
/// (monitor::ping_ipv4) و روی بقیه None برمی‌گردد.
pub fn probe_server(server: &StreamServer) -> ProbeResult {
    let host = server.host.trim();
    let base = ProbeResult {
        id: server.id.clone(),
        name: server.name.clone(),
        region: server.region.clone(),
        host: host.to_string(),
        port: server.port,
        ping_ms: None,
        loss: 100.0,
        tcp_ms: None,
        ok: false,
        score: DOWN_SCORE,
    };
    if host.is_empty() {
        return base;
    }
    // resolve: اولین آدرس IPv4 برای هر دو پروب.
    let addr = (host, server.port)
        .to_socket_addrs()
        .ok()
        .and_then(|mut it| it.find(|a| a.is_ipv4()));
    let Some(addr) = addr else {
        return base;
    };

    // TCP probe — زمان برقراری اتصال.
    let started = Instant::now();
    let tcp_ms = match TcpStream::connect_timeout(&addr, TCP_TIMEOUT) {
        Ok(_) => Some(started.elapsed().as_secs_f64() * 1000.0),
        Err(_) => None,
    };
    let ok = tcp_ms.is_some();

    // ICMP ping — میانگین موفق‌ها + درصد تلفات.
    let ip = match addr.ip() {
        std::net::IpAddr::V4(v4) => v4.octets(),
        _ => return base,
    };
    let mut sum = 0.0f64;
    let mut replies = 0usize;
    for _ in 0..PING_COUNT {
        if let Some(ms) = crate::monitor::ping_ipv4(ip, PING_TIMEOUT_MS) {
            sum += ms as f64;
            replies += 1;
        }
    }
    let (ping_ms, loss) = if replies > 0 {
        (
            Some(sum / replies as f64),
            (PING_COUNT - replies) as f64 / PING_COUNT as f64 * 100.0,
        )
    } else {
        (None, 100.0)
    };

    ProbeResult {
        ping_ms,
        loss,
        tcp_ms,
        ok,
        score: compute_score(ok, tcp_ms, ping_ms, loss),
        ..base
    }
}

/// اسکن موازی همه‌ی سرورها (یک نخ به‌ازای هر سرور)؛ خروجی به ترتیب
/// ورودی برمی‌گردد تا فرانت خودش بر اساس امتیاز مرتب کند.
pub fn scan_all(servers: &[StreamServer]) -> Vec<ProbeResult> {
    std::thread::scope(|scope| {
        let handles: Vec<_> = servers
            .iter()
            .map(|s| scope.spawn(move || probe_server(s)))
            .collect();
        handles
            .into_iter()
            .map(|h| h.join().expect("probe thread panicked"))
            .collect()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn score_down_server_is_max() {
        assert_eq!(compute_score(false, None, Some(10.0), 0.0), DOWN_SCORE);
    }

    #[test]
    fn score_formula_matches_streamscanner() {
        // tcp=50, ping=20, loss=25% → 50 + 6 + 500 = 556
        assert_eq!(compute_score(true, Some(50.0), Some(20.0), 25.0), 556.0);
    }

    #[test]
    fn score_without_ping_is_tcp_only() {
        assert_eq!(compute_score(true, Some(42.0), None, 100.0), 42.0);
    }

    #[test]
    fn rtmp_url_uses_default_shape() {
        let s = StreamServer {
            id: "x".into(),
            name: "n".into(),
            region: "ir".into(),
            host: "example.com".into(),
            port: 1935,
        };
        assert_eq!(s.rtmp_url(), "rtmp://example.com:1935/live");
    }

    #[test]
    fn servers_roundtrip_persists() {
        let dir = std::env::temp_dir().join(format!("lagslice-scan-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("servers.json");
        let list = vec![StreamServer {
            id: "a".into(),
            name: " سرور یک ".into(),
            region: "ir".into(),
            host: " 10.0.0.1 ".into(),
            port: 0,
        }];
        let saved = save_servers_to(&path, &list).unwrap();
        assert_eq!(saved[0].host, "10.0.0.1");
        assert_eq!(saved[0].port, DEFAULT_RTMP_PORT);
        let loaded = load_servers_from(&path);
        assert_eq!(loaded, saved);
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn probe_empty_host_is_down() {
        let s = StreamServer {
            id: "e".into(),
            name: String::new(),
            region: String::new(),
            host: "  ".into(),
            port: DEFAULT_RTMP_PORT,
        };
        let r = probe_server(&s);
        assert!(!r.ok);
        assert_eq!(r.score, DOWN_SCORE);
    }
}
