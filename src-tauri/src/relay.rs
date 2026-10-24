// رله‌ی تطبیقی RTMP برای LagSlice
// Copyright (c) 2026 Taha Arefi — دوگانه‌ی MIT / Apache-2.0 (مطابق درخت جاری ریپو).
//
// مسئله: وقتی Meld مستقیم به Kick می‌فرستد و ظرفیت مسیر لحظه‌ای کمتر از
// بیت‌ریت انکودر می‌شود، فریم‌ها در صف TCP جمع می‌شوند و تأخیرِ دیده‌شده
// توسط بیننده همین‌طور بالا می‌رود. راه‌حل این ماژول: Meld با خروجی
// Custom RTMP به رله‌ی لوکال (127.0.0.1:1935/live) می‌فرستد؛ رله نرخ
// واقعی تخلیه به ingest مقصد را می‌سنجد و نرخ ارسال را با نردبان تطبیقی
// تنظیم می‌کند. وقتی صف خروجی از سقف می‌گذرد، به‌جای انباشته‌شدن تأخیر،
// قدیمی‌ترین GOP کاملِ ویدیو حذف می‌شود (کی‌فریم‌ها هرگز حذف نمی‌شوند،
// وگرنه دیکودر می‌شکند)؛ بیننده افت فریم‌ریت می‌بیند، نه رشد تأخیر.
//
// امنیت: کلید استریم مقصد فقط در حافظه نگه داشته می‌شود؛ هیچ‌وقت در
// لاگ، وضعیت، یا فایل دیسک نوشته نمی‌شود و در هیچ ساختار Debug چاپ
// نمی‌شود. فرانت آن را فقط در localStorage خود دستگاه نگه می‌دارد.
//
// این فایل فقط به std وابسته است تا منطقش (نردبان، سطل توکن، فیلتر GOP،
// پارس چانک و AMF0) با `rustc --test` بدون وابستگی ویندوز قابل آزمون باشد.

use std::collections::{HashMap, VecDeque};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

// ---------------------------------------------------------------- نردبان
/// نردبان بیت‌ریت خروجی (Kbps). سقف نردبان از تنظیم «بیت‌ریت استریم» برنامه
/// می‌آید (پیش‌فرض ۸۰۰۰ = سقف Kick)؛ پله‌ی آخر ۱۵۰۰ کف اضطراری است تا
/// استریم زنده بماند حتی وقتی مسیر خیلی تنگ است.
pub const LADDER_DEFAULT_TOP_KBPS: u32 = 8000;
pub const LADDER_FLOOR_KBPS: u32 = 1500;

/// تصمیم کنترل‌کننده در یک پنجره‌ی نمونه‌گیری (پنجره = ۲ ثانیه).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RelayDecision {
    Hold,
    StepDown,
    StepUp,
}

/// کنترل‌کننده‌ی نردبان با هیسترزیس نامتقارن — پایین سریع، بالا کند:
/// پایین‌آمدن = ۲ پنجره‌ی بد پیاپی (تأخیر دشمن است، معطل نمی‌کنیم)؛
/// بالارفتن = از ۳ پروب اخیر دست‌کم ۲ پروب بالای پله‌ی بالاتر × ۱٫۰۵
/// (معادل میانه‌ی ۳ پروب اخیر با ۵٪ حاشیه)، هر پله فقط یک قدم.
/// آستانه‌ها با حاشیه‌اند تا روی مرز نوسان نکنیم.
pub struct LadderController {
    pub rungs: Vec<u32>,
    pub idx: usize,
    bad_windows: u32,
    /// ۳ پروب اخیر (قدیمی‌ترین اول) برای قانون صعود میانه‌ای.
    probe_hist: std::collections::VecDeque<f64>,
    pub capacity_ema_kbps: f64,
}

impl LadderController {
    pub fn new(top_kbps: u32) -> Self {
        let mut rungs: Vec<u32> = vec![8000, 6000, 4000, 2500, 1500]
            .into_iter()
            .filter(|r| *r <= top_kbps)
            .collect();
        if rungs.is_empty() {
            rungs.push(top_kbps.max(LADDER_FLOOR_KBPS));
        }
        if *rungs.last().unwrap() != LADDER_FLOOR_KBPS && top_kbps > LADDER_FLOOR_KBPS {
            rungs.push(LADDER_FLOOR_KBPS);
        }
        Self {
            rungs,
            idx: 0,
            bad_windows: 0,
            probe_hist: std::collections::VecDeque::new(),
            capacity_ema_kbps: 0.0,
        }
    }

    pub fn current_kbps(&self) -> u32 {
        self.rungs[self.idx]
    }

    /// آیا پله‌ی جاری سقف نردبان است (وضعیت سالم)؟
    pub fn at_top(&self) -> bool {
        self.idx == 0
    }

    /// نمونه‌ی پنجره‌ی عادی (ارسال با سقف پله‌ی جاری). این نمونه فقط
    /// برای پایین‌آمدن معتبر است: چون ارسال سقف دارد، drain اندازه‌گیری
    /// شده هرگز از پله‌ی جاری بیشتر نمی‌شود، پس با همین نمونه نمی‌شود
    /// فهمید مسیر پله‌ی بالاتر را می‌کشد یا نه. پایین‌آمدن: میانگین
    /// نمایی < پله‌ی جاری × ۰٫۸۵ در ۲ پنجره‌ی پیاپی.
    pub fn note_capacity(&mut self, cap_kbps: f64) -> RelayDecision {
        if self.capacity_ema_kbps <= 0.0 {
            self.capacity_ema_kbps = cap_kbps;
        } else {
            // میانگین نمایی با آلفای ۰٫۴: به تغییرهای تازه وزن بیشتر می‌دهد
            // ولی تک‌نمونه‌های پرت را صاف می‌کند.
            self.capacity_ema_kbps =
                0.4 * cap_kbps + 0.6 * self.capacity_ema_kbps;
        }
        let cur = self.current_kbps() as f64;
        if self.capacity_ema_kbps < cur * 0.85 {
            self.bad_windows += 1;
            self.probe_hist.clear();
            if self.bad_windows >= 2 && self.idx + 1 < self.rungs.len() {
                self.idx += 1;
                self.bad_windows = 0;
                return RelayDecision::StepDown;
            }
        } else {
            self.bad_windows = 0;
        }
        RelayDecision::Hold
    }

    /// نمونه‌ی پنجره‌ی پروب (ارسال بدون سقف سطل توکن). فقط همین نمونه
    /// برای بالارفتن معتبر است، چون drain در آن واقعاً ظرفیت سوکت را
    /// نشان می‌دهد، نه سقف مصنوعی. بالارفتن (قانون ۰٫۹٫۸): از ۳ پروب
    /// اخیر دست‌کم ۲ پروب بالای پله‌ی بالاتر × ۱٫۰۵ باشند — معادل
    /// میانه‌ی ۳ پروب اخیر با ۵٪ حاشیه — هر بار فقط یک پله.
    /// قانون قبلی (۳ پروب پیاپی بالای ×۱٫۱۰) روی مسیر پرنوسان عملاً
    /// هیچ‌وقت صعود نمی‌داد: لاگ ۰٫۹٫۷ با پروب‌های ۲۰۲۱–۳۰۲۴ هیچ‌وقت
    /// ۳تای پیاپی بالای ۲۷۵۰ نداشت و نردبان ۸۵ ثانیه روی کف ۱۵۰۰ قفل
    /// ماند، در حالی که ظرفیت واقعی مسیر ~۲۵۰۰ بود. دلیل اصولی قانون
    /// تازه: با سقف سن ۰٫۹٫۶، صعود بیش‌ازحد فقط افت فریمِ محدود
    /// می‌آورد ولی ماندن پایین، عقب‌ماندگی بی‌نهایت در Meld می‌سازد —
    /// پس نردبان باید ظرفیت را تعقیب کند، نه در کف بماند. نزول همان
    /// ۲ پنجره‌ی بد می‌ماند تا صعود اشتباه سریع اصلاح شود.
    pub fn note_probe(&mut self, probe_kbps: f64) -> RelayDecision {
        if self.idx == 0 {
            self.probe_hist.clear();
            return RelayDecision::Hold;
        }
        self.probe_hist.push_back(probe_kbps);
        while self.probe_hist.len() > 3 {
            self.probe_hist.pop_front();
        }
        // میانه‌ی ۳ پروب اخیر لازم است: با کمتر از ۳ نمونه، هنوز
        // پنجره‌ی کامل نداریم و صعود نمی‌کنیم.
        if self.probe_hist.len() == 3 {
            let next = self.rungs[self.idx - 1] as f64;
            let good = self
                .probe_hist
                .iter()
                .filter(|p| **p > next * 1.05)
                .count();
            if good >= 2 {
                self.idx -= 1;
                self.probe_hist.clear();
                self.bad_windows = 0;
                return RelayDecision::StepUp;
            }
        }
        RelayDecision::Hold
    }
}

// ------------------------------------------------------------- سطل توکن
/// سطل توکن برای سقف نرخ ارسال: با نرخ پله‌ی جاری پر می‌شود و هر بایت
/// ارسالی یک توکن مصرف می‌کند. وقتی خالی است، فرستنده صبر می‌کند —
/// همین صبر است که صف را می‌سازد و فیلتر GOP را فعال می‌کند.
pub struct TokenBucket {
    pub rate_kbps: f64,
    tokens: f64,
    capacity: f64,
    last: Instant,
}

impl TokenBucket {
    pub fn new(rate_kbps: f64) -> Self {
        Self {
            rate_kbps,
            tokens: 0.0,
            capacity: rate_kbps * 125.0, // یک ثانیه بافر توکن (Kbps→Byte/s)
            last: Instant::now(),
        }
    }

    pub fn set_rate(&mut self, rate_kbps: f64) {
        self.rate_kbps = rate_kbps;
        self.capacity = rate_kbps * 125.0;
        if self.tokens > self.capacity {
            self.tokens = self.capacity;
        }
    }

    fn refill(&mut self) {
        let now = Instant::now();
        let dt = now.duration_since(self.last).as_secs_f64();
        self.last = now;
        self.tokens += dt * self.rate_kbps * 125.0;
        if self.tokens > self.capacity {
            self.tokens = self.capacity;
        }
    }

    /// اگر به‌اندازه‌ی `bytes` توکن هست، مصرف کن و true بده.
    pub fn try_take(&mut self, bytes: usize) -> bool {
        self.refill();
        if self.tokens >= bytes as f64 {
            self.tokens -= bytes as f64;
            true
        } else {
            false
        }
    }

    /// چقدر باید صبر کرد تا `bytes` توکن جمع شود (برای sleep فرستنده).
    pub fn wait_ms(&mut self, bytes: usize) -> u64 {
        self.refill();
        if self.tokens >= bytes as f64 {
            0
        } else {
            let need = bytes as f64 - self.tokens;
            ((need / (self.rate_kbps * 125.0)) * 1000.0).ceil() as u64
        }
    }
}

