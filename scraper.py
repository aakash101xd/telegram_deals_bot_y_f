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

# NEW: Fetching two tracking IDs
TRACKING_IDS = [
    os.getenv('AMAZON_TRACKING_ID'),
    os.getenv('AMAZON_TRACKING_ID_2')
]

SESSION_NAME = 'my_telegram_user_session'
POSTED_LINKS_FILE = 'posted_links.json'

# --- Helper Functions ---

def load_bot_memory():
    """Loads posted links and the last used tracking ID index."""
    if os.path.exists(POSTED_LINKS_FILE):
        with open(POSTED_LINKS_FILE, 'r') as f:
            try:
                data = json.load(f)
                # Handle old format vs new format
                if isinstance(data, list):
                    return set(data), 0
                return set(data.get('links', [])), data.get('last_index', 0)
            except:
                return set(), 0
    return set(), 0

def save_bot_memory(links_set, last_index):
    """Saves memory back to JSON."""
    with open(POSTED_LINKS_FILE, 'w') as f:
        json.dump({
            'links': list(links_set),
            'last_index': last_index
        }, f)

# ... (Keep find_links_in_text, get_clean_amazon_url, get_product_asin functions same as before) ...

def find_links_in_text(text):
    return re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)

def get_clean_amazon_url(url):
    match = re.search(r"(https://www\.amazon\.in/.*?/dp/[A-Z0-9]{10})", url)
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
    # Check if both IDs are present
    if not all([API_ID, API_HASH, BOT_TOKEN, CHAT_ID, TRACKING_IDS[0], TRACKING_IDS[1]]):
        print("Missing secrets!")
        return
        
    posted_links, current_idx = load_bot_memory()
    
    async with aiohttp.ClientSession() as session:
        async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
            new_links = await scan_and_process_links(client, posted_links, session)
        
        bot = Bot(token=BOT_TOKEN)
        
        for link in new_links:
            details = await fetch_product_details(session, link)
            if details:
                # MODIFIED: Logic to alternate between IDs
                active_id = TRACKING_IDS[current_idx]
                
                caption = (
                    f"🔥 <b>{html.escape(details['title'])}</b>\n\n"
                    f"💰 <b>Price:</b> {details['price']}\n\n"
                    f"🔗 <a href='{details['url']}/?tag={active_id}'>Buy Now (ID: {active_id})</a>"
                )
                
                await bot.send_message(chat_id=CHAT_ID, text=caption, parse_mode=ParseMode.HTML)
                
                # Add to posted links
                posted_links.add(link)
                
                # Toggle index: 0 becomes 1, 1 becomes 0
                current_idx = 1 - current_idx
    
    # Save both the updated links and the next index to use
    save_bot_memory(posted_links, current_idx)

if __name__ == "__main__":
    asyncio.run(main())
