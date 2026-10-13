# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Taha Arefi
"""مدل و ذخیره‌سازی لیست سرورهای RTMP برای تب «اسکن سرورها».

مدل سرور: {"id", "name", "region", "host", "port"}
توابع parse/suggest/detect از StreamScanner (کد خود طه) پورت شده‌اند.
موتور پروب (ping_host/tcp_probe/probe_server) در netmon.py است.
"""
import json
import os
import re
import uuid
from urllib.parse import urlparse

DEFAULT_RTMP_PORT = 1935


def _data_dir():
    try:
        base = os.environ.get("APPDATA")
        if base:
            d = os.path.join(base, "LagSlice")
            os.makedirs(d, exist_ok=True)
            return d
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


SERVERS_PATH = os.path.join(_data_dir(), "servers.json")

# نمونه‌ی اولیه؛ طه هاست واقعی MasterStream را خودش وارد می‌کند.
DEFAULT_SERVERS = [
    {"id": "ms1", "name": "MasterStream 1", "region": "ir",
     "host": "", "port": DEFAULT_RTMP_PORT},
]


def server_rtmp_url(s):
    """آدرس RTMP کامل یک سرور: rtmp://host:port/live"""
    host = ((s or {}).get("host") or "").strip()
    if not host:
        return ""
    port = (s or {}).get("port") or DEFAULT_RTMP_PORT
    return f"rtmp://{host}:{port}/live"


def _clean(s):
    if isinstance(s, dict):
        return {
            "id": str(s.get("id") or uuid.uuid4().hex[:8]),
            "name": str(s.get("name") or ""),
            "region": str(s.get("region") or ""),
            "host": str(s.get("host") or "").strip(),
            "port": int(s.get("port") or DEFAULT_RTMP_PORT),
        }
    return None


def load_servers():
    try:
        with open(SERVERS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                out = [_clean(s) for s in data]
                return [s for s in out if s]
    except (OSError, ValueError):
        pass
    return [dict(s) for s in DEFAULT_SERVERS]


def save_servers(servers):
    clean = [_clean(s) for s in (servers or [])]
    clean = [s for s in clean if s]
    with open(SERVERS_PATH, "w", encoding="utf-8") as fh:
        json.dump(clean, fh, ensure_ascii=False, indent=2)
    return clean


def add_server(name, host, port=DEFAULT_RTMP_PORT, region=""):
    servers = load_servers()
    s = _clean({"name": name, "host": host, "port": port, "region": region})
    servers.append(s)
    return save_servers(servers), s


def update_server(server_id, **fields):
    servers = load_servers()
    for s in servers:
        if s["id"] == server_id:
            for k in ("name", "region", "host", "port"):
                if k in fields:
                    s[k] = fields[k]
            _clean(s)
            break
    return save_servers(servers)


def delete_server(server_id):
    servers = [s for s in load_servers() if s["id"] != server_id]
    return save_servers(servers)


def parse_rtmp(text):
    """برگرداندن (host, port) از یک RTMP URL یا host تنها."""
    text = (text or "").strip()
    if not text:
        return "", DEFAULT_RTMP_PORT
    if "://" not in text:
        text = "rtmp://" + text
    try:
        u = urlparse(text)
        return u.hostname or "", u.port or DEFAULT_RTMP_PORT
    except Exception:
        return "", DEFAULT_RTMP_PORT


def suggest_name(host):
    """نام پیشنهادی از روی هاست؛ مثلاً ir1.example.com -> IR1"""
    host = (host or "").strip().lower()
    if not host:
        return ""
    if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", host):
        return "سرور " + host
    label = re.sub(r"[-_]+", " ", host.split(".")[0]).strip()
    return label.upper() if label else host


_REGION_RULES = [
    ("ir", ("ir",), ("iran", "tehran", "shiraz", "tabriz", "mashhad",
                     "isfahan", "karaj", "ahvaz", "qom", "ika", "thr")),
    ("de", ("de",), ("germany", "berlin", "frankfurt", "munich",
                      "nuremberg", "falkenstein", "fra")),
    ("fr", ("fr",), ("france", "paris", "roubaix", "gravelines", "par")),
    ("nl", ("nl",), ("netherlands", "amsterdam", "rotterdam", "ams")),
    ("uk", ("uk",), ("england", "london", "manchester", "lhr", "lon")),
    ("tr", ("tr",), ("turkey", "istanbul", "ankara", "ist")),
    ("ae", ("ae",), ("uae", "dubai", "emirates", "dxb")),
]


def detect_region(host):
    """حدس منطقه از روی هاست (کد کشور، TLD، نام شهر)."""
    h = (host or "").strip().lower()
    if not h:
        return ""
    tokens = [t for t in re.split(r"[.\-_]", h) if t]
    tld = tokens[-1] if tokens else ""
    for region, tlds, words in _REGION_RULES:
        if tld in tlds:
            return region
        for tok in tokens:
            if tok in words:
                return region
            m = re.fullmatch(r"(ir|de|fr|nl|uk|tr|ae)\d*", tok)
            if m and m.group(1) in tlds:
                return region
            for w in words:
                if len(w) >= 3 and re.fullmatch(w + r"\d*", tok):
                    return region
    return ""


def import_rtmp(text, name="", region=""):
    """ساخت آبجکت سرور از یک RTMP URL یا host."""
    host, port = parse_rtmp(text)
    return {
        "id": uuid.uuid4().hex[:8],
        "name": name or suggest_name(host),
        "region": region or detect_region(host),
        "host": host,
        "port": port,
    }
def import_rtmp_bulk(text):
    """درون‌ریزی گروهی: هر خط یک RTMP URL (قالب اختیاری: نام | rtmp://...).
    تعداد افزوده‌شده را برمی‌گرداند؛ تکراری‌ها نادیده گرفته می‌شوند."""
    servers = load_servers()
    seen = {(s.get("host", "").lower(), int(s.get("port") or 0)) for s in servers}
    added = 0
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = ""
        if "|" in line:
            name, line = [p.strip() for p in line.split("|", 1)]
        host, port = parse_rtmp(line)
        if not host or (host.lower(), port) in seen:
            continue
        servers.append({
            "id": uuid.uuid4().hex[:8],
            "name": name or suggest_name(host),
            "region": detect_region(host),
            "host": host,
            "port": port,
        })
        seen.add((host.lower(), port))
        added += 1
    if added:
        save_servers(servers)
    return added
