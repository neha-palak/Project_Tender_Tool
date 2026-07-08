import threading
import webbrowser

from Website_frontend.server import app

URL = "http://127.0.0.1:5001"


def _open_browser():
    webbrowser.open(URL)


# Open the dashboard in the default browser shortly after the server comes up,
# then run Flask in the main thread so the process stays alive serving requests.
# Same behaviour on macOS and Windows — no bundled webview window.
threading.Timer(1.5, _open_browser).start()

app.run(
    host="127.0.0.1",
    port=5001,
    debug=False,
    use_reloader=False,
)
