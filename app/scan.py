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

# موتور یکپارچه از netmon (تک‌منبع؛ IcmpSendEcho بدون هیچ پروسه‌ای).
# منطق پروب/امتیازدهی عین StreamScanner؛ این ماژول فقط نخ اسکن Qt را دارد.
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6 import QtCore

from netmon import (
    ping_host, tcp_probe, probe_server,
    DOWN_SCORE, DEFAULT_RTMP_PORT,
)

__all__ = ["ping_host", "tcp_probe", "probe_server",
           "DOWN_SCORE", "DEFAULT_RTMP_PORT", "ScanThread"]



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
