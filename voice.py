import pyttsx3
import speech_recognition as sr
import time
import threading
import win32com.client

try:
    import pythoncom
except ImportError:
    pythoncom = None

thread_voice = threading.local()
active_speakers = []
active_speakers_lock = threading.Lock()
speech_stop_event = threading.Event()

try:
    speaker = win32com.client.Dispatch("SAPI.SpVoice")

    preferred_voice = None
    for i in range(speaker.GetVoices().Count):
        voice = speaker.GetVoices().Item(i)
        description = voice.GetDescription().lower()
        if "david" in description:
            preferred_voice = voice
            break
        if "zira" in description and preferred_voice is None:
            preferred_voice = voice

    if preferred_voice:
        speaker.Voice = preferred_voice

    speaker.Rate = 0
except Exception as e:
    print("SAPI INIT ERROR:", e)
    speaker = None

engine = pyttsx3.init()
engine.setProperty('rate', 175)


def get_speaker():
    if getattr(thread_voice, "speaker", None):
        return thread_voice.speaker

    if pythoncom:
        pythoncom.CoInitialize()

    local_speaker = win32com.client.Dispatch("SAPI.SpVoice")
    preferred_voice = None

    for i in range(local_speaker.GetVoices().Count):
        voice = local_speaker.GetVoices().Item(i)
        description = voice.GetDescription().lower()
        if "david" in description:
            preferred_voice = voice
            break
        if "zira" in description and preferred_voice is None:
            preferred_voice = voice

    if preferred_voice:
        local_speaker.Voice = preferred_voice

    local_speaker.Rate = 0
    thread_voice.speaker = local_speaker
    register_speaker(local_speaker)
    return local_speaker


def register_speaker(local_speaker):
    with active_speakers_lock:
        if local_speaker not in active_speakers:
            active_speakers.append(local_speaker)


def stop_speaking():
    speech_stop_event.set()
    with active_speakers_lock:
        speakers = list(active_speakers)

    for active_speaker in speakers:
        try:
            active_speaker.Speak("", 2)
        except Exception:
            pass

    try:
        engine.stop()
    except Exception:
        pass


def speak(text):
    print("IMOT:", text)
    speech_stop_event.clear()
    try:
        local_speaker = get_speaker()
        if local_speaker:
            local_speaker.Speak(str(text), 1)
            while not speech_stop_event.is_set():
                try:
                    if local_speaker.Status.RunningState != 2:
                        break
                except Exception:
                    break
                time.sleep(0.05)
            if speech_stop_event.is_set():
                local_speaker.Speak("", 2)
        else:
            engine.say(str(text))
            engine.runAndWait()
    except Exception as e:
        print("SPEECH ERROR:", e)

def listen():
    r = sr.Recognizer()
    r.pause_threshold = 1.4
    r.phrase_threshold = 0.2
    r.non_speaking_duration = 0.6

    try:
        with sr.Microphone() as source:
            print("Listening...")
            r.adjust_for_ambient_noise(source, duration=0.25)
            audio = r.listen(source, timeout=None, phrase_time_limit=None)

        command = r.recognize_google(audio)
        print("You:", command)
        return command.lower()

    except sr.UnknownValueError:
        print("Didn't catch that.")
        return ""
    except Exception as e:
        print("RECOGNITION ERROR:", e)
        return ""
