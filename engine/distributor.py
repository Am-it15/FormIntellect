import random
import json
import os

CONFIGS_DIR = "configs"


# ── Presets ───────────────────────────────────────────────────────────────────

def apply_preset(options: list, preset: str) -> list:
    """
    Return weights list for given preset name.
    Presets: uniform | bell | skewed_left | skewed_right | realistic
    """
    n = len(options)
    if n == 0:
        return []

    if preset == "uniform":
        w = [100.0 / n] * n
        return w

    if preset == "bell":
        mid = (n - 1) / 2.0
        raw = [1.0 / (1 + abs(i - mid) * 1.2) for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    if preset == "skewed_right":
        raw = [n - i for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    if preset == "skewed_left":
        raw = [i + 1 for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    if preset == "realistic":
        if n == 1:
            return [100.0]
        if n == 2:
            return [60.0, 40.0]
        if n == 3:
            return [20.0, 50.0, 30.0]
        if n == 4:
            return [10.0, 40.0, 35.0, 15.0]
        if n == 5:
            return [5.0, 20.0, 45.0, 20.0, 10.0]
        mid = (n - 1) / 2.0
        raw = [1.0 / (1 + abs(i - mid) * 0.8) for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    return [100.0 / n] * n


# ── Single response generator ─────────────────────────────────────────────────

def generate_response(dist_config: dict, identity_row: dict = None) -> dict:
    """
    Generate one synthetic response row from dist_config.
    dist_config: {entry_id: spec_dict}
    """
    row = dict(identity_row) if identity_row else {}

    for eid, spec in dist_config.items():
        stype = spec.get("type", "")

        if stype in {"radio", "select", "scale", "grid"}:
            options = spec.get("options", [])
            weights = spec.get("weights", [])
            if options and weights:
                row[eid] = random.choices(options, weights=weights, k=1)[0]
            elif options:
                row[eid] = random.choice(options)
            else:
                row[eid] = ""

        elif stype == "checkbox":
            probs    = spec.get("probs", {})
            selected = [opt for opt, prob in probs.items() if random.random() < prob / 100.0]
            row[eid] = ", ".join(selected) if selected else ""

        elif stype in {"text", "textarea"}:
            mode = spec.get("mode", "blank")
            if mode == "pool":
                pool  = spec.get("pool", [])
                texts = [p[0] for p in pool]
                wts   = [p[1] for p in pool]
                row[eid] = random.choices(texts, weights=wts, k=1)[0] if pool else ""
            else:
                row[eid] = ""

        elif stype in {"date", "time", "datetime-local"}:
            row[eid] = spec.get("fixed", "")

        else:
            row[eid] = ""

    return row


def generate_batch(dist_config: dict, identity_rows: list) -> list:
    return [generate_response(dist_config, identity) for identity in identity_rows]


# ── Config save / load ────────────────────────────────────────────────────────

def save_config(dist_config: dict, name: str) -> str:
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = os.path.join(CONFIGS_DIR, f"{safe_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dist_config, f, indent=2)
    return path


def load_config(name: str) -> dict:
    path = os.path.join(CONFIGS_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_configs() -> list:
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    return [
        f[:-5] for f in os.listdir(CONFIGS_DIR)
        if f.endswith(".json") and f != ".gitkeep"
    ]


# ── Weight helpers ────────────────────────────────────────────────────────────

def normalize_weights(weights: list) -> list:
    total = sum(weights)
    if total == 0:
        return [100.0 / len(weights)] * len(weights)
    return [round(w / total * 100, 4) for w in weights]


def counts_to_weights(counts: list, total: int) -> list:
    if total == 0:
        return [100.0 / len(counts)] * len(counts)
    return [round(c / total * 100, 4) for c in counts]


def weights_to_counts(weights: list, total: int) -> list:
    return [round(w / 100.0 * total) for w in weights]
