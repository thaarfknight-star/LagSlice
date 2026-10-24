# LagSlice ⚡ (نسخه‌ی Rust)

بازنویسی LagSlice از پایتون/PyQt6 به **Rust + Tauri 2** — برنامه‌ی ویندوزی مدیریت پهنای‌باند و آپلود بین گیم (بیشتر CS2) و استریم (Meld Studio + سرورهای MasterStream)، با رابط فارسی راست‌به‌چپ و اجرای با دسترسی ادمین.

## تغییرات نسخه‌های اخیر

- **نسخه‌ی 0.9.3 — رله‌ی تطبیقی RTMP + راهنمای داخل‌برنامه‌ای:** Meld با Custom RTMP به رله‌ی لوکال می‌فرستد و رله بیت‌ریت خروجی به Kick را تطبیقی تنظیم می‌کند تا نوسان شبکه به تأخیر تبدیل نشود؛ صفحه‌ی «راهنما» کل برنامه را آموزش می‌دهد. (در انتظار بازبینی DEVagent، هنوز به main پوش نشده.)

## قابلیت محوری: رزرو آپلود برای هر برنامه

- مانیتورینگ زنده‌ی نرخ آپلود/دانلود هر پروسه (EStats ویندوز + IP Helper)
- **رزرو آپلود برای استریم:** سهم Meld Studio کنار گذاشته می‌شود و بقیه‌ی برنامه‌ها خودکار سقف می‌گیرند
- سقف دستی per-app از جدول برنامه‌ها
- پیاده‌سازی سقف‌ها با Windows Policy-based QoS (پالیسی رجیستری در `HKLM\SOFTWARE\Policies\Microsoft\Windows\QoS`) — فقط پالیسی‌های با پیشوند `LagSlice-` ساخته می‌شوند و هنگام خروج برنامه همه پاک می‌شوند
- پینگ سرورهای MasterStream با ICMP

> نکته‌ی فنی صادقانه: shaping لحظه‌ای per-flow درایور کرنل امضاشده می‌خواهد و فاز دو است؛ فاز اول همین مکانیزم پالیسی داخلی ویندوز است.

## ساخت

```bash
cd src-tauri
cargo build --release --target x86_64-pc-windows-gnu   # کراس از لینوکس
# یا روی ویندوز: cargo tauri build
```

## لایسنس

دوگانه، به انتخاب مصرف‌کننده:

Licensed under either of Apache License, Version 2.0 (LICENSE-APACHE) or MIT license (LICENSE-MIT) at your option.

Copyright (c) 2026 Taha Arefi
