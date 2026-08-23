#!/usr/bin/env python3
"""Shared configuration — reads from .env file or environment variables."""

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def load_env():
    """Load .env file into os.environ if present."""
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_env()

# Bing Webmaster Tools
BING_API_KEY = os.environ.get("BING_API_KEY", "")

# Serper.dev (SERP data for KD analysis)
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")

# Brave Search API (volume estimation)
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")

# Ahrefs free Domain Rating API (v3/public/domain-rating-free)
# Free key: ahrefs.com -> Account settings -> API keys
AHREFS_API_KEY = os.environ.get("AHREFS_API_KEY", "")

# Google Search Console
GSC_SITE_URL = os.environ.get("GSC_SITE_URL", "")  # e.g. sc-domain:example.com
ADC_PATH = os.environ.get(
    "ADC_PATH",
    os.path.expanduser("~/.config/gcloud/application_default_credentials.json"),
)

# Google OAuth (for setup_gsc.py only)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
