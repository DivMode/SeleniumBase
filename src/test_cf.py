"""Test CF bypass with SeleniumBase UC mode + rrweb replay recording.

Events are pushed from the Chrome extension to the replay server in
real-time via fetch(). No client-side extraction needed — events survive
page navigation during captcha solve.
"""
import json
import os
import time
import urllib.request

from seleniumbase import SB

REPLAY_SERVER = os.environ.get("REPLAY_SERVER", "http://replay:3000")
TARGET_URL = os.environ.get("TARGET_URL", "https://nopecha.com/demo/cloudflare")


def create_session() -> str | None:
    """Create a replay session on the server and set it as 'current'."""
    req = urllib.request.Request(
        f"{REPLAY_SERVER}/replays/session",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            print(f"[replay] Session created: {result.get('id')}")
            return result.get("id")
    except Exception as e:
        print(f"[replay] Failed to create session: {e}")
        return None


def add_marker(session_id: str, marker: dict) -> None:
    """Add a custom marker event to the session via the replay server."""
    event = {
        "type": 5,
        "timestamp": int(time.time() * 1000),
        "data": marker,
    }
    payload = json.dumps({"events": [event]}).encode()
    req = urllib.request.Request(
        f"{REPLAY_SERVER}/replays/{session_id}/events",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[replay] Failed to add marker: {e}")


def test_nopecha():
    disable = os.environ.get("SELENIUMBASE_REPLAY", "1") == "0"

    # Create replay session BEFORE browser launch so extension can discover it
    session_id = None
    if not disable:
        session_id = create_session()

    # Chrome mixed content + Private Network Access blocks fetch() from
    # HTTPS pages to HTTP replay server on Docker internal network.
    # --disable-web-security bypasses CORS + mixed content entirely.
    with SB(
        uc=True,
        xvfb=True,
        extension_dir="/app/extensions/replay",
        chromium_arg="--disable-web-security,--allow-running-insecure-content",
    ) as sb:
        sb.uc_open_with_reconnect(TARGET_URL, reconnect_time=5)

        try:
            sb.uc_gui_handle_captcha()
        except Exception as e:
            print(f"Captcha handle failed: {e}")

        source = sb.get_page_source()
        solved = "challenge" not in source.lower()
        url = sb.get_current_url()
        print(f"Solved: {solved}")
        print(f"URL: {url}")

        if not disable and session_id:
            # Wait for extension's final flush (1s interval + margin)
            time.sleep(3)

            # Add result marker
            add_marker(session_id, {
                "tag": "cf_test_result",
                "payload": {
                    "url": url,
                    "title": sb.get_title(),
                    "solved": solved,
                },
            })

            replay_url = f"{REPLAY_SERVER}/replay/{session_id}"
            print(f"[replay] URL: {replay_url}")

        return solved


if __name__ == "__main__":
    test_nopecha()
