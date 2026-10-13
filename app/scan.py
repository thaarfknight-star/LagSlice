# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
#
# موتور اسکن سرورهای استریم LagSlice.
# منطق پروب (پینگ + TCP + امتیازدهی) با اقتباس از StreamScanner
# (ریپوی thaarfknight-star/StreamScanner — همان مالک) بازنویسی شده است.

"""تست موازی سرورها: پینگ ICMP + اتصال TCP به پورت RTMP + امتیازدهی.

امتیاز کمتر = بهتر. فرمول (اثبات‌شده در StreamScanner):
    score = tcp_ms + ping_ms * 0.3 + loss * 20
سرور قطع (TCP ناموفق): score = 1_000_000
"""

import ctypes
import ipaddress
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6 import QtCore

from servers import DEFAULT_RTMP_PORT

DOWN_SCORE = 1_000_000.0


def _icmp_echo_once(iphlpapi, kernel32, handle, dest, timeout_ms):
    """یک اکوی ICMP؛ برمی‌گرداند RTT به میلی‌ثانیه یا None."""
    req = b"LagSlicePing" * 2  # 24 بایت داده‌ی درخواست
    reply = ctypes.create_string_buffer(1024)
    n = iphlpapi.IcmpSendEcho(handle, dest, req, len(req), None,
                              reply, len(reply), timeout_ms)
    if not n:
        return None
    # struct ICMP_ECHO_REPLY: فیلد RoundTripTime در آفست ۸ است
    return float(int.from_bytes(bytes(reply[8:12]), "little"))


def _ping_host_icmp(host, count, timeout_s):
    """پینگ بدون اسپاون هیچ پروسه‌ای با IcmpSendEcho ویندوز.

    برمی‌گرداند (avg_ms, loss_pct)؛ در صورت عدم دسترسی (None, 100).
    به دسترسی ادمین نیاز ندارد.
    """
    try:
        dest = int(ipaddress.IPv4Address(socket.gethostbyname(host)))
    except Exception:
        return None, 100.0
    iphlpapi = ctypes.WinDLL("iphlpapi")
    kernel32 = ctypes.WinDLL("kernel32")
    iphlpapi.IcmpCreateFile.restype = ctypes.c_void_p
    iphlpapi.IcmpSendEcho.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ushort,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
    ]
    iphlpapi.IcmpSendEcho.restype = ctypes.c_ulong
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = iphlpapi.IcmpCreateFile()
    if not handle:
        return None, 100.0
    timeout_ms = max(1, int(timeout_s * 1000))
    rtts = []
    try:
        for _ in range(count):
            rtt = _icmp_echo_once(iphlpapi, kernel32, handle, dest, timeout_ms)
            if rtt is not None:
                rtts.append(rtt)
    finally:
        kernel32.CloseHandle(handle)
    if not rtts:
        return None, 100.0
    loss = (count - len(rtts)) / count * 100.0
    return sum(rtts) / len(rtts), loss


def ping_host(host, count=2, timeout_s=2):
    """میانگین پینگ (ms) و درصد packet loss؛ در صورت عدم دسترسی (None, 100).

    روی ویندوز: IcmpSendEcho بدون هیچ پروسه‌ای (دستور طه).
    روی بقیه: ping بومی سیستم (مثل StreamScanner).
    """
    if not host:
        return None, 100.0
    count = max(1, int(count or 1))
    if sys.platform == "win32":
        try:
            return _ping_host_icmp(host, count, timeout_s)
        except Exception:
            return None, 100.0
    # غیر ویندوز: ping بومی سیستم (مثل StreamScanner)
    cmd = ["ping", "-c", str(count), "-W", str(max(1, int(timeout_s))), host]
    try:
        kw = {}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kw = {"startupinfo": si, "creationflags": getattr(
                subprocess, "CREATE_NO_WINDOW", 0)}
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=count * timeout_s + 5, **kw)
        out = proc.stdout or ""
        times = [float(x) for x in re.findall(r"time[=<](\d+(?:\.\d+)?)\s*ms", out)]
        loss_m = re.search(r"(\d+)%\s*(?:packet\s*)?loss", out, re.IGNORECASE)
        if loss_m is None:
            loss_m = re.search(r"Lost = \d+ \((\d+)% loss\)", out)
        loss = float(loss_m.group(1)) if loss_m else (0.0 if times else 100.0)
        avg = sum(times) / len(times) if times else None
        return avg, loss
    except Exception:
        return None, 100.0


def tcp_probe(host, port, timeout=4.0):
    """زمان برقراری اتصال TCP به پورت RTMP (ms) یا None."""
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
    """تست کامل یک سرور؛ دیکشنری نتیجه با کلیدهای ping_ms/loss/tcp_ms/ok/score."""
    s = dict(server or {})
    host, port = s.get("host", ""), s.get("port") or DEFAULT_RTMP_PORT
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
        "host": host, "port": port, "note": s.get("note", ""),
        "ping_ms": ping_ms, "loss": loss, "tcp_ms": tcp_ms,
        "ok": ok, "score": score,
    }


class ScanThread(QtCore.QThread):
    """اسکن موازی سرورها در نخ جدا.

    سیگنال‌ها:
        progress(int, int) — (انجام‌شده، کل)
        result_ready(dict) — نتیجه‌ی هر سرور
        finished_all(list) — همه‌ی نتایج
    """

    progress = QtCore.pyqtSignal(int, int)
    result_ready = QtCore.pyqtSignal(dict)
    finished_all = QtCore.pyqtSignal(list)

    def __init__(self, servers, max_workers=16, parent=None):
        super().__init__(parent)
        self._servers = list(servers or [])
        self._max_workers = max(1, int(max_workers or 16))
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        servers = self._servers
        total = len(servers)
        results = [None] * total
        done = 0
        if not servers:
            self.finished_all.emit([])
            return
        with ThreadPoolExecutor(
                max_workers=min(self._max_workers, total)) as ex:
            futs = {ex.submit(probe_server, s): i
                    for i, s in enumerate(servers)}
            for fut in as_completed(futs):
                if self._stop:
                    break
                i = futs[fut]
                try:
                    r = fut.result()
                except Exception:
                    s = servers[i]
                    r = {"id": s.get("id"), "name": s.get("name"),
                         "region": s.get("region"), "host": s.get("host"),
                         "port": s.get("port"), "note": s.get("note", ""),
                         "ping_ms": None, "loss": 100.0, "tcp_ms": None,
                         "ok": False, "score": DOWN_SCORE}
                results[i] = r
                done += 1
                self.result_ready.emit(r)
                self.progress.emit(done, total)
        self.finished_all.emit([r for r in results if r is not None])
