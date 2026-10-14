#!/usr/bin/env python3
"""
One-time setup for Google Search Console API access.

Creates OAuth credentials and saves them for use by search_performance.py.

Prerequisites:
  1. Google Cloud project with Search Console API enabled
  2. OAuth Desktop client (https://console.cloud.google.com/apis/credentials)
  3. Fill in GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env

Usage:
  python3 -m zens_ink.setup_gsc

You'll get a URL to open in your browser, authorize, then paste the
redirect URL back here.
"""

import json
import os
import sys
import urllib.parse
import urllib.request

from zens_ink.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ADC_PATH

SCOPES = " ".join([
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
])
REDIRECT = "http://localhost:8484"


def main():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        print("ERROR: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set in .env\n")
        print("Setup steps:")
        print("  1. Go to https://console.cloud.google.com/apis/credentials")
        print("  2. Create Credentials -> OAuth client ID -> Desktop app")
        print("  3. Copy Client ID and Client Secret into .env")
        sys.exit(1)

    # Build auth URL
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        })
    )

    print("\n" + "=" * 60)
    print("  GSC OAuth Setup")
    print("=" * 60)
    print(f"\n  Step 1: Open this URL in your browser:\n")
    print(f"  {auth_url}\n")
    print(f"  Step 2: Authorize the app. Your browser will redirect to:")
    print(f"  {REDIRECT}/?code=...\n")
    print(f"  (The page won't load — that's fine. Copy the full URL from")
    print(f"   the address bar.)\n")

    redirect_url = input("  Step 3: Paste the full redirect URL here:\n  > ").strip()

    # Extract code
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
    if "code" not in parsed:
        print("\n  ERROR: No 'code' parameter found in the URL.")
        sys.exit(1)

    code = parsed["code"][0]

    # Exchange code for tokens
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }).encode()

    try:
        resp = urllib.request.urlopen(
            urllib.request.Request("https://oauth2.googleapis.com/token", data=data),
            timeout=15)
    except urllib.error.HTTPError as e:
        print(f"\n  ERROR: Token exchange failed ({e.code}): {e.read().decode()[:200]}")
        sys.exit(1)

    tokens = json.loads(resp.read().decode())
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("\n  ERROR: No refresh_token returned. Try revoking access and re-authorizing:")
        print("  https://myaccount.google.com/permissions")
        sys.exit(1)

    # Save credentials
    creds = {
        "type": "authorized_user",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }

    _adc_dir = os.path.dirname(ADC_PATH)
    if _adc_dir:  # bare filename → dirname is "" and makedirs("") raises
        os.makedirs(_adc_dir, exist_ok=True)
    with open(ADC_PATH, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(ADC_PATH, 0o600)

    # Quick test
    access_token = tokens["access_token"]
    test_req = urllib.request.Request(
        "https://searchconsole.googleapis.com/webmasters/v3/sites",
        headers={"Authorization": f"Bearer {access_token}"})
    try:
        resp2 = urllib.request.urlopen(test_req, timeout=10)
        sites = json.loads(resp2.read().decode()).get("siteEntry", [])
        site_list = [s["siteUrl"] for s in sites]
        print(f"\n  SUCCESS! Saved to {ADC_PATH}")
        print(f"  Verified sites: {', '.join(site_list) if site_list else '(none yet)'}")
        print(f"\n  Set GSC_SITE_URL in .env to one of the above, e.g.:")
        print(f"  GSC_SITE_URL=sc-domain:yourdomain.com")
    except Exception as e:
        print(f"\n  Credentials saved to {ADC_PATH}")
        print(f"  Warning: verification test failed ({e})")
        print(f"  Make sure Search Console API is enabled in your GCP project.")


if __name__ == "__main__":
    main()
