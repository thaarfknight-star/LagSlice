# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""پایش شبکه: سرعت آپلود/دانلود لحظه‌ای + پینگ و جیتر سرور استریم.

روی ویندوز اجرا می‌شود؛ برای تست منطق روی لینوکس هم کار می‌کند
(پینگ با دستور بومی هر سیستم‌عامل).
"""
import re
import subprocess
import platform
import time
from collections import deque

import psutil
from PyQt6 import QtCore


class NetMonitor(QtCore.QThread):
    """هر ۱ ثانیه آمار شبکه را می‌خواند و سیگنال می‌فرستد."""

    updated = QtCore.pyqtSignal(dict)

    def __init__(self, get_servers, parent=None):
        super().__init__(parent)
        self._get_servers = get_servers
        self._running = True
        self._last = None
        self._last_t = None
        self._ping_hist = deque(maxlen=10)

    def stop(self):
        self._running = False

    def run(self):
        psutil.net_io_counters()  # مقدار اولیه
        while self._running:
            t0 = time.time()
            cur = psutil.net_io_counters()
            if self._last is not None:
                dt = t0 - self._last_t
                up = (cur.bytes_sent - self._last.bytes_sent) * 8 / dt / 1e6
                down = (cur.bytes_recv - self._last.bytes_recv) * 8 / dt / 1e6
            else:
                up, down = 0.0, 0.0
            self._last, self._last_t = cur, t0

            servers = self._get_servers() or []
            ping_ms, jitter_ms = None, None
            if servers:
                ping_ms = self._ping(servers[0])
                if ping_ms is not None:
                    self._ping_hist.append(ping_ms)
                    if len(self._ping_hist) >= 3:
                        vals = list(self._ping_hist)
                        avg = sum(vals) / len(vals)
                        jitter_ms = (sum((v - avg) ** 2 for v in vals) / len(vals)) ** 0.5

            stats = {
                "up_mbps": max(up, 0.0),
                "down_mbps": max(down, 0.0),
                "ping_ms": ping_ms,
                "jitter_ms": jitter_ms,
                "server": servers[0] if servers else "",
            }
            # emit مستقیم امن است (سیگنال‌های Qt بین تردی صف می‌شوند)
            self.updated.emit(stats)
            time.sleep(1.0)

    @staticmethod
    def _ping(host):
        """یک پینگ؛ برمی‌گرداند میلی‌ثانیه یا None."""
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "1", "-w", "1000", host]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", host]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            m = re.search(r"time[=<](\d+(?:\.\d+)?)\s*ms", out.stdout)
            if m:
                return float(m.group(1))
            # خروجی فارسی/بومی ویندوز گاهی «زمان=…» است
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:ms|میلی)", out.stdout)
            if m:
                return float(m.group(1))
        except Exception:
            pass
        return None


def delay_health(up_mbps, bitrate_mbps):
    """وضعیت تخمینی تأخیر ویور بر اساس پایداری آپلود.

    صادقانه: تأخیر واقعی ویور را نمی‌شود از روی PC اندازه گرفت؛
    این تابع «ریسک» بالا رفتن تأخیر از ۲۰ ثانیه را برآورد می‌کند.
    """
    if up_mbps <= 0.05:
        return ("unknown", "نامشخص", "در حال اندازه‌گیری…")
    if up_mbps >= bitrate_mbps * 1.5:
        return ("good", "پایدار", "آپلود کافی است؛ تأخیر ویور در محدوده امن")
    if up_mbps >= bitrate_mbps:
        return ("warn", "لب مرز", "آپلود نزدیک به بیت‌ریت است؛ ریسک افزایش تأخیر")
    return ("bad", "بحرانی", "آپلود کمتر از بیت‌ریت؛ خطر تأخیر بالای ۲۰ ثانیه")
