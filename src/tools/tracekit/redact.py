from __future__ import annotations
import re, reprlib

repr_limited = reprlib.Repr()
repr_limited.maxstring = 200
repr_limited.maxother = 200

def redact_value(key: str, value, pattern: re.Pattern) -> str:
    v = repr_limited.repr(value)
    if pattern.search(str(key)):
        return "***redacted***"
    return v

def safe_locals(locals_dict: dict, pattern: re.Pattern) -> dict:
    out = {}
    for k, v in locals_dict.items():
        try:
            out[str(k)] = redact_value(str(k), v, pattern)
        except Exception:
            out[str(k)] = "<unrepr-able>"
    return out
