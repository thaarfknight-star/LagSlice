// رله‌ی RTMP برای LagSlice (نسخه‌ی مجهز به Pre-buffer شروع لایو، سقف ۳ ثانیه و پیوستگی تایم‌استمپ)
// Copyright (c) 2026 Taha Arefi — دوگانه‌ی MIT / Apache-2.0 (مطابق درخت جاری ریپو).

use std::collections::{HashMap, VecDeque};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

// ------------------------------------------------------------- فیلتر هوشمند GOP
/// یک پیام RTMP کاملِ آماده‌ی ارسال (بدون هدر چانک).
#[derive(Clone)]
pub struct QueuedMsg {
    pub msg_type: u8, // 8=audio, 9=video, 18=data
    pub timestamp: u32,
    pub payload: Vec<u8>,
    /// فقط برای ویدیو: آیا این پیام شروع یک GOP است (کی‌فریم)؟
    pub is_keyframe: bool,
    /// لحظه‌ی رسیدن از Meld — مبنای سقف سن صف (حداکثر ۳ ثانیه).
    pub enqueued_at: Instant,
}

/// تشخیص کی‌فریم در تگ ویدیوی FLV.
pub fn is_keyframe_tag(payload: &[u8]) -> bool {
    if payload.is_empty() || (payload[0] & 0xF0) != 0x10 {
        return false;
    }
    let codec = payload[0] & 0x0F;
    if codec == 7 || codec == 12 {
        payload.get(1) == Some(&1)
    } else {
        true
    }
}

/// تشخیص هدر سکانس AVC/HEVC (0x17 0x00) که پارامترهای دیکودر است و نباید حذف شود.
pub fn is_sequence_header_tag(payload: &[u8]) -> bool {
    if payload.len() < 2 {
        return false;
    }
    let codec = payload[0] & 0x0F;
    ((codec == 7 || codec == 12) && (payload[0] & 0xF0) == 0x10 && payload[1] == 0)
        || (payload[0] == 0x17 && payload[1] == 0)
}

/// تشخیص هدر سکانس صدای AAC (0xAF 0x00)
pub fn is_audio_sequence_header(payload: &[u8]) -> bool {
    payload.len() >= 2 && (payload[0] >> 4) == 10 && payload[1] == 0
}

/// تشخیص فریم‌های غیرمرجع ویدیو (Disposable / B-Frame)
pub fn is_disposable_video_tag(payload: &[u8]) -> bool {
    !payload.is_empty() && (payload[0] & 0xF0) == 0x30
}

/// صف خروجی هوشمند با پیش‌بافرینگ شروع استریم و سقف ۳ ثانیه
pub struct OutQueue {
    pub msgs: VecDeque<QueuedMsg>,
    pub bytes: usize,
    pub max_bytes: usize,
    pub dropped_gops: u64,
    pub dropped_bytes: u64,
    pub dropping_until_keyframe: bool,
}

impl OutQueue {
    pub fn new(max_bytes: usize) -> Self {
        Self {
            msgs: VecDeque::with_capacity(1024),
            bytes: 0,
            max_bytes,
            dropped_gops: 0,
            dropped_bytes: 0,
            dropping_until_keyframe: false,
        }
    }

    pub fn push(&mut self, m: QueuedMsg) {
        if m.msg_type == 9 && !is_sequence_header_tag(&m.payload) {
            if self.dropping_until_keyframe {
                if m.is_keyframe {
                    self.dropping_until_keyframe = false;
                } else {
                    self.dropped_bytes += m.payload.len() as u64;
                    return;
                }
            }
        }

        self.bytes += m.payload.len();
        self.msgs.push_back(m);
        self.enforce_cap();
    }

