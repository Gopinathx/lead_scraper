import re
import asyncio
import requests
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from asgiref.sync import sync_to_async
from django.db import close_old_connections
from .models import Lead
import httpx


# --- Phone Normalizer Utility ---

def normalize_phone_number(phone_str: str, default_country_code: str = "91") -> str:
    """
    Cleans raw scraper strings into standard E.164 format (+919876543210).
    """
    if not phone_str or phone_str == "N/A":
        return "N/A"

    # Remove non-digit characters except leading +
    cleaned = re.sub(r"[^\d+]", "", phone_str)

    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    cleaned = cleaned.lstrip("0")

    # Handle standard 10-digit local mobile numbers
    if len(cleaned) == 10:
        return f"+{default_country_code}{cleaned}"

    # Handle 12-digit numbers starting with country code
    if len(cleaned) == 12 and cleaned.startswith(default_country_code):
        return f"+{cleaned}"

    # Return cleaned string with + if valid digits, otherwise N/A
    return f"+{cleaned}" if len(cleaned) >= 10 else "N/A"


# --- Email Extraction Utility ---

async def extract_emails_async(url: str) -> str:
    if not url or url == "N/A" or not url.startswith("http"):
        return "N/A"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    found_emails = set()
    subpaths = ["", "/contact", "/about", "/contact-us"]

    try:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return "N/A"

    async with httpx.AsyncClient(headers=headers, timeout=5.0, follow_redirects=True) as client:
        for path in subpaths:
            try:
                target = urljoin(base, path)
                resp = await client.get(target)
                if resp.status_code == 200:
                    matches = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", resp.text)
                    clean = [
                        e.lower() for e in matches 
                        if not any(e.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".css", ".js", ".svg", ".webp", ".gif"])
                    ]
                    found_emails.update(clean)
                    if found_emails:
                        break
            except Exception:
                continue

    return ", ".join(sorted(list(found_emails))[:3]) if found_emails else "N/A"


# --- Async Helpers for Django ORM ---

@sync_to_async(thread_sensitive=False)
def clear_old_leads():
    close_old_connections()
    Lead.objects.all().delete()

@sync_to_async(thread_sensitive=False)
def save_lead_to_db(name, phone, website, emails, address):
    close_old_connections()
    return Lead.objects.create(
        name=name,
        phone=phone,
        website=website,
        emails=emails,
        address=address
    )


# --- Main Async Scraper ---

