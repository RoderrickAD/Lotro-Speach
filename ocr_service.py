import pytesseract
import cv2
import numpy as np
import mss 
import mss.tools 
import re
import os
from utils import log_message

class OCRExtractor:
    def __init__(self, config):
        self.config = config
        
        # Tesseract muss hier initialisiert werden
        tess_path = self.config.get("tesseract_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        pytesseract.pytesseract.tesseract_cmd = tess_path
        
        # Lade Templates für Template Matching
        self.templates = self._load_templates()

    def _load_templates(self):
        """Lädt die Template-Bilder aus dem 'templates'-Ordner als Graustufen."""
        template_dir = os.path.join(os.getcwd(), "templates")
        templates = {}
        template_names = {
            "top_left": "top_left.png",
            "top_right": "top_right.png",
            "bottom_right": "bottom_right.png",
            "bottom_left": "bottom_left.png"
        }

        if not os.path.exists(template_dir):
            return None

        success = True
        for key, filename in template_names.items():
            filepath = os.path.join(template_dir, filename)
            if os.path.exists(filepath):
                templates[key] = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE) 
            else:
                success = False
        
        if success and len(templates) == 4:
            return templates
        else:
            return None
    
    def get_monitor_screenshot(self):
        try:
            mon_idx = int(self.config.get("monitor_index", 1))
        except ValueError:
            mon_idx = 1
            
        try:
            with mss.mss() as sct:
                if mon_idx >= len(sct.monitors) or mon_idx < 1: mon_idx = 1 
                monitor = sct.monitors[mon_idx]
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                return img
        except Exception as e:
            log_message(f"Screenshot Fehler: {e}")
            return None
        
    def auto_find_quest_text(self, img):
        # Falls keine Templates da sind oder Template Matching fehlschlägt, Fallback nutzen
        if self.templates is None:
            return self._fallback_auto_find_quest_text(img)
            
        # Hier könnte Template-Matching Code stehen.
        # Wir nutzen vorerst den robusten Fallback, da er weniger fehleranfällig ist.
        return self._fallback_auto_find_quest_text(img)

    def _fallback_auto_find_quest_text(self, img):
        """Die Standard-Methode zur Erkennung des Quest-Textes."""
        h_img, w_img = img.shape[:2]
        
        if h_img < 50 or w_img < 50: return img

        crop_top = int(h_img * 0.12)  
        crop_bottom = int(h_img * 0.12)
        crop_left = int(w_img * 0.18) 
        crop_right = int(w_img * 0.05)

        if (crop_top >= h_img - crop_bottom) or (crop_left >= w_img - crop_right):
            potential_dialog_area = img
        else:
            potential_dialog_area = img[crop_top:h_img-crop_bottom, crop_left:w_img-crop_right]

        # Bildverarbeitung
        gray = cv2.cvtColor(potential_dialog_area, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        # HIER WAR DER FEHLER - JETZT KORRIGIERT:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
        dilated = cv2.dilate(mask, kernel, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        final_result = potential_dialog_area
        
        if contours:
            c = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            # Etwas Padding und Prüfen ob Rechteck sinnvoll ist
            if w > 50 and h > 20:
                final_result = potential_dialog_area[y:y+h, x:x+w]

        # --- DEBUG BILD SPEICHERN (NEU) ---
        if self.config.get("debug_mode", False):
            try:
                debug_path = os.path.join(os.getcwd(), "last_detection_debug.png")
                cv2.imwrite(debug_path, final_result)
                log_message(f"Debug-Bild gespeichert: {debug_path}")
            except Exception as e:
                log_message(f"Konnte Debug-Bild nicht speichern: {e}")
        # ----------------------------------

        return final_result

    def run_ocr(self):
        """Wird von core.py aufgerufen."""
        img = self.get_monitor_screenshot()
        if img is None: return ""

        cropped_img = self.auto_find_quest_text(img)
        gray = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
        
        # Tesseract Konfiguration
        custom_config = f'--psm {self.config.get("ocr_psm", 6)}'
        whitelist = self.config.get("ocr_whitelist", "")
        if whitelist and len(whitelist) > 5:
            custom_config += f' -c tessedit_char_whitelist="{whitelist}"'
            
        try:
            txt = pytesseract.image_to_string(gray, lang=self.config.get("ocr_language", "deu+eng"), config=custom_config)
            return txt.strip()
        except Exception as e:
            log_message(f"OCR Fehler: {e}")
            return ""
