from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import os
import smtplib
import datetime
import re
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
# SAVED TENDERS PERSISTENCE LAYER
# ═══════════════════════════════════════════════════════════════
SAVED_EXCEL_PATH = os.path.join(BASE_DIR, "saved_tenders.xlsx")


def load_saved_ids() -> set:
    """Load saved tender Primary Keys from Excel on startup."""
    if not os.path.exists(SAVED_EXCEL_PATH):
        return set()
    try:
        df = pd.read_excel(SAVED_EXCEL_PATH)
        if "Primary Key" in df.columns:
            return set(df["Primary Key"].astype(str).tolist())
    except Exception as e:
        print(f"[!] Could not load saved_tenders.xlsx: {e}")
    return set()


# def save_tender_to_excel(tender_id: str):
#     """Append a tender row (pulled from live Excel) to saved_tenders.xlsx."""
#     live_excel = os.path.join(BASE_DIR, "all_tenders_pipeline.xlsx")
#     if not os.path.exists(live_excel):
#         print("[!] Live Excel not found, cannot save tender.")
#         return

#     try:
#         df_live = pd.read_excel(live_excel)
#         df_live = df_live.fillna("")
#         df_live["Primary Key"] = df_live["Primary Key"].astype(str)

#         # Find the matching row in live data
#         row = df_live[df_live["Primary Key"] == tender_id]
#         if row.empty:
#             print(f"[!] Tender {tender_id} not found in live Excel.")
#             return

#         if os.path.exists(SAVED_EXCEL_PATH):
#             df_saved = pd.read_excel(SAVED_EXCEL_PATH)
#             df_saved = df_saved.fillna("")
#             df_saved["Primary Key"] = df_saved["Primary Key"].astype(str)
#             # Skip if already saved (deduplicate)
#             if tender_id in df_saved["Primary Key"].values:
#                 return
#             df_merged = pd.concat([df_saved, row], ignore_index=True)
#         else:
#             df_merged = row.copy()

#         df_merged.to_excel(SAVED_EXCEL_PATH, index=False)
#         print(f"[✓] Tender {tender_id} saved to saved_tenders.xlsx")

#     except Exception as e:
#         print(f"[✕] Failed to save tender {tender_id}: {e}")


# def remove_tender_from_excel(tender_id: str):
#     """Remove a tender row from saved_tenders.xlsx."""
#     if not os.path.exists(SAVED_EXCEL_PATH):
#         return
#     try:
#         df = pd.read_excel(SAVED_EXCEL_PATH)
#         df["Primary Key"] = df["Primary Key"].astype(str)
#         df = df[df["Primary Key"] != tender_id]
#         df.to_excel(SAVED_EXCEL_PATH, index=False)
#         print(f"[✓] Tender {tender_id} removed from saved_tenders.xlsx")
#     except Exception as e:
#         print(f"[✕] Failed to remove tender {tender_id}: {e}")

import threading
SAVED_EXCEL_LOCK = threading.Lock()   # serializes all reads/writes to saved_tenders.xlsx

def save_tender_to_excel(tender_id: str, founder_name: str):
    """Append/update a tender row in saved_tenders.xlsx, tracking who starred it."""
    live_excel = os.path.join(BASE_DIR, "all_tenders_pipeline.xlsx")
    if not os.path.exists(live_excel):
        print("[!] Live Excel not found, cannot save tender.")
        return

    with SAVED_EXCEL_LOCK:
        try:
            df_live = pd.read_excel(live_excel)
            df_live = df_live.fillna("")
            df_live["Primary Key"] = df_live["Primary Key"].astype(str)

            row = df_live[df_live["Primary Key"] == tender_id].copy()
            if row.empty:
                print(f"[!] Tender {tender_id} not found in live Excel.")
                return

            if os.path.exists(SAVED_EXCEL_PATH):
                df_saved = pd.read_excel(SAVED_EXCEL_PATH)
                df_saved = df_saved.fillna("")
                df_saved["Primary Key"] = df_saved["Primary Key"].astype(str)
                if "Starred By" not in df_saved.columns:
                    df_saved["Starred By"] = ""
            else:
                df_saved = pd.DataFrame(columns=list(row.columns) + ["Starred By"])

            existing = df_saved[df_saved["Primary Key"] == tender_id]

            if not existing.empty:
                idx = existing.index[0]
                current_names = [n.strip() for n in str(df_saved.at[idx, "Starred By"]).split(",") if n.strip()]
                if founder_name not in current_names:
                    current_names.append(founder_name)
                df_saved.at[idx, "Starred By"] = ", ".join(current_names)
            else:
                row["Starred By"] = founder_name
                df_saved = pd.concat([df_saved, row], ignore_index=True)

            df_saved.to_excel(SAVED_EXCEL_PATH, index=False)
            print(f"[✓] Tender {tender_id} saved by {founder_name} to saved_tenders.xlsx")

        except Exception as e:
            print(f"[✕] Failed to save tender {tender_id}: {e}")


