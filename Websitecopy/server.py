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
    BASE_DIR = os.path.join(sys._MEIPASS, "Website")
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
SAVED_TENDERS_DB = set()
NOTIFIED_ALERTS_DB = set() # Prevents duplicate email spams

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
    # excel_path = "live_tenders_pipeline.xlsx"
    # excel_path = "../Scraper/live_tenders_pipeline.xlsx"

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    excel_path = os.path.join(BASE_DIR, "live_tenders_pipeline.xlsx")
    
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
            "sourceFile": "Local Excel Engine (live_tenders_pipeline.xlsx)",
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

    if not tender_id:
        return jsonify({"error": "Missing parameter: tenderId"}), 400

    if is_saved:
        SAVED_TENDERS_DB.add(tender_id)
    else:
        SAVED_TENDERS_DB.discard(tender_id)

    return jsonify({"status": "success", "savedCount": len(SAVED_TENDERS_DB)}), 200
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
