import hashlib
import os
import time
import difflib
import threading
import json
from utils import load_config, load_mapping, save_mapping, log_message
from ocr_service import OCRExtractor
from tts_service import TTSService

MAX_CACHE_SIZE_BYTES = 1024 * 1024 * 1024 

class CoreEngine:
    def __init__(self):
        self.config = load_config()
        self.ocr_extractor = OCRExtractor(self.config)
        self.tts_service = TTSService(self.config)
        self.voices = []
        self.cache_dir = os.path.join(os.getcwd(), "AudioCache")
        if not os.path.exists(self.cache_dir): os.makedirs(self.cache_dir)
        threading.Thread(target=self._clean_cache, daemon=True).start()
        threading.Thread(target=self.fetch_voices, daemon=True).start()

    def _clean_cache(self):
        total_size = 0; file_details = []
        for root, _, files in os.walk(self.cache_dir):
            for name in files:
                filepath = os.path.join(root, name)
                if os.path.exists(filepath):
                    stat = os.stat(filepath); total_size += stat.st_size; file_details.append((filepath, stat.st_mtime))
        if total_size > MAX_CACHE_SIZE_BYTES:
            file_details.sort(key=lambda x: x[1])
            for filepath, _ in file_details:
                if total_size <= MAX_CACHE_SIZE_BYTES: break
                try: size = os.path.getsize(filepath); os.remove(filepath); total_size -= size
                except: pass

    def fetch_voices(self):
        self.voices = self.tts_service.fetch_voices(); return self.voices

    def get_npc_from_log(self): return self.tts_service.get_npc_from_log()

    def select_voice(self, npc_name, npc_gender):
        if not self.voices:
            self.fetch_voices()
            if not self.voices: return "21m00Tcm4TlvDq8ikWAM", "NOTFALL (Rachel)" 
        mapping = load_mapping()
        if npc_name in mapping: return mapping[npc_name], "Gedächtnis"
        filtered = [v for v in self.voices if npc_gender.lower() in v.get('labels', {}).get('gender', '').lower()]
        if not filtered: filtered = self.voices
        idx = int(hashlib.md5(npc_name.encode('utf-8')).hexdigest(), 16) % len(filtered)
        vid = filtered[idx]['voice_id']
        mapping[npc_name] = vid; save_mapping(mapping)
        return vid, "Berechnet"

    def run_pipeline(self, skip_audio=False):
        # 1. OCR mit Quellen-Info
        # Änderung: Wir entpacken das Tuple (text, source)
        txt, source = self.ocr_extractor.run_ocr()
        
        if not txt or len(txt) < 5 or "Kein Text" in txt:
            return txt, source

        if skip_audio:
            return txt, source

        # 2. TTS
        npc_log, gender = self.get_npc_from_log()
        name = npc_log if npc_log != "Unknown" else "Unknown"
        vid, method = self.select_voice(name, gender)

        delay = float(self.config.get("audio_delay", 0.5))
        cache_key = f"{txt}_{vid}" 
        text_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()
        cache_file = os.path.join(self.cache_dir, f"quest_{text_hash}.mp3")

        self.tts_service.generate_and_play(
            text=txt, voice_id=vid, cache_file=cache_file, delay=delay, name=name, method=method
        )
        
        # Gebe Text und Quelle zurück
        return txt, source
