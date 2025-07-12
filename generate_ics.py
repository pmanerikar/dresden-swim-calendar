import requests
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
        start_dt = datetime.strptime(evt["start"], "%H:%M").replace(
            year=base_date.year, month=base_date.month, day=base_date.day
        )
        end_dt = datetime.strptime(evt["end"], "%H:%M").replace(
            year=base_date.year, month=base_date.month, day=base_date.day
        )
        date_for_event = next_weekday(base_date, evt["weekday"])
        event = Event()
        event.name = evt["title"]
        event.begin = tz.localize(date_for_event.replace(hour=start_dt.hour, minute=start_dt.minute))
        event.end = tz.localize(date_for_event.replace(hour=end_dt.hour, minute=end_dt.minute))
        event.description = f"{evt['title']} on {date_for_event.strftime('%A')}"
        event.make_recurring("RRULE:FREQ=WEEKLY")
        cal.events.add(event)
    return cal

if __name__ == "__main__":
    text = extract_text_blocks()
    events = extract_events_from_text(text)
    calendar = create_calendar(events)
    with open("schedule.ics", "w") as f:
        f.writelines(calendar)
    print("✅ ICS calendar created and updated.")
