import pytesseract
import cv2
import numpy as np
import mss 
import mss.tools 
import os
from utils import log_message

class OCRExtractor:
    def __init__(self, config):
        self.config = config
        
        # Tesseract Pfad setzen
        tess_path = self.config.get("tesseract_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        pytesseract.pytesseract.tesseract_cmd = tess_path
        
        self.templates = self._load_templates()

    def _load_templates(self):
        """Lädt Templates aus dem Ordner."""
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

    def isolate_text_colors(self, img):
        """
        Filtert Farben und invertiert das Bild (Schwarz auf Weiß).
        """
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 1. Gelb / Gold
        lower_yellow = np.array([15, 70, 70])
        upper_yellow = np.array([35, 255, 255])
        mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

        # 2. Weiß / Silber / Hellgrau
        lower_white = np.array([0, 0, 140])      
        upper_white = np.array([180, 50, 255])   
        mask_white = cv2.inRange(hsv, lower_white, upper_white)

        combined_mask = cv2.bitwise_or(mask_yellow, mask_white)
        final_image = cv2.bitwise_not(combined_mask)

        return final_image

    def find_text_region(self, img):
        """Findet den Bereich per Template."""
        h_img, w_img = img.shape[:2]

        if self.templates is None:
            return None, None

        gray_screenshot = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        found_positions = {}
        threshold = 0.80

        for key, template_img in self.templates.items():
            res = cv2.matchTemplate(gray_screenshot, template_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= threshold:
                found_positions[key] = max_loc 
            else:
                return None, None

        if len(found_positions) < 4:
            return None, None

        try:
            h_tr, w_tr = self.templates["top_right"].shape
            h_br, w_br = self.templates["bottom_right"].shape
            h_bl, w_bl = self.templates["bottom_left"].shape

            final_x1 = min(found_positions["top_left"][0], found_positions["bottom_left"][0])
            final_y1 = min(found_positions["top_left"][1], found_positions["top_right"][1])
            final_x2 = max(found_positions["top_right"][0] + w_tr, found_positions["bottom_right"][0] + w_br)
            final_y2 = max(found_positions["bottom_left"][1] + h_bl, found_positions["bottom_right"][1] + h_br)
            
            padding = 10
            final_x1 = max(0, final_x1 - padding)
            final_y1 = max(0, final_y1 - padding)
            final_x2 = min(w_img, final_x2 + padding)
            final_y2 = min(h_img, final_y2 + padding)

            w_final = final_x2 - final_x1
            h_final = final_y2 - final_y1

            dialog_region = img[final_y1:final_y2, final_x1:final_x2]
            
            if w_final < 50 or h_final < 50:
                return None, None
            
            log_message(f"Templates gefunden. Bereich: {w_final}x{h_final}")
            return dialog_region, (final_x1, final_y1, w_final, h_final)
            
        except Exception as e:
            log_message(f"Fehler bei Template-Berechnung: {e}")
            return None, None

    def run_ocr(self):
        img = self.get_monitor_screenshot()
        if img is None: return "Kein Text gefunden"

        cropped_img, coords = self.find_text_region(img)
        
        if cropped_img is None:
            log_message("Kein Dialog-Template erkannt.")
            return "Kein Text gefunden"

        # --- DEBUG BILD 1: Ausschnitt ---
        if self.config.get("debug_mode", False):
            try:
                cv2.imwrite("debug_detection_view.png", cropped_img)
            except: pass

        # Bildverarbeitung (Farben filtern)
        processed_img = self.isolate_text_colors(cropped_img)

        # === NEU: UPSCALING FÜR BESSERE UMLAUTE ===
        # Vergrößert das Bild um Faktor 2.5 mit kubischer Interpolation.
        # Das hilft Tesseract extrem bei Punkten auf i, ö, ä, ü.
        processed_img = cv2.resize(processed_img, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        
        # Optional: Leichtes Weichzeichnen nach Upscale entfernt Pixel-Artefakte
        # processed_img = cv2.GaussianBlur(processed_img, (3, 3), 0)

        # --- DEBUG BILD 2: OCR Input (Vergrößert) ---
        if self.config.get("debug_mode", False):
            try:
                cv2.imwrite("debug_ocr_input.png", processed_img)
            except: pass

        # Tesseract Config
        psm = self.config.get("ocr_psm", 6)
        # Stelle sicher, dass "deu" genutzt wird für Umlaute!
        lang = self.config.get("ocr_language", "deu+eng") 
        whitelist = self.config.get("ocr_whitelist", "")
        
        custom_config = f'--psm {psm}'
        
        # Whitelist ist gefährlich für Umlaute, wenn man sie in der Config falsch eingibt.
        # Wenn Umlaute fehlen, lösche den Inhalt der Whitelist in den Einstellungen!
        if whitelist and len(whitelist) > 5:
            custom_config += f' -c tessedit_char_whitelist="{whitelist}"'
            
        try:
            txt = pytesseract.image_to_string(processed_img, lang=lang, config=custom_config)
            result = txt.strip()
            
            # === NEU: DEBUG TEXT DATEI ===
            if self.config.get("debug_mode", False):
                try:
                    with open("debug_ocr_text.txt", "w", encoding="utf-8") as f:
                        f.write(f"--- OCR ROHDATEN ---\nConfig: {custom_config}\nSprache: {lang}\n\nErgebnis:\n{result}")
                        log_message("Debug-Text in 'debug_ocr_text.txt' gespeichert.")
                except Exception as e:
                    log_message(f"Konnte Debug-Text nicht speichern: {e}")
            # ==============================

            if not result: return "Kein Text gefunden"
            return result
        except Exception as e:
            log_message(f"OCR Fehler: {e}")
            return "Kein Text gefunden"
