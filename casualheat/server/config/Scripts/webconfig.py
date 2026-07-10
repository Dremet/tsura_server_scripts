"""Read the web-managed server config written by the tsura.org admin panels.

The tsura.org admin area writes /srv/tsura/server_config/<server>.json.
Game-server scripts read it at session start / event init. Every accessor
falls back to the script's built-in default if the file or a field is
missing or malformed — a broken config must never break a session.
"""

import json

CONFIG_DIR = "/srv/tsura/server_config"


def load(server):
    """Return the config dict for `server`, or {} if unreadable."""
    try:
        with open(f"{CONFIG_DIR}/{server}.json", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("config root is not an object")
        return cfg
    except Exception as exc:
        print(f"webconfig: using built-in defaults ({exc})")
        return {}


def _get(cfg, path):
    cur = cfg
    for key in path if isinstance(path, tuple) else (path,):
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(str(path))
        cur = cur[key]
    return cur


def get_num(cfg, path, default):
    """Number at `path` (a key or tuple of nested keys); int if integral."""
    try:
        val = float(_get(cfg, path))
        return int(val) if val.is_integer() else val
    except Exception:
        return default


def get_range(cfg, section, lo_key, hi_key, default):
    """Inclusive int range (lo, hi) for random.randint; swaps if inverted."""
    lo = int(get_num(cfg, (section, lo_key), default[0]))
    hi = int(get_num(cfg, (section, hi_key), default[1]))
    return (lo, hi) if lo <= hi else (hi, lo)


def get_weighted(cfg, key, default):
    """List of [name, weight] pairs -> [(str, float), ...]; drops weight<=0."""
    try:
        items = [(str(name), float(weight)) for name, weight in cfg[key]]
        items = [(n, w) for n, w in items if n and w > 0]
        return items if items else default
    except Exception:
        return default


def get_strlist(cfg, key, default):
    try:
        items = [str(v) for v in cfg[key] if str(v)]
        return items if items else default
    except Exception:
        return default


def get_str(cfg, path, default):
    """Non-empty string at `path` (key or tuple of nested keys)."""
    try:
        val = str(_get(cfg, path)).strip()
        return val if val else default
    except Exception:
        return default


def get_intlist(cfg, path, default):
    """Non-empty list of ints at `path` (e.g. a points table)."""
    try:
        vals = [int(v) for v in _get(cfg, path)]
        return vals if vals else default
    except Exception:
        return default


def get_admins(cfg, default):
    """List of [steam_id, label] pairs -> [(str, str), ...]."""
    try:
        admins = [(str(sid), str(label)) for sid, label in cfg["ingame_admins"]]
        admins = [(s, lbl) for s, lbl in admins if s.isdigit()]
        return admins if admins else default
    except Exception:
        return default
