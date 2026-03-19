import pandas as pd
from datetime import datetime

def normalize_value(raw, entry_type="text"):
    if pd.isna(raw): return "NA"
    if isinstance(raw, (pd.Timestamp, datetime)):
        if entry_type == "date":           return raw.strftime("%Y-%m-%d")
        if entry_type == "time":           return raw.strftime("%H:%M")
        if entry_type == "datetime-local": return raw.strftime("%Y-%m-%dT%H:%M")
    text = str(raw).strip()
    if not text: return "NA"
    if text.lower() in {"na","n/a","none","null"}: return text
    if entry_type == "datetime-local" and " " in text and "T" not in text:
        text = text.replace(" ","T",1)
    return text

def best_option(value, options):
    if not options: return value
    if value in options: return value
    lower_map = {o.lower(): o for o in options if isinstance(o, str)}
    matched = lower_map.get(value.lower())
    if matched: return matched
    try:
        num = float(value)
        candidates = []
        for o in options:
            try: candidates.append((abs(float(o)-num), o))
            except: pass
        if candidates: return sorted(candidates)[0][1]
    except ValueError: pass
    return options[0]

def auto_correct(df, pending_indices, required_columns, field_types, options_by_entry):
    corrections, errors = [], []
    for idx in pending_indices:
        for col, entry in required_columns.items():
            etype = field_types.get(entry, "text")
            value = normalize_value(df.at[idx, col], etype)
            new_val, reason = value, None
            opts = options_by_entry.get(entry)
            if opts:
                if etype == "checkbox" or "," in value:
                    parts = [v.strip() for v in value.split(",") if v.strip()]
                    fixed = [best_option(v, opts) for v in parts]
                    candidate = ", ".join(dict.fromkeys(fixed))
                    if candidate != value: new_val = candidate; reason = "normalized checkbox options"
                else:
                    candidate = best_option(value, opts)
                    if candidate != value: new_val = candidate; reason = "normalized to allowed option"
            if etype == "date":
                try:
                    new_val = pd.to_datetime(value).strftime("%Y-%m-%d")
                    if new_val != value: reason = "normalized date"
                except: errors.append((idx, col, entry, value, "invalid date")); continue
            elif etype == "time":
                try:
                    new_val = pd.to_datetime(value).strftime("%H:%M")
                    if new_val != value: reason = "normalized time"
                except: errors.append((idx, col, entry, value, "invalid time")); continue
            elif etype == "datetime-local":
                try:
                    new_val = pd.to_datetime(value).strftime("%Y-%m-%dT%H:%M")
                    if new_val != value: reason = "normalized datetime"
                except: errors.append((idx, col, entry, value, "invalid datetime")); continue
            if new_val != value:
                df.at[idx, col] = new_val
                corrections.append((idx, col, entry, value, new_val, reason))
    return corrections, errors

def validate_data(df, pending_indices, required_columns, field_types, options_by_entry):
    errors = []
    for idx in pending_indices:
        for col, entry in required_columns.items():
            etype = field_types.get(entry, "text")
            value = normalize_value(df.at[idx, col], etype)
            if etype in {"radio","select"} and "," in value:
                errors.append((idx, col, entry, value, "multiple values for single-choice")); continue
            opts = options_by_entry.get(entry)
            if opts:
                parts = [v.strip() for v in value.split(",") if v.strip()] if (etype=="checkbox" or "," in value) else [value]
                bad = [v for v in parts if v not in opts]
                if bad: errors.append((idx, col, entry, value, f"not in options: {', '.join(bad)}")); continue
            if etype == "date":
                try: datetime.strptime(value, "%Y-%m-%d")
                except: errors.append((idx, col, entry, value, "invalid date (YYYY-MM-DD)"))
            elif etype == "time":
                valid = any(True for fmt in ("%H:%M","%H:%M:%S") if _try_parse(value,fmt))
                if not valid: errors.append((idx, col, entry, value, "invalid time (HH:MM)"))
            elif etype == "datetime-local":
                valid = any(True for fmt in ("%Y-%m-%dT%H:%M","%Y-%m-%dT%H:%M:%S") if _try_parse(value,fmt))
                if not valid: errors.append((idx, col, entry, value, "invalid datetime (YYYY-MM-DDTHH:MM)"))
    return errors

def _try_parse(value, fmt):
    try: datetime.strptime(value, fmt); return True
    except: return False
