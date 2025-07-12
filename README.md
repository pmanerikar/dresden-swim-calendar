# dresden-swim-calendar
Check the dresden baeder webpages and create a subscribe-able  calendar for Fruh Schwimmen , Lehrschwinbecken and Offentiches Schwimmen

## Script Logic

The script (`generate_ics.py`) automates the extraction of swimming session schedules from the Dresden Baeder website and generates a recurring ICS calendar file. Here’s how it works:

1. **Web Scraping with Selenium and BeautifulSoup**
   - The script uses Selenium to load the web page in headless mode, ensuring all dynamic content is rendered.
   - BeautifulSoup parses the loaded HTML to extract relevant schedule information.

2. **Extracting Events**
   - The script looks for structured blocks (e.g., `<div class="wpb_text_column">`) that contain session information.
   - For each block, it extracts the session type (e.g., Frühschwimmen, Öffentliches Schwimmen, Lehrschwimmbecken) from the `<h3>` tag.
   - It then parses the schedule details from the `<p>` tag, splitting by `<br>` and newlines.
   - Using regular expressions, it identifies time ranges and associated weekdays (e.g., "16:00 – 20:00 Uhr (Montag, Mittwoch)").
   - For each weekday listed, it creates an event dictionary with the session type, weekday, start time, and end time.

3. **Deduplication**
   - The script deduplicates events to avoid duplicate calendar entries.

4. **Calendar Generation**
   - For each event, it calculates the next occurrence of the specified weekday.
   - It creates a recurring weekly event using the `ics` library, setting the correct start and end times in the Europe/Berlin timezone.
   - All events are added to a calendar object.

5. **Output**
   - The calendar is serialized and written to `schedule.ics`, which can be imported or subscribed to in calendar applications.

## Usage

1. Install dependencies:
   - `pip install selenium beautifulsoup4 ics pytz`
   - Download the appropriate ChromeDriver for your system.

2. Run the script:
   ```
   python generate_ics.py
   ```

3. The resulting `schedule.ics` file will contain all recurring swim sessions for the week.
