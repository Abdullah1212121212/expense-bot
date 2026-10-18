import os
import re
import sqlite3
import random
from datetime import datetime
from fastapi import FastAPI, Request
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Pre-filled credentials
BOT_TOKEN = "8959063928:AAEVbPxPq5085Bke0gmH-VSW3M4CuK7R15I"
CHAT_ID = "8959063928"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

app = FastAPI()
scheduler = AsyncIOScheduler()

# Database setup
conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL,
        merchant TEXT,
        timestamp TEXT
    )"""
)
conn.commit()

async def send_telegram(text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            TELEGRAM_URL,
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
        )

def extract_details(text: str):
    # Matches patterns like Rs. 450, INR 1,200.50, paid Rs 30
    amount_match = re.search(r'(?:Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)', text, re.IGNORECASE)
    if not amount_match:
        return None, None
    amount = float(amount_match.group(1).replace(",", ""))

    # Matches recipient/merchant names
    merchant_match = re.search(r'(?:to|at|vpa)\s+([A-Za-z0-9\s]+?)(?:\s+on|\.|\son|\susing|$)', text, re.IGNORECASE)
    merchant = merchant_match.group(1).strip() if merchant_match else "Unknown Merchant"
    return amount, merchant

@app.post("/api/transaction")
async def handle_transaction(request: Request):
    payload = await request.json()
    raw_text = payload.get("text", "")

    amount, merchant = extract_details(raw_text)
    if not amount:
        return {"status": "ignored"}

    cursor.execute(
        "INSERT INTO expenses (amount, merchant, timestamp) VALUES (?, ?, ?)",
        (amount, merchant, datetime.now().isoformat())
    )
    conn.commit()

    roasts = [
        f"💸 *₹{amount:,.0f} gone* to *{merchant}*.\nYour bank balance is crying in the corner.",
        f"💸 Paid *₹{amount:,.0f}* at *{merchant}*.\nDopamine secured, retirement postponed.",
        f"💸 Farewell, *₹{amount:,.0f}*.\n{merchant} thanks you for your voluntary charity."
    ]
    await send_telegram(random.choice(roasts))
    return {"status": "recorded"}

@scheduler.scheduled_job("cron", hour=23, minute=30)
async def daily_digest():
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE timestamp LIKE ?", (f"{today}%",))
    total = cursor.fetchone()[0] or 0.0

    if total == 0:
        msg = "🌙 *Daily Wrap:* ₹0 spent today!\nDid you stay asleep all day, or did your card decline?"
    elif total < 500:
        msg = f"🌙 *Daily Wrap:* ₹{total:,.0f} spent.\nSurprisingly responsible. Are you feeling okay?"
    else:
        msg = f"🌙 *Daily Wrap:* ₹{total:,.0f} vaporized today.\nCapitalism salutes your contribution."
    await send_telegram(msg)

@scheduler.scheduled_job("cron", day_of_week="sun", hour=22, minute=0)
async def weekly_digest():
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE date(timestamp) >= date('now', '-7 days')")
    total = cursor.fetchone()[0] or 0.0
    await send_telegram(f"📊 *Weekly Damage Report:*\nYou burned *₹{total:,.0f}* this week. Look at your life choices.")

@app.on_event("startup")
def start_scheduler():
    scheduler.start()
