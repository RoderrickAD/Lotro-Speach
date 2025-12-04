import requests
import pygame
import threading
import time
import re
import os
import pyttsx3
import torch # Für GPU Check
from requests.exceptions import RequestException
from utils import log_message

class TTSService:
    def __init__(self, config):
        self.config = config
        
        try: pygame.mixer.init()
        except Exception as e: log_message(f"Audio Init Fehler: {e}")

        # Pyttsx3 (System)
        self.local_engine = None
        try:
            self.local_engine = pyttsx3.init()
        except: pass

        # XTTS (Coqui) - Platzhalter, wird erst bei Bedarf geladen
        self.xtts_model = None 

    def _load_xtts_model(self):
        """Lädt das riesige KI-Modell in den Speicher."""
        if self.xtts_model is not None: return True
        
        log_message("Lade Coqui XTTS v2 Modell (Das dauert einen Moment)...")
        try:
            from TTS.api import TTS
            # Prüfen ob GPU verfügbar ist
            use_gpu = torch.cuda.is_available()
            device_name = "cuda" if use_gpu else "cpu"
            log_message(f"XTTS läuft auf: {device_name.upper()}")
            
            # Modell laden (lädt beim ersten Mal automatisch aus dem Internet herunter)
            self.xtts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device_name)
            log_message("XTTS Modell erfolgreich geladen!")
            return True
        except Exception as e:
            log_message(f"KRITISCHER FEHLER beim Laden von XTTS: {e}")
            return False

    def get_available_xtts_voices(self):
        """Scannt den 'voices' Ordner nach .wav Dateien."""
        voice_dir = os.path.join(os.getcwd(), "voices")
        if not os.path.exists(voice_dir): os.makedirs(voice_dir)
        return [f for f in os.listdir(voice_dir) if f.lower().endswith(".wav")]

    def get_local_voices(self):
        if not self.local_engine: return []
        try: return [(v.id, v.name) for v in self.local_engine.getProperty('voices')]
        except: return []

    def fetch_voices(self):
        # ElevenLabs Stimmen laden
        api_key = self.config.get("api_key", "").strip()
        if api_key:
            try:
                headers = {"xi-api-key": api_key}
                resp = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
                if resp.status_code == 200: return resp.json().get('voices', [])
            except: pass
        return []

    def get_npc_from_log(self):
        try:
            path = self.config.get("lotro_log_path", "")
            if not os.path.exists(path): return "Unknown", "Unknown"
            with open(path, "r", encoding="utf-8", errors="ignore") as f: lines = f.readlines()[-50:]
            dialog_pattern = re.compile(r"^\s*\[\d{2}:\d{2}:\d{2}\]\s*([^\]]+?)\s*sagt[:\.]", re.IGNORECASE)
            npc_name = "Unknown"
            for line in reversed(lines):
                match = dialog_pattern.search(line)
                if match:
                    npc_name = re.sub(r'\[.*?\]', '', match.group(1).strip()).strip()
                    break
            gender = "Female" if any(x in npc_name.lower() for x in ["frau", "lady", "she", "galadriel"]) else "Male"
            return npc_name, gender
        except: return "Unknown", "Unknown"

    def _play_audio_thread(self, filepath):
        try:
            if not pygame.mixer.get_init(): pygame.mixer.init()
            if pygame.mixer.music.get_busy(): pygame.mixer.music.stop() 
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy(): time.sleep(0.1)
            pygame.mixer.music.unload()
        except Exception as e: log_message(f"Playback Fehler: {e}")

    def toggle_pause(self):
        try:
            if pygame.mixer.music.get_busy(): pygame.mixer.music.pause()
            else: pygame.mixer.music.unpause()
        except: pass

    def generate_and_play(self, text, voice_id, cache_file, delay, name, method):
        if delay > 0: time.sleep(delay)
        if os.path.exists(cache_file):
            log_message(f"Spiele aus Cache ({method})...")
            threading.Thread(target=self._play_audio_thread, args=(cache_file,)).start()
            return

        provider = self.config.get("tts_provider", "elevenlabs")
        
        if provider == "xtts":
            log_message(f"Generiere mit XTTS KI ({name})...")
            self._generate_xtts(text, cache_file)
        elif provider == "local":
            log_message(f"Generiere Systemstimme ({name})...")
            self._generate_local(text, cache_file)
        else:
            log_message(f"Generiere Cloud ({name})...")
            self._generate_elevenlabs(text, voice_id, cache_file)

    def _generate_xtts(self, text, filepath):
        """Generiert Audio mit Coqui XTTS."""
        # 1. Modell laden falls noch nicht geschehen
        if not self._load_xtts_model(): return

        # 2. Referenzdatei finden
        ref_file = self.config.get("xtts_reference_wav", "")
        ref_path = os.path.join(os.getcwd(), "voices", ref_file)
        
        if not ref_file or not os.path.exists(ref_path):
            log_message("FEHLER: Keine gültige Referenzstimme (.wav) im Ordner 'voices' ausgewählt!")
            # Fallback: Erste Datei im Ordner nehmen
            files = self.get_available_xtts_voices()
            if files:
                ref_path = os.path.join(os.getcwd(), "voices", files[0])
                log_message(f"Nutze Fallback-Stimme: {files[0]}")
            else:
                log_message("ABBRUCH: Ordner 'voices' ist leer.")
                return

        # 3. Generieren
        try:
            # XTTS generiert direkt eine WAV Datei
            self.xtts_model.tts_to_file(
                text=text,
                file_path=filepath,
                speaker_wav=ref_path,
                language="de"
            )
            
            if os.path.exists(filepath):
                threading.Thread(target=self._play_audio_thread, args=(filepath,)).start()
        except Exception as e:
            log_message(f"XTTS Generierung gescheitert: {e}")

    def _generate_local(self, text, filepath):
        try:
            temp_engine = pyttsx3.init()
            voice_id = self.config.get("local_voice_id", "")
            if voice_id: temp_engine.setProperty('voice', voice_id)
            temp_engine.setProperty('rate', 145) 
            temp_engine.save_to_file(text, filepath)
            temp_engine.runAndWait()
            if os.path.exists(filepath):
                threading.Thread(target=self._play_audio_thread, args=(filepath,)).start()
        except Exception as e: log_message(f"Lokaler TTS Fehler: {e}")

    def _generate_elevenlabs(self, text, voice_id, filepath):
        try:
            voice_settings = self.config.get("voice_settings", {"stability": 0.5, "similarity_boost": 0.75})
            headers = {"xi-api-key": self.config.get("api_key", ""), "Content-Type": "application/json"}
            data = {"text": text, "model_id": "eleven_turbo_v2_5", "voice_settings": voice_settings}
            resp = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", headers=headers, json=data)
            if resp.status_code == 200:
                with open(filepath, "wb") as f: f.write(resp.content)
                threading.Thread(target=self._play_audio_thread, args=(filepath,)).start()
            else: log_message(f"API Fehler {resp.status_code}: {resp.text}")
        except Exception as e: log_message(f"Cloud TTS Fehler: {e}")
