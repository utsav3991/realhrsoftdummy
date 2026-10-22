"""The built employee app's files, from the Vite manifest (frontend/vite.config.ts)."""

import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

BUILD_DIR = Path(__file__).resolve().parent / "static" / "marketplace"
MANIFEST = BUILD_DIR / ".vite" / "manifest.json"
ENTRY = "src/main.ts"


@dataclass(frozen=True)
class EntryAssets:
    script: str
    styles: tuple[str, ...]


def entry() -> EntryAssets | None:
    """URLs of the entry script and its CSS, or ``None`` before the first build."""
    try:
        chunk = json.loads(MANIFEST.read_text())[ENTRY]
    except FileNotFoundError, KeyError, ValueError:
        return None
    base = f"{settings.STATIC_URL.rstrip('/')}/marketplace/"
    return EntryAssets(
        script=base + chunk["file"],
        styles=tuple(base + css for css in chunk.get("css", ())),
    )
