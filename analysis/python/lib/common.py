from __future__ import annotations

from pathlib import Path
import json
import yaml

ROOT = Path('/Users/apple/Documents/lancet-research-platform')


def load_config() -> dict:
    cfg_path = ROOT / 'configs' / 'study_config.yaml'
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text(encoding='utf-8')) or {}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, obj: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
