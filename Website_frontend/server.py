from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import os
import glob
import smtplib
import datetime
import re
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import sys

# app = Flask(__name__)
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))


if getattr(sys, "frozen", False):
    BASE_DIR = os.path.join(sys._MEIPASS, "Website_frontend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=BASE_DIR,
    static_url_path=""
)
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.after_request
def apply_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

# In-memory trackers for runtime state synchronization
NOTIFIED_ALERTS_DB = set()  # Prevents duplicate email spams

# ═══════════════════════════════════════════════════════════════
# SHARED DATA LOCATION
# ═══════════════════════════════════════════════════════════════
# All shared data — the weekly scrape output plus each founder's saved list —
# lives in ONE folder so the 3-4 people pointing at the same Google Drive-synced
# folder see a single source of truth instead of drifting local copies. Set
# TENDER_DATA_DIR to the shared Drive folder on each machine; it falls back to the
# app's own folder for standalone/local use. Static site files (html/js/css) still
# come from BASE_DIR (bundled in the exe) — only the data files move here.
def _resolve_data_dir():
    env = os.environ.get("TENDER_DATA_DIR", "").strip()
    if env:
        return env
    if getattr(sys, "frozen", False):
        # In a packaged app, BASE_DIR (_MEIPASS) is a temp extraction folder that
        # is wiped on every launch — saved files written there would vanish. Fall
        # back to a persistent user folder. For the shared Google Drive setup,
        # point TENDER_DATA_DIR at the synced folder instead.
        persistent = os.path.join(os.path.expanduser("~"), "TenderToolData")
        os.makedirs(persistent, exist_ok=True)
        return persistent
    return BASE_DIR


DATA_DIR = _resolve_data_dir()
LIVE_EXCEL_PATH = os.path.join(DATA_DIR, "all_tenders_pipeline.xlsx")

# ═══════════════════════════════════════════════════════════════
# SAVED TENDERS PERSISTENCE LAYER  (one file per founder)
# ═══════════════════════════════════════════════════════════════
# Google Drive has no cross-machine file locking: if two people wrote the SAME
# saved file at once, Drive would silently create a "(conflicted copy)" and drop
# one person's stars. So each founder writes ONLY their own saved_<name>.xlsx and
# never touches anyone else's — two machines can never collide. Reads MERGE every
# founder file into one shared list, and "Starred By" is derived from which files
# contain a given tender. Saved rows are snapshots of the tender at save time, so
# they survive even after the weekly scrape drops the tender from the live sheet.
SAVED_EXCEL_LOCK = threading.Lock()   # serializes this process's writes to its own file


def _founder_slug(founder_name: str) -> str:
    """Filesystem-safe token for a founder's saved file name."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", str(founder_name).strip())
    return slug.strip("_") or "unknown"


def saved_path_for(founder_name: str) -> str:
    return os.path.join(DATA_DIR, f"saved_{_founder_slug(founder_name)}.xlsx")


# The pre-split single file is named saved_tenders.xlsx, which also matches the
# saved_*.xlsx glob — exclude it so it's never mistaken for a founder named "tenders"
# (and so migration correctly sees "no per-founder files yet").
LEGACY_SAVED_NAME = "saved_tenders.xlsx"


def list_saved_files() -> list:
    """Every founder's saved file currently present in the shared folder."""
    return sorted(
        p for p in glob.glob(os.path.join(DATA_DIR, "saved_*.xlsx"))
        if os.path.basename(p) != LEGACY_SAVED_NAME
    )


def _founder_from_path(path: str) -> str:
    base = os.path.basename(path)
    if base.startswith("saved_") and base.endswith(".xlsx"):
        return base[len("saved_"):-len(".xlsx")]
    return base


def load_saved_ids() -> set:
    """Union of saved Primary Keys across ALL founder files, re-read from disk so
    stars added on another machine (and synced via Drive) are picked up. Used for
    the expiry-alert emails (team-wide watchlist), NOT for per-user star state."""
    ids = set()
    for path in list_saved_files():
        try:
            df = pd.read_excel(path)
            if "Primary Key" in df.columns:
                ids.update(df["Primary Key"].astype(str).tolist())
        except Exception as e:
            print(f"[!] Could not read {os.path.basename(path)}: {e}")
    return ids