// ------------------------------------------------------------- فیلتر GOP
/// یک پیام RTMP کاملِ آماده‌ی ارسال (بدون هدر چانک).
#[derive(Clone)]
pub struct QueuedMsg {
    pub msg_type: u8, // 8=audio, 9=video, 18=data
    pub timestamp: u32,
    pub payload: Vec<u8>,
    /// فقط برای ویدیو: آیا این پیام شروع یک GOP است (کی‌فریم)؟
    pub is_keyframe: bool,
    /// لحظه‌ی رسیدن از Meld — مبنای سقف سن صف (نه timestamp مدیا
    /// که مبدأ دلخواه دارد و دورش می‌زند).
    pub enqueued_at: Instant,
}

/// تشخیص کی‌فریم در تگ ویدیوی FLV.
/// برای AVC (codec=7، خروجی Meld/Kick): بایت اول 0x17 به‌تنهایی کافی
/// نیست — بایت دوم نوع پکت است: 0 = هدر سکانس (SPS/PPS، نه فریم)،
/// 1 = NALU واقعی. هدر سکانس اگر کی‌فریم حساب شود، حذف GOP فقط همان
/// هدر را می‌برد و IDR بعدی‌اش بی‌سرپرست می‌ماند (دیکودر تا هدر بعدی
/// تصویر را دیکود نمی‌کند). پس کی‌فریم AVC یعنی 0x17 + بایت دوم 1.
/// برای کدک‌های دیگر، frame_type==1 کافی است.
pub fn is_keyframe_tag(payload: &[u8]) -> bool {
    if payload.is_empty() || (payload[0] & 0xF0) != 0x10 {
        return false;
    }
    if (payload[0] & 0x0F) == 7 {
        payload.get(1) == Some(&1)
    } else {
        true
    }
}

/// تشخیص هدر سکانس AVC (0x17 0x00): پارامترهای دیکودر، نه فریم.
pub fn is_sequence_header_tag(payload: &[u8]) -> bool {
    payload.len() >= 2 && payload[0] == 0x17 && payload[1] == 0
}

/// صف خروجی با سقف بایت. وقتی از سقف می‌گذرد، قدیمی‌ترین GOP کامل
/// حذف می‌شود. صوت و متادیتای وسط GOP حذف‌شده با همان GOP می‌روند تا
/// همگام‌سازی صدا و تصویر به‌هم نریزد (پس جمله‌ی «صوت هرگز حذف نمی‌شود»
/// غلط است). هدر سکانس هرگز جدا از GOP خودش حذف نمی‌شود: قانون توقف
/// در کی‌فریم بعدی فقط وقتی اعمال می‌شود که دست‌کم یک فریم ویدیویی
/// (غیر از هدر سکانس) در همین عملیات حذف شده باشد؛ وگرنه هدر سکانس با
/// GOP بعدش یک‌جا حذف می‌شود.
pub struct OutQueue {
    pub msgs: VecDeque<QueuedMsg>,
    pub bytes: usize,
    pub max_bytes: usize,
    pub dropped_gops: u64,
    pub dropped_bytes: u64,
}

impl OutQueue {
    pub fn new(max_bytes: usize) -> Self {
        Self {
            msgs: VecDeque::new(),
            bytes: 0,
            max_bytes,
            dropped_gops: 0,
            dropped_bytes: 0,
        }
    }

    pub fn push(&mut self, m: QueuedMsg) {
        self.bytes += m.payload.len();
        self.msgs.push_back(m);
        self.enforce_cap();
    }

    /// یک GOP کامل از جلو حذف کن و بایت حذف‌شده را برگردان: تا
    /// کی‌فریم بعدی، ولی فقط وقتی دست‌کم یک فریم ویدیویی واقعی در
    /// همین عملیات حذف شده باشد. این شرط جلوی جداافتادن هدر سکانس از
    /// GOP خودش را می‌گیرد: اگر جلو فقط هدر سکانس (و صوت/متادیتا)
    /// باشد، حذف ادامه پیدا می‌کند تا GOP بعدش هم با همان هدر برود.
    fn drop_front_gop(&mut self) -> usize {
        let mut removed_bytes = 0usize;
        let mut dropped_video_frames = 0usize;
        while let Some(front) = self.msgs.front() {
            if front.msg_type == 9 && front.is_keyframe && dropped_video_frames > 0 {
                break;
            }
            let m = self.msgs.pop_front().unwrap();
            if m.msg_type == 9 && !is_sequence_header_tag(&m.payload) {
                dropped_video_frames += 1;
            }
            removed_bytes += m.payload.len();
        }
        if dropped_video_frames == 0 && removed_bytes == 0 {
            return 0;
        }
        self.bytes = self.bytes.saturating_sub(removed_bytes);
        self.dropped_bytes += removed_bytes as u64;
        self.dropped_gops += 1;
        removed_bytes
    }

    fn enforce_cap(&mut self) {
        // حالت مرزی ثبت‌شده: اگر صف فقط یک پیام دارد (مثلاً یک کی‌فریم
        // غول‌پیکر بزرگ‌تر از سقف)، هیچ کاری نمی‌شود تا پیام بعدی برسد.
        while self.bytes > self.max_bytes && self.msgs.len() > 1 {
            if self.drop_front_gop() == 0 {
                break;
            }
        }
    }

    /// سقف سن صف: GOPهایی که از رسیدنشان بیش از MAX_QUEUE_AGE گذشته
    /// دور انداخته می‌شوند تا تأخیر عبوری از رله — هرچقدر هم تخلیه‌ی
    /// واقعی تا ingest کند باشد — از سقف رد نشود. اولویت با فریم تازه
    /// و کی‌فریم تازه است، نه ارسال مدیای کهنه. مثل سقف بایت،
    /// تک‌پیام تنها رها می‌شود تا صف هیچ‌وقت کاملاً خالی نشود.
    pub fn enforce_age(&mut self, now: Instant) {
        while self.msgs.len() > 1 {
            let Some(front) = self.msgs.front() else {
                break;
            };
            if now.duration_since(front.enqueued_at) <= MAX_QUEUE_AGE {
                break;
            }
            if self.drop_front_gop() == 0 {
                break;
            }
        }
    }
}

// ---------------------------------------------------------------- RTMP
/// ثابت‌های هندشیک RTMP.
pub const RTMP_VERSION: u8 = 3;
/// اندازه‌ی چانک پیش‌فرض؛ بعد از اتصال، هر دو طرف را به ۴۰۹۶ می‌بریم.
pub const CHUNK_SIZE_DEFAULT: usize = 128;
pub const CHUNK_SIZE_NEGOTIATED: u32 = 4096;

/// ساخت C0+C1 برای شروع هندشیک (کلاینت).
pub fn client_handshake_bytes() -> Vec<u8> {
    let mut v = Vec::with_capacity(1537);
    v.push(RTMP_VERSION);
    v.extend_from_slice(&[0u8; 4]); // time = 0
    v.extend_from_slice(&[0u8; 4]); // zero
    // بقیه‌ی C1: بایت‌های تصادفی لازم نیست؛ صفر هم قبول است.
    v.extend_from_slice(&[0u8; 1528]);
    v
}

/// بررسی S0 دریافتی از سرور.
pub fn check_server_version(b: u8) -> bool {
    b == RTMP_VERSION
}

#[derive(Debug, Clone, Copy)]
pub struct MsgHeader {
    pub msg_type: u8,
    pub timestamp: u32,
    pub stream_id: u32,
    pub length: usize,
    /// آیا تایم‌استمپ این پیام extended است؟ اگر بله، همه‌ی چانک‌های
    /// ادامه‌دار (fmt=3) همین پیام هم باید ۴ بایت extended داشته باشند
    /// (خواننده و انکودر هر دو باید آن را رعایت کنند).
    pub extended: bool,
}

/// رمزگشایی هدر پایه‌ی چانک: برمی‌گرداند (fmt, csid, طول هدر).
pub fn parse_basic_header(buf: &[u8]) -> Option<(u8, u32, usize)> {
    let b0 = *buf.first()?;
    let fmt = b0 >> 6;
    let mut csid = (b0 & 0x3F) as u32;
    let mut n = 1;
    if csid == 0 {
        let b1 = *buf.get(1)? as u32;
        csid = 64 + b1;
        n = 2;
    } else if csid == 1 {
        let b1 = *buf.get(1)? as u32;
        let b2 = *buf.get(2)? as u32;
        csid = 64 + b1 + 256 * b2;
        n = 3;
    }
    Some((fmt, csid, n))
}

/// رمزگشایی هدر پیام برای fmt های ۰ تا ۳ با توجه به هدر قبلی همان csid.
pub fn parse_msg_header(
    fmt: u8,
    buf: &[u8],
    prev: Option<&MsgHeader>,
) -> Option<(MsgHeader, usize)> {
    let p = prev.copied();
    match fmt {
        0 => {
            if buf.len() < 11 {
                return None;
            }
            let ts = u24(&buf[0..3]);
            let len = u24(&buf[3..6]) as usize;
            let msg_type = buf[6];
            let stream_id = u32::from_le_bytes([buf[7], buf[8], buf[9], 0]);
            let mut ts_full = ts;
            let mut n = 11;
            let extended = ts == 0xFFFFFF;
            if extended {
                if buf.len() < 15 {
                    return None;
                }
                ts_full = u32::from_be_bytes([buf[11], buf[12], buf[13], buf[14]]);
                n = 15;
            }
            Some((
                MsgHeader { msg_type, timestamp: ts_full, stream_id, length: len, extended },
                n,
            ))
        }
        1 => {
            if buf.len() < 7 {
                return None;
            }
            let ts_delta = u24(&buf[0..3]);
            let len = u24(&buf[3..6]) as usize;
            let msg_type = buf[6];
            let prev = p?;
            let mut ts = prev.timestamp + ts_delta;
            let mut n = 7;
            let extended = ts_delta == 0xFFFFFF;
            if extended {
                if buf.len() < 11 {
                    return None;
                }
                // طبق اسپک RTMP، extended در fmt=1/2 «دلتا» است نه مقدار
                // مطلق (برخلاف fmt=0 که مقدار مطلق است). تفسیر مطلق در
                // اینجا پرش بزرگ به عقب در تایم‌استمپ می‌دهد و پخش را
                // خراب می‌کند؛ تفسیر دلتا در بدترین حالت یک جابه‌جایی
                // ثابت روبه‌جلو می‌دهد که پخش‌کننده تحمل می‌کند.
                let ext_delta = u32::from_be_bytes([buf[7], buf[8], buf[9], buf[10]]);
                ts = prev.timestamp + ext_delta;
                n = 11;
            }
            Some((
                MsgHeader { msg_type, timestamp: ts, stream_id: prev.stream_id, length: len, extended },
                n,
            ))
        }
        2 => {
            if buf.len() < 3 {
                return None;
            }
            let ts_delta = u24(&buf[0..3]);
            let prev = p?;
            let mut ts = prev.timestamp + ts_delta;
            let mut n = 3;
            let extended = ts_delta == 0xFFFFFF;
            if extended {
                if buf.len() < 7 {
                    return None;
                }
                let ext_delta = u32::from_be_bytes([buf[3], buf[4], buf[5], buf[6]]);
                ts = prev.timestamp + ext_delta;
                n = 7;
            }
            Some((
                MsgHeader {
                    msg_type: prev.msg_type,
                    timestamp: ts,
                    stream_id: prev.stream_id,
                    length: prev.length,
                    extended,
                },
                n,
            ))
        }
        3 => {
            let prev = p?;
            Some((prev, 0))
        }
        _ => None,
    }
}

