from __future__ import annotations
import contextvars

req_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("req_id", default="-")