def load_saved_ids_for(founder_name: str) -> set:
    """Saved Primary Keys for ONE founder (their file only) — powers the per-user
    star state so a founder only sees stars filled on tenders THEY saved."""
    path = saved_path_for(founder_name)
    if not os.path.exists(path):
        return set()
    try:
        df = pd.read_excel(path)
        if "Primary Key" in df.columns:
            return set(df["Primary Key"].astype(str).tolist())
    except Exception as e:
        print(f"[!] Could not read {os.path.basename(path)}: {e}")
    return set()


def save_tender_to_excel(tender_id: str, founder_name: str):
    """Append a tender row (snapshot pulled from the live scrape) to THIS founder's
    file only. No-op if the tender is already in that founder's file."""
    if not os.path.exists(LIVE_EXCEL_PATH):
        print("[!] Live Excel not found, cannot save tender.")
        return
    path = saved_path_for(founder_name)
    with SAVED_EXCEL_LOCK:
        try:
            df_live = pd.read_excel(LIVE_EXCEL_PATH).fillna("")
            df_live["Primary Key"] = df_live["Primary Key"].astype(str)

            row = df_live[df_live["Primary Key"] == tender_id].copy()
            if row.empty:
                print(f"[!] Tender {tender_id} not found in live Excel.")
                return

            if os.path.exists(path):
                df_saved = pd.read_excel(path).fillna("")
                df_saved["Primary Key"] = df_saved["Primary Key"].astype(str)
                if tender_id in df_saved["Primary Key"].values:
                    return  # already saved by this founder
                df_saved = pd.concat([df_saved, row], ignore_index=True)
            else:
                df_saved = row

            df_saved.to_excel(path, index=False)
            print(f"[✓] Tender {tender_id} saved by {founder_name} -> {os.path.basename(path)}")
        except Exception as e:
            print(f"[✕] Failed to save tender {tender_id} for {founder_name}: {e}")


def remove_tender_from_excel(tender_id: str, founder_name: str):
    """Drop a tender from THIS founder's file only. Other founders' saves of the
    same tender are untouched — so the merged view keeps showing it as theirs."""
    path = saved_path_for(founder_name)
    if not os.path.exists(path):
        return
    with SAVED_EXCEL_LOCK:
        try:
            df = pd.read_excel(path).fillna("")
            df["Primary Key"] = df["Primary Key"].astype(str)
            before = len(df)
            df = df[df["Primary Key"] != tender_id]
            if len(df) == before:
                return  # this founder hadn't saved it
            df.to_excel(path, index=False)
            print(f"[✓] Tender {tender_id} unstarred by {founder_name} -> {os.path.basename(path)}")
        except Exception as e:
            print(f"[✕] Failed to remove tender {tender_id} for {founder_name}: {e}")


def merge_saved_tenders() -> list:
    """Merge every founder file into one deduplicated list, deriving 'Starred By'
    from which files contain each tender. Returns raw pandas rows + starred set."""
    merged = {}   # tender_id -> {"row": Series, "starredBy": [names]}
    order = []
    for path in list_saved_files():
        founder = _founder_from_path(path)
        try:
            df = pd.read_excel(path).fillna("")
        except Exception as e:
            print(f"[!] Could not read {os.path.basename(path)}: {e}")
            continue
        if "Primary Key" not in df.columns:
            continue
        df["Primary Key"] = df["Primary Key"].astype(str)
        for _, row in df.iterrows():
            tid = str(row.get("Primary Key"))
            if tid not in merged:
                merged[tid] = {"row": row, "starredBy": []}
                order.append(tid)
            if founder not in merged[tid]["starredBy"]:
                merged[tid]["starredBy"].append(founder)
    return [(tid, merged[tid]["row"], merged[tid]["starredBy"]) for tid in order]


