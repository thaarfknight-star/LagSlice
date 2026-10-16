# -*- coding: utf-8 -*-
"""LagSlice — per-process TCP up/down on Windows via iphlpapi EStats.

Copyright (C) 2026 Taha Arefi
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Uses GetExtendedTcpTable(TCP_TABLE_OWNER_PID_ALL) +
GetPerTcpConnectionEStats(TcpConnectionEstatsData) — no driver needed.
All Windows-only code is guarded so the module imports anywhere.
"""

import ctypes
import os
import socket
import sys
import time

WIN32 = sys.platform == "win32"

MIB_TCP_STATE_ESTAB = 5

# کلید عیب‌یابی کرش: با LAGSLICE_NO_ESTATS=1 هیچ فراخوانی EStats انجام نمی‌شود.
_NO_ESTATS = os.environ.get("LAGSLICE_NO_ESTATS", "") == "1"

_iphlpapi = None
_Row = None
_TcpRow = None
_RW = None
_ROD = None
_GetExtendedTcpTable = None
_GetPerTcpConnectionEStats = None

if WIN32:
    try:
        from ctypes import wintypes

        _iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)

        class _MIB_TCPROW_OWNER_PID(ctypes.Structure):
            _fields_ = [
                ("dwState", wintypes.DWORD),
                ("dwLocalAddr", wintypes.DWORD),
                ("dwLocalPort", wintypes.DWORD),
                ("dwRemoteAddr", wintypes.DWORD),
                ("dwRemotePort", wintypes.DWORD),
                ("dwOwningPid", wintypes.DWORD),
            ]

        class _MIB_TCPROW(ctypes.Structure):
            """ساختار ۲۰ بایتی دقیقی که GetPerTcpConnectionEStats می‌خواهد
            (PMIB_TCPROW) — به‌جای پاس دادن اشاره‌گر به سطر جدول مالک،
            یک کپی تمیز می‌سازیم تا هیچ شکی درباره‌ی چیدمان حافظه نماند."""

            _fields_ = [
                ("dwState", wintypes.DWORD),
                ("dwLocalAddr", wintypes.DWORD),
                ("dwLocalPort", wintypes.DWORD),
                ("dwRemoteAddr", wintypes.DWORD),
                ("dwRemotePort", wintypes.DWORD),
            ]

        class _TCP_ESTATS_DATA_RW_v0(ctypes.Structure):
            _fields_ = [("EnableCollection", wintypes.BOOLEAN)]

        class _TCP_ESTATS_DATA_ROD_v0(ctypes.Structure):
            _fields_ = [
                ("DataBytesOut", ctypes.c_uint64),
                ("DataSegsOut", ctypes.c_uint64),
                ("DataBytesIn", ctypes.c_uint64),
                ("DataSegsIn", ctypes.c_uint64),
            ]

        _Row, _RW, _ROD = _MIB_TCPROW_OWNER_PID, _TCP_ESTATS_DATA_RW_v0, _TCP_ESTATS_DATA_ROD_v0
        _TcpRow = _MIB_TCPROW

        _GetExtendedTcpTable = _iphlpapi.GetExtendedTcpTable
        _GetExtendedTcpTable.argtypes = [
            wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD),
            wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
        ]
        _GetExtendedTcpTable.restype = wintypes.DWORD

        _GetPerTcpConnectionEStats = _iphlpapi.GetPerTcpConnectionEStats
        _GetPerTcpConnectionEStats.argtypes = [
            ctypes.c_void_p, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
        ]
        _GetPerTcpConnectionEStats.restype = wintypes.ULONG
    except Exception:
        _iphlpapi = None


def _decode_port(dword_port):
    try:
        return socket.ntohs(int(dword_port) & 0xFFFF)
    except Exception:
        return 0


