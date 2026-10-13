# -*- coding: utf-8 -*-
"""پایش شبکه LagSlice: پینگ سرور استریم و سرعت لحظه‌ای up/down."""

import json
import os
import re
import subprocess

try:
    import psutil
    _PSUTIL_OK = True
except Exception:
    psutil = None
    _PSUTIL_OK = False

from app.procman import get_config_dir


def _settings_path():
    return os.path.join(get_config_dir(), "settings.json")


def load_settings():
    try:
        with open(_settings_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    with open(_settings_path(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def get_ingest_host():
    return (load_settings().get("ingest_host") or "").strip()


def set_ingest_host(host):
    s = load_settings()
    s["ingest_host"] = (host or "").strip()
    save_settings(s)


def ping_host(host, count=3, timeout_s=2):
    """پینگ؛ خروجی: میانگین ms یا None."""
    if not host:
        return None
    try:
        if os.name == "nt":
            cmd = ["ping", "-n", str(count), "-w", str(timeout_s * 1000), host]
        else:
            cmd = ["ping", "-c", str(count), "-W", str(timeout_s), host]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s * count + 5)
        text = out.stdout + out.stderr
        m = re.search(r"Average = (\d+)\s*ms", text)
        if m:
            return int(m.group(1))
        m = re.search(r"avg[=/]\s*([\d.]+)", text)
        if m:
            return int(float(m.group(1)))
        return None
    except Exception:
        return None


class NetSpeed:
    """سرعت لحظه‌ای شبکه با نمونه‌گیری ۱ ثانیه‌ای."""

    def __init__(self):
        self._prev = None

    def sample(self):
        """برمی‌گرداند (up_kbps, down_kbps) یا (None, None)."""
        if not _PSUTIL_OK:
            return None, None
        cur = psutil.net_io_counters()
        if self._prev is None:
            self._prev = cur
            return None, None
        up = (cur.bytes_sent - self._prev.bytes_sent) * 8 / 1000
        down = (cur.bytes_recv - self._prev.bytes_recv) * 8 / 1000
        self._prev = cur
        return max(0.0, up), max(0.0, down)


def quality_fa(ping_ms):
    if ping_ms is None:
        return "نامشخص", "#8b93a3"
    if ping_ms < 60:
        return "عالی", "#22e584"
    if ping_ms < 120:
        return "قابل‌قبول", "#ffb020"
    return "ضعیف", "#ff4d5e"
