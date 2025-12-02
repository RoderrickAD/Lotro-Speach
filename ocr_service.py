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

        success = True
        for key, filename in template_names.items():
            filepath = os.path.join(template_dir, filename)
            if os.path.exists(filepath):
                templates[key] = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE) 
                
                if templates[key] is None or templates[key].size == 0:
                    log_message(f"WARNUNG: Konnte Template '{filepath}' nicht laden oder Bild ist leer.")
                    success = False
                    break 
            else:
                log_message(f"FEHLER: Template '{filepath}' nicht gefunden.")
                success = False
                break

        if success and len(templates) == len(template_names):
            return templates
        else:
            log_message("FEHLER: Nicht alle Templates konnten geladen werden. Template Matching deaktiviert.")
            return None
    
    # Restliche Hilfsmethoden (get_monitor_screenshot, crop_to_content)

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
    
    def crop_to_content(self, img):
        """Trimmt schwarze/leere Ränder um das gefundene Textbild."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        denoised = cv2.medianBlur(gray, 5) 
        
        coords = cv2.findNonZero(denoised)
        if coords is not None:
            x, y, w, h = cv2.boundingRect(coords)
            
            pad = 5
            h_img, w_img = img.shape[:2]
            
            x = max(0, x - pad)
            y = max(0, y - pad)
            w = min(w_img - x, w + 2*pad)
            h = min(h_img - y, h + 2*pad)
            
            return img[y:y+h, x:x+w]
        
        return img
        
    def _filter_recognized_lines(self, raw_lines):
        """Filtert und bereinigt die Zeilen des rohen Tesseract-Outputs."""
        cleaned_lines = []
        for line in raw_lines:
            stripped = line.strip()
            if not stripped: continue
            
            is_dialog_start_end = stripped.startswith(('"', "'")) or stripped.endswith(('"', "'"))
            is_dialog_end_punc = stripped.endswith((".", "!", "?"))
            
            if (is_dialog_start_end or is_dialog_end_punc) or len(stripped) > 20:
                cleaned_lines.append(stripped)
                
        return cleaned_lines

    def auto_find_quest_text(self, img):
        if self.templates is None:
            log_message("Template Matching nicht verfügbar. Fallback auf frühere Methode.")
            return self._fallback_auto_find_quest_text(img)

        gray_screenshot = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        found_positions = {}
        threshold = 0.80

        for key, template_img in self.templates.items():
            if template_img is None: continue
            
            res = cv2.matchTemplate(gray_screenshot, template_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                found_positions[key] = max_loc 
            else:
                log_message(f"WARNUNG: Template '{key}' wurde nicht mit ausreichender Genauigkeit ({max_val:.2f}) gefunden. Fallback.")
                return self._fallback_auto_find_quest_text(img) 

        if len(found_positions) < 4:
            log_message("WARNUNG: Nicht alle vier Ecken-Templates gefunden. Fallback.")
            return self._fallback_auto_find_quest_text(img)

        final_x1 = min(found_positions["top_left"][0], found_positions["bottom_left"][0])
        final_y1 = min(found_positions["top_left"][1], found_positions["top_right"][1])
        final_x2 = max(found_positions["top_right"][0] + self.templates["top_right"].shape[1], 
                       found_positions["bottom_right"][0] + self.templates["bottom_right"].shape[1])
        final_y2 = max(found_positions["bottom_left"][1] + self.templates["bottom_left"].shape[0], 
                       found_positions["bottom_right"][1] + self.templates["bottom_right"].shape[0])
        
        padding = 10
        final_x1 = max(0, final_x1 - padding)
        final_y1 = max(0, final_y1 - padding)
        final_x2 = min(img.shape[1], final_x2 + padding)
        final_y2 = min(img.shape[0], final_y2 + padding)

        dialog_region = img[final_y1:final_y2, final_x1:final_x2]
        
        if dialog_region.shape[0] < 50 or dialog_region.shape[1] < 50:
            log_message("WARNUNG: Gefundener Dialogbereich ist zu klein. Fallback.")
            return self._fallback_auto_find_quest_text(img)
        
        log_message(f"Dialograhmen mittels Template Matching gefunden: ({final_x1}, {final_y1}) bis ({final_x2}, {final_y2})")

        # HIER IST DIE KORREKTUR: Sende das zugeschnittene Originalbild
        
        if self.config.get("debug_mode", False):
            # Speichere das Originalbild als Debug-Ausgabe
            cv2.imwrite("last_detection_debug_corrected.png", dialog_region)
        
        # Gebe das Originalbild zurück, ohne Bildverarbeitung
        return dialog_region 

    def _fallback_auto_find_quest_text(self, img):
        """Die ursprüngliche Methode zur Erkennung des Quest-Textes, als Fallback."""
        log_message("Führe Fallback-Text-Erkennung aus.")
        h_img, w_img = img.shape[:2]
        
        if h_img < 50 or w_img < 50: return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        crop_top = int(h_img * 0.12)  
        crop_bottom = int(h_img * 0.12)
        crop_left = int(w_img * 0.18) 
        crop_right = int(w_img * 0.05)

        if (crop_top >= h_img - crop_bottom) or (crop_left >= w_img - crop_right):
            potential_dialog_area = img
        else:
            potential_dialog_area = img[crop_top:h_img-crop_bottom, crop_left:w_img-crop_right]

        if potential_dialog_area.shape[0] < 50 or potential_dialog_area.shape[1] < 50:
            potential_dialog_area = img

        hsv = cv2.cvtColor(potential_dialog_area, cv2.COLOR_BGR2HSV)
        lower_white = np.array([0, 0, 160]) 
        upper_white = np.array([180, 50, 255]) 
        mask = cv2.inRange(hsv, lower_white, upper_white)
        
        kernel = cv2.