def _migrate_legacy_saved():
    """One-time, non-destructive split of an old single saved_tenders.xlsx (with a
    'Starred By' column) into per-founder files. Skips if any per-founder file
    already exists. Leaves the original file in place as a backup."""
    legacy = os.path.join(DATA_DIR, LEGACY_SAVED_NAME)
    if not os.path.exists(legacy) or list_saved_files():
        return
    try:
        df = pd.read_excel(legacy).fillna("")
        if "Primary Key" not in df.columns:
            return
        by_founder = {}
        for _, row in df.iterrows():
            names = [n.strip() for n in str(row.get("Starred By", "")).split(",") if n.strip()]
            if not names:
                names = ["unknown"]
            clean = row.drop(labels=["Starred By"], errors="ignore")
            for name in names:
                by_founder.setdefault(name, []).append(clean)
        for name, rows in by_founder.items():
            pd.DataFrame(rows).to_excel(saved_path_for(name), index=False)
        print(f"[✓] Migrated legacy saved_tenders.xlsx into {len(by_founder)} per-founder file(s).")
    except Exception as e:
        print(f"[!] Legacy saved migration skipped: {e}")


_migrate_legacy_saved()

# In-memory union, used only for the expiry-alert emails during the stream. It is
# refreshed from disk on each stream call so Drive-synced changes from other
# machines are reflected.
SAVED_TENDERS_DB = load_saved_ids()
print(f"[✓] Loaded {len(SAVED_TENDERS_DB)} saved tenders across {len(list_saved_files())} founder file(s). Data dir: {DATA_DIR}")

# ═══════════════════════════════════════════════════════════════
# GMAIL CONFIGURATION KEYS
# ═══════════════════════════════════════════════════════════════
GMAIL_USER = "your-email@gmail.com"          # 👈 Replace with your Gmail address
GMAIL_APP_PASS = "your-app-password-here"    # 👈 Replace with your 16-character Google App Password
RECEIVER_EMAIL = "your-email@gmail.com"       # 👈 Where you want to receive alerts