fn u24(b: &[u8]) -> u32 {
    ((b[0] as u32) << 16) | ((b[1] as u32) << 8) | (b[2] as u32)
}

/// ساخت یک چانک کامل fmt=0 برای یک پیام (تقسیم به قطعات CHUNK_SIZE).
/// csid ثابت بر اساس نوع: ویدیو ۶، صوت ۵، دیتا ۴، کامند ۳.
pub fn encode_message(msg_type: u8, timestamp: u32, stream_id: u32, payload: &[u8]) -> Vec<u8> {
    let csid: u8 = match msg_type {
        9 => 6,
        8 => 5,
        18 => 4,
        _ => 3,
    };
    let mut out = Vec::with_capacity(payload.len() + 64);
    let mut off = 0usize;
    let mut first = true;
    while off < payload.len() || first {
        first = false;
        if off == 0 {
            // هدر کامل fmt=0
            out.push((0 << 6) | csid);
            if timestamp >= 0xFFFFFF {
                out.extend_from_slice(&[0xFF, 0xFF, 0xFF]);
            } else {
                out.push((timestamp >> 16) as u8);
                out.push((timestamp >> 8) as u8);
                out.push(timestamp as u8);
            }
            let len = payload.len() as u32;
            out.push((len >> 16) as u8);
            out.push((len >> 8) as u8);
            out.push(len as u8);
            out.push(msg_type);
            out.extend_from_slice(&stream_id.to_le_bytes());
            if timestamp >= 0xFFFFFF {
                out.extend_from_slice(&timestamp.to_be_bytes());
            }
        } else {
            // ادامه با fmt=3 — اگر تایم‌استمپ پیام extended است، طبق
            // اسپک همه‌ی چانک‌های پیام (از جمله ادامه‌ها) باید ۴ بایت
            // extended داشته باشند؛ وگرنه خواننده‌ی طرف مقابل از همگام
            // می‌افتد.
            out.push((3 << 6) | csid);
            if timestamp >= 0xFFFFFF {
                out.extend_from_slice(&timestamp.to_be_bytes());
            }
        }
        let take = CHUNK_SIZE_NEGOTIATED as usize;
        let end = (off + take).min(payload.len());
        out.extend_from_slice(&payload[off..end]);
        off = end;
        if payload.is_empty() {
            break;
        }
    }
    out
}

// ------------------------------------------------------------- AMF0 حداقلی
#[derive(Debug, Clone, PartialEq)]
pub enum AmfValue {
    Number(f64),
    Bool(bool),
    Str(String),
    Null,
    Object(Vec<(String, AmfValue)>),
}

pub struct AmfReader<'a> {
    buf: &'a [u8],
    pos: usize,
}

impl<'a> AmfReader<'a> {
    pub fn new(buf: &'a [u8]) -> Self {
        Self { buf, pos: 0 }
    }

    fn take(&mut self, n: usize) -> Option<&'a [u8]> {
        if self.pos + n > self.buf.len() {
            return None;
        }
        let s = &self.buf[self.pos..self.pos + n];
        self.pos += n;
        Some(s)
    }

    pub fn value(&mut self) -> Option<AmfValue> {
        let t = *self.take(1)?.first()?;
        match t {
            0x00 => {
                let b = self.take(8)?;
                Some(AmfValue::Number(f64::from_be_bytes(b.try_into().ok()?)))
            }
            0x01 => {
                let b = self.take(1)?;
                Some(AmfValue::Bool(b[0] != 0))
            }
            0x02 => {
                let b = self.take(2)?;
                let len = u16::from_be_bytes(b.try_into().ok()?) as usize;
                let s = self.take(len)?;
                Some(AmfValue::Str(String::from_utf8_lossy(s).into_owned()))
            }
            0x03 => {
                let mut pairs = Vec::new();
                loop {
                    let kb = self.take(2)?;
                    let klen = u16::from_be_bytes(kb.try_into().ok()?) as usize;
                    if klen == 0 {
                        let end = self.take(1)?;
                        if end[0] == 0x09 {
                            break;
                        }
                        return None;
                    }
                    let k = self.take(klen)?;
                    let key = String::from_utf8_lossy(k).into_owned();
                    let v = self.value()?;
                    pairs.push((key, v));
                }
                Some(AmfValue::Object(pairs))
            }
            0x05 => Some(AmfValue::Null),
            0x08 => {
                let _count = self.take(4)?;
                let mut pairs = Vec::new();
                loop {
                    let kb = self.take(2)?;
                    let klen = u16::from_be_bytes(kb.try_into().ok()?) as usize;
                    if klen == 0 {
                        let end = self.take(1)?;
                        if end[0] == 0x09 {
                            break;
                        }
                        return None;
                    }
                    let k = self.take(klen)?;
                    let key = String::from_utf8_lossy(k).into_owned();
                    let v = self.value()?;
                    pairs.push((key, v));
                }
                Some(AmfValue::Object(pairs))
            }
            // تایپ ناشناخته: به‌جای مصرف ۱ بایت و به‌هم‌ریختن پارس
            // آرگومان‌های بعد، کل کامند را نامعتبر اعلام کن. (تایپ‌های
            // 0x06/0x0A/0x0B/0x0C/0x0F/0x10 در آرگومان‌های connect و
            // publish فعلی Meld استفاده نمی‌شوند.)
            _ => None,
        }
    }

    /// خواندن یک پیام کامند: (نام کامند، transaction id، بقیه‌ی آرگومان‌ها)
    /// اگر هر آرگومانی ناقص باشد، کل کامند None می‌شود تا wait_command
    /// روی آرگومان‌های نصفه تصمیم نگیرد.
    pub fn command(&mut self) -> Option<(String, f64, Vec<AmfValue>)> {
        let name = match self.value()? {
            AmfValue::Str(s) => s,
            _ => return None,
        };
        let txn = match self.value()? {
            AmfValue::Number(n) => n,
            _ => 0.0,
        };
        let mut args = Vec::new();
        while self.pos < self.buf.len() {
            match self.value() {
                Some(v) => args.push(v),
                None => return None,
            }
        }
        Some((name, txn, args))
    }
}

pub fn amf_str(s: &str) -> Vec<u8> {
    let mut v = vec![0x02];
    v.extend_from_slice(&(s.len() as u16).to_be_bytes());
    v.extend_from_slice(s.as_bytes());
    v
}

pub fn amf_num(n: f64) -> Vec<u8> {
    let mut v = vec![0x00];
    v.extend_from_slice(&n.to_be_bytes());
    v
}

pub fn amf_null() -> Vec<u8> {
    vec![0x05]
}

pub fn amf_object(pairs: &[(&str, AmfValue)]) -> Vec<u8> {
    let mut v = vec![0x03];
    for (k, val) in pairs {
        v.extend_from_slice(&(k.len() as u16).to_be_bytes());
        v.extend_from_slice(k.as_bytes());
        match val {
            AmfValue::Str(s) => v.extend_from_slice(&amf_str(s)),
            AmfValue::Number(n) => v.extend_from_slice(&amf_num(*n)),
            AmfValue::Bool(b) => {
                v.push(0x01);
                v.push(if *b { 1 } else { 0 });
            }
            AmfValue::Null => v.extend_from_slice(&amf_null()),
            _ => v.extend_from_slice(&amf_null()),
        }
    }
    v.extend_from_slice(&[0x00, 0x00, 0x09]);
    v
}

/// پاسخ `_result` برای یک transaction.
pub fn amf_result(txn: f64, extra: &[u8]) -> Vec<u8> {
    let mut v = amf_str("_result");
    v.extend_from_slice(&amf_num(txn));
    v.extend_from_slice(&amf_null());
    v.extend_from_slice(extra);
    v
}

/// پیام onStatus برای کامند (مثل NetConnection.Connect.Success).
pub fn amf_on_status(txn: f64, code: &str, level: &str) -> Vec<u8> {
    let mut v = amf_str("onStatus");
    v.extend_from_slice(&amf_num(txn));
    v.extend_from_slice(&amf_null());
    v.extend_from_slice(&amf_object(&[
        ("level", AmfValue::Str(level.to_string())),
        ("code", AmfValue::Str(code.to_string())),
    ]));
    v
}

/// خواندن یک فیلد رشته‌ای از اولین آبجکت در آرگومان‌های کامند
/// (مثل code یا description در onStatus/_error).
pub fn amf_get<'a>(args: &'a [AmfValue], key: &str) -> Option<&'a str> {
    for a in args {
        if let AmfValue::Object(pairs) = a {
            for (k, v) in pairs {
                if k == key {
                    if let AmfValue::Str(s) = v {
                        return Some(s);
                    }
                }
            }
        }
    }
    None
}

// ------------------------------------------------------- وضعیت و ران‌تایم
/// تصویری از وضعیت رله برای فرانت — بدون هیچ رازی (کلید اینجا نیست).
#[derive(Clone, Debug)]
pub struct RelaySnapshot {
    pub running: bool,
    pub target_host: String,
    pub listen_addr: String,
    pub current_kbps: u32,
    pub capacity_ema_kbps: f64,
    /// آخرین drain پنجره‌ی پروب (Kbps)؛ صفر یعنی هنوز پروبی نشده.
    /// توجه: capacity_ema میانگین drain پنجره‌های عادی (سقف‌دار) است و
    /// «ظرفیت مسیر» نیست — ظرفیت واقعی فقط از پروب خوانده می‌شود.
    pub probe_kbps: f64,
    pub at_top: bool,
    pub forwarded_bytes: u64,
    pub forwarded_msgs: u64,
    pub dropped_gops: u64,
    pub dropped_bytes: u64,
    pub queue_bytes: usize,
    /// سن قدیمی‌ترین GOP صف (ثانیه)؛ صفر یعنی صف خالی.
    pub queue_age_secs: f64,
    /// نرخ واقعی تخلیه‌ی آخرین پنجره‌ی ۲ ثانیه‌ای (Kbps).
    pub drain_kbps: f64,
    pub uptime_secs: u64,
    pub last_error: Option<String>,
    /// مسیر کامل فایل لاگ ("" یعنی لاگ انتخاب نشده است).
    pub log_path: String,
}

pub struct RelayStats {
    pub forwarded_bytes: u64,
    pub forwarded_msgs: u64,
    pub dropped_gops: u64,
    pub dropped_bytes: u64,
}

/// ران‌تایم رله: نخ پمپ + پرچم توقف + آمار مشترک.
/// کلید استریم فقط در همین ساختار و فقط در حافظه است؛ Debug دستی آن را
/// چاپ نمی‌کند.
pub struct RelayRuntime {
    stop: Arc<AtomicBool>,
    stats: Arc<Mutex<RelayStats>>,
    ladder: Arc<Mutex<LadderController>>,
    queue_bytes: Arc<Mutex<usize>>,
    queue_age: Arc<Mutex<f64>>,
    drain: Arc<Mutex<f64>>,
    last_probe: Arc<Mutex<f64>>,
    target_host: Arc<Mutex<String>>,
    last_error: Arc<Mutex<Option<String>>>,
    log_path: Arc<Mutex<String>>,
    started_at: Arc<Mutex<Option<Instant>>>,
    running: Arc<AtomicBool>,
    handle: Option<std::thread::JoinHandle<()>>,
    stream_key: String,
}

