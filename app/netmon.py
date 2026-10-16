# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
# -*- coding: utf-8 -*-
"""پایش شبکه: سرعت آپلود/دانلود لحظه‌ای + پینگ و جیتر سرور استریم.

روی ویندوز اجرا می‌شود؛ برای تست منطق روی لینوکس هم کار می‌کند
(پینگ با دستور بومی هر سیستم‌عامل).
"""
import sys
import os
import time
import re
import socket
import subprocess
from collections import deque

import psutil
from PyQt6 import QtCore

from estats import ProcNetMonitor


# ---- ضربان عیب‌یابی کرش ----
# با LAGSLICE_DIAG=1 نخ مانیتور قبل/بعد هر عملیات native یک خط در
# LagSlice-diag.log (کنار exe) می‌نویسد؛ آخرین خط موقع کرش نشان می‌دهد
# دقیقاً کدام فراخوانی مرده است.
_DIAG = os.environ.get("LAGSLICE_DIAG", "") == "1"
_diag_fh = None


def _diag_path():
    try:
        d = os.path.dirname(sys.executable)
        if d:
            return os.path.join(d, "LagSlice-diag.log")
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "LagSlice-diag.log")


def _diag(msg):
    if not _DIAG:
        return
    global _diag_fh
    try:
        if _diag_fh is None:
            _diag_fh = open(_diag_path(), "a", encoding="utf-8", buffering=1)
        _diag_fh.write(msg + "\n")
    except Exception:
        pass


# ============ موتور پروب سرور (پورت StreamScanner) ============
# توابع خالص، بدون وابستگی به Qt.
# قرارداد ورودی probe_server: دیکشنری {id, name, region, host, port}

DEFAULT_RTMP_PORT = 1935
DOWN_SCORE = 1_000_000.0


def ping_host(host, count=4, timeout_ms=1000):
    """(avg_ms|None, loss_pct) — پینگ با ping.exe مخفی (بدون پنجره‌ی cmd).

    منطق StreamScanner: میانگین زمان‌های موفق، loss درصدی.
    روی ویندوز پنجره‌ی cmd مخفی می‌شود (STARTUPINFO + CREATE_NO_WINDOW).
    """
    if not host:
        return None, 100.0
    count = max(1, int(count or 1))
    timeout_ms = max(1, int(timeout_ms or 1000))
    if sys.platform == "win32":
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs = dict(startupinfo=si,
                      creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        cmd = ["ping", "-c", str(count), "-W",
               str(max(1, timeout_ms // 1000)), host]
        kwargs = {}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=count * (timeout_ms / 1000.0) + 10,
                              **kwargs)
        out = proc.stdout or ""
        times = [float(x)
                 for x in re.findall(r"time[=<](\d+(?:\.\d+)?)\s*ms", out)]
        if not times:
            # خروجی فارسی/بومی ویندوز گاهی «زمان=…» است
            times = [float(x) for x in
                     re.findall(r"(\d+(?:\.\d+)?)\s*(?:ms|میلی)", out)]
        loss_m = re.search(r"(\d+)%\s*(?:packet\s*)?loss", out, re.IGNORECASE)
        if loss_m is None:
            loss_m = re.search(r"Lost = \d+ \((\d+)% loss\)", out)
        loss = float(loss_m.group(1)) if loss_m else (0.0 if times else 100.0)
        avg = sum(times) / len(times) if times else None
        return avg, loss
    except Exception:
        return None, 100.0


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
        _diag("run: start")
        psutil.net_io_counters()  # مقدار اولیه
        _diag("run: net_io baseline ok")
        self._procmon.sample()  # baseline برای EStats
        _diag("run: estats baseline ok")
        while self._running:
            t0 = time.time()
            self._tick += 1
            _diag(f"tick {self._tick}: net_io begin")
            cur = psutil.net_io_counters()
            _diag(f"tick {self._tick}: net_io ok")
            if self._last is not None:
                dt = t0 - self._last_t
                up = (cur.bytes_sent - self._last.bytes_sent) * 8 / dt / 1e6
                down = (cur.bytes_recv - self._last.bytes_recv) * 8 / dt / 1e6
            else:
                up, down = 0.0, 0.0
            self._last, self._last_t = cur, t0

            # آمار per-process هر ۲ تیک (EStats کمی سنگین است)
            per_proc = {}
            if self._tick % 2 == 0:
                _diag(f"tick {self._tick}: estats begin")
                try:
                    per_proc = self._procmon.sample()
                except Exception:
                    per_proc = {}
                _diag(f"tick {self._tick}: estats ok")

            servers = self._get_servers() or []
            ping_ms, jitter_ms = None, None
            if servers:
                _diag(f"tick {self._tick}: ping begin")
                ping_ms = self._ping(servers[0])
                _diag(f"tick {self._tick}: ping ok")
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
            _diag(f"tick {self._tick}: emit begin")
            self.updated.emit(stats)
            _diag(f"tick {self._tick}: emit ok")
            time.sleep(1.0)
        _diag("run: end")

    @staticmethod
    def _ping(host):
        """یک پینگ؛ برمی‌گرداند میلی‌ثانیه یا None. از موتور مشترک ping_host."""
        try:
            avg, _loss = ping_host(host, count=1, timeout_ms=1000)
            return avg
        except Exception:
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
