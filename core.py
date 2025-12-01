import hashlib
import os
import time
import difflib
import threading
import json
from utils import load_config, load_mapping, save_mapping, log_message
from ocr_service import OCRExtractor
from tts_service import TTSService

# Konstante für die maximale Cache-Größe in Bytes (ca. 1 GB)
MAX_CACHE_SIZE_BYTES = 1024 * 1024 * 1024 

class CoreEngine:
    def __init__(self):
        self.config = load_config()
        
        # Komponenten-Injektion
        self.ocr_extractor = OCRExtractor(self.config)
        self.tts_service = TTSService(self.config)
        
        self.voices = []
        self.cache_dir = os.path.join(os.getcwd(), "AudioCache")
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        
        # Starte Cache-Bereinigung asynchron (UX Verbesserung)
        threading.Thread(target=self._clean_cache, daemon=True).start()
        
        # Lade Stimmen beim Start (asynchron)
        threading.Thread(target=self.fetch_voices, daemon=True).start()

    def _clean_cache(self):
        """Löscht die ältesten Dateien, wenn der Cache die MAX_CACHE_SIZE überschreitet."""
        # Logik bleibt gleich, läuft jetzt im Daemon-Thread
        total_size = 0
        file_details = []
        
        for root, _, files in os.walk(self.cache_dir):
            for name in files:
                filepath = os.path.join(root, name)
                if os.path.exists(filepath):
                    stat = os.stat(filepath)
                    total_size += stat.st_size
                    file_details.append((filepath, stat.st_mtime))

        if total_size > MAX_CACHE_SIZE_BYTES:
            log_message(f"Cache-Größe ({total_size // (1024*1024)} MB) überschreitet Limit. Bereinige...")
            file_details.sort(key=lambda x: x[1])

            for filepath, _ in file_details:
                if total_size <= MAX_CACHE_SIZE_BYTES:
                    break
                
                try:
                    size = os.path.getsize(filepath)
                    os.remove(filepath)
                    total_size -= size
                    log_message(f"Gelöscht: {filepath}")
                except Exception as e:
                    log_message(f"Fehler beim Löschen von {filepath}: {e}")

    def is_new_text(self, new_text, old_text):
        if not new_text or len(new_text) < 15: return False
        if not old_text: return True
        ratio = difflib.SequenceMatcher(None, new_text, old_text).ratio()
        return ratio <= 0.85

    def fetch_voices(self):
        self.voices = self.tts_service.fetch_voices()
        return self.voices

    def get_npc_from_log(self):
        """Delegiert die Log-Analyse an den TTS Service."""
        return self.tts_service.get_npc_from_log()

    def select_voice(self, npc_name, npc_gender):
        if not self.voices:
            log_message("Keine Stimmen im Speicher. Versuche Laden...")
            self.fetch_voices()
            if not self.voices: 
                return "21m00Tcm4TlvDq8ikWAM", "NOTFALL (Rachel)" 

        mapping = load_mapping()
        if npc_name in mapping:
            return mapping[npc_name], "Gedächtnis"

        filtered = [v for v in self.voices if npc_gender.lower() in v.get('labels', {}).get('gender', '').lower()]
        if not filtered: filtered = self.voices
        
        idx = int(hashlib.md5(npc_name.encode('utf-8')).hexdigest(), 16) % len(filtered)
        vid = filtered[idx]['voice_id']
        mapping[npc_name] = vid
        save_mapping(mapping)
        return vid, "Berechnet"

    def run_pipeline(self):
        """Steuert den gesamten OCR- und TTS-Prozess."""
        
        # 1. OCR (Delegiert an OCRExtractor)
        txt = self.ocr_extractor.run_ocr()
        if not txt or len(txt) < 5:
            return ""

        # 2. TTS Vorbereitung
        npc_log, gender = self.get_npc_from_log()
        name = npc_log if npc_log != "Unknown" else "Unknown"
        vid, method = self.select_voice(name, gender)

        # 3. Caching und Wiedergabe (Delegiert an TTSService)
        delay = float(self.config.get("audio_delay", 0.5))
        
        cache_key = f"{txt}_{vid}" 
        text_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"quest_{text_hash}.mp3")

        self.tts_service.generate_and_play(
            text=txt, 
            voice_id=vid, 
            cache_file=cache_file, 
            delay=delay,
            name=name,
            method=method
        )
        
        return txt
