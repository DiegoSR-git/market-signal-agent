from __future__ import annotations

import json
import os
from pathlib import Path


class JsonStorageProvider:
    name = "json"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save_snapshot(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class SupabaseStorageProvider:
    name = "supabase"

    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.secret = os.getenv("SUPABASE_SECRET_KEY")
        if not self.url or not self.secret:
            raise RuntimeError("Supabase backend no configurado")

    def save_snapshot(self, payload: dict) -> None:
        raise RuntimeError("Supabase writes requieren configurar cliente backend y RLS auditada")
