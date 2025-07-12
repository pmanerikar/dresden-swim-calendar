from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import re
from ics import Calendar, Event
from datetime import datetime, timedelta
import pytz
import spacy
from transformers import pipeline

# Load German language model for spaCy (using smaller model for faster processing)
nlp = spacy.load("de_core_news_sm")

# Initialize zero-shot classification pipeline
classifier = pipeline("zero-shot-classification", model="deepset/gbert-base")

POOL_URLS = {
    "Schwimmsportkomplex Freiberger Platz": "https://dresdner-baeder.de/hallenbaeder/schwimmsportkomplex-freiberger-platz/",
    "Georg-Arnhold-Bad Halle": "https://dresdner-baeder.de/hallenbaeder/georg-arnhold-bad-halle/"
}
tz = pytz.timezone("Europe/Berlin")

weekday_map = {
    "Montag": 0, "Dienstag": 1, "Mittwoch": 2, "Donnerstag": 3, "Freitag": 4,
    "Samstag": 5, "Sonntag": 6
}

def extract_events_with_nlp(url, pool_name):
    """
    Extract swim events using NLP techniques.
    Uses spaCy for entity recognition and transformers for classification.
    """
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    html = driver.page_source
    driver.quit()

    soup = BeautifulSoup(html, "html.parser")
    events = []

    # Categories for classification
    categories = ["Frühschwimmen", "Öffentliches Schwimmen", "Lehrschwimmbecken"]

    # Process all text content
    for element in soup.find_all(['p', 'div', 'section', 'article']):
        text = element.get_text(strip=True)
        if not text:
            continue

        # Use spaCy for initial processing
        doc = nlp(text)

        # Look for time patterns
        time_matches = re.finditer(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})", text)
        for time_match in time_matches:
            start_time, end_time = time_match.groups()
            
            # Find weekdays in the surrounding context
            weekdays_found = []
            for token in doc:
                if token.text in weekday_map:
                    weekdays_found.append(token.text)

            # If no weekdays found directly, look in broader context
            if not weekdays_found:
                for sent in doc.sents:
                    for token in nlp(sent.text):
                        if token.text in weekday_map:
                            weekdays_found.append(token.text)

            # Use transformer to classify the type of swimming session
            if weekdays_found:
                # Get the sentence containing the time
                relevant_sentence = next((sent.text for sent in doc.sents 
                                       if start_time in sent.text), text)
                
                # Classify the type of swimming session
                result = classifier(
                    relevant_sentence,
                    candidate_labels=categories,
                    hypothesis_template="Dies ist ein {}."
                )
                
                session_type = result['labels'][0]  # Get most likely category

                # Create events for each weekday found
                for weekday in weekdays_found:
                    events.append({
                        "title": f"{session_type} ({pool_name})",
                        "weekday": weekday_map[weekday],
                        "start": start_time,
                        "end": end_time,
                        "pool": pool_name,
                        "confidence": result['scores'][0]  # Store classification confidence
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
        event.description = (f"{evt['title']} on {date_for_event.strftime('%A')} at {pool_name}"
                           f"\nConfidence: {evt.get('confidence', 1.0):.2%}")
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
        events = extract_events_with_nlp(url, pool_name)
        events = deduplicate_events(events)
        print(f"---- Final Events for {pool_name} ----")
        print(events)
        calendar = create_calendar(events, pool_name)
        filename = f"schedule_{pool_name.lower().replace(' ', '_').replace('-', '').replace('(', '').replace(')', '')}.ics"
        with open(filename, "w") as f:
            f.writelines(calendar.serialize_iter())
        print(f"✅ ICS calendar created for {pool_name}: {filename}.")