    /// حذف تمیز قدیمی‌ترین GOP کامل از ابتدای صف تا رسیدن به کی‌فریم بعدی
    fn drop_front_gop(&mut self) -> usize {
        let kf_count = self
            .msgs
            .iter()
            .filter(|m| m.msg_type == 9 && m.is_keyframe)
            .count();

        let mut removed_bytes = 0usize;
        let mut dropped_video_frames = 0usize;
        let mut kept_headers = VecDeque::new();

        while let Some(front) = self.msgs.front() {
            if front.msg_type == 9 && front.is_keyframe && dropped_video_frames > 0 {
                break;
            }
            let m = self.msgs.pop_front().unwrap();

            // اگر هدر سکانس صدا یا متادیتای اولیه است، هرگز حذف نشود
            if (m.msg_type == 8 && is_audio_sequence_header(&m.payload)) || m.msg_type == 18 {
                kept_headers.push_back(m);
                continue;
            }

            if m.msg_type == 9 && !is_sequence_header_tag(&m.payload) {
                dropped_video_frames += 1;
            }
            removed_bytes += m.payload.len();
        }

        if kf_count <= 1 && dropped_video_frames > 0 {
            let has_kf_now = self
                .msgs
                .iter()
                .any(|m| m.msg_type == 9 && m.is_keyframe);
            if !has_kf_now {
                self.dropping_until_keyframe = true;
            }
        }

        while let Some(hdr) = kept_headers.pop_back() {
            self.msgs.push_front(hdr);
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
        while self.bytes > self.max_bytes && self.msgs.len() > 1 {
            if self.drop_front_gop() == 0 {
                break;
            }
        }
    }

    /// اعمال سقف سن صف (حداکثر ۳ ثانیه در حین استریم)
    pub fn enforce_age(&mut self, now: Instant, cap: Duration) {
        while self.msgs.len() > 1 {
            let Some(front) = self.msgs.front() else {
                break;
            };
            if now.saturating_duration_since(front.enqueued_at) <= cap {
                break;
            }
            if self.drop_front_gop() == 0 {
                break;
            }
        }
    }

    pub fn oldest_age(&self, now: Instant) -> Duration {
        self.msgs
            .front()
            .map(|m| now.saturating_duration_since(m.enqueued_at))
            .unwrap_or(Duration::ZERO)
    }
}

// ---------------------------------------------------------------- RTMP
pub const RTMP_VERSION: u8 = 3;
pub const CHUNK_SIZE_DEFAULT: usize = 128;
pub const CHUNK_SIZE_NEGOTIATED: u32 = 4096;

pub fn client_handshake_bytes() -> Vec<u8> {
    let mut v = Vec::with_capacity(1537);
    v.push(RTMP_VERSION);
    v.extend_from_slice(&[0u8; 4]);
    v.extend_from_slice(&[0u8; 4]);
    v.extend_from_slice(&[0u8; 1528]);
    v
}

pub fn check_server_version(b: u8) -> bool {
    b == RTMP_VERSION
}

#[derive(Debug, Clone, Copy)]
pub struct MsgHeader {
    pub msg_type: u8,
    pub timestamp: u32,
    pub stream_id: u32,
    pub length: usize,
    pub extended: bool,
}

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
                MsgHeader {
                    msg_type,
                    timestamp: ts_full,
                    stream_id,
                    length: len,
                    extended,
                },
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
            let mut ts = prev.timestamp.wrapping_add(ts_delta);
            let mut n = 7;
            let extended = ts_delta == 0xFFFFFF;
            if extended {
                if buf.len() < 11 {
                    return None;
                }
                let ext_delta = u32::from_be_bytes([buf[7], buf[8], buf[9], buf[10]]);
                ts = prev.timestamp.wrapping_add(ext_delta);
                n = 11;
            }
            Some((
                MsgHeader {
                    msg_type,
                    timestamp: ts,
                    stream_id: prev.stream_id,
                    length: len,
                    extended,
                },
                n,
            ))
        }
        2 => {
            if buf.len() < 3 {
                return None;
            }
            let ts_delta = u24(&buf[0..3]);
            let prev = p?;
            let mut ts = prev.timestamp.wrapping_add(ts_delta);
            let mut n = 3;
            let extended = ts_delta == 0xFFFFFF;
            if extended {
                if buf.len() < 7 {
                    return None;
                }
                let ext_delta = u32::from_be_bytes([buf[3], buf[4], buf[5], buf[6]]);
                ts = prev.timestamp.wrapping_add(ext_delta);
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
            _ => None,
        }
    }

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

pub fn amf_result(txn: f64, extra: &[u8]) -> Vec<u8> {
    let mut v = amf_str("_result");
    v.extend_from_slice(&amf_num(txn));
    v.extend_from_slice(&amf_null());
    v.extend_from_slice(extra);
    v
}

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
#[derive(Clone, Debug)]
pub struct RelaySnapshot {
    pub running: bool,
    pub target_host: String,
    pub listen_addr: String,
    pub current_kbps: u32,
    pub capacity_ema_kbps: f64,
    pub forwarded_bytes: u64,
    pub forwarded_msgs: u64,
    pub dropped_gops: u64,
    pub dropped_bytes: u64,
    pub queue_bytes: usize,
    pub queue_age_secs: f64,
    pub drain_kbps: f64,
    pub uptime_secs: u64,
    pub last_error: Option<String>,
    pub log_path: String,
}

