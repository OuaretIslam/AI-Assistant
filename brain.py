import ollama
import json
import re

MODEL = 'llama3'
VALID_ACTIONS = {
    "open_app",
    "close_app",
    "stop_speaking",
    "open_website",
    "web_search",
    "youtube_search",
    "latest_news",
    "weather",
    "get_time",
    "get_date",
    "take_note",
    "read_notes",
    "write_text",
    "open_notepad_write",
    "chat",
}

VOICE_ASSISTANT_PERSONALITY = (
    "Answer naturally like a friendly human voice assistant. "
    "Keep most answers to 1 to 3 short spoken sentences unless the user asks for detail. "
    "If you are not sure, say so quickly and give the most useful next step instead of rambling. "
    "Sound casual and human, with contractions and plain words. "
    "Use the recent memory if the user asks about the previous question or conversation. "
    "When the user asks for dating, flirting, texting, confidence, or 'rizz' help, act like a respectful wingman: "
    "be warm, specific, and practical; help the user sound confident but still like themselves; "
    "suggest consent-aware, non-pushy approaches; never encourage manipulation, pressure, harassment, or deception; "
    "if the user's request is vague, give one strong example and one quick question to personalize it."
)


def ask_ai(prompt, context=""):
    context_text = ""
    if context:
        context_text = f"\nRecent memory:\n{context}\n"

    response = ollama.chat(
        model=MODEL,
        messages=[{
            'role': 'user',
            'content': (
                VOICE_ASSISTANT_PERSONALITY +
                f"{context_text}\nUser: {prompt}"
            )
        }]
    )
    return response['message']['content']


