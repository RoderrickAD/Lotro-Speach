import json
import os
import datetime

CONFIG_FILE = "config.json"
MAPPING_FILE = "voice_mapping.json"
LOG_FILE = "app.log"

DEFAULT_CONFIG = {
    "api_key": "",          # ElevenLabs Key
    "gemini_api_key": "",   # NEU: Google Gemini Key
    "use_ai_ocr": False,    # NEU: Schalter für KI-Modus
    
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "lotro_log_path": os.path.join(os.path.expanduser("~"), "Documents", "The Lord of the Rings Online", "Script.log"),
    "ocr_coords": None, 
    "hotkey": "ctrl+alt+s",
    "monitor_index": 1, 
    "audio_delay": 0.5,
    "ocr_language": "deu+eng",
    "ocr_psm": 6,
    "ocr_whitelist": "",
    "debug_mode": False,
    "padding_top": 10,
    "padding_bottom": 20,
    "padding_left": 10,
    "padding_right": 50
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            updated = False
            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val
                    updated = True
            if updated: save_config(data)
            return data
    except:
        return DEFAULT_CONFIG.copy()

def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Speichern der Config: {e}")

def load_mapping():
    if not os.path.exists(MAPPING_FILE): return {}
    try:
        with open(MAPPING_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_mapping(mapping_data):
    try:
        with open(MAPPING_FILE, "w", encoding="utf-8") as f: json.dump(mapping_data, f, indent=4)
    except: pass

def log_message(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(entry + "\n")
    except: pass
    return entry