pub struct RelayStats {
    pub forwarded_bytes: u64,
    pub forwarded_msgs: u64,
    pub dropped_gops: u64,
    pub dropped_bytes: u64,
}

pub struct RelayRuntime {
    stop: Arc<AtomicBool>,
    stats: Arc<Mutex<RelayStats>>,
    drain_ema: Arc<Mutex<f64>>,
    queue_bytes: Arc<Mutex<usize>>,
    queue_age: Arc<Mutex<f64>>,
    drain: Arc<Mutex<f64>>,
    input_kbps: Arc<Mutex<f64>>,
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
            drain_ema: Arc::new(Mutex::new(0.0)),
            queue_bytes: Arc::new(Mutex::new(0)),
            queue_age: Arc::new(Mutex::new(0.0)),
            drain: Arc::new(Mutex::new(0.0)),
            input_kbps: Arc::new(Mutex::new(0.0)),
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

    pub fn start(&mut self, target_url: &str, stream_key: &str) -> Result<(), String> {
        if self.is_running() {
            return Err("رله از قبل در حال اجراست".to_string());
        }
        let (host, port, app) = Self::parse_target(target_url)?;
        if stream_key.trim().is_empty() {
            return Err("کلید استریم خالی است".to_string());
        }
        if let Some(h) = self.handle.take() {
            let _ = h.join();
        }
        *self.last_error.lock().unwrap() = None;
        *self.target_host.lock().unwrap() = host.clone();
        self.stream_key = stream_key.to_string();
        self.stop.store(false, Ordering::SeqCst);
        self.running.store(true, Ordering::SeqCst);
        *self.started_at.lock().unwrap() = Some(Instant::now());
        let log_path = pick_log_path();
        *self.log_path.lock().unwrap() = log_path.to_string_lossy().into_owned();

        let stop = self.stop.clone();
        let stats = self.stats.clone();
        let drain_ema = self.drain_ema.clone();
        let queue_bytes = self.queue_bytes.clone();
        let queue_age = self.queue_age.clone();
        let drain = self.drain.clone();
        let input_kbps = self.input_kbps.clone();
        let last_error = self.last_error.clone();
        let running = self.running.clone();
        let key = stream_key.to_string();
        let target = format!("rtmp://{host}:{port}/{app}");
        self.handle = Some(std::thread::spawn(move || {
            let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                run_pump(
                    stop,
                    &stats,
                    &queue_bytes,
                    &queue_age,
                    &drain,
                    &drain_ema,
                    input_kbps,
                    &target,
                    &key,
                    &log_path,
                )
            }));
            match res {
                Ok(inner) => {
                    if let Err(e) = inner {
                        *last_error.lock().unwrap() = Some(e);
                    }
                }
                Err(payload) => {
                    *last_error.lock().unwrap() = Some(format!(
                        "نخ رله ناگهان از کار افتاد: {}",
                        panic_message(&payload)
                    ));
                }
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
            current_kbps: *self.input_kbps.lock().unwrap() as u32,
            capacity_ema_kbps: *self.drain_ema.lock().unwrap(),
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

// ------------------------------------------------------------- پمپ RTMP (با پیش‌بافرینگ ۲.۵ ثانیه‌ای در شروع لایو)
/// سقف بایت صف خروجی: ۶ مگابایت (نگهبان حافظه).
const MAX_QUEUE_BYTES: usize = 6_000_000;
/// زمان پیش‌بافرینگ در لحظه شروع استریم (وقتی بیت‌ریت از Meld می‌آید):
/// برنامه دقیقاً ۲.۵ ثانیه صبر می‌کند تا بافر پر و پایدار شود و سپس لایو را روان شروع می‌کند.
const DELAY_LINE: Duration = Duration::from_millis(2500);
/// سقف قطعی سن صف پس از شروع پخش: حداکثر ۳.۰ ثانیه (۳۰۰۰ میلی‌ثانیه).
const QUEUE_AGE_CAP: Duration = Duration::from_millis(3000);
/// سقف موقت سن صف در ۵ ثانیه اول شروع استریم، تا جهش اولیه بیت‌ریت Meld باعث حذف فریم در اول لایو نشود.
const STARTUP_GRACE_AGE_CAP: Duration = Duration::from_millis(4800);
const SOFT_CATCHUP_AGE: Duration = Duration::from_millis(2400);
const UPSTREAM_STALL_LIMIT: Duration = Duration::from_secs(120);
const UPSTREAM_STALL_NOTE: Duration = Duration::from_secs(10);
const SEND_SLICE_MSGS: usize = 64;
const WINDOW_SECS: f64 = 2.0;

// ------------------------------------------------------------- لاگ رله
const RELAY_LOG_FILE: &str = "LagSlice-relay-log.csv";
const RELAY_LOG_INTERVAL: Duration = Duration::from_secs(5);
const RELAY_LOG_HEADER: &str = "unix_s,uptime_s,current_kbps,capacity_ema_kbps,probe_kbps,queue_bytes,queue_age_s,drain_kbps,forwarded_bytes,forwarded_msgs,dropped_gops,dropped_bytes,last_error";

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

fn sanitize_log_field(s: &str) -> String {
    s.replace(',', "؛").replace(['\r', '\n'], " ")
}

fn session_end_line(unix: u64, result: &Result<(), String>) -> String {
    match result {
        Ok(()) => format!("# session end unix={unix} result=ok"),
        Err(e) => format!(
            "# session end unix={unix} result=error: {}",
            sanitize_log_field(e)
        ),
    }
}

fn panic_message(payload: &Box<dyn std::any::Any + Send>) -> String {
    if let Some(s) = payload.downcast_ref::<&str>() {
        s.to_string()
    } else if let Some(s) = payload.downcast_ref::<String>() {
        s.clone()
    } else {
        "نامشخص".to_string()
    }
}

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
    stop_flag: Option<Arc<AtomicBool>>,
}

impl ChunkConn {
    fn new(stream: TcpStream) -> Self {
        Self {
            stream,
            chunk_size: CHUNK_SIZE_DEFAULT,
            prev_headers: HashMap::new(),
            stop_flag: None,
        }
    }

    fn set_stop_flag(&mut self, flag: Arc<AtomicBool>) {
        self.stop_flag = Some(flag);
    }

    fn read_exact_into(&mut self, out: &mut [u8]) -> std::io::Result<()> {
        if self.stop_flag.is_none() {
            return self.stream.read_exact(out);
        }
        let mut done = 0;
        while done < out.len() {
            match self.stream.read(&mut out[done..]) {
                Ok(0) => {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::UnexpectedEof,
                        "اتصال بسته شد",
                    ))
                }
                Ok(n) => done += n,
                Err(e)
                    if e.kind() == std::io::ErrorKind::WouldBlock
                        || e.kind() == std::io::ErrorKind::TimedOut =>
                {
                    if self
                        .stop_flag
                        .as_ref()
                        .map(|f| f.load(Ordering::SeqCst))
                        .unwrap_or(false)
                    {
                        return Err(std::io::Error::new(
                            std::io::ErrorKind::Interrupted,
                            "توقف در میانه‌ی خواندن",
                        ));
                    }
                }
                Err(e) => return Err(e),
            }
        }
        Ok(())
    }

