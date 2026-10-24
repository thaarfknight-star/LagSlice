//! پینگ ICMP به آی‌پی IPv4 — تنها چیزی که از مانیتور قدیمی مانده است:
//! اسکنر سرورها و دستور ping_host از همین تابع استفاده می‌کنند.
//! (صفحه‌ی برنامه‌ها و موتور محدودیت در ۰٫۹٫۱۲ کامل حذف شدند.)

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
