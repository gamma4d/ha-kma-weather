"""KMA (기상청) weather — pure logic core.

stdlib-only. NO Home Assistant / aiohttp imports here so the logic is fully
unit-testable offline (the HA glue lives in coordinator.py / weather.py /
sensor.py; the network wrapper lives at the bottom of this file behind an
optional aiohttp import).

Data source = 기상청 공공데이터포털 (data.go.kr) 단기예보/초단기/중기 조회서비스.
See README.md and docs/16 for the decision rationale.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


class KmaError(Exception):
    """A KMA API response that is malformed or carries a non-success resultCode."""

# ---------------------------------------------------------------------------
# lat/lon -> KMA 5km grid  (Lambert Conformal Conic; KMA's dfs_xy_conv)
# Constants are fixed by KMA (활용가이드 별첨): RE 6371.00877 km, GRID 5 km,
# standard parallels 30/60, origin (126E, 38N) at grid (43, 136).
# ---------------------------------------------------------------------------
_RE = 6371.00877      # earth radius (km)
_GRID = 5.0           # grid spacing (km)
_SLAT1 = 30.0         # standard latitude 1 (deg)
_SLAT2 = 60.0         # standard latitude 2 (deg)
_OLON = 126.0         # origin longitude (deg)
_OLAT = 38.0          # origin latitude (deg)
_XO = 43             # origin grid x
_YO = 136            # origin grid y


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """Convert WGS84 lat/lon (deg) to KMA integer grid (nx, ny)."""
    degrad = math.pi / 180.0
    re = _RE / _GRID
    slat1 = _SLAT1 * degrad
    slat2 = _SLAT2 * degrad
    olon = _OLON * degrad
    olat = _OLAT * degrad

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * degrad * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * degrad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    nx = int(ra * math.sin(theta) + _XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + _YO + 0.5)
    return nx, ny


# ---------------------------------------------------------------------------
# KMA categorized value strings -> float (mm / cm).
# Encodings: "강수없음"/"적설없음", "1.0mm 미만", "X.Xmm", "30.0~50.0mm",
# "50.0mm 이상", or a bare number. Best-effort single float; callers keep the
# raw string for display honesty.
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_amount(val) -> float:
    """Parse a KMA precipitation/snow value to a float (lower bound of ranges)."""
    if val is None:
        return 0.0
    s = str(val).strip()
    if not s or "없음" in s:
        return 0.0
    m = _NUM_RE.search(s)
    return float(m.group()) if m else 0.0


# ---------------------------------------------------------------------------
# Issuance schedules -> (base_date 'YYYYMMDD', base_time 'HHMM').
# `now` is a naive datetime interpreted as KST wall-clock. A safety margin is
# applied so we never request a base_time the API hasn't published yet.
# ---------------------------------------------------------------------------
_VILAGE_SLOTS = (2, 5, 8, 11, 14, 17, 20, 23)  # 단기예보 1일 8회
_VILAGE_MARGIN = timedelta(minutes=15)         # available ~+10min; +15 for safety


def _fmt(dt: datetime) -> tuple[str, str]:
    return dt.strftime("%Y%m%d"), dt.strftime("%H%M")


def vilage_base(now: datetime) -> tuple[str, str]:
    """단기예보 getVilageFcst base time — latest of the 8 daily slots available."""
    chosen = None
    for h in _VILAGE_SLOTS:
        slot = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if slot + _VILAGE_MARGIN <= now:
            chosen = slot
    if chosen is None:
        chosen = (now - timedelta(days=1)).replace(
            hour=23, minute=0, second=0, microsecond=0
        )
    return _fmt(chosen)


def ultra_ncst_base(now: datetime) -> tuple[str, str]:
    """초단기실황 getUltraSrtNcst — hourly at HH:00, published ~HH:40."""
    if now.minute >= 40:
        base = now.replace(minute=0, second=0, microsecond=0)
    else:
        base = (now - timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return _fmt(base)


def ultra_fcst_base(now: datetime) -> tuple[str, str]:
    """초단기예보 getUltraSrtFcst — hourly at HH:30, published ~HH:45."""
    if now.minute >= 45:
        base = now.replace(minute=30, second=0, microsecond=0)
    else:
        base = (now - timedelta(hours=1)).replace(minute=30, second=0, microsecond=0)
    return _fmt(base)


def mid_base(now: datetime) -> tuple[str, str]:
    """중기예보 (getMidLandFcst/getMidTa) tmFc — issued 06:00 and 18:00 KST."""
    if now.hour >= 18:
        base = now.replace(hour=18, minute=0, second=0, microsecond=0)
    elif now.hour >= 6:
        base = now.replace(hour=6, minute=0, second=0, microsecond=0)
    else:
        base = (now - timedelta(days=1)).replace(
            hour=18, minute=0, second=0, microsecond=0
        )
    return _fmt(base)


# ---------------------------------------------------------------------------
# SKY (1 맑음 / 3 구름많음 / 4 흐림) + PTY (0 없음 / 1 비 / 2 비눈 / 3 눈 / 4 소나기;
# 초단기 also 5 빗방울 / 6 빗방울눈날림 / 7 눈날림) -> Home Assistant condition.
# ---------------------------------------------------------------------------
def map_condition(sky, pty, is_day: bool = True) -> str:
    """Map KMA SKY/PTY codes to a Home Assistant weather condition string."""
    sky = int(sky)
    pty = int(pty)
    if pty != 0:
        if pty in (1, 4, 5):      # 비, 소나기, 빗방울
            return "rainy"
        if pty in (2, 6):         # 비/눈, 빗방울눈날림
            return "snowy-rainy"
        if pty in (3, 7):         # 눈, 눈날림
            return "snowy"
        return "rainy"
    if sky <= 2:                  # 맑음
        return "sunny" if is_day else "clear-night"
    if sky == 3:                  # 구름많음
        return "partlycloudy"
    return "cloudy"               # 흐림


# ---------------------------------------------------------------------------
# Response envelope -> item list.
# ---------------------------------------------------------------------------
def extract_items(resp: dict) -> list[dict]:
    """Pull response.body.items.item; raise KmaError on a non-'00' resultCode."""
    try:
        header = resp["response"]["header"]
    except (KeyError, TypeError) as exc:
        raise KmaError(f"malformed KMA response (no header): {resp!r}") from exc
    code = str(header.get("resultCode", ""))
    if code not in ("00", "0"):
        raise KmaError(f"KMA resultCode={code} ({header.get('resultMsg')})")
    try:
        item = resp["response"]["body"]["items"]["item"]
    except (KeyError, TypeError) as exc:
        raise KmaError(f"malformed KMA response (no items): {resp!r}") from exc
    return item if isinstance(item, list) else [item]


# ---------------------------------------------------------------------------
# Forecast assembly. Output dicts use Home Assistant Forecast keys
# (datetime / native_temperature / native_templow / humidity /
#  precipitation_probability / native_precipitation / condition).
# ---------------------------------------------------------------------------
def _fcst_dt(date: str, time: str) -> datetime:
    return datetime(
        int(date[0:4]), int(date[4:6]), int(date[6:8]),
        int(time[0:2]), int(time[2:4]), tzinfo=KST,
    )


def _is_day(hour: int) -> bool:
    return 6 <= hour < 19


def _group_by_time(items: list[dict]) -> dict[tuple[str, str], dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}
    for it in items:
        key = (it["fcstDate"], it["fcstTime"])
        out.setdefault(key, {})[it["category"]] = it["fcstValue"]
    return out


def build_hourly(items: list[dict]) -> list[dict]:
    """단기예보/초단기예보 items -> sorted hourly HA forecast list."""
    grouped = _group_by_time(items)
    out: list[dict] = []
    for date, time in sorted(grouped):
        c = grouped[(date, time)]
        if "TMP" not in c and "T1H" not in c and "SKY" not in c:
            continue
        dt = _fcst_dt(date, time)
        entry: dict = {"datetime": dt.isoformat()}
        temp = c.get("TMP", c.get("T1H"))
        if temp is not None:
            entry["native_temperature"] = float(temp)
        if "REH" in c:
            entry["humidity"] = int(float(c["REH"]))
        if "POP" in c:
            entry["precipitation_probability"] = int(float(c["POP"]))
        precip = c.get("PCP", c.get("RN1"))
        if precip is not None:
            entry["native_precipitation"] = parse_amount(precip)
        entry["condition"] = map_condition(
            c.get("SKY", 1), c.get("PTY", 0), is_day=_is_day(dt.hour)
        )
        out.append(entry)
    return out


def merge_hourly(primary_items: list[dict], fill_items: list[dict]) -> list[dict]:
    """Merge two hourly sources, sorted, de-duped by time. For an overlapping
    hour the dicts are merged per-key with `primary` winning — so the finer
    초단기예보 (temp/condition) overlays while keeping POP from 단기예보."""
    out: dict[str, dict] = {h["datetime"]: dict(h) for h in build_hourly(fill_items)}
    for h in build_hourly(primary_items):
        merged = out.get(h["datetime"], {})
        merged.update(h)
        out[h["datetime"]] = merged
    return [out[k] for k in sorted(out)]


def build_3h(hourly: list[dict]) -> list[dict]:
    """Subsample an hourly forecast to 3-hour marks (00/03/06/.../21)."""
    return [h for h in hourly if int(h["datetime"][11:13]) % 3 == 0]


def build_daily(items: list[dict]) -> list[dict]:
    """단기예보 items -> per-day HA forecast (TMX/TMN, max POP, afternoon condition)."""
    grouped = _group_by_time(items)
    days: dict[str, dict] = {}
    for (date, time), c in grouped.items():
        d = days.setdefault(date, {"pops": [], "tmx": None, "tmn": None, "slots": {}})
        if "POP" in c:
            d["pops"].append(int(float(c["POP"])))
        if "TMX" in c:
            d["tmx"] = float(c["TMX"])
        if "TMN" in c:
            d["tmn"] = float(c["TMN"])
        d["slots"][time] = c
    out: list[dict] = []
    for date in sorted(days):
        d = days[date]
        entry: dict = {"datetime": _fcst_dt(date, "0000").isoformat()}
        if d["tmx"] is not None:
            entry["native_temperature"] = d["tmx"]
        if d["tmn"] is not None:
            entry["native_templow"] = d["tmn"]
        if d["pops"]:
            entry["precipitation_probability"] = max(d["pops"])
        # representative condition: prefer an afternoon slot, else the median slot
        rep = None
        for t in ("1500", "1400", "1300", "1200", "1600"):
            if t in d["slots"]:
                rep = d["slots"][t]
                break
        if rep is None and d["slots"]:
            keys = sorted(d["slots"])
            rep = d["slots"][keys[len(keys) // 2]]
        if rep is not None:
            entry["condition"] = map_condition(rep.get("SKY", 1), rep.get("PTY", 0), is_day=True)
        out.append(entry)
    return out


def _ncst_val(items: list[dict], cat: str):
    for it in items:
        if it.get("category") == cat:
            return it.get("obsrValue")
    return None


def _nearest_sky(items: list[dict], now: datetime):
    grouped = _group_by_time(items)
    best = None
    best_dt = None
    for (date, time), c in grouped.items():
        if "SKY" not in c:
            continue
        dt = _fcst_dt(date, time)
        if dt < now - timedelta(hours=1):
            continue
        if best_dt is None or dt < best_dt:
            best_dt, best = dt, c["SKY"]
    if best is None:
        for _, c in sorted(grouped.items()):
            if "SKY" in c:
                return c["SKY"]
        return 1
    return best


def build_current(ncst_items: list[dict], fcst_items: list[dict], now: datetime) -> dict:
    """초단기실황(getUltraSrtNcst) + SKY borrowed from the nearest forecast slot."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=KST)
    cur: dict = {}
    t = _ncst_val(ncst_items, "T1H")
    if t is not None:
        cur["temperature"] = float(t)
    reh = _ncst_val(ncst_items, "REH")
    if reh is not None:
        cur["humidity"] = int(float(reh))
    cur["precipitation"] = parse_amount(_ncst_val(ncst_items, "RN1"))
    pty = _ncst_val(ncst_items, "PTY") or 0
    cur["pty"] = int(pty)
    sky = _nearest_sky(fcst_items, now)
    cur["condition"] = map_condition(sky, pty, is_day=_is_day(now.hour))
    return cur
