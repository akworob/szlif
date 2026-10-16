"""The user's settings (the model the installer chose), outside the repo."""

import json
import os
from pathlib import Path
from typing import Dict


def config_path() -> Path:
    return Path(os.environ.get("SZLIF_CONFIG") or Path.home() / ".szlif.json")


def load() -> Dict:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: Dict) -> None:
    config_path().write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
