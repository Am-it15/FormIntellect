import random
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")
MIN_SECONDS_PER_ROW = 2


def validate_time_window(start_input, end_input, start_rand_min, start_rand_max,
                         end_rand_min, end_rand_max, total_rows, date_str=None):
    min_required = total_rows * MIN_SECONDS_PER_ROW
    if start_rand_min > start_rand_max:
        start_rand_min, start_rand_max = start_rand_max, start_rand_min
    if end_rand_min > end_rand_max:
        end_rand_min, end_rand_max = end_rand_max, end_rand_min
    today = date_str or datetime.now(IST).strftime("%Y-%m-%d")
    try:
        start_dt = IST.localize(datetime.strptime(f"{today} {start_input}", "%Y-%m-%d %H:%M"))
        end_dt   = IST.localize(datetime.strptime(f"{today} {end_input}",   "%Y-%m-%d %H:%M"))
    except ValueError:
        return {"ok": False, "error": "Invalid time format. Use HH:MM (e.g. 09:30)"}
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    original_window_sec = int((end_dt - start_dt).total_seconds())
    for _ in range(1000):
        rs  = random.randint(start_rand_min, start_rand_max)
        re_ = random.randint(end_rand_min,   end_rand_max)
        rand_start = start_dt + timedelta(seconds=rs)
        rand_end   = end_dt   + timedelta(seconds=re_)
        if rand_end <= rand_start:
            rand_end = rand_start + timedelta(seconds=1)
        window_sec = int((rand_end - rand_start).total_seconds())
        if window_sec > original_window_sec and window_sec >= min_required:
            return {
                "ok": True, "error": None,
                "rand_start": rand_start.isoformat(),
                "rand_end":   rand_end.isoformat(),
                "rand_start_fmt": rand_start.strftime("%d-%m-%Y %H:%M:%S IST"),
                "rand_end_fmt":   rand_end.strftime("%d-%m-%Y %H:%M:%S IST"),
                "original_window_sec": original_window_sec,
                "window_sec": window_sec,
                "rs": rs, "re": re_,
                "min_required_sec": min_required,
            }
    return {"ok": False, "error": (
        f"Could not find valid randomization after 1000 attempts. "
        f"Final window must be > {original_window_sec}s AND >= {min_required}s. "
        f"Increase end_rand_max or widen your base time window."
    )}


def build_offsets(window_sec, total_rows):
    safe_window = max(window_sec, total_rows * MIN_SECONDS_PER_ROW + 5)
    if total_rows > safe_window:
        step = safe_window / total_rows
        return [int(i * step) + 1 for i in range(total_rows)]
    return sorted(random.sample(range(1, safe_window + 1), total_rows))


def seconds_until(target_iso):
    target = datetime.fromisoformat(target_iso)
    if target.tzinfo is None:
        target = IST.localize(target)
    return max(0.0, (target - datetime.now(IST)).total_seconds())


def format_human(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def format_mm_ss(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"
