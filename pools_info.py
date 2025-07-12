import os
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from ics import Calendar, Event
import pytz

from openai import OpenAI

# === Constants ===
tz = pytz.timezone("Europe/Berlin")
POOL_HOMEPAGE = "https://dresdner-baeder.de/hallenbaeder/"
os.environ["OPENAI_MODEL_NAME"] = "gpt-4"
api_key = os.environ.get("OPENAI_API_KEY")
# The OpenAI library will pick this up automatically if set

# === Scraper ===
def get_pool_links():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(POOL_HOMEPAGE, timeout=60000)
        page.wait_for_timeout(3000)  # Wait for JS to load
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    links = soup.find_all("a", href=True)
    target_links = {}
    for link in links:
        text = link.get_text(strip=True).lower().replace('\u00ad', '')  # Remove soft hyphens
        href = link['href']
        # Only consider hallenbaeder pages
        if "georg-arnhold-bad" in text and "hallenbaeder" in href:
            target_links["Georg-Arnhold-Bad"] = href
        elif "schwimmsportkomplex" in text and "hallenbaeder" in href:
            target_links["Schwimmsportkomplex"] = href
    return target_links

def extract_text_from_url(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        html = page.content()
        browser.close()
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n")

# === Tool ===
def parse_swim_hours(pool_name: str, text: str) -> str:
    client = OpenAI()
    prompt = f"""
You are an expert in understanding German pool schedules. From this webpage text of {pool_name}, extract the opening hours for:
- Fr\u00fchschwimmen (early swimming)
- Lehrschwimmbecken (training pool)
- \u00d6ffentliches Schwimmen (general swimming)
Some pools may just show \"\u00d6ffnungszeiten\" meaning general public swim. Return them grouped by category like:

Fr\u00fchschwimmen:
Montag – Freitag: 06:30 – 08:00 Uhr

Lehrschwimmbecken:
Samstag: 12:00 – 15:00 Uhr

\u00d6ffentliches Schwimmen:
Montag – Sonntag: 10:00 – 20:00 Uhr

Text:
{text[:4000]}
"""
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL_NAME"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response.choices[0].message.content.strip()

# === Calendar ===
def expand_weekdays(german_str):
    map_day = {
        "Montag": "Monday", "Dienstag": "Tuesday", "Mittwoch": "Wednesday",
        "Donnerstag": "Thursday", "Freitag": "Friday", "Samstag": "Saturday", "Sonntag": "Sunday"
    }
    result = []
    parts = german_str.replace("–", "-").split("-")
    all_days = list(map_day.keys())
    if len(parts) == 2 and parts[0].strip() in map_day:
        start, end = parts[0].strip(), parts[1].strip()
        start_idx = all_days.index(start)
        end_idx = all_days.index(end)
        for d in all_days[start_idx:end_idx+1]:
            result.append(map_day[d])
    elif parts[0].strip() in map_day:
        result.append(map_day[parts[0].strip()])
    return result

def create_calendar(name_to_schedule: dict, filename="pool_schedule.ics"):
    calendar = Calendar()
    today = datetime.now(tz).date()
    weekday_map = {
        "Montag": "Monday", "Dienstag": "Tuesday", "Mittwoch": "Wednesday",
        "Donnerstag": "Thursday", "Freitag": "Friday", "Samstag": "Saturday", "Sonntag": "Sunday",
        "Täglich": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    }
    for pool, content in name_to_schedule.items():
        for section in ["Frühschwimmen", "Lehrschwimmbecken", "Öffentliches Schwimmen"]:
            matches = re.findall(rf"{section}:\s*(.*?)(?=\n\S|$)", content, re.DOTALL)
            if not matches:
                continue
            schedule_lines = matches[0].strip().split("\n")
            for line in schedule_lines:
                # Remove parenthetical notes
                line = re.sub(r"\(.*?\)", "", line)
                # Split days and times
                day_part, *time_parts = line.split(":")
                day_part = day_part.strip()
                if not time_parts:
                    continue
                time_str = ":".join(time_parts).strip()
                # Handle multiple days
                days = []
                for d in day_part.split(","):
                    d = d.strip()
                    if d in weekday_map:
                        if isinstance(weekday_map[d], list):
                            days.extend(weekday_map[d])
                        else:
                            days.append(weekday_map[d])
                # Handle multiple time ranges
                for time_range in time_str.split(","):
                    time_range = time_range.strip()
                    m = re.match(r"(\d{1,2}[:.]\d{2})\s*[–-]\s*(\d{1,2}[:.]\d{2})", time_range)
                    if not m:
                        continue
                    start, end = m.groups()
                    for i in range(7):
                        day = today + timedelta(days=i)
                        if day.strftime("%A") in days:
                            begin_dt = tz.localize(datetime.combine(day, datetime.strptime(start, "%H:%M").time()))
                            end_dt = tz.localize(datetime.combine(day, datetime.strptime(end, "%H:%M").time()))
                            event = Event()
                            event.name = f"{section} ({pool})"
                            event.begin = begin_dt
                            event.end = end_dt
                            event.location = pool
                            calendar.events.add(event)
    with open(filename, "w") as f:
        f.writelines(calendar)
    print(f"✅ Calendar saved as {filename}")

# === Main Execution ===
def main():
    pool_links = get_pool_links()
    print("🔗 Found pool links:", pool_links)
    name_to_schedule = {}
    for pool_name, url in pool_links.items():
        print(f"\n🌐 Scraping {pool_name} @ {url}")
        text = extract_text_from_url(url)
        # Call the function directly
        result = parse_swim_hours(pool_name, text)
        name_to_schedule[pool_name] = result
        print(f"\n--- LLM output for {pool_name} ---\n{result}\n")

    create_calendar(name_to_schedule)

if __name__ == "__main__":
    main()
