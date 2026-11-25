import json
from pathlib import Path

from .models import PageRecord

def write_json(records: list[PageRecord], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