impl RelayRuntime {
    pub fn new() -> Self {
        Self {
            stop: Arc::new(AtomicBool::new(false)),
            stats: Arc::new(Mutex::new(RelayStats {
                forwarded_bytes: 0,
                forwarded_msgs: 0,
                dropped_gops: 0,
                dropped_bytes: 0,
            })),
            ladder: Arc::new(Mutex::new(LadderController::new(LADDER_DEFAULT_TOP_KBPS))),
            queue_bytes: Arc::new(Mutex::new(0)),
            queue_age: Arc::new(Mutex::new(0.0)),
            drain: Arc::new(Mutex::new(0.0)),
            last_probe: Arc::new(Mutex::new(0.0)),
            target_host: Arc::new(Mutex::new(String::new())),
            last_error: Arc::new(Mutex::new(None)),
            log_path: Arc::new(Mutex::new(String::new())),
            started_at: Arc::new(Mutex::new(None)),
            running: Arc::new(AtomicBool::new(false)),
            handle: None,
            stream_key: String::new(),
        }
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    /// پارس آدرس مقصد: rtmp://host[:port]/app — برمی‌گرداند (host, port, app).
    pub fn parse_target(url: &str) -> Result<(String, u16, String), String> {
        let rest = url
            .strip_prefix("rtmp://")
            .ok_or_else(|| "آدرس مقصد باید با rtmp:// شروع شود".to_string())?;
        let (hostport, app) = match rest.find('/') {
            Some(i) => (&rest[..i], rest[i + 1..].to_string()),
            None => (rest, String::new()),
        };
        if app.is_empty() {
            return Err("آدرس مقصد باید مسیر اپ (مثل live) داشته باشد".to_string());
        }
        let (host, port) = match hostport.rfind(':') {
            Some(i) => {
                let p: u16 = hostport[i + 1..]
                    .parse()
                    .map_err(|_| "پورت مقصد عدد معتبر نیست".to_string())?;
                (hostport[..i].to_string(), p)
            }
            None => (hostport.to_string(), 1935),
        };
        if host.is_empty() {
            return Err("هاست مقصد خالی است".to_string());
        }
        Ok((host, port, app))
    }

    /// شروع رله. اگر از قبل در حال اجراست، خطا می‌دهد.
    /// توجه: این تابع فقط نخ پمپ را راه می‌اندازد و فوراً برمی‌گردد؛
    /// خطاهای اتصالِ بعدی در last_error وضعیت دیده می‌شوند.
    pub fn start(&mut self, target_url: &str, stream_key: &str, top_kbps: u32) -> Result<(), String> {
        if self.is_running() {
            return Err("رله از قبل در حال اجراست".to_string());
        }
        let (host, port, app) = Self::parse_target(target_url)?;
        if stream_key.trim().is_empty() {
            return Err("کلید استریم خالی است".to_string());
        }
        // نخ قبلی اگر تمام شده باشد، join می‌شود تا handle تازه شود.
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
        *self.last_error.lock().unwrap() = None;
        *self.target_host.lock().unwrap() = host.clone();
        *self.ladder.lock().unwrap() = LadderController::new(top_kbps.max(LADDER_FLOOR_KBPS));
        self.stream_key = stream_key.to_string();
        self.stop.store(false, Ordering::SeqCst);
        self.running.store(true, Ordering::SeqCst);
        *self.started_at.lock().unwrap() = Some(Instant::now());
        // مسیر لاگ از همین‌جا مشخص است تا پنل از لحظه‌ی استارت آن را
        // نشان بدهد، حتی پیش از اینکه اولین نمونه نوشته شود.
        let log_path = pick_log_path();
        *self.log_path.lock().unwrap() = log_path.to_string_lossy().into_owned();

        let stop = self.stop.clone();
        let stats = self.stats.clone();
        let ladder = self.ladder.clone();
        let queue_bytes = self.queue_bytes.clone();
        let queue_age = self.queue_age.clone();
        let drain = self.drain.clone();
        let last_probe = self.last_probe.clone();
        let last_error = self.last_error.clone();
        let running = self.running.clone();
        let key = stream_key.to_string();
        let target = format!("rtmp://{host}:{port}/{app}");
        self.handle = Some(std::thread::spawn(move || {
            let res = run_pump(
                &stop,
                &stats,
                &ladder,
                &queue_bytes,
                &queue_age,
                &drain,
                &last_probe,
                &target,
                &key,
                &log_path,
            );
            if let Err(e) = res {
                *last_error.lock().unwrap() = Some(e);
            }
            running.store(false, Ordering::SeqCst);
        }));
        Ok(())
    }

    pub fn stop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
        self.running.store(false, Ordering::SeqCst);
    }

    pub fn snapshot(&self) -> RelaySnapshot {
        let st = self.stats.lock().unwrap();
        let lad = self.ladder.lock().unwrap();
        let uptime = self
            .started_at
            .lock()
            .unwrap()
            .map(|t| t.elapsed().as_secs())
            .unwrap_or(0);
        RelaySnapshot {
            running: self.is_running(),
            target_host: self.target_host.lock().unwrap().clone(),
            listen_addr: "127.0.0.1:1935/live".to_string(),
            current_kbps: lad.current_kbps(),
            capacity_ema_kbps: lad.capacity_ema_kbps,
            probe_kbps: *self.last_probe.lock().unwrap(),
            at_top: lad.at_top(),
            forwarded_bytes: st.forwarded_bytes,
            forwarded_msgs: st.forwarded_msgs,
            dropped_gops: st.dropped_gops,
            dropped_bytes: st.dropped_bytes,
            queue_bytes: *self.queue_bytes.lock().unwrap(),
            queue_age_secs: *self.queue_age.lock().unwrap(),
            drain_kbps: *self.drain.lock().unwrap(),
            uptime_secs: uptime,
            last_error: self.last_error.lock().unwrap().clone(),
            log_path: self.log_path.lock().unwrap().clone(),
        }
    }
}

// ------------------------------------------------------------- پمپ RTMP
/// سقف بایت صف خروجی: ۲ مگابایت. این سقف به‌تنهایی تأخیر را مهار
/// نمی‌کند — تأخیر صف = بایت صف ÷ نرخ واقعی تخلیه، و اگر تخلیه تا
/// ingest کند شود همان ۲ مگ چند دقیقه تأخیر می‌شود. مهار قطعی تأخیر
/// با سقف سن است (MAX_QUEUE_AGE): هرچه تخلیه کند باشد، GOP کهنه
/// دور انداخته می‌شود و فریم تازه جلو می‌آید.
const MAX_QUEUE_BYTES: usize = 2_000_000;
/// سقف سن صف: GOP قدیمی‌تر از ۴ ثانیه (از لحظه‌ی رسیدن از Meld)
/// حتماً دور انداخته می‌شود — تأخیر عبوری از رله از ~۴ ثانیه رد
/// نمی‌شود، مستقل از اینکه تخلیه‌ی واقعی چقدر کند باشد. سهم ثابت
/// MasterStream از تأخیر پایه جداست و با این سقف کم نمی‌شود.
const MAX_QUEUE_AGE: Duration = Duration::from_secs(4);
const WINDOW_SECS: f64 = 2.0;

// ------------------------------------------------------------- لاگ رله
/// لاگ رله (۰٫۹٫۷): هر ۵ ثانیه یک سطر CSV از همان عددهایی که پنل
/// نشان می‌دهد، تا کاربر بتواند فایل را برای تحلیل بفرستد — مخصوصاً
/// وقتی تأخیر ویور تا دقیقه می‌رسد ولی سن صف زیر سقف است: آن‌وقت
/// رشد، بیرون از رله است (سمت Meld یا مسیر MasterStream تا Kick).
/// نوشتن لاگ هرگز رله را خراب نمی‌کند: هر خطا ساکت نادیده گرفته
/// می‌شود و فایل با open-append-close در هر نمونه نوشته می‌شود تا
/// حتی با کرش برنامه، نمونه‌های قبلی روی دیسک مانده باشند.
const RELAY_LOG_FILE: &str = "LagSlice-relay-log.csv";
const RELAY_LOG_INTERVAL: Duration = Duration::from_secs(5);
const RELAY_LOG_HEADER: &str = "unix_s,uptime_s,current_kbps,capacity_ema_kbps,probe_kbps,queue_bytes,queue_age_s,drain_kbps,forwarded_bytes,forwarded_msgs,dropped_gops,dropped_bytes,last_error";

/// مسیر لاگ: اول دسکتاپ، بعد Documents، وگرنه پوشه‌ی موقت سیستم.
/// فقط پوشه‌ای انتخاب می‌شود که واقعاً وجود داشته باشد؛ مسیر نهایی
/// در snapshot برمی‌گردد و پنل آن را نشان می‌دهد تا کاربر فایل را
/// پیدا کند. کلید استریم هرگز در لاگ نیست.
fn pick_log_path() -> std::path::PathBuf {
    if let Ok(home) = std::env::var("USERPROFILE") {
        for sub in ["Desktop", "Documents"] {
            let dir = std::path::Path::new(&home).join(sub);
            if dir.is_dir() {
                return dir.join(RELAY_LOG_FILE);
            }
        }
    }
    std::env::temp_dir().join(RELAY_LOG_FILE)
}

/// پاک‌سازی یک ستون CSV: ویرگول و خط جدید، ساختار سطر را خراب
/// می‌کنند — با «؛» و فاصله عوض می‌شوند.
fn sanitize_log_field(s: &str) -> String {
    s.replace(',', "؛").replace(['\r', '\n'], " ")
}

/// یک سطر نمونه‌ی لاگ (بدون خط جدید انتهایی).
#[allow(clippy::too_many_arguments)]
fn format_log_sample(
    unix_s: u64,
    uptime_s: u64,
    current_kbps: u32,
    capacity_ema_kbps: f64,
    probe_kbps: f64,
    queue_bytes: usize,
    queue_age_s: f64,
    drain_kbps: f64,
    forwarded_bytes: u64,
    forwarded_msgs: u64,
    dropped_gops: u64,
    dropped_bytes: u64,
    last_error: &str,
) -> String {
    format!(
        "{unix_s},{uptime_s},{current_kbps},{:.0},{:.0},{queue_bytes},{queue_age_s:.1},{drain_kbps:.0},{forwarded_bytes},{forwarded_msgs},{dropped_gops},{dropped_bytes},{}",
        capacity_ema_kbps, probe_kbps, sanitize_log_field(last_error)
    )
}

/// افزودن یک خط به لاگ: اگر فایل خالی باشد اول سطر سرستون نوشته
/// می‌شود. هر خطایی ساکت رد می‌شود — لاگ، رله را متوقف نمی‌کند.
fn append_log_line(path: &std::path::Path, line: &str) {
    use std::io::Write;
    let need_header = std::fs::metadata(path).map(|m| m.len() == 0).unwrap_or(true);
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        if need_header {
            let _ = writeln!(f, "{RELAY_LOG_HEADER}");
        }
        let _ = writeln!(f, "{line}");
    }
}

