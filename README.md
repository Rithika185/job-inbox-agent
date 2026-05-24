# AI Job Inbox Agent

An AI agent that monitors your Gmail and alerts you instantly when important job application emails arrive.

## What it does
- Checks your Gmail every 5 minutes
- Uses AI to understand email intent (not just keywords)
- Classifies emails into: OFFER, MOVING FORWARD, REJECTED, IRRELEVANT
- Fires a sound alert + Telegram message for important emails
- Ignores all noise (newsletters, job alerts, spam)

## Tech Stack
- Python
- Gmail API
- Groq AI (llama-3.3-70b)
- Telegram Bot API

## Setup
1. Clone this repo
2. Install dependencies: `pip install groq google-auth google-auth-oauthlib google-api-python-client requests`
3. Add your Gmail API `credentials.json`
4. Create `config.env` with your keys:
GROQ_API_KEY=your_key
TELEGRAM_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
5. Run: `python3 agent.py`

## Built by
Rithika K S — ML Engineer, built this to solve my own problem of missing important job emails.
