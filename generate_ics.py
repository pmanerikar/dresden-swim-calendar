from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz

POOL_URLS = {
    "Schwimmsportkomplex Freiberger Platz": "https://dresdner-baeder.de/hallenbaeder/schwimmsportkomplex-freiberger-platz/",
    "Georg-Arnhold-Bad Halle": "https://dresdner-baeder.de/hallenbaeder/georg-arnhold-bad-halle/"
}
tz = pytz.timezone("Europe/Berlin")

weekday_map = {
    "Montag": 0, "Dienstag": 1, "Mittwoch": 2, "Donnerstag": 3, "Freitag": 4,
    "Samstag": 5, "Sonntag": 6, "täglich": "all"
}

def extract_events(url, pool_name):
    """Extract swim events from the web page."""
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    events = []

    print(f"\n=== Checking daily opening hours for {pool_name} ===")
    # First check for general daily opening hours
    for block in soup.find_all(['div', 'section', 'article']):
        text = block.get_text("\n", strip=True)
        print("\nChecking block:")
        print(f"Text: {text[:200]}...")  # Print first 200 chars of block
        
        if "Öffnungszeiten" in text:
            print("Found Öffnungszeiten")
        if "täglich" in text.lower():
            print("Found täglich")
            
        if "Öffnungszeiten" in text and "täglich" in text.lower():
            print("\nFound block with both Öffnungszeiten and täglich!")
            # Look for time patterns
            time_match = re.search(r"(?:täglich|Öffnungszeiten)[^\d]*((\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2}))", text, re.IGNORECASE)
            if time_match:
                start_time, end_time = time_match.groups()[1:]
                print(f"Found times: {start_time} - {end_time}")
                # Create daily events for all weekdays
                for weekday in list(weekday_map.keys())[:-1]:  # All weekdays except "täglich"
                    events.append({
                        "title": f"Öffentliches Schwimmen ({pool_name})",
                        "weekday": weekday_map[weekday],
                        "start": start_time,
                        "end": end_time,
                        "pool": pool_name,
                        "daily": True
                    })
                print(f"Created daily events for all weekdays")
                continue
            else:
                print("No time pattern match found in this block")
                # Try a more lenient time pattern
                time_match = re.finditer(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})", text)
                for match in time_match:
                    print(f"Found time with lenient pattern: {match.group()}")

    print(f"\n=== Processing specific schedules for {pool_name} ===")
    # Process all other text blocks for specific schedules
    for block in soup.find_all(['div', 'section', 'article']):
        session_type = None
        
        # Try to find session type from headings
        heading = block.find(['h2', 'h3', 'h4'])
        if heading:
            session_type = heading.get_text(strip=True)
        
        text = block.get_text("\n", strip=True)
        
        # Skip if this is the general opening hours block
        if "Öffnungszeiten" in text and "täglich" in text.lower():
            continue
        
        # Check for daily schedule
        daily_schedule = "täglich" in text.lower()
        
        # Look for time patterns
        time_matches = re.finditer(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})", text)
        for time_match in time_matches:
            start_time, end_time = time_match.groups()
            
            weekdays_found = []
            if daily_schedule:
                weekdays_found = list(weekday_map.keys())[:-1]  # All weekdays except "täglich"
            else:
                # Look for weekday patterns
                for day in weekday_map:
                    if day in text and day != "täglich":
                        weekdays_found.append(day)
            
            # Determine session type if not already set
            if not session_type:
                if "früh" in text.lower():
                    session_type = "Frühschwimmen"
                elif "öffentlich" in text.lower():
                    session_type = "Öffentliches Schwimmen"
                elif "lehr" in text.lower():
                    session_type = "Lehrschwimmbecken"
                else:
                    session_type = "Öffentliches Schwimmen"
            
            for weekday in weekdays_found:
                events.append({
                    "title": f"{session_type} ({pool_name})",
                    "weekday": weekday_map[weekday],
                    "start": start_time,
                    "end": end_time,
                    "pool": pool_name,
                    "daily": daily_schedule
                })
    
    return events

def next_weekday(base_date, target_weekday):
    days_ahead = target_weekday - base_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return base_date + timedelta(days=days_ahead)

def create_calendar(events, pool_name):
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
        schedule_type = "daily" if evt.get("daily", False) else "weekly"
        event.description = f"{evt['title']} on {date_for_event.strftime('%A')} at {pool_name}\nSchedule: {schedule_type}"
        event.rrule = {"freq": "weekly"}
        cal.events.add(event)
    return cal

def deduplicate_events(events):
    seen = set()
    unique_events = []
    for evt in events:
        key = (evt["title"], evt["weekday"], evt["start"], evt["end"], evt.get("pool"))
        if key not in seen:
            seen.add(key)
            unique_events.append(evt)
    return unique_events

if __name__ == "__main__":
    for pool_name, url in POOL_URLS.items():
        print(f"Extracting events for {pool_name} ...")
        events = extract_events(url, pool_name)
        events = deduplicate_events(events)
        print(f"---- Final Events for {pool_name} ----")
        print(events)
        calendar = create_calendar(events, pool_name)
        filename = f"schedule_{pool_name.lower().replace(' ', '_').replace('-', '').replace('(', '').replace(')', '')}.ics"
        with open(filename, "w") as f:
            f.writelines(calendar.serialize_iter())
        print(f"✅ ICS calendar created for {pool_name}: {filename}.")
