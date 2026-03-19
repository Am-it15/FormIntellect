import json, re, urllib.parse, requests

def extract_entry_ids(prefilled_link):
    parsed = urllib.parse.urlparse(prefilled_link)
    pairs  = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    seen, ids = set(), []
    for key, _ in pairs:
        if key.startswith("entry.") and key not in seen:
            ids.append(key); seen.add(key)
    return ids

def fetch_form_metadata(prefilled_link):
    result = {"field_types": {}, "options_by_entry": {}, "grid_info": {}, "questions_order": [], "form_title": "", "error": None}
    try:
        resp = requests.get(prefilled_link, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        result["error"] = f"Could not fetch form: {exc}"; return result
    html = resp.text
    m = re.search(r"<title>([^<]+)</title>", html)
    if m: result["form_title"] = m.group(1).replace(" - Google Forms","").strip()
    field_types = {}
    for m in re.finditer(r'name="(entry\.\d+)"[^>]*type="([^"]+)"', html):
        eid, itype = m.group(1), m.group(2).lower()
        if eid not in field_types: field_types[eid] = itype
        elif "checkbox" in (field_types[eid], itype): field_types[eid] = "checkbox"
    for m in re.finditer(r'<textarea[^>]*name="(entry\.\d+)"', html): field_types.setdefault(m.group(1), "textarea")
    for m in re.finditer(r'<select[^>]*name="(entry\.\d+)"', html):   field_types.setdefault(m.group(1), "select")
    blob = _parse_fb_blob(html)
    options_by_entry, grid_info, questions_order = {}, {}, []
    if blob:
        options_by_entry = _options_from_blob(blob)
        grid_info        = _grid_from_blob(blob)
        for eid in grid_info: field_types[eid] = "grid"
        try:
            for item in blob[1][1]:
                if not isinstance(item, list) or len(item) < 5: continue
                label = item[1] if isinstance(item[1], str) else ""
                question = item[4]
                if not isinstance(question, list): continue
                for q_item in question:
                    if not isinstance(q_item, list) or not q_item: continue
                    eid_raw = q_item[0]
                    if eid_raw is None: continue
                    eid = f"entry.{eid_raw}"
                    questions_order.append((eid, label, field_types.get(eid, "text")))
        except Exception: pass
    if not questions_order:
        for eid in extract_entry_ids(prefilled_link):
            questions_order.append((eid, eid, field_types.get(eid, "text")))
    result["field_types"] = field_types; result["options_by_entry"] = options_by_entry
    result["grid_info"] = grid_info;     result["questions_order"] = questions_order
    return result

def build_column_mapping(columns, prefilled_link, status_col):
    entry_cols    = [c for c in columns if c.startswith("entry.")]
    prefilled_ids = extract_entry_ids(prefilled_link)
    non_status    = [c for c in columns if c != status_col]
    if entry_cols: return {c: c for c in entry_cols}
    if prefilled_ids:
        matched = [c for c in prefilled_ids if c in columns]
        if matched: return {c: c for c in matched}
        if len(prefilled_ids) == len(non_status): return dict(zip(non_status, prefilled_ids))
    raise ValueError("Cannot map columns to entry IDs. Rename columns to entry.<id>, or ensure column count matches the prefilled link.")

def _parse_fb_blob(html):
    token = "FB_PUBLIC_LOAD_DATA_"
    idx = html.find(token)
    if idx == -1: return None
    start = html.find("[", idx)
    if start == -1: return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if escape: escape = False
            elif ch == "\\": escape = True
            elif ch == '"': in_str = False
            continue
        if ch == '"': in_str = True
        elif ch == "[": depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try: return json.loads(html[start:i+1])
                except: return None
    return None

def _options_from_blob(blob):
    result = {}
    try: items = blob[1][1]
    except: return result
    for item in items:
        if not isinstance(item, list) or len(item) < 5: continue
        question = item[4]
        if not isinstance(question, list) or not question: continue
        q0 = question[0]
        if not isinstance(q0, list) or len(q0) < 2: continue
        eid = q0[0]
        if eid is None: continue
        opts = [opt[0] for opt in q0[1] if isinstance(opt, list) and opt and isinstance(opt[0], str)] if isinstance(q0[1], list) else []
        if opts: result[f"entry.{eid}"] = opts
    return result

def _grid_from_blob(blob):
    result = {}
    try: items = blob[1][1]
    except: return result
    for item in items:
        if not isinstance(item, list) or len(item) < 5: continue
        q_label = item[1] if isinstance(item[1], str) else ""
        question = item[4]
        if not isinstance(question, list) or len(question) < 2: continue
        sub_entries, col_options, row_labels = [], [], []
        for q_item in question:
            if not isinstance(q_item, list) or len(q_item) < 2: continue
            eid = q_item[0]
            if eid is None: continue
            opts = [opt[0] for opt in q_item[1] if isinstance(opt, list) and opt and isinstance(opt[0], str)] if isinstance(q_item[1], list) else []
            if opts:
                sub_entries.append(f"entry.{eid}")
                if not col_options: col_options = opts
            row_labels.append(q_item[3] if len(q_item) > 3 and isinstance(q_item[3], str) else f"entry.{eid}")
        if len(sub_entries) >= 2:
            if len(row_labels) != len(sub_entries): row_labels = list(sub_entries)
            for i, eid in enumerate(sub_entries):
                result[eid] = {"question_label": q_label, "sub_label": row_labels[i], "all_sub_entries": sub_entries, "options": col_options}
    return result
