"""
MAX∞ Keep-Alive Pinger
─────────────────────────────────────────────────
Runs as a separate thread inside the app.
Pings /health every 14 minutes to prevent Render's
free tier from putting the app to sleep.
─────────────────────────────────────────────────
"""

import threading
import time
import requests
import os


def keep_alive():
    """Ping self every 14 minutes to prevent Render sleep."""
    domain = os.getenv("APP_DOMAIN", "")
    if not domain:
        print("[KEEP-ALIVE] APP_DOMAIN not set — skipping pinger")
        return

    url = f"https://{domain}/health"
    print(f"[KEEP-ALIVE] Starting pinger → {url}")

    while True:
        time.sleep(14 * 60)  # 14 minutes
        try:
            r = requests.get(url, timeout=10)
            print(f"[KEEP-ALIVE] ping {r.status_code}")
        except Exception as e:
            print(f"[KEEP-ALIVE] ping failed: {e}")


def start_keep_alive():
    """Start the keep-alive thread. Call this once at app startup."""
    t = threading.Thread(target=keep_alive, daemon=True)
    t.start()