def _enum_rows():
    """Yields (state, rport, lport, raddr, pid, row_fields).

    row_fields پنج‌تایی اعداد سطر TCP است که برای GetPerTcpConnectionEStats
    در یک ساختار _MIB_TCPROW تمیز کپی می‌شود.
    """
    from ctypes import wintypes

    buf = None
    for _try in range(4):
        size = wintypes.DWORD(0)
        if _GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 5, 0) != 122:
            return
        buf = ctypes.create_string_buffer(size.value)
        if _GetExtendedTcpTable(buf, ctypes.byref(size), False, 2, 5, 0) == 0:
            break
        buf = None  # جدول بین دو فراخوانی بزرگ شد؛ دوباره سایز بگیر
    if buf is None:
        return
    n = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD)).contents.value
    base = ctypes.addressof(buf) + ctypes.sizeof(wintypes.DWORD)
    rsize = ctypes.sizeof(_Row)
    for i in range(n):
        addr = base + i * rsize
        try:
            row = _Row.from_address(addr)
            yield (
                int(row.dwState),
                _decode_port(row.dwRemotePort),
                _decode_port(row.dwLocalPort),
                int(row.dwRemoteAddr),
                int(row.dwOwningPid),
                (int(row.dwState), int(row.dwLocalAddr),
                 int(row.dwLocalPort), int(row.dwRemoteAddr),
                 int(row.dwRemotePort)),
            )
        except Exception:
            continue


def _make_tcp_row(fields):
    """کپی تمیز ۲۰ بایتی از سطر برای پاس دادن به GetPerTcpConnectionEStats."""
    r = _TcpRow()
    (r.dwState, r.dwLocalAddr, r.dwLocalPort,
     r.dwRemoteAddr, r.dwRemotePort) = fields
    return r


def _enable(fields):
    row = _make_tcp_row(fields)
    rw = _RW()
    rw.EnableCollection = True
    try:
        return _GetPerTcpConnectionEStats(
            ctypes.byref(row), 0,
            ctypes.byref(rw), 0, ctypes.sizeof(rw),
            None, 0, 0, None, 0, 0,
        ) == 0
    except Exception:
        return False


def _read(fields):
    row = _make_tcp_row(fields)
    rod = _ROD()
    try:
        rc = _GetPerTcpConnectionEStats(
            ctypes.byref(row), 0,
            None, 0, 0, None, 0, 0,
            ctypes.byref(rod), 0, ctypes.sizeof(rod),
        )
        if rc != 0:
            return None
        return int(rod.DataBytesOut), int(rod.DataBytesIn)
    except Exception:
        return None


class ProcNetMonitor:
    """Samples per-PID TCP rates. sample() -> {pid: {up_bps, down_bps, conns}}."""

    RTMP_PORTS = {1935, 443, 80}

    def __init__(self):
        self._enabled = set()
        self._prev = {}
        self._last_t = None
        self.available = bool(_iphlpapi) and not _NO_ESTATS

    def sample(self):
        if not self.available:
            return {}
        now = time.monotonic()
        dt = (now - self._last_t) if self._last_t else 2.0
        self._last_t = now
        if dt <= 0:
            dt = 2.0
        try:
            return self._sample(dt)
        except Exception:
            return {}

    def _sample(self, dt):
        cur = {}
        per_pid = {}
        seen = set()
        for state, rport, lport, raddr, pid, fields in _enum_rows():
            if state != MIB_TCP_STATE_ESTAB:
                continue
            key = (raddr, rport, lport, pid)
            seen.add(key)
            if key not in self._enabled:
                if _enable(fields):
                    self._enabled.add(key)
                else:
                    continue
            val = _read(fields)
            if val is None:
                continue
            cur[key] = val
            prev = self._prev.get(key)
            if prev is not None:
                d_out = max(0, val[0] - prev[0])
                d_in = max(0, val[1] - prev[1])
                e = per_pid.get(pid)
                if e is None:
                    e = per_pid[pid] = {
                        "up_bps": 0.0, "down_bps": 0.0,
                        "conns": 0, "rtmp_conns": 0,
                    }
                e["up_bps"] += d_out * 8.0 / dt
                e["down_bps"] += d_in * 8.0 / dt
                e["conns"] += 1
                if rport in self.RTMP_PORTS:
                    e["rtmp_conns"] += 1
        self._prev = cur
        self._enabled.intersection_update(seen)
        return per_pid