    fn read_message(&mut self) -> std::io::Result<Option<(MsgHeader, Vec<u8>)>> {
        let b0 = match self.read_byte_timeout()? {
            Some(b) => b,
            None => return Ok(None),
        };
        let fmt = b0 >> 6;
        let mut csid = (b0 & 0x3F) as u32;
        if csid == 0 {
            let b = self.read_byte_blocking()?;
            csid = 64 + b as u32;
        } else if csid == 1 {
            let b1 = self.read_byte_blocking()?;
            let b2 = self.read_byte_blocking()?;
            csid = 64 + b1 as u32 + 256 * b2 as u32;
        }
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
            let mut sb = vec![0u8; 4];
            self.read_exact_into(&mut sb)?;
            let size = u32::from_be_bytes(sb.try_into().unwrap()) as usize;
            if size > 0 {
                self.chunk_size = size;
            }
            return self.read_message();
        }
        let mut body = Vec::with_capacity(header.length);
        let mut remaining = header.length;
        let mut first = true;
        let cur_extended = header.extended;
        while remaining > 0 {
            if !first {
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
            Err(e)
                if e.kind() == std::io::ErrorKind::WouldBlock
                    || e.kind() == std::io::ErrorKind::TimedOut =>
            {
                Ok(None)
            }
            Err(e) => Err(e),
        }
    }

    fn read_byte_blocking(&mut self) -> std::io::Result<u8> {
        let mut b = [0u8; 1];
        self.read_exact_into(&mut b)?;
        Ok(b[0])
    }
}

fn write_all(stream: &mut TcpStream, bytes: &[u8]) -> std::io::Result<()> {
    stream.write_all(bytes)
}

