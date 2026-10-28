"""Unit tests never inherit production services from a developer's .env."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

from app.config import Settings, get_settings

Settings.model_config["env_file"] = None
get_settings.cache_clear()
