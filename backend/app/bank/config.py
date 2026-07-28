"""Runtime flags for the independent Typhoon Bank module."""

from __future__ import annotations

import os


def typhoon_bank_enabled() -> bool:
    return os.getenv("TYPHOON_BANK_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
