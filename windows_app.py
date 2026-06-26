import threading
import time
import webbrowser

from Website_frontend.server import app


def run_flask():
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False,
        use_reloader=False
    )


threading.Thread(
    target=run_flask,
    daemon=True
).start()

time.sleep(2)

webbrowser.open("http://127.0.0.1:5001")

# Keep the EXE alive while Flask is running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass