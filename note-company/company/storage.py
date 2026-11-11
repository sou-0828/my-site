"""ファイル置き場と設定の読み書き。"""
from __future__ import annotations

import csv
import json
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
STATE = ROOT / "state"
JST = timezone(timedelta(hours=9))


def load_env() -> None:
    """note-company/.env を読み込む（既に設定済みの環境変数は上書きしない）。"""
    import os

    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def now_jst() -> datetime:
    return datetime.now(JST)


def today() -> str:
    return now_jst().strftime("%Y-%m-%d")


def config() -> dict[str, Any]:
    with open(ROOT / "config.toml", "rb") as f:
        return tomllib.load(f)


def day_dir(day: str | None = None) -> Path:
    d = OUTPUT / (day or today())
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_sales() -> list[dict[str, str]]:
    """data/sales.csv（noteの売上データ）を読む。"""
    path = DATA / "sales.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_docs(folder: str, limit_chars: int = 400_000) -> str:
    """data/notes や data/letters の .md / .txt をまとめて読む。"""
    parts: list[str] = []
    total = 0
    for p in sorted((DATA / folder).glob("*")):
        if p.suffix.lower() not in {".md", ".txt"} or p.name.startswith("_"):
            continue
        body = p.read_text(encoding="utf-8")
        total += len(body)
        if total > limit_chars:
            print(f"[warn] {folder} が大きすぎるため {p.name} 以降を読み込みませんでした")
            break
        parts.append(f'<document name="{p.name}">\n{body}\n</document>')
    return "\n\n".join(parts)