fn write_all_retry<W: Write>(
    stream: &mut W,
    bytes: &[u8],
    stop: &AtomicBool,
) -> std::io::Result<Option<Duration>> {
    let mut done = 0usize;
    let mut stall_since: Option<Instant> = None;
    let mut max_stall = Duration::ZERO;
    while done < bytes.len() {
        match stream.write(&bytes[done..]) {
            Ok(0) => {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::UnexpectedEof,
                    "اتصال بسته شد",
                ))
            }
            Ok(n) => {
                done += n;
                if let Some(s) = stall_since.take() {
                    max_stall = max_stall.max(s.elapsed());
                }
            }
            Err(e)
                if e.kind() == std::io::ErrorKind::WouldBlock
                    || e.kind() == std::io::ErrorKind::TimedOut =>
            {
                if stop.load(Ordering::SeqCst) {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::Interrupted,
                        "توقف در میانه‌ی ارسال به ingest",
                    ));
                }
                if stall_since.is_none() {
                    stall_since = Some(Instant::now());
                }
                if stall_since.unwrap().elapsed() > UPSTREAM_STALL_LIMIT {
                    return Err(std::io::Error::new(
                        std::io::ErrorKind::TimedOut,
                        "ارسال به ingest بیش از ۱۲۰ ثانیه متوقف ماند",
                    ));
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            Err(e) => return Err(e),
        }
    }
    if max_stall >= Duration::from_secs(1) {
        Ok(Some(max_stall))
    } else {
        Ok(None)
    }
}

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
    let mut s = vec![RTMP_VERSION];
    s.extend_from_slice(&[0u8; 1536]);
    s.extend_from_slice(&c1);
    stream.write_all(&s)?;
    stream.flush()?;
    let mut c2 = [0u8; 1536];
    stream.read_exact(&mut c2)?;
    Ok(())
}

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
    stream.write_all(&s1)?;
    stream.flush()?;
    Ok(())
}

fn send_chunk_size(stream: &mut TcpStream, size: u32) -> std::io::Result<()> {
    let mut msg = vec![0u8; 4];
    msg[0] = (size >> 24) as u8;
    msg[1] = (size >> 16) as u8;
    msg[2] = (size >> 8) as u8;
    msg[3] = size as u8;
    let chunk = encode_message(1, 0, 0, &msg);
    stream.write_all(&chunk)
}

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

fn delay_send_wait(age: Duration) -> Option<Duration> {
    if age < DELAY_LINE {
        Some(std::cmp::min(DELAY_LINE - age, Duration::from_millis(30)))
    } else {
        None
    }
}

struct StopOnDrop(Arc<AtomicBool>);
impl Drop for StopOnDrop {
    fn drop(&mut self) {
        self.0.store(true, Ordering::SeqCst);
    }
}

/// نخ خواننده‌ی Meld: در ۵ ثانیه اول شروع استریم (فاز Pre-buffer)، مهلت سقف سن را
/// روی ۴.۸ ثانیه می‌گذارد تا بافر ۲.۵ ثانیه‌ای بدون هیچ حذفی پر شود؛ سپس سقف قطعی ۳ ثانیه را اعمال می‌کند.
fn run_reader(
    mut meld_conn: ChunkConn,
    queue: &Mutex<OutQueue>,
    stop: &AtomicBool,
    input_kbps: &Mutex<f64>,
    prebuffer_done: &AtomicBool,
) -> Result<(), String> {
    let mut rate_start = Instant::now();
    let mut rate_bytes: u64 = 0;
    let reader_started = Instant::now();

    while !stop.load(Ordering::SeqCst) {
        match meld_conn.read_message() {
            Ok(Some((h, body))) => match h.msg_type {
                8 | 9 | 18 => {
                    let is_kf = h.msg_type == 9 && is_keyframe_tag(&body);
                    rate_bytes += body.len() as u64;
                    if rate_start.elapsed().as_secs_f64() >= 1.0 {
                        let elapsed = rate_start.elapsed().as_secs_f64().max(0.1);
                        let rate = rate_bytes as f64 * 8.0 / 1000.0 / elapsed;
                        let mut cur = input_kbps.lock().unwrap();
                        if *cur <= 0.0 {
                            *cur = rate;
                        } else {
                            *cur = 0.4 * rate + 0.6 * *cur;
                        }
                        rate_bytes = 0;
                        rate_start = Instant::now();
                    }
                    let now = Instant::now();
                    let mut q = queue.lock().unwrap();

                    if prebuffer_done.load(Ordering::Relaxed)
                        && h.msg_type == 9
                        && is_disposable_video_tag(&body)
                        && q.oldest_age(now) >= SOFT_CATCHUP_AGE
                    {
                        q.dropped_bytes += body.len() as u64;
                        continue;
                    }

                    q.push(QueuedMsg {
                        msg_type: h.msg_type,
                        timestamp: h.timestamp,
                        payload: body,
                        is_keyframe: is_kf,
                        enqueued_at: now,
                    });

                    let active_cap = if !prebuffer_done.load(Ordering::Relaxed)
                        && reader_started.elapsed() < Duration::from_secs(6)
                    {
                        STARTUP_GRACE_AGE_CAP
                    } else {
                        QUEUE_AGE_CAP
                    };
                    q.enforce_age(now, active_cap);
                }
                _ => {}
            },
            Ok(None) => {}
            Err(e) => {
                if e.kind() == std::io::ErrorKind::Interrupted {
                    return Ok(());
                }
                stop.store(true, Ordering::SeqCst);
                return Err(format!("خواندن از Meld قطع شد: {e}"));
            }
        }
    }
    Ok(())
}

