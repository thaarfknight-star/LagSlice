# -*- coding: utf-8 -*-
"""ساخت PDF راهنمای فارسی LagSlice با تم لوگو (تیره + نئون).

اجرا:  python docs/build_guide.py
خروجی: docs/LagSlice-guide-fa.pdf
"""
import os

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
OUT = os.path.join(HERE, "LagSlice-guide-fa.pdf")

BG = (0x0B / 255, 0x0F / 255, 0x17 / 255)
CYAN = (0x00 / 255, 0xE5 / 255, 0xFF / 255)
PINK = (0xFF / 255, 0x2B / 255, 0xD6 / 255)
TEXT = (0xE8 / 255, 0xEC / 255, 0xF4 / 255)
DIM = (0x9A / 255, 0xA3 / 255, 0xB5 / 255)


def fa(t):
    return get_display(arabic_reshaper.reshape(t))


def build():
    pdfmetrics.registerFont(TTFont("Vazir", os.path.join(FONT_DIR, "Vazirmatn-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("VazirB", os.path.join(FONT_DIR, "Vazirmatn-Bold.ttf")))

    title_style = ParagraphStyle("title", fontName="VazirB", fontSize=22,
                                 textColor=CYAN, alignment=TA_CENTER, spaceAfter=6)
    sub_style = ParagraphStyle("sub", fontName="Vazir", fontSize=12,
                               textColor=DIM, alignment=TA_CENTER, spaceAfter=14)
    h_style = ParagraphStyle("h", fontName="VazirB", fontSize=15,
                             textColor=CYAN, alignment=TA_RIGHT,
                             spaceBefore=14, spaceAfter=6)
    h2_style = ParagraphStyle("h2", fontName="VazirB", fontSize=12,
                              textColor=PINK, alignment=TA_RIGHT,
                              spaceBefore=8, spaceAfter=4)
    p_style = ParagraphStyle("p", fontName="Vazir", fontSize=11, leading=17,
                             textColor=TEXT, alignment=TA_RIGHT, spaceAfter=6)
    q_style = ParagraphStyle("q", fontName="VazirB", fontSize=11, leading=16,
                             textColor=PINK, alignment=TA_RIGHT, spaceBefore=8, spaceAfter=2)

    doc = SimpleDocTemplate(OUT, pagesize=A4,
                            rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title="راهنمای LagSlice", author="LagSlice")

    def bg(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BG)
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.setFillColor(CYAN)
        canvas.setFont("Vazir", 8)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, fa("LagSlice ⚡ — بهینه‌ساز استریم"))
        canvas.restoreState()

    story = []
    logo = os.path.join(ROOT, "assets", "lagslice-logo.png")
    if os.path.exists(logo):
        story.append(Image(logo, width=42 * mm, height=42 * mm))
        story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(fa("راهنمای LagSlice"), title_style))
    story.append(Paragraph(fa("بهینه‌ساز استریم برای اینترنت ایران — نسخه 0.2.0"), sub_style))

    sections = [
        ("معرفی", [
            "LagSlice برنامه‌ای ویندوزی برای استریمرهای گیمر است. وقتی هم‌زمان بازی می‌کنید (مثل CS2) و استریم می‌فرستید (با MeldStudio)، برنامه‌های دیگر ویندوز پهنای باند و آپلود شما را می‌خورند و تأخیر چیزی که بیننده می‌بیند بالا می‌رود.",
            "LagSlice پهنای باند را زیر نظر می‌گیرد، برنامه‌های اینترنت‌خور را پیدا و با یک کلیک می‌بندد، و کمک می‌کند تأخیر استریم زیر ۲۰ ثانیه بماند.",
        ]),
        ("اجرا با دسترسی ادمین", [
            "برای اینکه LagSlice بتواند برنامه‌های دیگر را ببندد، باید با دسترسی Administrator اجرا شود. روی فایل LagSlice.exe راست‌کلیک کنید و Run as administrator را بزنید.",
            "اگر بدون ادمین اجرا شود، بالای برنامه یک هشدار زرد می‌بینید و بستن بعضی برنامه‌ها کار نمی‌کند.",
        ]),
        ("داشبورد", [
            "چهار کارت بالای برنامه وضعیت زنده را نشان می‌دهند:",
            "• آپلود لحظه‌ای و دانلود لحظه‌ای: سرعت فعلی اینترنت شما.",
            "• پینگ سرور: تأخیر تا سروری که در تنظیمات معرفی کرده‌اید (پیش‌فرض 8.8.8.8).",
            "• وضعیت تأخیر ویور (تخمینی): بر اساس نسبت آپلود شما به بیت‌ریت استریم، ریسک بالا رفتن تأخیر را نشان می‌دهد: پایدار، لب مرز یا بحرانی.",
        ]),
        ("تب برنامه‌ها", [
            "لیست برنامه‌های در حال اجرا را با میزان آپلود و دانلود واقعی هر کدام (بدون نیاز به درایور اضافه) نشان می‌دهد. برنامه‌های اینترنت‌خور با 🔥 مشخص شده‌اند.",
            "با دکمه‌ی «بستن» کنار هر برنامه می‌توانید آن را ببندید. برنامه‌های لیست امن و پروسس‌های سیستمی ویندوز هرگز در این لیست نیستند.",
        ]),
        ("تب لیست امن", [
            "برنامه‌هایی که در «حالت استریم» هرگز نباید بسته شوند (مثل cs2.exe و MeldStudio) این‌جا هستند.",
            "برای افزودن، دکمه‌ی «انتخاب از برنامه‌های در حال اجرا» را بزنید، در کادر جست‌وجو تایپ کنید، تیک برنامه‌ها را بزنید و تأیید کنید. برای حذف، برنامه را انتخاب و «حذف انتخاب‌شده» را بزنید.",
        ]),
        ("تب تنظیمات", [
            "• سرور پینگ: سروری که برنامه برای اندازه‌گیری پینگ و جیتر به آن پینگ می‌زند (پیش‌فرض 8.8.8.8). عدد روی کارت «پینگ سرور» از همین‌جا می‌آید. می‌توانید سرور MasterStream یا هر سرور دیگری بگذارید؛ چند سرور را با ویرگول جدا کنید.",
            "• بیت‌ریت استریم: همان عددی که در MeldStudio برای بیت‌ریت خروجی گذاشته‌اید (مثلاً 8 مگابیت). کارت تأخیر با همین عدد حساب می‌کند.",
            "• زبان: فارسی یا English — کل برنامه و جهت‌چینی بلافاصله عوض می‌شود.",
        ]),
        ("تب لاگ", [
            "همه‌ی اتفاق‌های برنامه با ساعت ثبت می‌شود: بستن برنامه‌ها، تغییر لیست امن، شروع/توقف حالت استریم.",
        ]),
        ("حالت استریم", [
            "با دکمه‌ی بزرگ «شروع حالت استریم»، همه‌ی برنامه‌های اینترنت‌خور که در لیست امن نیستند یک‌جا بسته می‌شوند. موقع استریم همین یک دکمه کافی است.",
        ]),
    ]
    faqs = [
        ("چرا با وجود بستن برنامه‌ها هنوز تأخیر دارم؟",
         "اگر آپلود اینترنت شما از بیت‌ریت استریم کمتر باشد، هیچ برنامه‌ای نمی‌تواند معجزه کند؛ بیت‌ریت MeldStudio را کم کنید یا کیفیت را پایین بیاورید تا کارت تأخیر «پایدار» شود."),
        ("آیا LagSlice بازی یا استریم من را می‌بندد؟",
         "نه. هر چه در لیست امن باشد هرگز بسته نمی‌شود؛ cs2.exe و MeldStudio از اول در لیست امن هستند."),
        ("برنامه با آنتی‌ویروس مشکل دارد؟",
         "LagSlice فقط برنامه‌های کاربر را می‌بندد و به فایل‌های سیستمی دست نمی‌زند. اگر آنتی‌ویروس هشدار داد، آن را به لیست استثناها اضافه کنید."),
        ("تنظیمات من کجا ذخیره می‌شود؟",
         "در پوشه‌ی کاربری ویندوز (%APPDATA%\\LagSlice)؛ با آپدیت نسخه پاک نمی‌شود."),
    ]

    for title, paras in sections:
        story.append(Paragraph(fa(title), h_style))
        for p in paras:
            story.append(Paragraph(fa(p), p_style))

    story.append(Paragraph(fa("سوالات متداول"), h_style))
    for q, a in faqs:
        story.append(Paragraph(fa(q), q_style))
        story.append(Paragraph(fa(a), p_style))

    doc.build(story, onFirstPage=bg, onLaterPages=bg)
    print("wrote", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    build()
