import sys
import threading
import time
import webview

from Website_frontend.server import app


def run_flask():
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False,
        use_reloader=False
    )


flask_thread = threading.Thread(
    target=run_flask,
    daemon=True
)

flask_thread.start()

time.sleep(2)

window = webview.create_window(
    "Tender Intelligence Dashboard",
    "http://127.0.0.1:5001",
    width=1400,
    height=900
)

# EdgeChromium is a Windows-only backend; on macOS/Linux pywebview must pick its
# native backend (WebKit on macOS) instead, so only request EdgeChromium on
# Windows and fall back to the default if it isn't available.
if sys.platform.startswith("win"):
    try:
        webview.start(gui="edgechromium")
    except Exception:
        webview.start()
else:
    webview.start()
