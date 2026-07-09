import logging
import os
import socket
import sys
import threading
import time
import webbrowser

# In a windowless build (no console on Windows / no Terminal on macOS) PyInstaller
# leaves stdout/stderr as None. Flask/Werkzeug still try to log, and writing to a
# None stream would crash the app. Point them at the null device so any stray log
# line is silently discarded instead.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

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
