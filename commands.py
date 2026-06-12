import os
import json
import subprocess
import time
import tkinter as tk
import xml.etree.ElementTree as ET
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import win32com.client

NOTES_FILE = Path(__file__).with_name("notes.txt")

APPS = {
    "chrome": "start chrome",
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "vscode": "code",
    "vs code": "code",
    "paint": "mspaint",
    "explorer": "explorer",
    "files": "explorer",
    "steam": "steam://open/main",
    "discord": "discord",
    "spotify": "spotify",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
}

PROCESSES = {
    "chrome": "chrome.exe",
    "notepad": "notepad.exe",
    "calculator": "CalculatorApp.exe",
    "calc": "CalculatorApp.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "steam": "steam.exe",
    "discord": "Discord.exe",
    "spotify": "Spotify.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
}

WEBSITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "github": "https://github.com",
    "gmail": "https://mail.google.com",
    "chatgpt": "https://chatgpt.com",
}

SEEN_NEWS = {}

def run_action(action, value):
    raw_value = str(value or "").strip()
    value = raw_value.lower()

    if action == "open_app":
        return open_app(raw_value)

    elif action == "close_app":
        return close_app(raw_value)

    elif action == "stop_speaking":
        from voice import stop_speaking
        stop_speaking()
        return "Stopped speaking"

    elif action == "open_website":
        url = WEBSITES.get(value)
        if not url and "." in value:
            url = value if value.startswith("http") else f"https://{value}"

        if url:
            webbrowser.open(url)
            return f"Opening {value}"

        return f"I don't know that website yet"

    elif action == "web_search":
        webbrowser.open(f"https://www.google.com/search?q={quote_plus(raw_value)}")
        return f"Searching Google for {raw_value}"

    elif action == "youtube_search":
        webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(raw_value)}")
        return f"Searching YouTube for {raw_value}"

    elif action == "latest_news":
        return get_latest_news(raw_value)

    elif action == "weather":
        return get_weather(raw_value)

    elif action == "get_time":
        return datetime.now().strftime("It is %I:%M %p")

    elif action == "get_date":
        return datetime.now().strftime("Today is %A, %B %d, %Y")

    elif action == "take_note":
        if not raw_value:
            return "What should I write down?"
        with NOTES_FILE.open("a", encoding="utf-8") as file:
            file.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} - {raw_value}\n")
        return "Note saved"

    elif action == "read_notes":
        if not NOTES_FILE.exists():
            return "You do not have any notes yet"

        notes = NOTES_FILE.read_text(encoding="utf-8").strip()
        if not notes:
            return "You do not have any notes yet"

        return notes[-700:]

    elif action == "write_text":
        return write_text(raw_value)

    elif action == "open_notepad_write":
        return open_notepad_and_write(raw_value)

    elif action == "chat":
        return raw_value

    return None


def open_app(app_name):
    value = app_name.lower().strip()
    app_command = APPS.get(value)

    try:
        if app_command:
            if app_command.startswith("steam://"):
                os.startfile(app_command)
            else:
                subprocess.Popen(app_command, shell=True)
            return f"Opening {app_name}"

        subprocess.Popen(f'start "" "{app_name}"', shell=True)
        return f"Trying to open {app_name}"
    except Exception:
        try:
            os.startfile(app_name)
            return f"Opening {app_name}"
        except Exception as e:
            return f"I could not open {app_name}: {e}"


def close_app(app_name):
    value = app_name.lower().strip()
    process_name = PROCESSES.get(value)

    if not process_name:
        process_name = value if value.endswith(".exe") else f"{value}.exe"

    try:
        result = subprocess.run(
            ["taskkill", "/IM", process_name],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode == 0:
            return f"Closed {app_name}"

        error = (result.stderr or result.stdout).strip()
        return f"I could not close {app_name}: {error or 'app not found'}"
    except Exception as e:
        return f"I could not close {app_name}: {e}"


def set_clipboard(text):
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    root.destroy()


def paste_clipboard():
    shell = win32com.client.Dispatch("WScript.Shell")
    shell.SendKeys("^v")


def write_text(text):
    if not text:
        return "Tell me what to write"

    try:
        set_clipboard(text)
        time.sleep(0.15)
        paste_clipboard()
        return f"I wrote {text}"
    except Exception as e:
        return f"I could not write that: {e}"


def open_notepad_and_write(text):
    if not text:
        return "Tell me what to write in Notepad"

    try:
        subprocess.Popen("notepad")
        time.sleep(0.8)
        shell = win32com.client.Dispatch("WScript.Shell")
        shell.AppActivate("Notepad")
        time.sleep(0.2)
        set_clipboard(text)
        paste_clipboard()
        return f"I opened Notepad and wrote {text}"
    except Exception as e:
        return f"I could not write in Notepad: {e}"


def get_latest_news(topic=""):
    query = topic or "urgent breaking news"
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=8) as response:
            xml_text = response.read()
    except Exception as e:
        webbrowser.open(f"https://news.google.com/search?q={quote_plus(query)}")
        return f"I could not read the news feed, so I opened Google News for {query}"

    try:
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")[:5]
    except ET.ParseError:
        webbrowser.open(f"https://news.google.com/search?q={quote_plus(query)}")
        return f"I could not parse the news feed, so I opened Google News for {query}"

    seen_titles = SEEN_NEWS.setdefault(query.lower(), set())
    fresh_updates = []
    fallback_updates = []

    for item in items:
        title = clean_news_title(item.findtext("title", "").strip())
        source = item.findtext("source", "").strip()
        if title:
            if source:
                update = f"According to {source}, {title}"
            else:
                update = title

            fallback_updates.append((title, update))
            if title not in seen_titles:
                fresh_updates.append((title, update))

    if not fallback_updates:
        return f"I could not find recent news for {query}"

    selected = fresh_updates[:3]
    if not selected:
        seen_titles.clear()
        selected = fallback_updates[:3]

    for title, _ in selected:
        seen_titles.add(title)

    intro = "Here's what I'm seeing right now"
    if topic:
        intro += f" about {topic}"

    return intro + ". " + ". ".join(update for _, update in selected)


def clean_news_title(title):
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title


def get_weather(location=""):
    place = location.strip() or ""
    label = place or "your area"
    url_place = quote_plus(place) if place else ""
    url = f"https://wttr.in/{url_place}?format=j1"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))

        current = data["current_condition"][0]
        condition = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        feels_c = current["FeelsLikeC"]
        humidity = current["humidity"]
        wind_kmph = current["windspeedKmph"]

        return (
            f"The weather in {label} is {condition}, {temp_c} degrees Celsius, "
            f"feels like {feels_c}, with {humidity}% humidity and wind at {wind_kmph} kilometers per hour."
        )
    except Exception as e:
        webbrowser.open(f"https://www.google.com/search?q={quote_plus('weather ' + label)}")
        return f"I could not read the weather directly, so I opened the weather search for {label}"
