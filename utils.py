import json
import os
import datetime

CONFIG_FILE = "config.json"
MAPPING_FILE = "voice_mapping.json"
LOG_FILE = "app.log"

DEFAULT_CONFIG = {
    "api_key": "",
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "lotro_log_path": os.path.join(os.path.expanduser("~"), "Documents", "The Lord of the Rings Online", "Script.log"),
    "ocr_coords": None, # None bedeutet: Ganzer Monitor wird gescannt
    "hotkey": "ctrl+alt+s",
    "monitor_index": 1, # 1 = Hauptmonitor
    "audio_delay": 0.5  # Sekunden Pause vor Sprachausgabe
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Fehlende Keys mit Defaults ergänzen
            for key, val in DEFAULT_CONFIG.items():
                if key not in data:
                    data[key] = val
            return data
    except:
        return DEFAULT_CONFIG

def save_config(config_data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)

def load_mapping():
    if not os.path.exists(MAPPING_FILE):
        return {}
    try:
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_mapping(mapping_data):
    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping_data, f, indent=4)

def log_message(message):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except:
        pass
    return entry
