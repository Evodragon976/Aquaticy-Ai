"""Sichtbare Containergrenzen fuer Arbeitsspeicher und Prozessoren."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path


def _read(name: str) -> str:
    try:
        return Path('/sys/fs/cgroup', name).read_text().strip()
    except OSError:
        return ''


def _positive(value: str) -> int | None:
    try:
        number = int(value)
        return number if 0 < number < 1 << 60 else None
    except ValueError:
        return None


def memory_limit() -> int | None:
    return (_positive(_read('memory.max'))
            or _positive(_read('memory/memory.limit_in_bytes')))


def memory_current() -> int | None:
    return (_positive(_read('memory.current'))
            or _positive(_read('memory/memory.usage_in_bytes')))


def cpu_limit() -> float | None:
    values = _read('cpu.max').split()
    if len(values) != 2:
        values = [_read('cpu/cpu.cfs_quota_us'), _read('cpu/cpu.cfs_period_us')]
    quota, period = (_positive(value) for value in values)
    return quota / period if quota is not None and period is not None else None


def cpu_count() -> float:
    count = float(os.cpu_count() or 1)
    with contextlib.suppress(OSError, AttributeError):
        count = min(count, len(os.sched_getaffinity(0)))
    quota = cpu_limit()
    return min(count, quota) if quota is not None else count
