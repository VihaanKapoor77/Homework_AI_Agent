"""Validated timeouts; generous browser operations, short DOM polling."""
from __future__ import annotations
import math
import os
import warnings

MAX_TIMER_MS = 2_147_483_647

def milliseconds(name: str, default: float) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be a finite positive number of milliseconds') from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be a finite positive number of milliseconds')
    if value > MAX_TIMER_MS:
        warnings.warn(f'{name} exceeds the browser timeout limit and was clamped', UserWarning)
        return MAX_TIMER_MS
    return max(1, math.ceil(value))

ACTION_MS = milliseconds('BROWSER_ACTION_TIMEOUT_MS', 120000)
NAVIGATION_MS = milliseconds('BROWSER_NAVIGATION_TIMEOUT_MS', 180000)
READY_MS = milliseconds('DELTAMATH_READY_TIMEOUT_MS', 12000)
STARTUP_SECONDS = milliseconds('BROWSER_STARTUP_TIMEOUT_MS', 120000)/1000
STEP_SECONDS = milliseconds('BROWSER_STEP_TIMEOUT_MS', 240000)/1000
TASK_SECONDS = milliseconds('BROWSER_TASK_TIMEOUT_MS', 1200000)/1000
REQUEST_SECONDS = milliseconds('REQUEST_TIMEOUT_MS', 900000)/1000
LLM_SECONDS = milliseconds('LLM_TIMEOUT_MS', 90000)/1000

def configure_browser_events():
    """Retain explicit browser timeouts without altering global async cancellation."""
    return None
