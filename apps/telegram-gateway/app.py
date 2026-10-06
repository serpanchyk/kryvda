"""Vercel entrypoint: Vercel loads the top-level ``app`` from this file."""

import sys
from pathlib import Path

# Vercel bundles this directory as-is; make the src-layout package importable either way.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from telegram_monitor_gateway.asgi import app  # noqa: E402

__all__ = ["app"]