def send_gmail_notification(subject, html_content):
    if GMAIL_USER == "your-email@gmail.com" or GMAIL_APP_PASS == "your-app-password-here":
        print(f"[!] Notification skipped. Set up credentials to deliver email: {subject}")
        return False

    try:
        # Set up safe SMTP communication portal with Gmail
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = GMAIL_USER
        msg['To'] = RECEIVER_EMAIL

        # Inject the HTML design body
        part = MIMEText(html_content, 'html')
        msg.attach(part)

        # Connect to secure server node
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, RECEIVER_EMAIL, msg.as_string())
        server.quit()

        print(f"[✓] Notification Email dispatched successfully: {subject}")
        return True
    except Exception as e:
        print(f"[✕] SMTP Pipeline Failure encountered: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
# SYSTEM LOGIC CORE TIME INTERPRETER
# ═══════════════════════════════════════════════════════════════
def calculate_days_remaining(closing_date_str):
    try:
        # Dynamic fix: always checks against today's date instead of a hardcoded day
        anchor_date = pd.to_datetime(datetime.datetime.now().date())
        closing_date = pd.to_datetime(str(closing_date_str).split(' ')[0])
        return (closing_date - anchor_date).days
    except:
        return 999

# ═══════════════════════════════════════════════════════════════
# DATA ROUTE PORTS
# ═══════════════════════════════════════════════════════════════
@app.route('/api/sensio-stream', methods=['GET'])
def stream_excel_data():
    excel_path = LIVE_EXCEL_PATH

    print("Current working dir:", os.getcwd())
    print("Excel path:", excel_path)
    print("Exists?", os.path.exists(excel_path))
    if not os.path.exists(excel_path):
        return jsonify({"error": f"{excel_path} file not found locally", "tenders": []}), 200

    # Refresh saved-tender union from disk so expiry alerts reflect the current
    # (possibly Drive-synced) state of every founder's file.
    saved_ids_now = load_saved_ids()
    SAVED_TENDERS_DB.clear()
    SAVED_TENDERS_DB.update(saved_ids_now)

    try:
        # Read the Excel sheet using pandas
        df = pd.read_excel(excel_path)
        df = df.fillna("")

        tenders_pool = []
        for idx, row in df.iterrows():
            tender_id = str(row.get("Primary Key", f"TEN-{idx}"))
            title = row.get("Tender Title", "Untitled Tender")
            category = str(row.get("Sector", "health")).strip().lower()
            country = row.get("Country", "Global")
            opening_date = str(row.get("Opening date", "N/A"))
            closing_date = str(row.get("Closing date", "N/A"))

            raw_relevancy = row.get("Relevancy Score", 0.50)
            try:
                relevancy_score = float(raw_relevancy)
            except:
                relevancy_score = 0.50

            raw_budget = row.get("INR Budget Maximum", 0)
            try:
                budget_inr = int(re.sub(r'[^\d]', '', str(raw_budget)))
            except:
                budget_inr = 0

            description = row.get("Description", "")
            eligibility = f"Authority: {row.get('Organisation name', 'Unknown')}"
            link = row.get("Tender URL", "https://google.com")
            if isinstance(link, dict) and "text" in link:
                link = link["text"]

            print(budget_inr)

            # Format to matches frontend data.js architecture requirements
            tenders_pool.append({
                "id": tender_id,
                "title": title,
                "category": category,
                "country": country,
                "openingDate": opening_date,
                "closingDate": closing_date,
                "relevancyScore": relevancy_score / 10 if relevancy_score > 1.0 else relevancy_score,
                "budgetINR": budget_inr,
                "description": description,
                "eligibility": eligibility,
                "link": link
            })

            # ──── STREAM INTEGRATION ENGINE: MAIL THRESHOLD HOOKS ────
            days_left = calculate_days_remaining(closing_date)

            # Hook 1: High Relevancy Trigger (Checks original sheet scale where 9.0+ means 90%+)
            if relevancy_score >= 9.0 or relevancy_score == 1.0:
                alert_key = f"{tender_id}_relevancy"
                if alert_key not in NOTIFIED_ALERTS_DB:
                    display_score = f"{relevancy_score * 100:.0f}" if relevancy_score <= 1.0 else f"{relevancy_score * 10:.0f}"
                    subject = f"🔥 High Relevancy Match Found: {title}"
                    html = f"""
                    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #0d9488; border-radius: 8px; max-width:600px;">
                        <h2 style="color: #0d9488; margin-top:0;">Sensio Target Acquisition</h2>
                        <p>An exceptional procurement structure matching your operational blueprint has been scanned at <strong>{display_score}% Weight</strong>.</p>
                        <hr style="border:none; border-top:1px solid #cbd5e1; margin:16px 0;"/>
                        <p><strong>Tender ID:</strong> {tender_id}</p>
                        <p><strong>Title:</strong> {title}</p>
                        <p><strong>Sector:</strong> {category.upper()}</p>
                        <br/>
                        <a href="{link}" target="_blank" style="background: #0d9488; color: white; padding: 10px 16px; text-decoration: none; border-radius: 6px; font-weight:600; display:inline-block;">Access Tender Portal</a>
                    </div>
                    """
                    if send_gmail_notification(subject, html):
                        NOTIFIED_ALERTS_DB.add(alert_key)

            # Hook 2: Watchlist Expiry Warning Core (0 to 7 days remaining)
            if tender_id in SAVED_TENDERS_DB and 0 <= days_left <= 7:
                alert_key = f"{tender_id}_expiry"
                if alert_key not in NOTIFIED_ALERTS_DB:
                    subject = f"⚠️ Critical Timeline Warning: Watchlist Tender closes in {days_left} days!"
                    html = f"""
                    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #dc2626; border-radius: 8px; max-width:600px;">
                        <h2 style="color: #dc2626; margin-top:0;">Sensio Framework Urgent Exception</h2>
                        <p>Action is required. A saved watchlist tender pipeline is approaching its final expiration threshold.</p>
                        <hr style="border:none; border-top:1px solid #cbd5e1; margin:16px 0;"/>
                        <p><strong>Tender ID:</strong> {tender_id}</p>
                        <p><strong>Title:</strong> {title}</p>
                        <p><strong>Time Remaining:</strong> <span style="color:#dc2626; font-weight:700;">{days_left} Days Left</span></p>
                    </div>
                    """
                    if send_gmail_notification(subject, html):
                        NOTIFIED_ALERTS_DB.add(alert_key)

        return jsonify({
            "sourceFile": "Local Excel Engine (all_tenders_pipeline.xlsx)",
            "tenders": tenders_pool
        }), 200

    except Exception as e:
        return jsonify({"error": f"Internal mapping failure: {str(e)}", "tenders": []}), 500

# ═══════════════════════════════════════════════════════════════
# CROSS-ORIGIN BACKEND SYNCHRONIZATION ENDPOINT
# ═══════════════════════════════════════════════════════════════
@app.route('/api/save-tender', methods=['POST'])
def sync_saved_state():
    data = request.get_json() or {}
    tender_id = str(data.get("tenderId", ""))
    is_saved = data.get("isSaved", False)
    founder_name = str(data.get("founderName", "")).strip()

    if not tender_id:
        return jsonify({"error": "Missing parameter: tenderId"}), 400
    if not founder_name:
        return jsonify({"error": "Missing parameter: founderName"}), 400

    if is_saved:
        save_tender_to_excel(tender_id, founder_name)
    else:
        remove_tender_from_excel(tender_id, founder_name)

    # Refresh the in-memory union (used for expiry emails) in place.
    fresh = load_saved_ids()
    SAVED_TENDERS_DB.clear()
    SAVED_TENDERS_DB.update(fresh)

    return jsonify({"status": "success", "savedCount": len(SAVED_TENDERS_DB)}), 200

@app.route('/api/saved-tenders', methods=['GET'])
def get_saved_tenders():
    """Return the merged saved list across all founder files (shared view)."""
    try:
        tenders = []
        for tender_id, row, starred_by in merge_saved_tenders():
            link = row.get("Tender URL", "https://google.com")
            if isinstance(link, dict) and "text" in link:
                link = link["text"]
            raw_budget = row.get("INR Budget Maximum", 0)
            try:
                budget_inr = int(re.sub(r'[^\d]', '', str(raw_budget)))
            except:
                budget_inr = 0
            raw_relevancy = row.get("Relevancy Score", 0.50)
            try:
                relevancy_score = float(raw_relevancy)
            except:
                relevancy_score = 0.50
            tenders.append({
                "id": tender_id,
                "title": row.get("Tender Title", "Untitled Tender"),
                "category": str(row.get("Sector", "health")).strip().lower(),
                "country": row.get("Country", "Global"),
                "openingDate": str(row.get("Opening date", "N/A")),
                "closingDate": str(row.get("Closing date", "N/A")),
                "relevancyScore": relevancy_score / 10 if relevancy_score > 1.0 else relevancy_score,
                "budgetINR": budget_inr,
                "description": row.get("Description", ""),
                "eligibility": f"Authority: {row.get('Organisation name', 'Unknown')}",
                "link": link,
                "starredBy": ", ".join(starred_by),
                "saved": True,
            })
        return jsonify({"tenders": tenders}), 200
    except Exception as e:
        return jsonify({"error": str(e), "tenders": []}), 500


@app.route('/api/saved-ids', methods=['GET'])
def get_saved_ids():
    """Per-founder star state for the dashboard / All Tenders pages: a star is
    filled only for tenders the CURRENT founder saved, not ones teammates saved.
    Pass ?founder=<name>; with no founder, return empty (nothing is 'mine' yet).
    Re-read from disk each call so Drive-synced changes are reflected."""
    founder = request.args.get('founder', '').strip()
    if not founder:
        return jsonify({"savedIds": []}), 200
    return jsonify({"savedIds": list(load_saved_ids_for(founder))}), 200

from flask import send_from_directory

@app.route("/")
def dashboard():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(BASE_DIR, path)

if __name__ == '__main__':
    app.run(
        host='127.0.0.1',
        port=5001,
        debug=False,
        use_reloader=False
    )