fn unix_now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

struct ChunkConn {
    stream: TcpStream,
    chunk_size: usize,
    prev_headers: HashMap<u32, MsgHeader>,
}

impl ChunkConn {
    fn new(stream: TcpStream) -> Self {
        Self {
            stream,
            chunk_size: CHUNK_SIZE_DEFAULT,
            prev_headers: HashMap::new(),
        }
    }

    /// خواندن دقیق n بایت (با timeout سوکت؛ خطا = قطع یا timeout).
    fn read_exact_into(&mut self, out: &mut [u8]) -> std::io::Result<()> {
        self.stream.read_exact(out)
    }

    /// خواندن یک پیام کامل RTMP. None یعنی timeout (باید دوباره صدا شود).
    fn read_message(&mut self) -> std::io::Result<Option<(MsgHeader, Vec<u8>)>> {
        // هدر پایه
        let b0 = match self.read_byte_timeout()? {
            Some(b) => b,
            None => return Ok(None),
        };
        let fmt = b0 >> 6;
        let mut csid = (b0 & 0x3F) as u32;
        let mut hdr_len = 1;
        if csid == 0 {
            let b = self.read_byte_blocking()?;
            csid = 64 + b as u32;
            hdr_len = 2;
        } else if csid == 1 {
            let b1 = self.read_byte_blocking()?;
            let b2 = self.read_byte_blocking()?;
            csid = 64 + b1 as u32 + 256 * b2 as u32;
            hdr_len = 3;
        }
        let _ = hdr_len;
        // هدر پیام — توجه: اگر فیلد تایم‌استمپ 0xFFFFFF باشد، یک
        // تایم‌استمپ ۴ بایتی extended هم در ادامه می‌آید و باید همان‌جا
        // خوانده شود؛ وگرنه parse ناموفق می‌شود و پمپ می‌میرد. این حالت
        // وقتی پیش می‌آید که تایم‌استمپ استریم از ۲^۲۴ میلی‌ثانیه
        // (حدود ۴٫۷ ساعت) بگذرد — یعنی دقیقاً استریم‌های طولانی.
        // (باگ ۰٫۹٫۳: قبلاً فقط ۱۱/۷/۳ بایت خوانده می‌شد و extended
        // اصلاً خوانده نمی‌شد.)
        let need = match fmt {
            0 => 11,
            1 => 7,
            2 => 3,
            _ => 0,
        };
        let mut hb = vec![0u8; need];
        if need > 0 {
            self.read_exact_into(&mut hb)?;
            if fmt != 3 && u24(&hb[0..3]) == 0xFFFFFF {
                let mut eb = [0u8; 4];
                self.read_exact_into(&mut eb)?;
                hb.extend_from_slice(&eb);
            }
        }
        let prev = self.prev_headers.get(&csid).copied();
        let (header, _) = match parse_msg_header(fmt, &hb, prev.as_ref()) {
            Some(v) => v,
            None => {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "هدر پیام RTMP نامعتبر",
                ))
            }
        };
        if header.msg_type == 1 {
            // Set Chunk Size — اندازه‌ی چانک ورودی را به‌روز کن.
            let mut sb = vec![0u8; 4];
            self.read_exact_into(&mut sb)?;
            let size = u32::from_be_bytes(sb.try_into().unwrap()) as usize;
            if size > 0 {
                self.chunk_size = size;
            }
            return self.read_message();
        }
        // بدنه‌ی پیام، چانک‌به‌چانک
        let mut body = Vec::with_capacity(header.length);
        let mut remaining = header.length;
        let mut first = true;
        // پرچم extended پیام جاری: اگر چانک اول extended داشت، همه‌ی
        // چانک‌های ادامه‌دار همین پیام هم ۴ بایت extended دارند.
        let cur_extended = header.extended;
        while remaining > 0 {
            if !first {
                // هدر چانک ادامه: هدر پایه‌ی کامل را بخوان (csid ممکن
                // است ۲ یا ۳ بایتی باشد)، fmt=3 بودن را چک کن، و اگر
                // پیام جاری extended است، ۴ بایت extended را هم مصرف کن
                // (مقدارش تکرار تایم‌استمپ پیام است و برای خواندن بدنه
                // لازم نیست، ولی نخوردنش همگام‌سازی را خراب می‌کند).
                let cb = self.read_byte_blocking()?;
                let cfmt = cb >> 6;
                let cext = cb & 0x3F;
                if cfmt != 3 {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::InvalidData,
                        "ادامه‌ی چانک باید fmt=3 باشد",
                    ));
                }
                if cext == 0 {
                    let _ = self.read_byte_blocking()?;
                } else if cext == 1 {
                    let _ = self.read_byte_blocking()?;
                    let _ = self.read_byte_blocking()?;
                }
                if cur_extended {
                    let mut eb = [0u8; 4];
                    self.read_exact_into(&mut eb)?;
                }
            }
            first = false;
            let take = remaining.min(self.chunk_size);
            let mut chunk = vec![0u8; take];
            self.read_exact_into(&mut chunk)?;
            body.extend_from_slice(&chunk);
            remaining -= take;
        }
        self.prev_headers.insert(csid, header);
        Ok(Some((header, body)))
    }

    fn read_byte_timeout(&mut self) -> std::io::Result<Option<u8>> {
        let mut b = [0u8; 1];
        match self.stream.read(&mut b) {
            Ok(0) => Err(std::io::Error::new(
                std::io::ErrorKind::UnexpectedEof,
                "اتصال بسته شد",
            )),
            Ok(_) => Ok(Some(b[0])),
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock
                || e.kind() == std::io::ErrorKind::TimedOut =>
            {
                Ok(None)
            }
            Err(e) => Err(e),
        }
    }

    fn read_byte_blocking(&mut self) -> std::io::Result<u8> {
        let mut b = [0u8; 1];
        self.stream.read_exact(&mut b)?;
        Ok(b[0])
    }
}

fn write_all(stream: &mut TcpStream, bytes: &[u8]) -> std::io::Result<()> {
    stream.write_all(bytes)
}

/// هندشیک سمت سرور (با Meld): S0+S1+S2 بفرست و C0+C1+C2 را بگیر.
fn server_handshake(stream: &mut TcpStream) -> std::io::Result<()> {
    let mut c0 = [0u8; 1];
    stream.read_exact(&mut c0)?;
    if !check_server_version(c0[0]) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "نسخه‌ی RTMP کلاینت پشتیبانی نمی‌شود",
        ));
    }
    let mut c1 = [0u8; 1536];
    stream.read_exact(&mut c1)?;
    // S0 + S1 (صفر) + S2 (بازتاب C1)
    let mut s = vec![RTMP_VERSION];
    s.extend_from_slice(&[0u8; 1536]);
    s.extend_from_slice(&c1);
    stream.write_all(&s)?;
    stream.flush()?;
    let mut c2 = [0u8; 1536];
    stream.read_exact(&mut c2)?;
    Ok(())
}

/// هندشیک سمت کلاینت (به ingest): C0+C1 بفرست، S0+S1+S2 بگیر، C2 بفرست.
fn client_handshake(stream: &mut TcpStream) -> std::io::Result<()> {
    stream.write_all(&client_handshake_bytes())?;
    stream.flush()?;
    let mut s0 = [0u8; 1];
    stream.read_exact(&mut s0)?;
    if !check_server_version(s0[0]) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "نسخه‌ی RTMP سرور پشتیبانی نمی‌شود",
        ));
    }
    let mut s1 = [0u8; 1536];
    stream.read_exact(&mut s1)?;
    let mut s2 = [0u8; 1536];
    stream.read_exact(&mut s2)?;
    // C2 = بازتاب S1
    stream.write_all(&s1)?;
    stream.flush()?;
    Ok(())
}

/// ارسال Set Chunk Size (type=1, stream 0).
fn send_chunk_size(stream: &mut TcpStream, size: u32) -> std::io::Result<()> {
    let mut msg = vec![0u8; 4];
    msg[0] = (size >> 24) as u8;
    msg[1] = (size >> 16) as u8;
    msg[2] = (size >> 8) as u8;
    msg[3] = size as u8;
    let chunk = encode_message(1, 0, 0, &msg);
    stream.write_all(&chunk)
}

/// انتظار برای یک کامند خاص از سمت مقابل (با timeout کلی).
fn wait_command(
    conn: &mut ChunkConn,
    want: &str,
    timeout: Duration,
) -> std::io::Result<(f64, Vec<AmfValue>)> {
    let start = Instant::now();
    loop {
        if start.elapsed() > timeout {
            return Err(std::io::Error::new(
                std::io::ErrorKind::TimedOut,
                format!("timeout در انتظار کامند {want}"),
            ));
        }
        match conn.read_message()? {
            Some((h, body)) if h.msg_type == 20 => {
                let mut r = AmfReader::new(&body);
                if let Some((name, txn, args)) = r.command() {
                    if name == want {
                        return Ok((txn, args));
                    }
                }
            }
            Some(_) => {}
            None => {
                std::thread::sleep(Duration::from_millis(20));
            }
        }
    }
}

/// انتظار برای اولین کامند از میان چند نام (مثل _result یا _error).
/// برمی‌گرداند (نام، transaction، آرگومان‌ها).
fn wait_command_any(
    conn: &mut ChunkConn,
    wants: &[&str],
    timeout: Duration,
) -> std::io::Result<(String, f64, Vec<AmfValue>)> {
    let start = Instant::now();
    loop {
        if start.elapsed() > timeout {
            return Err(std::io::Error::new(
                std::io::ErrorKind::TimedOut,
                format!("timeout در انتظار کامند {}", wants.join("/")),
            ));
        }
        match conn.read_message()? {
            Some((h, body)) if h.msg_type == 20 => {
                let mut r = AmfReader::new(&body);
                if let Some((name, txn, args)) = r.command() {
                    if wants.contains(&name.as_str()) {
                        return Ok((name, txn, args));
                    }
                }
            }
            Some(_) => {}
            None => {
                std::thread::sleep(Duration::from_millis(20));
            }
        }
    }
}

