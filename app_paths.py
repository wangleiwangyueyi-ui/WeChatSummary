"""Separate installed program files from each Windows user's private data.

Existing source/portable installations keep their original data directory.
An installer adds installed-mode.json to opt into per-user storage.
"""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
INSTALLED = (APP_DIR / 'installed-mode.json').is_file()
LEGACY_DATA = (APP_DIR / 'config.json').is_file()
DATA_DIR = Path(os.environ['WECHATSUMMARY_DATA_DIR']) if os.environ.get('WECHATSUMMARY_DATA_DIR') else (
    Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'WeChatSummary'
    if INSTALLED and not LEGACY_DATA else APP_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR = APP_DIR / 'models' / 'sensevoice'
