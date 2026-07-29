import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from risk_engine.rules_loader import load_rules  # noqa: E402


@pytest.fixture(scope="session")
def rules():
    return load_rules(ROOT / "rules")


@pytest.fixture(scope="session")
def nice():
    return json.loads((ROOT / "tests/fixtures/nice_06088.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def answers_apartment():
    return json.loads(
        (ROOT / "tests/fixtures/answers_nice_apartment.json").read_text(encoding="utf-8"))
