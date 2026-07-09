import logging
import os
import socket
import sys
import threading
import time
import webbrowser

# In a windowless build (no console on Windows / no Terminal on macOS) PyInstaller
# leaves stdout/stderr as None. Flask/Werkzeug + our own startup prints still write
# there, so a None stream would crash the app. Point them at the null device.
# Use UTF-8 with errors="replace" so unicode banners/checkmarks in the code can't
# blow up on Windows' default cp1252 console encoding (UnicodeEncodeError).
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name)
    if _stream is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8", errors="replace"))
    else:
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Keep the request log quiet — nothing is watching it, and we run windowless.
logging.getLogger("werkzeug").setLevel(logging.ERROR)

from Website_frontend.server import app

HOST = "127.0.0.1"
PORT = 5001
URL = f"http://{HOST}:{PORT}"


def _open_browser_when_ready():
    # Wait until Flask is actually accepting connections before opening the
    # browser, so the founder never lands on a "connection refused" page while
    # the server is still starting up.
    for _ in range(120):  # up to ~60s
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((HOST, PORT)) == 0:
                break
        time.sleep(0.5)
    webbrowser.open(URL)


# Open the dashboard in the default browser once the server is up, then run Flask
# in the main thread so the process stays alive serving requests. Same behaviour
# on macOS and Windows — no bundled webview window.
threading.Thread(target=_open_browser_when_ready, daemon=True).start()

app.run(
    host=HOST,
    port=PORT,
    debug=False,
    use_reloader=False,
)
