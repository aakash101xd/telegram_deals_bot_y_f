import asyncio
import os
import json
import re
import html
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from telethon.sync import TelegramClient
from telegram import Bot
from telegram.constants import ParseMode

# --- Configuration ---
API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TRACKING_ID = os.getenv('AMAZON_TRACKING_ID')

SESSION_NAME = 'my_telegram_user_session'
POSTED_LINKS_FILE = 'posted_links.json'

def load_posted_links():
    if os.path.exists(POSTED_LINKS_FILE):
        with open(POSTED_LINKS_FILE, 'r') as f:
            try: return set(json.load(f))
            except: return set()
    return set()

def save_posted_links(links_set):
    with open(POSTED_LINKS_FILE, 'w') as f:
        json.dump(list(links_set), f)

def find_links_in_text(text):
    return re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

def get_clean_amazon_url(url):
    match = re.search(r"(https://www\.amazon\.in/.*?/dp/[A-Z0-9]{10})", url)
    return match.group(1) if match else None

def get_product_asin(product_url):
    match = re.search(r"/dp/([A-Z0-9]{10})", product_url)
    return match.group(1) if match else None

async def resolve_short_link(session, url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        async with session.get(url, headers=headers, timeout=10, allow_redirects=True) as response:
            return str(response.url)
    except: return None

async def scan_and_process_links(client, posted_links, session):
    new_links = set()
    time_window = datetime.utcnow() - timedelta(hours=24) 
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            try:
                async for message in client.iter_messages(dialog.entity, limit=200):
                    if message.date.replace(tzinfo=None) < time_window: break
                    if message.text:
                        for link in find_links_in_text(message.text):
                            if 'amazon' in link or 'amzn' in link:
                                res = await resolve_short_link(session, link)
                                clean = get_clean_amazon_url(res) if res else None
                                if clean and clean not in posted_links:
                                    new_links.add(clean)
            except: continue
    return list(new_links)

async def fetch_product_details(session, url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        async with session.get(url, headers=headers, timeout=20) as response:
            soup = BeautifulSoup(await response.text(), 'html.parser')
        price_tag = soup.select_one('.a-price-whole')
        price = f"₹{price_tag.text}" if price_tag else "Check Website"
        title_tag = soup.select_one('#productTitle')
        if not title_tag: return None
        return {"title": title_tag.text.strip(), "price": price, "url": url}
    except: return None

async def main():
    if not all([API_ID, API_HASH, BOT_TOKEN, CHAT_ID, TRACKING_ID]): return
    posted = load_posted_links()
    async with aiohttp.ClientSession() as session:
        async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
            new_links = await scan_and_process_links(client, posted, session)
        bot = Bot(token=BOT_TOKEN)
        for link in new_links:
            details = await fetch_product_details(session, link)
            if details:
                caption = f"🔥 <b>{html.escape(details['title'])}</b>\n\n💰 <b>Price:</b> {details['price']}\n\n🔗 <a href='{details['url']}/?tag={TRACKING_ID}'>Buy Now</a>"
                await bot.send_message(chat_id=CHAT_ID, text=caption, parse_mode=ParseMode.HTML)
                posted.add(link)
    save_posted_links(posted)

if __name__ == "__main__":
    asyncio.run(main())
