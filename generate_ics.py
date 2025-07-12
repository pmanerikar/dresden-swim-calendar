from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz

URL = "https://dresdner-baeder.de/hallenbaeder/schwimmsportkomplex-freiberger-platz/"
tz = pytz.timezone("Europe/Berlin")

# German weekday mapping
weekday_map = {
    "Montag": 0, "Dienstag": 1, "Mittwoch": 2, "Donnerstag": 3, "Freitag": 4,
    "Samstag": 5, "Sonntag": 6
}

# Keywords to detect types of swim sessions
SWIM_KEYWORDS = {
    "früh": "Frühschwimmen",
    "öffentlich": "Öffentliches Schwimmen",
    "lehr": "Lehrschwimmbecken"
}

def extract_text_blocks():
    """Get all text from accordion or structured blocks."""
    response = requests.get(URL)
    soup = BeautifulSoup(response.content, "html.parser")
    
    content_blocks = soup.find_all(['section', 'div', 'article'], recursive=True)
    all_text = "\n".join([block.get_text(separator="\n", strip=True) for block in content_blocks])
    
    return all_text

def extract_events_from_text(text):
    """Extract swim events using regex and keyword matching."""
    events = []
    lines = text.splitlines()
    current_category = None
    for line in lines:
        # Detect section header
        for key in SWIM_KEYWORDS:
            if key in line.lower():
                current_category = SWIM_KEYWORDS[key]
                break

        # Match weekday and time like "Montag: 06:00–08:00"
        match = re.search(r'(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag)[\s:]+(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})', line)
        if match and current_category:
            weekday_str, start_time, end_time = match.groups()
            weekday_num = weekday_map[weekday_str]
            events.append({
                "title": current_category,
                "weekday": weekday_num,
                "start": start_time,
                "end": end_time
            })
    return events

def extract_events_from_table():
    """Extract swim events from the baeder__table on the website."""
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(URL)
    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="baeder__table")
    print("---- Table Found ----")
    print("Yes" if table else "No")
    events = []
    if not table:
        print("No schedule table found.")
        return events

    for row in table.find_all("tr"):
        cols = row.find_all("td")
        print("---- Row Columns ----")
        print([col.get_text(strip=True) for col in cols])
        if len(cols) < 3:
            continue
        weekday = cols[0].get_text(strip=True)
        time_range = cols[1].get_text(strip=True)
        session_type = cols[2].get_text(strip=True)
        match = re.match(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})", time_range)
        print(f"Weekday: {weekday}, Time Range: {time_range}, Session: {session_type}, Match: {bool(match)}")
        if weekday in weekday_map and match:
            start_time, end_time = match.groups()
            events.append({
                "title": session_type,
                "weekday": weekday_map[weekday],
                "start": start_time,
                "end": end_time
            })
    print("---- Events Extracted ----")
    print(events)
    return events

def extract_events_from_blocks():
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(URL)
    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    events = []
    for block in soup.find_all("div", class_="wpb_text_column"):
        h3 = block.find("h3")
        p = block.find("p")
        if not h3 or not p:
            continue
        session_type = h3.get_text(strip=True)
        # Split by <br> and newlines
        lines = []
        for elem in p.contents:
            if isinstance(elem, str):
                lines.extend([l.strip() for l in elem.splitlines() if l.strip()])
            elif elem.name == "br":
                continue
            else:
                lines.append(elem.get_text(strip=True))
        for line in lines:
            # Example: "16:00 – 20:00 Uhr (Montag, Mittwoch)"
            match = re.match(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2}).*?\((.*?)\)", line)
            if match:
                start, end, days = match.groups()
                for day in [d.replace('\xad', '').strip() for d in days.split(",")]:
                    if day in weekday_map:
                        events.append({
                            "title": session_type,
                            "weekday": weekday_map[day],
                            "start": start,
                            "end": end
                        })
    return events

def next_weekday(base_date, target_weekday):
    """Return the next date from base_date that is the target weekday."""
    days_ahead = target_weekday - base_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return base_date + timedelta(days=days_ahead)

def create_calendar(events):
    cal = Calendar()
    base_date = datetime.now(tz)
    for evt in events:
        date_for_event = next_weekday(base_date, evt["weekday"])
        start_hour, start_minute = map(int, evt["start"].split(":"))
        end_hour, end_minute = map(int, evt["end"].split(":"))
        start_dt = tz.localize(datetime(
            year=date_for_event.year,
            month=date_for_event.month,
            day=date_for_event.day,
            hour=start_hour,
            minute=start_minute
        ))
        end_dt = tz.localize(datetime(
            year=date_for_event.year,
            month=date_for_event.month,
            day=date_for_event.day,
            hour=end_hour,
            minute=end_minute
        ))
        event = Event()
        event.name = evt["title"]
        event.begin = start_dt
        event.end = end_dt
        event.description = f"{evt['title']} on {date_for_event.strftime('%A')}"
        event.rrule = {"freq": "weekly"}  # <-- set recurring rule properly
        cal.events.add(event)
    return cal

def deduplicate_events(events):
    seen = set()
    unique_events = []
    for evt in events:
        key = (evt["title"], evt["weekday"], evt["start"], evt["end"])
        if key not in seen:
            seen.add(key)
            unique_events.append(evt)
    return unique_events

if __name__ == "__main__":
    events = extract_events_from_blocks()
    events = deduplicate_events(events)  # Deduplicate here
    print("---- Final Events ----")
    print(events)
    calendar = create_calendar(events)
    with open("schedule.ics", "w") as f:
        f.writelines(calendar.serialize_iter())
    print("✅ ICS calendar created and updated.")