/// حلقه‌ی اصلی پمپ: Meld ←→ ingest مقصد (در عمل MasterStream).
fn run_pump(
    stop: &AtomicBool,
    stats: &Mutex<RelayStats>,
    ladder: &Mutex<LadderController>,
    queue_bytes: &Mutex<usize>,
    queue_age: &Mutex<f64>,
    drain: &Mutex<f64>,
    last_probe: &Mutex<f64>,
    target_url: &str,
    stream_key: &str,
    log_path: &std::path::Path,
) -> Result<(), String> {
    let (host, port, app) = RelayRuntime::parse_target(target_url)?;
    let listener = TcpListener::bind("127.0.0.1:1935")
        .map_err(|e| format!("شنود روی 127.0.0.1:1935 ناموفق بود: {e}"))?;
    listener
        .set_nonblocking(true)
        .map_err(|e| e.to_string())?;

    // انتظار برای اتصال Meld (تا ۶۰ ثانیه؛ کاربر اول رله را روشن می‌کند
    // بعد در Meld خروجی Custom RTMP را استارت می‌زند).
    let meld_stream = loop {
        if stop.load(Ordering::SeqCst) {
            return Ok(());
        }
        match listener.accept() {
            Ok((s, _)) => break s,
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(100));
            }
            Err(e) => return Err(format!("خطا در accept: {e}")),
        }
    };
    // نکته‌ی ویندوز (باگ ۰٫۹٫۴): سوکت پذیرفته‌شده از لیسنر
    // non-blocking، حالت non-blocking را به ارث می‌برد؛ روی ویندوز
    // set_read_timeout روی سوکت non-blocking بی‌اثر است و اولین read
    // هندشیک WouldBlock (10035) برمی‌گرداند، به‌جای اینکه تا timeout
    // صبر کند. پس اول blocking می‌کنیم، بعد timeoutها.
    meld_stream
        .set_nonblocking(false)
        .map_err(|e| e.to_string())?;
    // فاز هندشیک: خواندن ۵ ثانیه (لوکال است ولی زمان‌بندی پردازه
    // تضمین‌شده نیست)؛ بعد از publish به ۲۰۰ms برمی‌گردیم تا حلقه به
    // پرچم توقف سریع واکنش بدهد. نوشتن از اول ۵ ثانیه سقف دارد تا
    // stall سوکت، relay_stop را در join قفل نکند.
    meld_stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    meld_stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    let mut meld = meld_stream;
    server_handshake(&mut meld).map_err(|e| format!("هندشیک با Meld ناموفق: {e}"))?;
    send_chunk_size(&mut meld, CHUNK_SIZE_NEGOTIATED)
        .map_err(|e| format!("ارسال chunk size به Meld ناموفق: {e}"))?;
    let mut meld_conn = ChunkConn::new(meld);

    // سشن Meld: connect → createStream → publish (پاسخ‌های استاندارد).
    let (txn, args) = wait_command(&mut meld_conn, "connect", Duration::from_secs(10))
        .map_err(|e| format!("Meld connect نفرستاد: {e}"))?;
    let _ = args;
    let mut resp = amf_result(txn, &amf_object(&[
        ("fmsVer", AmfValue::Str("FMS/3,5,7,700".to_string())),
        ("capabilities", AmfValue::Number(31.0)),
        ("mode", AmfValue::Number(1.0)),
    ]));
    resp.extend_from_slice(&amf_on_status(
        0.0,
        "NetConnection.Connect.Success",
        "status",
    ));
    let chunk = encode_message(20, 0, 0, &resp);
    write_all(&mut meld_conn.stream, &chunk)
        .map_err(|e| format!("پاسخ connect به Meld ناموفق: {e}"))?;
    let (txn2, _) = wait_command(&mut meld_conn, "createStream", Duration::from_secs(10))
        .map_err(|e| format!("Meld createStream نفرستاد: {e}"))?;
    let chunk = encode_message(20, 0, 0, &amf_result(txn2, &amf_num(1.0)));
    write_all(&mut meld_conn.stream, &chunk)
        .map_err(|e| format!("پاسخ createStream ناموفق: {e}"))?;
    let (_, _) = wait_command(&mut meld_conn, "publish", Duration::from_secs(10))
        .map_err(|e| format!("Meld publish نفرستاد: {e}"))?;
    let chunk = encode_message(
        20,
        0,
        1,
        &amf_on_status(0.0, "NetStream.Publish.Start", "status"),
    );
    write_all(&mut meld_conn.stream, &chunk)
        .map_err(|e| format!("پاسخ publish ناموفق: {e}"))?;
    // فاز مدیا: خواندن Meld به ۲۰۰ms برمی‌گردد.
    meld_conn
        .stream
        .set_read_timeout(Some(Duration::from_millis(200)))
        .map_err(|e| e.to_string())?;

    // اتصال به ingest مقصد.
    let up_addr = format!("{host}:{port}");
    let mut up = TcpStream::connect(&up_addr)
        .map_err(|e| format!("اتصال به {host}:{port} ناموفق بود: {e}"))?;
    // فاز هندشیک مقصد: خواندن ۱۰ ثانیه — از ایران RTT تا ingest کیک
    // راحت از ۲۰۰ms می‌گذرد و timeout کوتاه شروع رله را بی‌دلیل fail
    // می‌کرد. بعد از publish به ۲۰۰ms برمی‌گردیم. نوشتن ۵ ثانیه سقف دارد.
    up.set_read_timeout(Some(Duration::from_secs(10)))
        .map_err(|e| e.to_string())?;
    up.set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    client_handshake(&mut up).map_err(|e| format!("هندشیک با ingest ناموفق: {e}"))?;
    send_chunk_size(&mut up, CHUNK_SIZE_NEGOTIATED)
        .map_err(|e| format!("ارسال chunk size به ingest ناموفق: {e}"))?;
    let mut up_conn = ChunkConn::new(up);
    // connect مقصد
    let mut connect_args = amf_str("connect");
    connect_args.extend_from_slice(&amf_num(0.0));
    connect_args.extend_from_slice(&amf_object(&[
        ("app", AmfValue::Str(app.clone())),
        ("tcUrl", AmfValue::Str(target_url.to_string())),
        ("fmsVer", AmfValue::Str("FMS/3,5,7,700".to_string())),
        ("capabilities", AmfValue::Number(31.0)),
    ]));
    let chunk = encode_message(20, 0, 0, &connect_args);
    write_all(&mut up_conn.stream, &chunk)
        .map_err(|e| format!("ارسال connect به ingest ناموفق: {e}"))?;
    // رد connect به‌صورت _error می‌آید؛ فقط _result را قبول‌کردن یعنی
    // ۱۰ ثانیه صبر بیهوده با پیام گمراه‌کننده‌ی timeout.
    let (conn_name, _, conn_args) =
        wait_command_any(&mut up_conn, &["_result", "_error"], Duration::from_secs(10))
            .map_err(|e| format!("پاسخ connect از ingest نیامد: {e}"))?;
    if conn_name == "_error" {
        let detail = amf_get(&conn_args, "description")
            .or_else(|| amf_get(&conn_args, "code"))
            .unwrap_or("نامشخص");
        return Err(format!("ingest اتصال را رد کرد: {detail}"));
    }
    // createStream مقصد
    let mut cs = amf_str("createStream");
    cs.extend_from_slice(&amf_num(0.0));
    cs.extend_from_slice(&amf_null());
    let chunk = encode_message(20, 0, 0, &cs);
    write_all(&mut up_conn.stream, &chunk)
        .map_err(|e| format!("ارسال createStream به ingest ناموفق: {e}"))?;
    let (cs_name, _, cs_args) =
        wait_command_any(&mut up_conn, &["_result", "_error"], Duration::from_secs(10))
            .map_err(|e| format!("پاسخ createStream از ingest نیامد: {e}"))?;
    if cs_name == "_error" {
        let detail = amf_get(&cs_args, "description")
            .or_else(|| amf_get(&cs_args, "code"))
            .unwrap_or("نامشخص");
        return Err(format!("ingest ساخت استریم را رد کرد: {detail}"));
    }
    let up_stream_id = match cs_args.first() {
        Some(AmfValue::Number(n)) => *n as u32,
        _ => 1,
    };
    // publish مقصد با کلید واقعی — فقط نام onStatus کافی نیست؛ باید
    // code دقیقاً NetStream.Publish.Start باشد، وگرنه (مثلاً BadName
    // برای کلید اشتباه) پمپ جلو می‌رود و UI «در حال اجرا» نشان می‌دهد
    // در حالی که مقصد هیچ‌چیز نمی‌گیرد.
    let mut pb = amf_str("publish");
    pb.extend_from_slice(&amf_num(0.0));
    pb.extend_from_slice(&amf_null());
    pb.extend_from_slice(&amf_str(stream_key));
    pb.extend_from_slice(&amf_str("live"));
    let chunk = encode_message(20, 0, up_stream_id, &pb);
    write_all(&mut up_conn.stream, &chunk)
        .map_err(|e| format!("ارسال publish به ingest ناموفق: {e}"))?;
    let (_, pub_args) = wait_command(&mut up_conn, "onStatus", Duration::from_secs(10))
        .map_err(|e| format!("تأیید publish از ingest نیامد: {e}"))?;
    let pub_code = amf_get(&pub_args, "code").unwrap_or("");
    if pub_code != "NetStream.Publish.Start" {
        return Err(format!("ingest انتشار را رد کرد: {pub_code}"));
    }
    // فاز مدیا: خواندن مقصد به ۲۰۰ms برمی‌گردد.
    up_conn
        .stream
        .set_read_timeout(Some(Duration::from_millis(200)))
        .map_err(|e| e.to_string())?;

    // حلقه‌ی پمپ با سطل توکن، فیلتر GOP و پنجره‌های پروب.
    // پروب چرا لازم است؟ در پنجره‌ی عادی، drain اندازه‌گیری‌شده با سطل
    // توکن به نرخ پله‌ی جاری سقف گرفته شده، پس هرگز از پله‌ی بالاتر
    // بیشتر نمی‌شود و شرط بالارفتن هیچ‌وقت برقرار نمی‌شود — نردبان
    // بعد از هر پایین‌آمدن برای همیشه پایین می‌ماند. پس هر ۵ پنجره،
    // یک پنجره‌ی پروب بدون سقف اجرا می‌شود (فقط وقتی پنجره‌ی قبلی نشان
    // داده باشد مسیر دارد با پله‌ی جاری همراهی می‌کند، تا وسط تراکم
    // پروب باعث افت اضافه نشود) و بالارفتن فقط از روی پروب تصمیم
    // گرفته می‌شود. سقف پروب را TCP و نرخ ورودی Meld تعیین می‌کنند،
    // نه سطل توکن.
    // سطر شروع سشن در لاگ (بدون کلید استریم — target_url فقط
    // آدرس و اپ دارد). نسخه از CARGO_PKG_VERSION می‌آید تا همیشه
    // با خود باینری هم‌گام باشد.
    append_log_line(
        log_path,
        &format!(
            "# session start unix={} target={} version={}",
            unix_now(),
            target_url,
            env!("CARGO_PKG_VERSION")
        ),
    );
    let mut queue = OutQueue::new(MAX_QUEUE_BYTES);
    let mut bucket = TokenBucket::new(ladder.lock().unwrap().current_kbps() as f64);
    let mut window_start = Instant::now();
    let mut window_bytes: u64 = 0;
    let mut window_index: u64 = 0;
    let mut probe_active = false;
    let pump_start = Instant::now();
    let mut last_log = pump_start;

    while !stop.load(Ordering::SeqCst) {
        // خواندن از Meld (timeout یعنی «فعلاً چیزی نیست»، خطا یعنی قطع).
        match meld_conn.read_message() {
            Ok(Some((h, body))) => match h.msg_type {
                8 | 9 | 18 => {
                    let is_kf = h.msg_type == 9 && is_keyframe_tag(&body);
                    queue.push(QueuedMsg {
                        msg_type: h.msg_type,
                        timestamp: h.timestamp,
                        payload: body,
                        is_keyframe: is_kf,
                        enqueued_at: Instant::now(),
                    });
                }
                _ => {} // کامندها/کنترل‌ها در فاز مدیا نادیده گرفته می‌شوند
            },
            Ok(None) => {}
            Err(e) => return Err(format!("خواندن از Meld قطع شد: {e}")),
        }
        // سقف سن صف — قبل از ارسال: GOPای که موقع بلاک‌شدن write
        // کهنه شده باشد هم نباید به‌عنوان مدیای تازه فرستاده شود.
        queue.enforce_age(Instant::now());
        // آمار صف برای فرانت
        *queue_bytes.lock().unwrap() = queue.bytes;
        *queue_age.lock().unwrap() = queue
            .msgs
            .front()
            .map(|f| Instant::now().duration_since(f.enqueued_at).as_secs_f64())
            .unwrap_or(0.0);
        {
            let mut st = stats.lock().unwrap();
            st.dropped_gops = queue.dropped_gops;
            st.dropped_bytes = queue.dropped_bytes;
        }
        // نمونه‌ی لاگ هر ۵ ثانیه: همان عددهای پنل، از همان
        // Mutexهایی که فرانت می‌خواند — پس لاگ و پنل یکی‌اند.
        if last_log.elapsed() >= RELAY_LOG_INTERVAL {
            last_log = Instant::now();
            let (cur, ema) = {
                let lad = ladder.lock().unwrap();
                (lad.current_kbps(), lad.capacity_ema_kbps)
            };
            let st = stats.lock().unwrap();
            let line = format_log_sample(
                unix_now(),
                pump_start.elapsed().as_secs(),
                cur,
                ema,
                *last_probe.lock().unwrap(),
                *queue_bytes.lock().unwrap(),
                *queue_age.lock().unwrap(),
                *drain.lock().unwrap(),
                st.forwarded_bytes,
                st.forwarded_msgs,
                st.dropped_gops,
                st.dropped_bytes,
                "",
            );
            append_log_line(log_path, &line);
        }
        // ارسال: در پنجره‌ی پروب بدون سقف، وگرنه تا جایی که توکن هست.
        while let Some(front) = queue.msgs.front() {
            let need = front.payload.len();
            if !probe_active && !bucket.try_take(need) {
                break;
            }
            let m = queue.msgs.pop_front().unwrap();
            queue.bytes = queue.bytes.saturating_sub(m.payload.len());
            let chunk = encode_message(m.msg_type, m.timestamp, up_stream_id, &m.payload);
            if let Err(e) = write_all(&mut up_conn.stream, &chunk) {
                return Err(format!("ارسال به ingest قطع شد: {e}"));
            }
            window_bytes += chunk.len() as u64;
            let mut st = stats.lock().unwrap();
            st.forwarded_bytes += chunk.len() as u64;
            st.forwarded_msgs += 1;
        }
        // پنجره‌ی ۲ ثانیه‌ای: سنجش drain و تصمیم نردبان. تقسیم بر زمان
        // واقعی پنجره است، نه ۲٫۰ ثابت — وقتی write روی مسیر تنگ بلاک
        // می‌شود، پنجره طولانی‌تر می‌شود و تقسیم بر ۲٫۰ ظرفیت را به
        // نسبت elapsed/2 بزرگ‌نمایی می‌کرد.
        if window_start.elapsed().as_secs_f64() >= WINDOW_SECS {
            let elapsed = window_start.elapsed().as_secs_f64().max(0.1);
            let drain_kbps = window_bytes as f64 * 8.0 / 1000.0 / elapsed;
            // نرخ واقعی تخلیه‌ی همین پنجره (هر ۲ ثانیه تازه می‌شود) —
            // در پنجره‌ی عادی سقف‌دار همان نرخ پله است و در پروب همان
            // ظرفیت مسیر؛ هر دو برای تشخیص گلوگاه در پنل لازم‌اند.
            *drain.lock().unwrap() = drain_kbps;
            window_bytes = 0;
            window_start = Instant::now();
            window_index += 1;
            let mut lad = ladder.lock().unwrap();
            if probe_active {
                probe_active = false;
                *last_probe.lock().unwrap() = drain_kbps;
                let before = lad.current_kbps();
                let decision = lad.note_probe(drain_kbps);
                if lad.current_kbps() != before {
                    bucket.set_rate(lad.current_kbps() as f64);
                    let _ = decision;
                }
            } else {
                let before = lad.current_kbps();
                let decision = lad.note_capacity(drain_kbps);
                if lad.current_kbps() != before {
                    bucket.set_rate(lad.current_kbps() as f64);
                    let _ = decision;
                }
                // پروب بعدی: هر ۵ پنجره، فقط وقتی در سقف نیستیم و
                // پنجره‌ی قبلی نشان داده مسیر با پله‌ی جاری همراه است.
                if lad.idx > 0
                    && window_index % 5 == 4
                    && drain_kbps >= lad.current_kbps() as f64 * 0.95
                {
                    probe_active = true;
                }
            }
        }
        // اگر چیزی برای ارسال نیست و توکن هم نیست، کمی صبر کن تا
        // حلقه CPU را اشغال نکند. در پنجره‌ی پروب صبر نمی‌کنیم تا
        // drain واقعی سوکت سنجیده شود.
        if queue.msgs.is_empty() {
            std::thread::sleep(Duration::from_millis(5));
        } else if !probe_active {
            if let Some(front) = queue.msgs.front() {
                let wait = bucket.wait_ms(front.payload.len());
                if wait > 0 {
                    std::thread::sleep(Duration::from_millis(wait.min(50)));
                }
            }
        }
    }
    // توقف تمیز: مرز سشن در لاگ می‌ماند تا نمونه‌های دو استریم
    // جدا خوانده شوند. (در قطع با خطا، سطر شروع بعدی مرز است.)
    append_log_line(log_path, &format!("# session end unix={}", unix_now()));
    Ok(())
}

