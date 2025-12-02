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

        # Falls Ordner nicht existiert, direkt abbrechen
        if not os.path.exists(template_dir):
            return None

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
                # log_message(f"FEHLER: Template '{filepath}' nicht gefunden.") # Optional logging
                success = False
                break

        if success and len(templates) == len(template_names):
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
                # Validierung des Monitor-Index
                if mon_idx >= len(sct.monitors) or mon_idx < 1: 
                    mon_idx = 1 
                
                monitor = sct.monitors[mon_idx]
                sct_img = sct.grab(monitor)
                img = np.array(sct_img)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                return img
        except Exception as e:
            log_message(f"Screenshot Fehler: {e}")
            return None
    
    def auto_find_quest_text(self, img):
        if self.templates is None:
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
                return self._fallback_auto_find_quest_text(img) 

        if len(found_positions) < 4:
            return self._fallback_auto_find_quest_text(img)

        # Koordinaten berechnen
        try:
            final_x1 = min(found_positions["top_left"][0], found_positions["bottom_left"][0])
            final_y1 = min(found_positions["top_left"][1], found_positions["top_right"][1])
            
            # Breite/Höhe der Templates berücksichtigen
            h_tr, w_tr = self.templates["top_right"].shape
            h_br, w_br = self.templates["bottom_right"].shape
            h_bl, w_bl = self.templates["bottom_left"].shape
            
            final_x2 = max(found_positions["top_right"][0] + w_tr, found_positions["bottom_right"][0] + w_br)
            final_y2 = max(found_positions["bottom_left"][1] + h_bl, found_positions["bottom_right"][1] + h_br)
            
            padding = 10
            final_x1 = max(0, final_x1 - padding)
            final_y1 = max(0, final_y1 - padding)
            final_x2 = min(img.shape[1], final_x2 + padding)
            final_y2 = min(img.shape[0], final_y2 + padding)

            dialog_region = img[final_y1:final_y2, final_x1:final_x2]
            
            if dialog_region.shape[0] < 50 or dialog_region.shape[1] < 50:
                return self._fallback_auto_find_quest_text(img)
            
            log_message(f"Dialograhmen gefunden: ({final_x1}, {final_y1})")
            return dialog_region
            
        except Exception as e:
            log_message(f"Fehler bei Template-Berechnung: {e}")
            return self._fallback_auto_find_quest_text(img)

    def _fallback_auto_find_quest_text(self, img):
        """Die ursprüngliche Methode zur Erkennung des Quest-Textes, als Fallback."""
        h_img, w_img = img.shape[:2]
        
        if h_img < 50 or w_img < 50: return img

        # Grober Crop, um UI-Elemente außen zu ignorieren
        crop_top = int(h_img * 0.12)  
        crop_bottom = int(h_img * 0.12)
        crop_left = int(w_img * 0.18) 
        crop_right = int(w_img * 0.05)

        if (crop_top >= h_img - crop_bottom) or (crop_left >= w_img - crop_right):
            potential_dialog_area = img
        else:
            potential_dialog_area = img[crop_top:h_img-crop_bottom, crop_left:w_img-crop_right]

        if potential_dialog_area.shape[0] < 50 or potential_dialog_area.shape[1] < 50:
            return img

        # Hier war dein Code abgebrochen - hier ist der Fix:
        gray = cv2.cvtColor(potential_dialog_area, cv2.COLOR_BGR2GRAY)
        
        # Versuche weiße Textbereiche zu finden
        _, mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,5))
        dilated = cv2.dilate(mask, kernel, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            # Den größten Bereich finden (wahrscheinlich der Textblock)
            c = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            # Ausschnitt zurückgeben
            return potential_dialog_area[y:y+h, x:x+w]
            
        return potential_dialog_area

    def run_ocr(self):
        """Hauptfunktion, die von core.py aufgerufen wird."""
        img = self.get_monitor_screenshot()
        if img is None:
            log_message("Kein Screenshot möglich.")
            return ""
        
        # Bereich finden
        cropped_img = self.auto_find_quest_text(img)
        
        # Vorverarbeitung für Tesseract
        gray = cv2.cvtColor(cropped_img, cv2.COLOR_BGR2GRAY)
        # Optional: Thresholding, falls nötig
        # _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Konfiguration
        psm = self.config.get("ocr_psm", 6)
        lang = self.config.get("ocr_language", "deu+eng")
        whitelist = self.config.get("ocr_whitelist", "")
        
        custom_config = f'--psm {psm}'
        if whitelist and len(whitelist) > 5:
             custom_config += f' -c tessedit_char_whitelist="{whitelist}"'
             
        try:
            txt = pytesseract.image_to_string(gray, lang=lang, config=custom_config)
            return txt.strip()
        except Exception as e:
            log_message(f"OCR Fehler: {e}")
            return ""