def safe_json_load(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [{"action": "chat", "value": text}]

    if isinstance(data, dict) and "actions" in data:
        data = data["actions"]

    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return [{"action": "chat", "value": text}]

    actions = []
    for item in data:
        if not isinstance(item, dict):
            continue

        action = item.get("action", "chat")
        value = item.get("value") or ""

        if action not in VALID_ACTIONS:
            action = "chat"
            value = text

        actions.append({"action": action, "value": value})

    return actions or [{"action": "chat", "value": text}]


def is_conversation(text):
    text = text.lower().strip()
    command_words = {
        "open",
        "close",
        "exit",
        "quit",
        "kill",
        "stop",
        "search",
        "google",
        "youtube",
        "play",
        "write",
        "type",
        "note",
        "remember",
        "news",
        "weather",
        "temperature",
        "forecast",
        "time",
        "date",
    }

    if any(re.search(rf"\b{word}\b", text) for word in command_words):
        return False

    casual_phrases = [
        "hi",
        "hello",
        "hey",
        "how are you",
        "how are you doing",
        "what's up",
        "whats up",
        "thank you",
        "thanks",
        "rizz",
        "flirt",
        "dating",
        "ask her out",
        "ask a girl out",
        "text her",
        "message her",
        "talk to her",
        "talk to a girl",
        "crush",
        "first date",
        "pickup line",
        "pick up line",
    ]
    if any(phrase in text for phrase in casual_phrases):
        return True

    return bool(re.match(r"^(what|why|how|who|where|when|can you|could you|do you|is|are|am|should|would)\b", text))


def quick_actions(user_input):
    text = user_input.lower()
    actions = []
    parts = [part.strip() for part in re.split(r"\b(?:and|then)\b", text) if part.strip()]

    for part in parts:
        part_actions = []

        if part in {"stop", "stop speaking", "be quiet", "quiet"}:
            actions.append({"action": "stop_speaking", "value": ""})
            continue

        if any(phrase in part for phrase in [
            "last question",
            "previous question",
            "last answer",
            "previous answer",
            "what do you think",
            "what you think",
        ]):
            actions.append({"action": "chat", "value": ""})
            continue

        if "time" in part:
            part_actions.append({"action": "get_time", "value": ""})

        if "date" in part or "day is it" in part:
            part_actions.append({"action": "get_date", "value": ""})

        news_match = re.search(
            r"(?:latest|urgent|breaking|current|other|more)?\s*news(?:\s+(?:about|from|in)\s+(.+))?",
            part,
        )
        if news_match and "newsletter" not in part:
            part_actions.append({"action": "latest_news", "value": (news_match.group(1) or "").strip()})

        weather_match = re.search(
            r"(?:weather|temperature|forecast)(?:\s+(?:in|for|at)\s+(.+))?",
            part,
        )
        if weather_match:
            part_actions.append({"action": "weather", "value": (weather_match.group(1) or "").strip()})

        if "open youtube" in part:
            part_actions.append({"action": "open_website", "value": "youtube"})

        if "open google" in part:
            part_actions.append({"action": "open_website", "value": "google"})

        if "open github" in part:
            part_actions.append({"action": "open_website", "value": "github"})

        notepad_write_match = re.search(r"open\s+notepad\s+(?:and\s+)?(?:write|type)\s+(.+)", part)
        if notepad_write_match:
            actions.append({"action": "open_notepad_write", "value": notepad_write_match.group(1).strip()})
            continue

        write_match = re.search(r"(?:write|type)\s+(.+)", part)
        if write_match:
            actions.append({"action": "write_text", "value": write_match.group(1).strip()})
            continue

        for app in ["chrome", "notepad", "calculator", "vscode", "paint", "explorer", "steam", "discord", "spotify"]:
            if f"open {app}" in part:
                part_actions.append({"action": "open_app", "value": app})

        close_match = re.search(r"(?:close|exit|quit|kill|stop)\s+(.+)", part)
        if close_match:
            app_name = close_match.group(1).strip()
            if app_name:
                part_actions.append({"action": "close_app", "value": app_name})
                actions.extend(part_actions)
                continue

        open_match = re.search(r"open\s+(.+)", part)
        if open_match and not any(action["action"] in {"open_app", "open_website"} for action in part_actions):
            app_name = open_match.group(1).strip()
            if app_name:
                part_actions.append({"action": "open_app", "value": app_name})

        youtube_match = re.search(r"(?:search|find|play)\s+(?:on\s+)?youtube\s+(?:for\s+)?(.+)", part)
        if youtube_match:
            part_actions.append({"action": "youtube_search", "value": youtube_match.group(1).strip()})

        google_match = re.search(r"(?:google|search|look up)\s+(?:for\s+)?(.+)", part)
        if google_match and "youtube" not in part:
            part_actions.append({"action": "web_search", "value": google_match.group(1).strip()})

        note_match = re.search(r"(?:take a note|note this|remember this)\s+(.+)", part)
        if note_match:
            part_actions.append({"action": "take_note", "value": note_match.group(1).strip()})

        if "read my notes" in part or "show my notes" in part:
            part_actions.append({"action": "read_notes", "value": ""})

        actions.extend(part_actions)

    return actions


def decide_actions(user_input):
    actions = quick_actions(user_input)
    if actions:
        return merge_actions(actions)

    if is_conversation(user_input):
        return [{"action": "chat", "value": ""}]

    response = ollama.chat(
        model=MODEL,
        messages=[{
            'role': 'user',
            'content': f"""
You are a task planner for a voice assistant.

Return ONLY valid JSON with this format:
[
  {{"action":"open_app","value":"notepad"}}
]

Valid actions:
- open_app
- close_app
- stop_speaking
- open_website
- web_search
- youtube_search
- latest_news
- weather
- get_time
- get_date
- take_note
- read_notes
- write_text
- open_notepad_write
- chat

Known apps include chrome, notepad, calculator, vscode, paint, explorer, steam, discord, spotify.
Known websites: youtube, google, github, gmail.
For close, exit, quit, kill, or stop followed by an app name, use close_app.
For "stop", "stop speaking", "be quiet", or "quiet", use stop_speaking.
For chat, put a short assistant response in value.
For dating, flirting, confidence, texting advice, or "rizz" help, use chat unless the user explicitly asks you to type/write text into another app.
For current events, urgent news, breaking news, or latest news, use latest_news.
For weather, temperature, or forecast questions, use weather.
For "open notepad and write ..." use open_notepad_write.
For "write ..." or "type ..." use write_text.
For multi-step requests, return multiple objects in order.

User: {user_input}
"""
        }]
    )

    return merge_actions(safe_json_load(response['message']['content']))


def decide_action(user_input):
    return decide_actions(user_input)[0]


def merge_actions(actions):
    merged = []
    index = 0

    while index < len(actions):
        current = actions[index]
        next_action = actions[index + 1] if index + 1 < len(actions) else None

        if (
            current.get("action") == "open_app"
            and current.get("value") == "notepad"
            and next_action
            and next_action.get("action") == "write_text"
        ):
            merged.append({"action": "open_notepad_write", "value": next_action.get("value", "")})
            index += 2
            continue

        merged.append(current)
        index += 1

    return merged
