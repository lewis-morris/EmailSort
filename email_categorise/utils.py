from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("email_categorise")


def configure_logging(verbosity: int = 0) -> None:
    if logging.getLogger().handlers:
        return
    level = logging.INFO if verbosity <= 0 else logging.DEBUG
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def days_ago(days: int) -> datetime:
    return utc_now() - timedelta(days=days)


def ensure_dir(path: str | Path) -> Path:
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_json(path: str | Path, default: Any) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if is_dataclass(data):
        data = asdict(data)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)


def account_state_dir(base_dir: Path, account_email: str) -> Path:
    safe = account_email.replace("@", "_at_").replace("/", "_")
    return ensure_dir(base_dir / safe)


_ENV_LOADED = False


def load_env_file(path: str | Path = ".env") -> Optional[Path]:
    """
    Lightweight .env reader (no external dependency).
    - Lines starting with # are ignored.
    - Supports KEY=VALUE with optional surrounding quotes.
    - Does not override variables that are already set.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return None

    env_path = Path(path).expanduser()
    if not env_path.exists():
        _ENV_LOADED = True
        return None

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

    _ENV_LOADED = True
    return env_path
