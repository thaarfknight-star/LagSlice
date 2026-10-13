#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ساخت PDF راهنمای فارسی LagSlice با تم تیره/نئون (فونت وزیرمتن).

اجرا:  python build_manual.py
خروجی: docs/LagSlice-guide-fa.pdf
"""
import os

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

BASE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(BASE, "assets", "fonts")
OUT = os.path.join(BASE, "docs", "LagSlice-guide-fa.pdf")

BG = HexColor("#0B0F17")
CARD = HexColor("#101724")
CYAN = HexColor("#00E5FF")
MAGENTA = HexColor("#FF00D4")
TEXT = HexColor("#E8EDF5")
MUTED = HexColor("#9AA4B5")

pdfmetrics.registerFont(TTFont("Vazir", os.path.join(FONTS, "Vazirmatn-Regular.ttf")))
pdfmetrics.registerFont(TTFont("VazirB", os.path.join(FONTS, "Vazirmatn-Bold.ttf")))


def fa(s):
    return get_display(arabic_reshaper.reshape(s))


W, H = A4


def rtl_text(c, x_right, y, s, font="Vazir", size=11, color=TEXT):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawRightString(x_right, y, fa(s))


SECTIONS = [
    ("معرفی LagSlice",
     ["LagSlice بهینه‌ساز استریم ویندوز برای اینترنت ایران است؛ ساخته‌شده برای استریمرهای گیمر (مثل CS2).",
      "پهنای باند و سرعت آپلود را بین بازی و استریم (MeldStudio + سرورهای MasterStream) مدیریت می‌کند تا تأخیر ویور زیر ۲۰ ثانیه بماند.",
      "برنامه‌های الکیِ اینترنت‌خور را با یک کلیک می‌بندد، بدون اینکه به برنامه‌های لیست امن دست بزند."]),
    ("اجرا با دسترسی ادمین",
     ["برای بستن برنامه‌ها و خواندن آمار دقیق شبکه، LagSlice باید با دسترسی ادمین اجرا شود.",
      "روی فایل LagSlice.exe راست‌کلیک کن و «Run as administrator» را بزن.",
      "اگر بدون ادمین اجرا شود، بالای پنجره یک هشدار زرد می‌بینی و بستن بعضی برنامه‌ها کار نمی‌کند."]),
    ("کارت‌های بالای پنجره",
     ["آپلود لحظه‌ای / دانلود لحظه‌ای: سرعت فعلی اینترنت تو (Mbps).",
      "پینگ سرور: تأخیر تا سروری که در تنظیمات گذاشتی (پیش‌فرض 8.8.8.8) + جیتر.",
      "وضعیت تأخیر ویور (تخمینی): ریسک بالا رفتن تأخیر از روی نسبت آپلود به بیت‌ریت. نکته‌ی صادقانه: تأخیر واقعی ویور را نمی‌شود از روی کامپیوتر اندازه گرفت؛ این کارت فقط «ریسک» را نشان می‌دهد."]),
    ("تب «برنامه‌ها»",
     ["جدول برنامه‌های اینترنت‌خور را نشان می‌دهد؛ وقتی آمار شبکه فعال باشد، ستون‌های «آپلود» و «دانلود» واقعی هر برنامه را می‌بینی (مرتب بر اساس آپلود).",
      "با دکمه‌ی «بستن» هر برنامه را می‌توانی ببندی. برنامه‌های لیست امن و پروسس‌های سیستمی هرگز نمایش داده نمی‌شوند."]),
    ("تب «لیست امن»",
     ["این برنامه‌ها در «حالت استریم» هرگز بسته نمی‌شوند (مثل cs2.exe و meldstudio.exe).",
      "با دکمه‌ی «انتخاب از برنامه‌های در حال اجرا» برنامه‌ها را تیک بزن و اضافه کن؛ با «حذف انتخاب‌شده» پاکشان کن."]),
    ("تب «تنظیمات»",
     ["سرور پینگ: سروری که برنامه برای اندازه‌گیری پینگ و جیتر به آن پینگ می‌زند (پیش‌فرض 8.8.8.8). عدد روی کارت «پینگ سرور» از همین‌جا می‌آید. می‌توانی آی‌پی سرور MasterStream یا هر سرور دیگری را بگذاری؛ چند سرور را با ویرگول جدا کن (پینگ به اولی گرفته می‌شود).",
      "بیت‌ریت استریم (Mbps): همان عددی که در MeldStudio برای استریم گذاشتی (مثلاً 8). کارت «وضعیت تأخیر» با همین عدد حساب می‌شود.",
      "زبان: فارسی / English — جهت کل برنامه هم عوض می‌شود."]),
    ("حالت استریم",
     ["با دکمه‌ی بزرگ «شروع حالت استریم»، برنامه‌های اینترنت‌خورِ غیر لیست امن را می‌بندد تا همه‌ی پهنای باند برای بازی و استریم بماند.",
      "قبل از بستن، اسم هر برنامه در تب «لاگ» نوشته می‌شود. با «توقف حالت استریم» به حالت عادی برمی‌گردی."]),
    ("سوالات متداول",
     ["چرا بعضی برنامه‌ها بسته نمی‌شوند؟ چون یا در لیست امن‌اند یا پروسس سیستمی‌اند، یا برنامه بدون دسترسی ادمین اجرا شده.",
      "عدد پینگ از کجاست؟ از سروری که در تنظیمات گذاشتی؛ اگر سرور MasterStream را بگذاری، دقیق‌ترین عدد برای استریم توست.",
      "برنامه اینترنت را کند می‌کند؟ نه؛ خودش فقط هر چند ثانیه آمار می‌خواند و مصرفش ناچیز است."]),
]


def build():
    c = canvas.Canvas(OUT, pagesize=A4)
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(CYAN)
    c.rect(0, H - 14 * mm, W, 3 * mm, fill=1, stroke=0)
    c.setFillColor(MAGENTA)
    c.rect(0, H - 17 * mm, W, 1.2 * mm, fill=1, stroke=0)

    rtl_text(c, W - 20 * mm, H - 45 * mm, "LagSlice ⚡", "VazirB", 34, CYAN)
    rtl_text(c, W - 20 * mm, H - 60 * mm, "راهنمای کاربر", "VazirB", 22, TEXT)
    rtl_text(c, W - 20 * mm, H - 72 * mm, "بهینه‌ساز استریم — اینترنت ایران", "Vazir", 13, MUTED)
    rtl_text(c, W - 20 * mm, H - 86 * mm, "نسخه‌ی 0.2.0", "Vazir", 11, MUTED)
    logo_p = os.path.join(BASE, "assets", "lagslice-logo.png")
    if os.path.exists(logo_p):
        c.drawImage(logo_p, W / 2 - 25 * mm, H - 135 * mm, width=50 * mm,
                    height=50 * mm, preserveAspectRatio=True, mask="auto")
        y = H - 145 * mm
    else:
        y = H - 110 * mm

    def need_space(lines_needed):
        nonlocal y
        if y - lines_needed * 7 * mm < 25 * mm:
            c.showPage()
            c.setFillColor(BG)
            c.rect(0, 0, W, H, fill=1, stroke=0)
            y = H - 25 * mm

    for title, paras in SECTIONS:
        need_space(len(paras) + 2)
        c.setFillColor(CARD)
        c.roundRect(15 * mm, y - 4 * mm, W - 30 * mm, 11 * mm, 2 * mm, fill=1, stroke=0)
        rtl_text(c, W - 22 * mm, y, title, "VazirB", 14, CYAN)
        y -= 13 * mm
        for p in paras:
            words, lines, cur = p.split(), [], ""
            for wd in words:
                if len(cur) + len(wd) + 1 > 72:
                    lines.append(cur)
                    cur = wd
                else:
                    cur = (cur + " " + wd).strip()
            if cur:
                lines.append(cur)
            need_space(len(lines))
            for ln in lines:
                rtl_text(c, W - 22 * mm, y, "• " + ln, "Vazir", 10.5, TEXT)
                y -= 6.2 * mm
            y -= 2.5 * mm
        y -= 4 * mm

    need_space(3)
    rtl_text(c, W - 20 * mm, 22 * mm, "© 2026 Taha Arefi — AGPL-3.0-only", "Vazir", 9, MUTED)
    c.save()
    print("PDF built:", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    build()
