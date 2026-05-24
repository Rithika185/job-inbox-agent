import os
import base64
import json
import time
import subprocess
import requests
from datetime import datetime

# Gmail API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Groq AI
from groq import Groq

# ─────────────────────────────────────────
# 1. LOAD SETTINGS FROM config.env
# ─────────────────────────────────────────

def load_config():
    config = {}
    if os.path.exists("config.env"):
        with open("config.env") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
    return config

config = load_config()

GROQ_API_KEY     = config.get("GROQ_API_KEY", "")
TELEGRAM_TOKEN   = config.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = config.get("TELEGRAM_CHAT_ID", "")
CHECK_EVERY      = 300  # seconds (5 minutes)

# ─────────────────────────────────────────
# 2. FEW-SHOT EXAMPLES
# ─────────────────────────────────────────

EXAMPLES = """
EXAMPLE 1 - MOVING_FORWARD:
Email: "Hi, we were impressed with your profile and would love for you to complete a technical assessment. Please find the link below..."
Label: MOVING_FORWARD | Company invited candidate to complete assessment

EXAMPLE 2 - REJECTED:
Email: "Thank you for taking the time to interview with us. After careful consideration, we have decided to move forward with other candidates."
Label: REJECTED | Company decided to pursue other candidates

EXAMPLE 3 - OFFER:
Email: "Congratulations! We are thrilled to extend you an offer to join our team as a Machine Learning Engineer. Please find the offer letter attached."
Label: OFFER | Job offer extended

EXAMPLE 4 - MOVING_FORWARD:
Email: "Excited to continue the conversation! Could you please schedule a 30 minute call with our hiring manager next week?"
Label: MOVING_FORWARD | Interview call scheduling requested

EXAMPLE 5 - REJECTED:
Email: "We regret to inform you that we will not be moving forward with your application at this time. We wish you the best in your search."
Label: REJECTED | Application not moving forward

EXAMPLE 6 - IRRELEVANT:
Email: "You have a new job alert: 50 new Machine Learning jobs in your area. Click here to view them."
Label: IRRELEVANT | Job alert newsletter, not application update
"""

# ─────────────────────────────────────────
# 3. GMAIL SETUP
# ─────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify"
]

def get_gmail_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# ─────────────────────────────────────────
# 4. READ EMAILS
# ─────────────────────────────────────────

def get_unread_emails(service):
    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=10
    ).execute()

    messages = results.get("messages", [])
    emails   = []

    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = full["payload"]["headers"]
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
        sender  = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")
        date    = next((h["value"] for h in headers if h["name"] == "Date"), "")

        body = ""
        payload = full["payload"]
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break
        elif "body" in payload:
            data = payload["body"].get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        emails.append({
            "id":      msg["id"],
            "subject": subject,
            "sender":  sender,
            "date":    date,
            "body":    body[:1000]
        })

    return emails

# ─────────────────────────────────────────
# 5. CLASSIFY EMAIL WITH GROQ
# ─────────────────────────────────────────

def classify_email(email):
    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""You are an AI that classifies job application emails.
Use the examples below to understand the patterns, then classify the new email.

{EXAMPLES}

Now classify this new email:
From: {email['sender']}
Subject: {email['subject']}
Body: {email['body']}

Reply in EXACTLY this format (one line only):
CATEGORY | COMPANY_NAME | one sentence summary

Categories to use: OFFER, MOVING_FORWARD, REJECTED, IRRELEVANT

Example reply:
MOVING_FORWARD | Google | Invited to schedule a technical interview"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=100
    )

    return response.choices[0].message.content.strip()

# ─────────────────────────────────────────
# 6. SEND TELEGRAM MESSAGE
# ─────────────────────────────────────────

def send_telegram(label, company, summary):
    try:
        msg = (
            "JOB ALERT\n"
            f"{label}\n\n"
            f"Company: {company}\n"
            f"Summary: {summary}\n"
            f"Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.get(url, params={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
        print("   Telegram message sent!")
    except Exception as e:
        print(f"   Telegram error: {e}")

# ─────────────────────────────────────────
# 7. ALERT — terminal + sound + telegram
# ─────────────────────────────────────────

def send_alert(category, company, summary):
    label_map = {
        "OFFER":          "OFFER RECEIVED",
        "MOVING_FORWARD": "MOVING FORWARD",
        "REJECTED":       "REJECTED",
    }
    label = label_map.get(category, "NEW EMAIL")

    print("\n" + "="*60)
    print(f"  *** {label} ***")
    print(f"  Company : {company}")
    print(f"  Summary : {summary}")
    print(f"  Time    : {datetime.now().strftime('%H:%M:%S')}")
    print("="*60 + "\n")

    # Mac sound alert
    for _ in range(3):
        os.system("afplay /System/Library/Sounds/Glass.aiff")
        time.sleep(0.5)

    # Telegram alert
    send_telegram(label, company, summary)

# ─────────────────────────────────────────
# 8. TRACK SEEN EMAILS
# ─────────────────────────────────────────

def load_seen_ids():
    if os.path.exists("seen_emails.json"):
        with open("seen_emails.json") as f:
            return set(json.load(f))
    return set()

def save_seen_ids(seen_ids):
    with open("seen_emails.json", "w") as f:
        json.dump(list(seen_ids), f)

# ─────────────────────────────────────────
# 9. MAIN LOOP
# ─────────────────────────────────────────

def main():
    print("="*60)
    print("   Job Inbox Agent - Started!")
    print(f"   Checking every {CHECK_EVERY // 60} minutes")
    print("="*60 + "\n")

    service  = get_gmail_service()
    seen_ids = load_seen_ids()

    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking inbox...")

        try:
            emails    = get_unread_emails(service)
            new_count = 0

            for email in emails:
                if email["id"] in seen_ids:
                    continue

                new_count += 1
                print(f"   From    : {email['sender'][:60]}")
                print(f"   Subject : {email['subject'][:60]}")

                result = classify_email(email)
                print(f"   Result  : {result}")

                parts = result.split("|")
                if len(parts) >= 3:
                    category = parts[0].strip().upper()
                    company  = parts[1].strip()
                    summary  = parts[2].strip()

                    if category in ["OFFER", "MOVING_FORWARD", "REJECTED"]:
                        send_alert(category, company, summary)
                    else:
                        print("   -> Irrelevant, skipping alert\n")

                seen_ids.add(email["id"])
                time.sleep(2)

            if new_count == 0:
                print("   No new emails.\n")

            save_seen_ids(seen_ids)

        except Exception as e:
            print(f"   Error: {e}\n")

        print(f"   Sleeping {CHECK_EVERY // 60} mins...\n")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