// ---------------------------------------------------------------- آزمون‌ها
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ladder_steps_down_after_two_bad_windows() {
        let mut l = LadderController::new(8000);
        assert_eq!(l.current_kbps(), 8000);
        assert_eq!(l.note_capacity(4000.0), RelayDecision::Hold);
        assert_eq!(l.note_capacity(4000.0), RelayDecision::StepDown);
        assert_eq!(l.current_kbps(), 6000);
    }

    #[test]
    fn ladder_capacity_window_never_steps_up() {
        // رگرسیون باگ بحرانی ۰٫۹٫۳: پنجره‌ی عادی (drain سقف‌دار) هرگز
        // نباید صعود بدهد — صعود فقط کار پروب است. حتی با ۲۰ پنجره‌ی
        // «خوب» در ۶۰۰۰، نردبان باید همان‌جا بماند.
        let mut l = LadderController::new(8000);
        l.note_capacity(4000.0);
        l.note_capacity(4000.0); // رفت روی ۶۰۰۰
        assert_eq!(l.current_kbps(), 6000);
        for _ in 0..20 {
            assert_eq!(l.note_capacity(9000.0), RelayDecision::Hold);
        }
        assert_eq!(l.current_kbps(), 6000);
    }

    #[test]
    fn ladder_probe_steps_up_on_two_of_last_three() {
        let mut l = LadderController::new(8000);
        l.note_capacity(4000.0);
        l.note_capacity(4000.0); // رفت روی ۶۰۰۰
        assert_eq!(l.current_kbps(), 6000);
        // آستانه‌ی صعود ۸۰۰۰×۱٫۰۵=۸۴۰۰ است؛ پنجره‌ی ناقص (کمتر از
        // ۳ پروب) صعود نمی‌دهد، ولی پنجره‌ی کامل با ۳تای خوب می‌دهد.
        assert_eq!(l.note_probe(8800.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(9000.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(9000.0), RelayDecision::StepUp);
        assert_eq!(l.current_kbps(), 8000);
    }

    #[test]
    fn ladder_probe_single_bad_probe_does_not_block_climb() {
        // قانون میانه‌ای ۰٫۹٫۸: یک پروب بد وسط پنجره، صعود را خراب
        // نمی‌کند — برخلاف قانون پیاپی قبلی که شمارنده را صفر می‌کرد.
        let mut l = LadderController::new(8000);
        l.note_capacity(4000.0);
        l.note_capacity(4000.0);
        assert_eq!(l.note_probe(9000.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(9000.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(5000.0), RelayDecision::StepUp);
        assert_eq!(l.current_kbps(), 8000);
    }

    #[test]
    fn ladder_probe_two_bad_probes_block_climb() {
        // ولی دو پروب بد در پنجره‌ی ۳تایی، صعود را می‌گیرد.
        let mut l = LadderController::new(8000);
        l.note_capacity(4000.0);
        l.note_capacity(4000.0);
        assert_eq!(l.note_probe(9000.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(5000.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(5000.0), RelayDecision::Hold);
        assert_eq!(l.current_kbps(), 6000);
    }

    #[test]
    fn ladder_climbs_on_real_097_log_probes() {
        // رگرسیون لاگ ۰٫۹٫۷: نردبان روی کف ۱۵۰۰ با پروب‌های
        // ۲۳۷۳، ۲۰۲۷، ۲۸۶۱، ۲۰۲۱، ۲۸۵۱، ۲۱۳۰، ۲۵۸۴، ۳۰۲۴.
        // آستانه‌ی صعود به ۲۵۰۰ برابر ۲۵۰۰×۱٫۰۵=۲۶۲۵ است؛ قانون
        // قبلی (۳ پیاپی بالای ۲۷۵۰) هیچ‌وقت صعود نمی‌داد، قانون
        // تازه دقیقاً در پروب پنجم (۲۸۵۱) صعود می‌دهد و بعد روی
        // ۲۵۰۰ می‌ماند (آستانه‌ی ۴۰۰۰×۱٫۰۵=۴۲۰۰ دست‌نیافتنی است).
        let mut l = LadderController::new(8000);
        l.idx = 4; // پله‌ی ۱۵۰۰
        assert_eq!(l.current_kbps(), 1500);
        assert_eq!(l.note_probe(2373.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(2027.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(2861.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(2021.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(2851.0), RelayDecision::StepUp);
        assert_eq!(l.current_kbps(), 2500);
        assert_eq!(l.note_probe(2130.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(2584.0), RelayDecision::Hold);
        assert_eq!(l.note_probe(3024.0), RelayDecision::Hold);
        assert_eq!(l.current_kbps(), 2500);
    }

    #[test]
    fn ladder_never_goes_below_floor() {
        let mut l = LadderController::new(8000);
        for _ in 0..20 {
            l.note_capacity(100.0);
        }
        assert_eq!(l.current_kbps(), 1500);
    }

    #[test]
    fn ladder_top_clamps_to_settings() {
        let l = LadderController::new(4000);
        assert_eq!(l.rungs[0], 4000);
        assert_eq!(l.current_kbps(), 4000);
    }

    #[test]
    fn token_bucket_refills_and_caps() {
        let mut b = TokenBucket::new(8000.0);
        assert!(!b.try_take(1_000_000));
        std::thread::sleep(Duration::from_millis(120));
        assert!(b.try_take(50_000));
    }

    #[test]
    fn keyframe_detection() {
        assert!(is_keyframe_tag(&[0x17, 0x01, 0x00]));
        assert!(!is_keyframe_tag(&[0x27, 0x01, 0x00]));
        assert!(!is_keyframe_tag(&[]));
        // هدر سکانس AVC کی‌فریم نیست (باگ مهم ۰٫۹٫۳).
        assert!(!is_keyframe_tag(&[0x17, 0x00, 0x00]));
        assert!(is_sequence_header_tag(&[0x17, 0x00, 0x00]));
        assert!(!is_sequence_header_tag(&[0x17, 0x01, 0x00]));
    }

    #[test]
    fn queue_drops_seq_header_with_its_gop() {
        // رگرسیون باگ مهم ۰٫۹٫۳: اگر جلو هدر سکانس باشد، حذف نباید فقط
        // همان هدر را ببرد و IDR بعدی را بی‌سرپرست بگذارد؛ هدر باید با
        // GOP خودش یک‌جا حذف شود و صف از IDR بعدی شروع شود.
        let mut q = OutQueue::new(100);
        q.push(QueuedMsg { msg_type: 9, timestamp: 0, payload: vec![0x17, 0x00, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], is_keyframe: false, enqueued_at: Instant::now() });
        q.push(QueuedMsg { msg_type: 9, timestamp: 33, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: Instant::now() });
        q.push(QueuedMsg { msg_type: 9, timestamp: 66, payload: vec![0x27; 40], is_keyframe: false, enqueued_at: Instant::now() });
        // اضافه‌کردن IDR دوم باید سقف را رد کند و هدر سکانس + GOP اول
        // را با هم بیندازد، نه فقط هدر را.
        q.push(QueuedMsg { msg_type: 9, timestamp: 99, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: Instant::now() });
        assert!(q.dropped_gops >= 1);
        assert_eq!(q.msgs.front().unwrap().timestamp, 99);
    }

    #[test]
    fn queue_drops_oldest_gop_over_cap() {
        let mut q = OutQueue::new(100);
        // GOP اول: کی‌فریم + ۲ فریم عادی (هرکدام ۴۰ بایت)
        q.push(QueuedMsg { msg_type: 9, timestamp: 0, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: Instant::now() });
        q.push(QueuedMsg { msg_type: 9, timestamp: 33, payload: vec![0x27; 40], is_keyframe: false, enqueued_at: Instant::now() });
        q.push(QueuedMsg { msg_type: 9, timestamp: 66, payload: vec![0x27; 40], is_keyframe: false, enqueued_at: Instant::now() });
        // GOP دوم: کی‌فریم — اضافه‌کردنش باید سقف را رد کند و GOP اول را بیندازد
        q.push(QueuedMsg { msg_type: 9, timestamp: 99, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: Instant::now() });
        assert!(q.dropped_gops >= 1);
        assert_eq!(q.msgs.front().unwrap().timestamp, 99);
    }

    #[test]
    fn queue_age_cap_drops_stale_gop() {
        // سقف سن ۰٫۹٫۶: GOPای که بیش از ۴ ثانیه در صف مانده باید برود
        // و GOP تازه بماند — حتی وقتی سقف بایت اصلاً رد نشده است.
        let mut q = OutQueue::new(1_000_000);
        let now = Instant::now();
        let old = now - Duration::from_secs(10);
        q.push(QueuedMsg { msg_type: 9, timestamp: 0, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: old });
        q.push(QueuedMsg { msg_type: 9, timestamp: 33, payload: vec![0x27; 40], is_keyframe: false, enqueued_at: old });
        q.push(QueuedMsg { msg_type: 9, timestamp: 99, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: now });
        q.enforce_age(now);
        assert_eq!(q.dropped_gops, 1);
        assert_eq!(q.msgs.front().unwrap().timestamp, 99);
    }

    #[test]
    fn queue_age_cap_keeps_single_stale_message() {
        // حالت مرزی مثل سقف بایت: تک‌پیام تنها رها می‌شود تا صف
        // هیچ‌وقت کاملاً خالی نشود.
        let mut q = OutQueue::new(1_000_000);
        let now = Instant::now();
        q.push(QueuedMsg { msg_type: 9, timestamp: 0, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: now - Duration::from_secs(60) });
        q.enforce_age(now);
        assert_eq!(q.dropped_gops, 0);
        assert_eq!(q.msgs.len(), 1);
    }

    #[test]
    fn chunk_roundtrip_fmt0() {
        let payload = vec![7u8; 300];
        let enc = encode_message(9, 1234, 1, &payload);
        // هدر fmt=0: بایت اول 0x06 (fmt=0, csid=6)، تایم‌استمپ، طول، نوع، استریم
        assert_eq!(enc[0], 0x06);
        assert_eq!(enc[1], 0x00);
        assert_eq!(enc[2], 0x04);
        assert_eq!(enc[3], 0xD2);
        let (fmt, csid, n) = parse_basic_header(&enc).unwrap();
        assert_eq!((fmt, csid, n), (0, 6, 1));
        let (h, used) = parse_msg_header(0, &enc[1..], None).unwrap();
        assert_eq!(h.msg_type, 9);
        assert_eq!(h.timestamp, 1234);
        assert_eq!(h.length, 300);
        assert_eq!(used, 11);
    }

    #[test]
    fn chunk_extended_timestamp_fmt0_roundtrip() {
        // تایم‌استمپ بالای 0xFFFFFF (استریم طولانی‌تر از ~۴٫۷ ساعت):
        // انکود باید FF FF FF + تایم‌استمپ ۴ بایتی بگذارد و پارس باید
        // همان مقدار را برگرداند. (باگ ۰٫۹٫۳ دقیقاً اینجا بود.)
        let ts: u32 = 0x01000000;
        let enc = encode_message(9, ts, 1, &[9u8; 10]);
        assert_eq!(&enc[1..4], &[0xFF, 0xFF, 0xFF]);
        assert_eq!(&enc[12..16], &[0x01, 0x00, 0x00, 0x00]);
        let (h, used) = parse_msg_header(0, &enc[1..], None).unwrap();
        assert_eq!(h.timestamp, ts);
        assert_eq!(used, 15);
    }

    #[test]
    fn chunk_extended_timestamp_fmt1_parse() {
        // fmt=1 با دلتای 0xFFFFFF + extended: طبق اسپک، extended در
        // fmt=1/2 «دلتا» است، پس تایم‌استمپ = قبلی + extended.
        // (تفسیر مطلق قبلی غلط بود و پرش به عقب می‌داد.)
        let prev = MsgHeader { msg_type: 9, timestamp: 1000, stream_id: 1, length: 100, extended: false };
        let buf: Vec<u8> = vec![
            0xFF, 0xFF, 0xFF, // delta = 0xFFFFFF → extended دارد
            0x00, 0x00, 0x64, // length = 100
            0x09, // type = video
            0x02, 0x00, 0x00, 0x00, // extended delta = 0x02000000
        ];
        let (h, used) = parse_msg_header(1, &buf, Some(&prev)).unwrap();
        assert_eq!(h.timestamp, 1000 + 0x02000000);
        assert_eq!(h.length, 100);
        assert_eq!(used, 11);
    }

    #[test]
    fn chunk_extended_multi_chunk_loopback() {
        // رگرسیون باگ مهم ۰٫۹٫۳: پیام با تایم‌استمپ extended که به دو
        // چانک تقسیم می‌شود، باید از راه ChunkConn سالم برگردد — یعنی
        // انکودر extended را روی چانک ادامه هم بنویسد و خواننده آن را
        // مصرف کند، وگرنه بدنه خراب و استریم از همگام می‌افتد.
        use std::io::Write;
        use std::net::TcpListener;
        let payload: Vec<u8> = (0..5000u32).map(|i| (i % 251) as u8).collect();
        // اول Set Chunk Size تا خواننده چانک ۴۰۹۶ را بشناسد (مثل جریان
        // واقعی که قبل از مدیا chunk size ردوبدل می‌شود).
        let mut enc = encode_message(1, 0, 0, &(CHUNK_SIZE_NEGOTIATED).to_be_bytes());
        enc.extend_from_slice(&encode_message(9, 0x01000000, 1, &payload));
        assert!(enc.len() > CHUNK_SIZE_NEGOTIATED as usize);
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        let writer = std::thread::spawn(move || {
            let (mut s, _) = listener.accept().unwrap();
            s.write_all(&enc).unwrap();
        });
        let stream = TcpStream::connect(addr).unwrap();
        stream.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
        let mut conn = ChunkConn::new(stream);
        let mut got = None;
        for _ in 0..100 {
            match conn.read_message() {
                Ok(Some(m)) => {
                    got = Some(m);
                    break;
                }
                Ok(None) => std::thread::sleep(Duration::from_millis(20)),
                Err(e) => panic!("خواندن loopback ناموفق: {e}"),
            }
        }
        writer.join().unwrap();
        let (h, body) = got.expect("پیام extended چندچانکی خوانده نشد");
        assert_eq!(h.timestamp, 0x01000000);
        assert_eq!(h.msg_type, 9);
        assert_eq!(body, payload);
    }

    #[test]
    fn amf_string_number_roundtrip() {
        let mut v = amf_str("connect");
        v.extend_from_slice(&amf_num(0.0));
        let mut r = AmfReader::new(&v);
        assert_eq!(r.value(), Some(AmfValue::Str("connect".to_string())));
        assert_eq!(r.value(), Some(AmfValue::Number(0.0)));
    }

    #[test]
    fn target_parse_ok_and_bad() {
        assert_eq!(
            RelayRuntime::parse_target("rtmp://live.kick.example.com:1935/app").unwrap(),
            ("live.kick.example.com".to_string(), 1935, "app".to_string())
        );
        assert!(RelayRuntime::parse_target("http://x/app").is_err());
        assert!(RelayRuntime::parse_target("rtmp://host").is_err());
    }

    #[test]
    fn log_sample_line_format() {
        // خروجی دقیق سطر نمونه: اعداد اعشاری با یک رقم اعشار برای
        // سن صف و بدون اعشار برای بقیه — پارسر تحلیل لاگ روی همین
        // قالب حساب می‌کند.
        assert_eq!(
            format_log_sample(1700000000, 65, 6000, 6123.6, 0.0, 123456, 3.7, 5987.2, 987654321, 54321, 12, 345678, ""),
            "1700000000,65,6000,6124,0,123456,3.7,5987,987654321,54321,12,345678,"
        );
    }

    #[test]
    fn log_field_sanitized() {
        // ویرگول و خط جدید در خطا، سطر CSV را نمی‌شکند.
        assert_eq!(
            sanitize_log_field("ارسال, قطع شد\nدوباره"),
            "ارسال؛ قطع شد دوباره"
        );
    }

    #[test]
    fn log_path_is_findable() {
        // مسیر همیشه یک فایل با همین نام است و پوشه‌ی والدش واقعاً
        // وجود دارد — وگرنه کاربر فایل را پیدا نمی‌کند.
        let p = pick_log_path();
        assert_eq!(p.file_name().unwrap(), RELAY_LOG_FILE);
        assert!(p.parent().unwrap().is_dir());
    }
}
