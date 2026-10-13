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

import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6 import QtCore

from servers import DEFAULT_RTMP_PORT

DOWN_SCORE = 1_000_000.0


def ping_host(host, count=2, timeout_s=2):
    """میانگین پینگ (ms) و درصد packet loss؛ در صورت عدم دسترسی (None, 100)."""
    if not host:
        return None, 100.0
    if sys.platform == "win32":
        cmd = ["ping", "-n", str(count), "-w", str(int(timeout_s * 1000)), host]
    else:
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