def remove_tender_from_excel(tender_id: str, founder_name: str):
    """Remove one founder's name from a tender's 'Starred By' list.
    Only drops the row entirely once nobody has it starred anymore."""
    if not os.path.exists(SAVED_EXCEL_PATH):
        return
    with SAVED_EXCEL_LOCK:
        try:
            df = pd.read_excel(SAVED_EXCEL_PATH)
            df = df.fillna("")
            df["Primary Key"] = df["Primary Key"].astype(str)
            if "Starred By" not in df.columns:
                df["Starred By"] = ""

            match = df[df["Primary Key"] == tender_id]
            if match.empty:
                return
            idx = match.index[0]
            current_names = [n.strip() for n in str(df.at[idx, "Starred By"]).split(",") if n.strip()]
            if founder_name in current_names:
                current_names.remove(founder_name)

            if current_names:
                df.at[idx, "Starred By"] = ", ".join(current_names)
            else:
                df = df.drop(index=idx)

            df.to_excel(SAVED_EXCEL_PATH, index=False)
            print(f"[✓] Tender {tender_id} unstarred by {founder_name} (remaining: {current_names or 'none — row removed'})")
        except Exception as e:
            print(f"[✕] Failed to remove tender {tender_id}: {e}")

# Load saved IDs into memory on startup
SAVED_TENDERS_DB = load_saved_ids()
print(f"[✓] Loaded {len(SAVED_TENDERS_DB)} saved tenders from disk.")

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
        anchor_date = pd.to_datetime(datetime.now().date())
        closing_date = pd.to_datetime(str(closing_date_str).split(' ')[0])
        return (closing_date - anchor_date).days
    except:
        return 999

# ═══════════════════════════════════════════════════════════════
# DATA ROUTE PORTS
# ═══════════════════════════════════════════════════════════════
@app.route('/api/sensio-stream', methods=['GET'])
def stream_excel_data():
    excel_path = os.path.join(BASE_DIR, "all_tenders_pipeline.xlsx")
    
    print("Current working dir:", os.getcwd())
    print("Excel path:", excel_path)
    print("Exists?", os.path.exists(excel_path))
    if not os.path.exists(excel_path):
        return jsonify({"error": f"{excel_path} file not found locally", "tenders": []}), 200
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
# @app.route('/api/save-tender', methods=['POST'])
# def sync_saved_state():
#     data = request.get_json() or {}
#     tender_id = str(data.get("tenderId", ""))
#     is_saved = data.get("isSaved", False)

#     if not tender_id:
#         return jsonify({"error": "Missing parameter: tenderId"}), 400

#     if is_saved:
#         SAVED_TENDERS_DB.add(tender_id)
#         save_tender_to_excel(tender_id)       # ← persist to Excel
#     else:
#         SAVED_TENDERS_DB.discard(tender_id)
#         remove_tender_from_excel(tender_id)   # ← remove from Excel

#     return jsonify({"status": "success", "savedCount": len(SAVED_TENDERS_DB)}), 200
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
        SAVED_TENDERS_DB.add(tender_id)
        save_tender_to_excel(tender_id, founder_name)
    else:
        remove_tender_from_excel(tender_id, founder_name)
        # Row might still be saved by a different founder — recheck before
        # dropping it from the in-memory set used for expiry-alert emails.
        still_saved = load_saved_ids()
        if tender_id in still_saved:
            SAVED_TENDERS_DB.add(tender_id)
        else:
            SAVED_TENDERS_DB.discard(tender_id)

    return jsonify({"status": "success", "savedCount": len(SAVED_TENDERS_DB)}), 200

@app.route('/api/saved-tenders', methods=['GET'])
def get_saved_tenders():
    """Return the full list of saved tenders from saved_tenders.xlsx."""
    if not os.path.exists(SAVED_EXCEL_PATH):
        return jsonify({"tenders": []}), 200
    try:
        df = pd.read_excel(SAVED_EXCEL_PATH)
        df = df.fillna("")
        tenders = []
        for idx, row in df.iterrows():
            tender_id = str(row.get("Primary Key", f"TEN-{idx}"))
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
                "starredBy": row.get("Starred By", ""),
                "saved": True,
            })
        return jsonify({"tenders": tenders}), 200
    except Exception as e:
        return jsonify({"error": str(e), "tenders": []}), 500


@app.route('/api/saved-ids', methods=['GET'])
def get_saved_ids():
    """Return just the set of saved Primary Keys — used on frontend load to restore star state."""
    return jsonify({"savedIds": list(SAVED_TENDERS_DB)}), 200
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