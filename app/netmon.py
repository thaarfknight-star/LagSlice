# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
# -*- coding: utf-8 -*-
"""پایش شبکه: سرعت آپلود/دانلود لحظه‌ای + پینگ و جیتر سرور استریم.

روی ویندوز اجرا می‌شود؛ برای تست منطق روی لینوکس هم کار می‌کند
(پینگ با دستور بومی هر سیستم‌عامل).
"""
import re
import subprocess
import platform
import sys
import time
import ctypes
import socket
import ipaddress
from collections import deque

import psutil
from PyQt6 import QtCore

from estats import ProcNetMonitor


def _ping_icmp(host, timeout_ms=1000):
    """پینگ بدون اسپاون هیچ پروسه‌ای، با IcmpSendEcho ویندوز (ctypes).

    فقط روی win32 صدا زده می‌شود. در صورت هر خطا None برمی‌گرداند
    تا فراخواننده به روش قدیمی (subprocess مخفی) برگردد.
    به ادمین نیاز ندارد.
    """
    iphlpapi, kernel32, handle = _icmp_handles()
    if not handle:
        return None
    try:
        dest = int(ipaddress.IPv4Address(socket.gethostbyname(host)))
        req = b"LagSlicePing" * 2  # 24 بایت داده‌ی درخواست
        reply = ctypes.create_string_buffer(1024)
        n = iphlpapi.IcmpSendEcho(handle, dest, req, len(req), None,
                                  reply, len(reply), timeout_ms)
        if not n:
            return None
        # struct ICMP_ECHO_REPLY: فیلد RoundTripTime در آفست ۸ است
        rtt = int.from_bytes(bytes(reply[8:12]), "little")
        return float(rtt)
    finally:
        kernel32.CloseHandle(handle)


# ============ موتور پروب سرور (پورت StreamScanner) ============
# توابع خالص، بدون وابستگی به Qt.
# قرارداد ورودی probe_server: دیکشنری {id, name, region, host, port}

DEFAULT_RTMP_PORT = 1935
DOWN_SCORE = 1_000_000.0


def _icmp_handles():
    """هندل ICMP + تنظیم argtypes؛ فقط روی win32 صدا زده می‌شود."""
    iphlpapi = ctypes.WinDLL("iphlpapi")
    kernel32 = ctypes.WinDLL("kernel32")
    iphlpapi.IcmpCreateFile.restype = ctypes.c_void_p
    iphlpapi.IcmpSendEcho.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ushort,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
    ]
    iphlpapi.IcmpSendEcho.restype = ctypes.c_ulong
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    return iphlpapi, kernel32, iphlpapi.IcmpCreateFile()


def ping_host(host, count=4, timeout_ms=1000):
    """(avg_ms|None, loss_pct) — چند اکوی IcmpSendEcho، بدون هیچ پروسه‌ای.

    منطق StreamScanner: میانگین اکوهای موفق، loss درصدی.
    به ادمین نیاز ندارد. روی غیر ویندوز (None, 100).
    """
    if not host:
        return None, 100.0
    count = max(1, int(count or 1))
    timeout_ms = max(1, int(timeout_ms or 1000))
    if sys.platform != "win32":
        return None, 100.0
    try:
        dest = int(ipaddress.IPv4Address(socket.gethostbyname(host)))
    except Exception:
        return None, 100.0
    try:
        iphlpapi, kernel32, handle = _icmp_handles()
    except Exception:
        return None, 100.0
    if not handle:
        return None, 100.0
    rtts = []
    try:
        req = b"LagSlicePing" * 2
        reply = ctypes.create_string_buffer(1024)
        for _ in range(count):
            n = iphlpapi.IcmpSendEcho(handle, dest, req, len(req), None,
                                      reply, len(reply), timeout_ms)
            if n:
                rtts.append(float(int.from_bytes(bytes(reply[8:12]), "little")))
    except Exception:
        pass
    finally:
        try:
            kernel32.CloseHandle(handle)
        except Exception:
            pass
    if not rtts:
        return None, 100.0
    return sum(rtts) / len(rtts), (count - len(rtts)) / count * 100.0


def tcp_probe(host, port, timeout=3.0):
    """tcp_ms|None — زمان اتصال TCP به پورت؛ عین StreamScanner (سوکت، بدون پروسه)."""
    if not host:
        return None
    try:
        t0 = time.perf_counter()
        with socket.create_connection((host, int(port)), timeout=timeout):
            pass
        return (time.perf_counter() - t0) * 1000.0
    except Exception:
        return None


def probe_server(server):
    """پروب کامل یک سرور؛ دیکشنری با کلیدهای
    id/name/region/host/port/ping_ms/loss/tcp_ms/ok/score.

    امتیازدهی عین StreamScanner: موفق = tcp + ping*0.3 + loss*20،
    ناموفق (TCP قطع) = 1_000_000.
    """
    s = dict(server or {})
    host = s.get("host", "")
    port = s.get("port") or DEFAULT_RTMP_PORT
    tcp_ms = tcp_probe(host, port)
    ok = tcp_ms is not None
    ping_ms, loss = ping_host(host)
    if not ok:
        score = DOWN_SCORE
    else:
        score = tcp_ms
        if ping_ms is not None:
            score += ping_ms * 0.3 + loss * 20.0
    return {
        "id": s.get("id"), "name": s.get("name"), "region": s.get("region"),
        "host": host, "port": port,
        "ping_ms": ping_ms, "loss": loss, "tcp_ms": tcp_ms,
        "ok": ok, "score": score,
    }


def server_rtmp_url(s):
    """rtmp://host:port/live — پورت پیش‌فرض 1935."""
    s = dict(s or {})
    return f"rtmp://{s.get('host', '')}:{s.get('port') or DEFAULT_RTMP_PORT}/live"


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
        self._procmon = ProcNetMonitor()
        self._tick = 0

    def stop(self):
        self._running = False

    def run(self):
        psutil.net_io_counters()  # مقدار اولیه
        self._procmon.sample()  # baseline برای EStats
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

            # آمار per-process هر ۲ تیک (EStats کمی سنگین است)
            self._tick += 1
            per_proc = {}
            if self._tick % 2 == 0:
                try:
                    per_proc = self._procmon.sample()
                except Exception:
                    per_proc = {}

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
                "per_proc": per_proc,
            }
            # emit مستقیم امن است (سیگنال‌های Qt بین تردی صف می‌شوند)
            self.updated.emit(stats)
            time.sleep(1.0)

    @staticmethod
    def _ping(host):
        """یک پینگ؛ برمی‌گرداند میلی‌ثانیه یا None."""
        # ویندوز: اول بدون هیچ پروسه‌ای (IcmpSendEcho)؛ اگر نشد، subprocess مخفی
        if sys.platform == "win32":
            try:
                r = _ping_icmp(host)
                if r is not None:
                    return r
            except Exception:
                pass
        try:
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "1", "-w", "1000", host]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", host]
            # ویندوز: مخفی‌سازی پنجره‌ی cmd (وگرنه هر ثانیه یک پنجره باز/بسته می‌شود)
            kwargs = {}
            if sys.platform == "win32":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs = dict(startupinfo=si,
                              creationflags=subprocess.CREATE_NO_WINDOW)
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=5, **kwargs)
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
    برمی‌گرداند کلید وضعیت؛ ترجمه با lang.tr انجام می‌شود.
    """
    if up_mbps <= 0.05:
        return "unknown"
    if up_mbps >= bitrate_mbps * 1.5:
        return "good"
    if up_mbps >= bitrate_mbps:
        return "warn"
    return "bad"