fn run_pump(
    stop: Arc<AtomicBool>,
    stats: &Mutex<RelayStats>,
    queue_bytes: &Mutex<usize>,
    queue_age: &Mutex<f64>,
    drain: &Mutex<f64>,
    drain_ema: &Mutex<f64>,
    input_kbps: Arc<Mutex<f64>>,
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
    meld_stream
        .set_nonblocking(false)
        .map_err(|e| e.to_string())?;
    meld_stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    meld_stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    meld_stream
        .set_nodelay(true)
        .map_err(|e| e.to_string())?;
    let mut meld = meld_stream;
    server_handshake(&mut meld).map_err(|e| format!("هندشیک با Meld ناموفق: {e}"))?;
    send_chunk_size(&mut meld, CHUNK_SIZE_NEGOTIATED)
        .map_err(|e| format!("ارسال chunk size به Meld ناموفق: {e}"))?;
    let mut meld_conn = ChunkConn::new(meld);

    let (txn, args) = wait_command(&mut meld_conn, "connect", Duration::from_secs(10))
        .map_err(|e| format!("Meld connect نفرستاد: {e}"))?;
    let _ = args;
    let mut resp = amf_result(
        txn,
        &amf_object(&[
            ("fmsVer", AmfValue::Str("FMS/3,5,7,700".to_string())),
            ("capabilities", AmfValue::Number(31.0)),
            ("mode", AmfValue::Number(1.0)),
        ]),
    );
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
    meld_conn
        .stream
        .set_read_timeout(Some(Duration::from_millis(200)))
        .map_err(|e| e.to_string())?;

    let up_addr = format!("{host}:{port}");
    let mut up = TcpStream::connect(&up_addr)
        .map_err(|e| format!("اتصال به {host}:{port} ناموفق بود: {e}"))?;
    up.set_nodelay(true).map_err(|e| e.to_string())?;
    up.set_read_timeout(Some(Duration::from_secs(10)))
        .map_err(|e| e.to_string())?;
    up.set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|e| e.to_string())?;
    client_handshake(&mut up).map_err(|e| format!("هندشیک با ingest ناموفق: {e}"))?;
    send_chunk_size(&mut up, CHUNK_SIZE_NEGOTIATED)
        .map_err(|e| format!("ارسال chunk size به ingest ناموفق: {e}"))?;
    let mut up_conn = ChunkConn::new(up);

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
    let (conn_name, _, conn_args) =
        wait_command_any(&mut up_conn, &["_result", "_error"], Duration::from_secs(10))
            .map_err(|e| format!("پاسخ connect از ingest نیامد: {e}"))?;
    if conn_name == "_error" {
        let detail = amf_get(&conn_args, "description")
            .or_else(|| amf_get(&conn_args, "code"))
            .unwrap_or("نامشخص");
        return Err(format!("ingest اتصال را رد کرد: {detail}"));
    }

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
    up_conn
        .stream
        .set_read_timeout(Some(Duration::from_millis(200)))
        .map_err(|e| e.to_string())?;

    append_log_line(
        log_path,
        &format!(
            "# session start unix={} target={} version={}",
            unix_now(),
            target_url,
            env!("CARGO_PKG_VERSION")
        ),
    );
    let queue = Arc::new(Mutex::new(OutQueue::new(MAX_QUEUE_BYTES)));
    let prebuffer_done = Arc::new(AtomicBool::new(false));
    let mut window_start = Instant::now();
    let mut window_bytes: u64 = 0;
    let pump_start = Instant::now();
    let mut last_log = pump_start;

    // متغیرهای پیوستگی تایم‌استمپ (جلوگیری از پرش زمانی در پلیر مقصد بعد از حذف GOP)
    let mut last_raw_ts: Option<u32> = None;
    let mut last_out_ts: u32 = 0;

    let _stop_guard = StopOnDrop(stop.clone());
    let mut pump_res: Result<(), String> = Ok(());
    meld_conn.set_stop_flag(stop.clone());
    let reader_handle = {
        let reader_queue = queue.clone();
        let reader_stop = stop.clone();
        let reader_input = input_kbps.clone();
        let reader_prebuf = prebuffer_done.clone();
        std::thread::spawn(move || {
            run_reader(
                meld_conn,
                &reader_queue,
                &reader_stop,
                &reader_input,
                &reader_prebuf,
            )
        })
    };

    'pump: while !stop.load(Ordering::SeqCst) {
        let now = Instant::now();
        let is_prebuffered = prebuffer_done.load(Ordering::Relaxed);

        let (q_bytes, q_age, d_gops, d_bytes) = {
            let mut q = queue.lock().unwrap();
            if is_prebuffered {
                q.enforce_age(now, QUEUE_AGE_CAP);
            }
            let age_s = q.oldest_age(now).as_secs_f64();
            (q.bytes, age_s, q.dropped_gops, q.dropped_bytes)
        };

        *queue_bytes.lock().unwrap() = q_bytes;
        *queue_age.lock().unwrap() = q_age;
        {
            let mut st = stats.lock().unwrap();
            st.dropped_gops = d_gops;
            st.dropped_bytes = d_bytes;
        }

        if last_log.elapsed() >= RELAY_LOG_INTERVAL {
            last_log = Instant::now();
            let cur = *input_kbps.lock().unwrap() as u32;
            let ema = *drain_ema.lock().unwrap();
            let st = stats.lock().unwrap();
            let line = format_log_sample(
                unix_now(),
                pump_start.elapsed().as_secs(),
                cur,
                ema,
                0.0,
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

        // فاز پیش‌بافرینگ (Pre-buffering) در لحظه لایو شدن:
        // وقتی بیت‌ریت از Meld می‌آید، هدرهای کانفیگ صدا/تصویر (timestamp=0) بلافاصله ارسال می‌شوند،
        // اما فریم‌های اصلی دقیقاً ۲.۵ ثانیه (DELAY_LINE) در صف جمع می‌شوند و سپس پخش زنده بدون تیک شروع می‌شود!
        if !is_prebuffered {
            let wait_opt = {
                let q = queue.lock().unwrap();
                if let Some(front) = q.msgs.front() {
                    let is_init_header = front.msg_type == 18
                        || is_sequence_header_tag(&front.payload)
                        || (front.msg_type == 8 && is_audio_sequence_header(&front.payload));
                    if is_init_header {
                        None
                    } else {
                        let age = Instant::now().saturating_duration_since(front.enqueued_at);
                        if age >= DELAY_LINE {
                            prebuffer_done.store(true, Ordering::Relaxed);
                            None
                        } else {
                            delay_send_wait(age)
                        }
                    }
                } else {
                    Some(Duration::from_millis(20))
                }
            };

            if let Some(w) = wait_opt {
                std::thread::sleep(w);
                continue;
            }
        }

        let mut sent_this_pass = 0usize;
        loop {
            if sent_this_pass >= SEND_SLICE_MSGS {
                break;
            }

            // اگر هنوز در فاز Pre-buffer هستیم، فقط هدرهای اولیه را بفرست تا زمانی که سن صف به ۲.۵ ثانیه برسد
            if !prebuffer_done.load(Ordering::Relaxed) {
                let can_send_now = {
                    let q = queue.lock().unwrap();
                    if let Some(front) = q.msgs.front() {
                        let is_init_header = front.msg_type == 18
                            || is_sequence_header_tag(&front.payload)
                            || (front.msg_type == 8 && is_audio_sequence_header(&front.payload));
                        let age = Instant::now().saturating_duration_since(front.enqueued_at);
                        if age >= DELAY_LINE {
                            prebuffer_done.store(true, Ordering::Relaxed);
                            true
                        } else {
                            is_init_header
                        }
                    } else {
                        false
                    }
                };
                if !can_send_now {
                    break;
                }
            }

            let m = {
                let mut q = queue.lock().unwrap();
                let Some(_) = q.msgs.front() else {
                    break;
                };
                let m = q.msgs.pop_front().unwrap();
                q.bytes = q.bytes.saturating_sub(m.payload.len());
                m
            };

            // تنظیم پیوسته تایم‌استمپ خروجی (حذف شکاف زمانی بعد از Drop شدن GOP)
            let smooth_ts = if let Some(prev_raw) = last_raw_ts {
                let raw_delta = m.timestamp.saturating_sub(prev_raw);
                // اگر بین دو فریم بیش از ۴۰۰ میلی‌ثانیه شکاف افتاده باشد (یعنی یک GOP در میان حذف شده)،
                // گام زمانی را به ۳۳ میلی‌ثانیه (یک فریم نرمال) محدود کن تا پلیر مقصد فریز نکند!
                let clamped_delta = if raw_delta > 400 { 33 } else { raw_delta };
                last_out_ts.wrapping_add(clamped_delta)
            } else {
                m.timestamp
            };
            last_raw_ts = Some(m.timestamp);
            last_out_ts = smooth_ts;

            let chunk = encode_message(m.msg_type, smooth_ts, up_stream_id, &m.payload);

            match write_all_retry(&mut up_conn.stream, &chunk, &stop) {
                Ok(Some(stall)) if stall >= UPSTREAM_STALL_NOTE => {
                    append_log_line(
                        log_path,
                        &format!("# ingest stall recovered after {}s", stall.as_secs()),
                    );
                }
                Ok(_) => {}
                Err(e) => {
                    if !(e.kind() == std::io::ErrorKind::Interrupted
                        && stop.load(Ordering::SeqCst))
                    {
                        pump_res = Err(format!("ارسال به ingest قطع شد: {e}"));
                    }
                    break 'pump;
                }
            }
            sent_this_pass += 1;
            window_bytes += chunk.len() as u64;
            let mut st = stats.lock().unwrap();
            st.forwarded_bytes += chunk.len() as u64;
            st.forwarded_msgs += 1;
        }

        if window_start.elapsed().as_secs_f64() >= WINDOW_SECS {
            let elapsed = window_start.elapsed().as_secs_f64().max(0.1);
            let drain_kbps = window_bytes as f64 * 8.0 / 1000.0 / elapsed;
            *drain.lock().unwrap() = drain_kbps;
            {
                let mut ema = drain_ema.lock().unwrap();
                if *ema <= 0.0 {
                    *ema = drain_kbps;
                } else {
                    *ema = 0.4 * drain_kbps + 0.6 * *ema;
                }
            }
            window_bytes = 0;
            window_start = Instant::now();
        }

        if queue.lock().unwrap().msgs.is_empty() {
            std::thread::sleep(Duration::from_millis(5));
        }
    }

    stop.store(true, Ordering::SeqCst);
    let reader_res = reader_handle
        .join()
        .unwrap_or_else(|_| Err("نخ خواننده panicked".to_string()));
    if pump_res.is_ok() {
        pump_res = reader_res;
    }
    append_log_line(log_path, &session_end_line(unix_now(), &pump_res));
    pump_res
}

