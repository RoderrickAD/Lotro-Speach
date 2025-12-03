import requests
import pygame
import threading
import time
import re
import os
from requests.exceptions import RequestException
from utils import log_message

class TTSService:
    def __init__(self, config):
        self.config = config
        try:
            pygame.mixer.init()
        except Exception as e:
            log_message(f"Audio Init Fehler: {e}")

    def fetch_voices(self):
        api_key = self.config.get("api_key", "").strip()
        if not api_key: 
            log_message("ElevenLabs API Key fehlt. Stimmen-Update übersprungen.")
            return []
            
        try:
            headers = {"xi-api-key": api_key}
            resp = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers)
            
            if resp.status_code == 200:
                voices = resp.json().get('voices', [])
                log_message(f"{len(voices)} Stimmen geladen.")
                return voices
            else:
                log_message(f"API Fehler beim Laden der Stimmen: {resp.text}")
        except RequestException as e:
            log_message(f"Netzwerkfehler beim Laden der Stimmen: {e}")
        return []

    def get_npc_from_log(self):
        """
        Versucht, den NPC-Namen und das Geschlecht aus den letzten Zeilen des LOTRO-Skript-Logs zu extrahieren.
        """
        try:
            path = self.config.get("lotro_log_path", "")
            if not os.path.exists(path):
                return "Unknown", "Unknown"

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                
            search_lines = lines[-50:] 
            dialog_pattern = re.compile(r"^\s*\[\d{2}:\d{2}:\d{2}\]\s*([^\]]+?)\s*sagt[:\.]", re.IGNORECASE)
            
            npc_name = "Unknown"
            
            for line in reversed(search_lines):
                match = dialog_pattern.search(line)
                if match:
                    raw_name = match.group(1).strip()
                    clean_name = re.sub(r'\[.*?\]', '', raw_name).strip()
                    
                    if clean_name:
                        npc_name = clean_name
                        break
            
            gender = "Female" if any(x in npc_name.lower() for x in ["frau", "lady", "she"]) else "Male"

            if npc_name == "Unknown" and lines:
                 last = lines[-1].strip()
                 gender = "Female" if any(x in last.lower() for x in ["female", "frau", "she"]) else "Male"
                 return last, gender

            return npc_name, gender

        except Exception as e: 
            log_message(f"Fehler bei NPC-Erkennung: {e}")
            return "Unknown", "Unknown"

    def _play_audio_thread(self, filepath):
        """Spielt die Audiodatei im Hintergrund ab."""
        try:
            if not pygame.mixer.get_init():
                 pygame.mixer.init()
                 
            if pygame.mixer.music.get_busy():
                 pygame.mixer.music.stop() 

            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
                
            pygame.mixer.music.unload()

        except Exception as e:
            log_message(f"Fehler beim Abspielen: {e}")

    def generate_and_play(self, text, voice_id, cache_file, delay, name, method):
        
        if delay > 0: time.sleep(delay)

        if os.path.exists(cache_file):
            log_message("Spiele aus Cache...")
            threading.Thread(target=self._play_audio_thread, args=(cache_file,)).start()
            return
        
        if method == "NOTFALL (Rachel)": 
            log_message(f"WARNUNG: Notfall-Stimme verwendet. API Key prüfen!")

        log_message(f"Generiere neu: '{name}' ({method})")
        try:
            voice_settings = self.config.get("voice_settings", {"stability": 0.5, "similarity_boost": 0.75})
            
            headers = {"xi-api-key": self.config.get("api_key", ""), "Content-Type": "application/json"}
            data = {"text": text, "model_id": "eleven_turbo_v2_5", "voice_settings": voice_settings}
            
            resp = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", headers=headers, json=data)
            
            if resp.status_code == 200:
                with open(cache_file, "wb") as f: f.write(resp.content)
                threading.Thread(target=self._play_audio_thread, args=(cache_file,)).start()
            else:
                error_detail = resp.json().get('detail', 'Keine Details verfügbar.') if 'application/json' in resp.headers.get('Content-Type', '') else resp.text
                log_message(f"API Fehler ({resp.status_code}): {error_detail}")
        except RequestException as e:
            log_message(f"Netzwerkfehler bei TTS-Generierung: {e}")
        except Exception as e:
            log_message(f"TTS Fehler: {e}")

    def play_audio_file(self, filepath):
        """Öffentliche Schnittstelle für die Wiedergabe, startet den Thread."""
        threading.Thread(target=self._play_audio_thread, args=(filepath,)).start()


def toggle_pause(self):
        """Pausiert oder setzt die Wiedergabe fort."""
        try:
            if not pygame.mixer.get_init():
                return

            if pygame.mixer.music.get_busy():
                # Musik läuft -> Pausieren
                log_message("Audio pausiert.")
                pygame.mixer.music.pause()
            else:
                # Prüfen, ob wir im Pause-Zustand sind (get_pos > 0 bedeutet es lief schon was)
                # Leider gibt get_busy() bei Pause False zurück. Wir versuchen unpause.
                # Ein 'blindes' Unpause schadet nicht.
                log_message("Audio fortgesetzt.")
                pygame.mixer.music.unpause()
        except Exception as e:
            log_message(f"Fehler beim Pausieren: {e}")
