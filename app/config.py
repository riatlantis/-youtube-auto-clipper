from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

def _secret_or_env(key: str, default: str = "") -> str:
    value = os.getenv(key, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        secret_value = str(st.secrets.get(key, "")).strip()
        if secret_value:
            return secret_value
    except Exception:
        pass
    return default


YOUTUBE_API_KEY = _secret_or_env("YOUTUBE_API_KEY", "")
DEFAULT_REGION = _secret_or_env("YOUTUBE_REGION", "ID").upper() or "ID"
DEFAULT_CATEGORY = _secret_or_env("YOUTUBE_CATEGORY_ID", "24") or "24"

DOWNLOAD_DIR = ROOT_DIR / "downloads"
OUTPUT_DIR = ROOT_DIR / "output"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