async def async_stream_gmaps_scraper(q_out, search_query, max_results=5):
    max_results = int(max_results)

    await q_out.put("data: 🧹 Clearing previous session data...\n\n")
    await clear_old_leads()

    await q_out.put("data: 🚀 Launching browser scraper...\n\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = await context.new_page()

        target_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        
        try:
            await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            await q_out.put(f"data: ⚠️ Page load warning: {str(e)}\n\n")

        await asyncio.sleep(3)

        feed_selector = 'div[role="feed"]'
        try:
            await page.wait_for_selector(feed_selector, timeout=10000)
        except Exception:
            pass

        collected = set()
        scroll_attempts = 0
        max_scroll_attempts = max_results * 4

        while len(collected) < max_results and scroll_attempts < max_scroll_attempts:
            scroll_attempts += 1
            
            elements = await page.query_selector_all('a[href*="/maps/place/"]')
            for el in elements:
                href = await el.get_attribute('href')
                if href and '/maps/place/' in href:
                    collected.add(href)
                if len(collected) >= max_results:
                    break

            feed = await page.query_selector(feed_selector)
            if feed:
                await feed.evaluate('el => el.scrollBy(0, 1000)')
            else:
                await page.mouse.wheel(0, 1000)

            await asyncio.sleep(1.5)

        target_links = list(collected)[:max_results]

        if not target_links:
            await q_out.put("data: ⚠️ No results found on Google Maps.\n\n")
            await browser.close()
            return

        await q_out.put(f"data: 🔍 Extracting {len(target_links)} locations...\n\n")

        count = 0
        for href in target_links:
            raw_phone, website, address, emails = "N/A", "N/A", "N/A", "N/A"

            try:
                await page.goto(href, timeout=15000, wait_until="domcontentloaded")
                await asyncio.sleep(2)

                # Name
                title_el = await page.query_selector('h1')
                name = (await title_el.inner_text()).strip() if title_el else "Unknown Location"

                await q_out.put(f"data: 📍 Processing ({count + 1}/{len(target_links)}): {name}\n\n")

                # Phone extraction
                phone_el = await page.query_selector('button[data-tooltip*="phone"], button[aria-label*="Phone"], button[data-item-id*="phone"]')
                if phone_el:
                    aria_label = await phone_el.get_attribute('aria-label') or ""
                    raw_phone = aria_label.replace("Phone: ", "").replace("Phone", "").strip()
                    if not raw_phone:
                        raw_phone = (await phone_el.inner_text()).strip()

                # Normalize Phone Number
                normalized_phone = normalize_phone_number(raw_phone, default_country_code="91")

                # Website extraction
                website_el = await page.query_selector('a[data-item-id="authority"], a[data-tooltip*="website"], a[aria-label*="Website"]')
                if website_el:
                    raw_website = await website_el.get_attribute('href')
                    if raw_website and raw_website.startswith('http'):
                        website = raw_website

                # Address extraction
                addr_el = await page.query_selector('button[data-item-id="address"], button[data-tooltip*="address"], button[aria-label*="Address"]')
                if addr_el:
                    aria_label = await addr_el.get_attribute('aria-label') or ""
                    address = aria_label.replace("Address: ", "").replace("Address", "").strip()

                # Emails extraction
                if website != "N/A":
                    emails = await extract_emails_async(website)

                # Save Lead with normalized phone
                lead = await save_lead_to_db(
                    name=name,
                    phone=normalized_phone,
                    website=website,
                    emails=emails,
                    address=address
                )
                
                count += 1
                await q_out.put(f"data: ✅ Saved ({count}/{len(target_links)}): {lead.name}\n\n")

                await asyncio.sleep(0.05)

            except Exception as err:
                await q_out.put(f"data: ⚠️ Error processing entry: {str(err)}\n\n")
                continue

        await browser.close()
        await q_out.put("data: 🎉 Scraping Complete!\n\n")


# import re
# import asyncio
# import requests
# from urllib.parse import urljoin, urlparse
# from playwright.async_api import async_playwright
# from asgiref.sync import sync_to_async
# from django.db import close_old_connections
# from .models import Lead


# # --- Async Helpers for Django ORM ---

# @sync_to_async
# def clear_old_leads():
#     close_old_connections()
#     Lead.objects.all().delete()

# @sync_to_async
# def save_lead_to_db(name, phone, website, emails, address):
#     close_old_connections()
#     return Lead.objects.create(
#         name=name,
#         phone=phone,
#         website=website,
#         emails=emails,
#         address=address
#     )


# # --- Utility Functions ---

# def extract_emails(url):
#     if not url or url == "N/A" or not url.startswith("http"):
#         return "N/A"

#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#     }
#     found_emails = set()
#     subpaths = ["", "/contact", "/about", "/contact-us"]

#     try:
#         parsed = urlparse(url)
#         base = f"{parsed.scheme}://{parsed.netloc}"
#     except Exception:
#         return "N/A"

#     for path in subpaths:
#         try:
#             target = urljoin(base, path)
#             resp = requests.get(target, headers=headers, timeout=4)
#             if resp.status_code == 200:
#                 matches = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", resp.text)
#                 clean = [
#                     e.lower() for e in matches 
#                     if not any(e.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".css", ".js", ".svg", ".webp", ".gif"])
#                 ]
#                 found_emails.update(clean)
#                 if found_emails:
#                     break
#         except Exception:
#             continue

#     return ", ".join(sorted(list(found_emails))[:3]) if found_emails else "N/A"


# # --- Main Async Scraper ---

# async def async_stream_gmaps_scraper(q_out, search_query, max_results=5):
#     # Ensure max_results is properly cast to int
#     max_results = int(max_results)

#     q_out.put("data: 🧹 Clearing previous session data...\n\n")
#     await clear_old_leads()

#     q_out.put("data: 🚀 Launching browser scraper...\n\n")

#     async with async_playwright() as p:
#         browser = await p.chromium.launch(
#             headless=False,
#             args=["--no-sandbox", "--disable-setuid-sandbox"]
#         )
#         context = await browser.new_context(
#             user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#             locale="en-US"
#         )
#         page = await context.new_page()

#         target_url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        
#         try:
#             await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
#         except Exception as e:
#             q_out.put(f"data: ⚠️ Page load warning: {str(e)}\n\n")

#         await asyncio.sleep(3)

#         # Target the scrollable results sidebar container specifically
#         feed_selector = 'div[role="feed"]'
#         try:
#             await page.wait_for_selector(feed_selector, timeout=10000)
#         except Exception:
#             pass

#         collected = set()
#         scroll_attempts = 0
#         max_scroll_attempts = max_results * 4  # Scale scroll attempts dynamically with user input

#         # Dynamic Scrolling Loop to honor user input max_results
#         while len(collected) < max_results and scroll_attempts < max_scroll_attempts:
#             scroll_attempts += 1
            
#             elements = await page.query_selector_all('a[href*="/maps/place/"]')
#             for el in elements:
#                 href = await el.get_attribute('href')
#                 if href and '/maps/place/' in href:
#                     collected.add(href)
#                 if len(collected) >= max_results:
#                     break

#             # Scroll the internal feed container directly
#             feed = await page.query_selector(feed_selector)
#             if feed:
#                 await feed.evaluate('el => el.scrollBy(0, 1000)')
#             else:
#                 await page.mouse.wheel(0, 1000)

#             await asyncio.sleep(1.5)

#         target_links = list(collected)[:max_results]

#         if not target_links:
#             q_out.put("data: ⚠️ No results found on Google Maps.\n\n")
#             await browser.close()
#             return

#         q_out.put(f"data: 🔍 Extracting {len(target_links)} locations...\n\n")

#         count = 0
#         for href in target_links:
#             phone, website, address, emails = "N/A", "N/A", "N/A", "N/A"

#             try:
#                 await page.goto(href, timeout=30000, wait_until="domcontentloaded")
#                 await asyncio.sleep(2)

#                 # Extract Name
#                 title_el = await page.query_selector('h1')
#                 name = (await title_el.inner_text()).strip() if title_el else "Unknown Location"

#                 q_out.put(f"data: 📍 Processing ({count + 1}/{len(target_links)}): {name}\n\n")

#                 # Extract Phone
#                 phone_el = await page.query_selector('button[data-tooltip*="phone"], button[aria-label*="Phone"], button[data-item-id*="phone"]')
#                 if phone_el:
#                     aria_label = await phone_el.get_attribute('aria-label') or ""
#                     phone = aria_label.replace("Phone: ", "").replace("Phone", "").strip()
#                     if not phone:
#                         phone = (await phone_el.inner_text()).strip()

#                 # Extract Website (Updated Google Maps Selectors)
#                 website_el = await page.query_selector('a[data-item-id="authority"], a[data-tooltip*="website"], a[aria-label*="Website"]')
#                 if website_el:
#                     raw_website = await website_el.get_attribute('href')
#                     if raw_website and raw_website.startswith('http'):
#                         website = raw_website

#                 # Extract Address
#                 addr_el = await page.query_selector('button[data-item-id="address"], button[data-tooltip*="address"], button[aria-label*="Address"]')
#                 if addr_el:
#                     aria_label = await addr_el.get_attribute('aria-label') or ""
#                     address = aria_label.replace("Address: ", "").replace("Address", "").strip()

#                 # Extract Emails from Website
#                 if website != "N/A":
#                     emails = await asyncio.to_thread(extract_emails, website)

#                 # Save Lead
#                 lead = await save_lead_to_db(
#                     name=name,
#                     phone=phone,
#                     website=website,
#                     emails=emails,
#                     address=address
#                 )
                
#                 count += 1
#                 q_out.put(f"data: ✅ Saved ({count}/{len(target_links)}): {lead.name}\n\n")

#             except Exception as err:
#                 q_out.put(f"data: ⚠️ Error processing entry: {str(err)}\n\n")
#                 continue

#         await browser.close()
#         q_out.put("data: 🎉 Scraping Complete!\n\n")