// ---------------------------------------------------------------- آزمون‌ها
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn keyframe_detection() {
        assert!(is_keyframe_tag(&[0x17, 0x01, 0x00]));
        assert!(!is_keyframe_tag(&[0x27, 0x01, 0x00]));
        assert!(!is_keyframe_tag(&[]));
        assert!(!is_keyframe_tag(&[0x17, 0x00, 0x00]));
        assert!(is_sequence_header_tag(&[0x17, 0x00, 0x00]));
        assert!(!is_sequence_header_tag(&[0x17, 0x01, 0x00]));
    }

    #[test]
    fn queue_drops_seq_header_with_its_gop() {
        let mut q = OutQueue::new(100);
        q.push(QueuedMsg { msg_type: 9, timestamp: 0, payload: vec![0x17, 0x00, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], is_keyframe: false, enqueued_at: Instant::now() });
        q.push(QueuedMsg { msg_type: 9, timestamp: 33, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: Instant::now() });
        q.push(QueuedMsg { msg_type: 9, timestamp: 66, payload: vec![0x27; 40], is_keyframe: false, enqueued_at: Instant::now() });
        q.push(QueuedMsg { msg_type: 9, timestamp: 99, payload: vec![0x17; 40], is_keyframe: true, enqueued_at: Instant::now() });
        assert!(q.dropped_gops >= 1);
        assert_eq!(q.msgs.front().unwrap().timestamp, 99);
    }

    #[test]
    fn prebuffer_delay_is_two_point_five_seconds() {
        assert_eq!(DELAY_LINE, Duration::from_millis(2500));
        assert_eq!(QUEUE_AGE_CAP, Duration::from_millis(3000));
        assert!(delay_send_wait(Duration::from_millis(1000)).is_some());
        assert!(delay_send_wait(Duration::from_millis(2500)).is_none());
    }
}
