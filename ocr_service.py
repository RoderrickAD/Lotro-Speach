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

        # KORRIGIERTE BILDVERARBEITUNG FÜR OPTIMIERTE OCR 
        final_image_gray = cv2.cvtColor(dialog_region, cv2.COLOR_BGR2GRAY)
        
        # 1. Kontrastverbesserung (CLAHE)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrasted = clahe.apply(final_image_gray)
        
        # 2. Stärkere Rauschunterdrückung
        denoised = cv2.medianBlur(contrasted, 3) 
        
        # 3. STATT AGGRESSIVER BINARISIERUNG: Einfacher Schwellenwert
        # cv2.THRESH_BINARY_INV: Erzeugt WEISSEN TEXT auf SCHWARZEM GRUND (optimal für den LOTRO-Text).
        # Schwellenwert 180 ist ein guter Startpunkt für gold-weißen Text auf dunklem Hintergrund.
        ret, optimized_img = cv2.threshold(denoised, 180, 255, cv2.THRESH_BINARY_INV) 

        # Die vorherige Zeile cv2.bitwise_not(optimized_img) wurde entfernt.
        
        if self.config.get("debug_mode", False):
            cv2.imwrite("last_detection_debug_corrected.png", optimized_img)
        
        return optimized_img 

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
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
        dilated = cv2.dilate(mask, kernel, iterations=2)
        
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return cv2.cvtColor(potential_dialog_area, cv2.COLOR_BGR2GRAY)
        
        valid_contours = [c for c in contours if cv2.contourArea(c) > 5000]
        if not valid_contours:
            return cv2.cvtColor(potential_dialog_area, cv2.COLOR_BGR2GRAY)
            
        best_cnt = max(valid_contours, key=cv2.contourArea)

        rx, ry, rw, rh = cv2.boundingRect(best_cnt)
        pad = 5
        rx1 = max(0, rx - pad)
        ry1 = max(0, ry - pad)
        rx2 = min(potential_dialog_area.shape[1], rx + rw + pad)
        ry2 = min(potential_dialog_area.shape[0], ry + rh + pad)
        
        cropped_roi = potential_dialog_area[ry1:ry2, rx1:rx2]
        cropped_mask = mask[ry1:ry2, rx1:rx2]
        
        masked_image = cv2.bitwise_and(cropped_roi, cropped_roi, mask=cropped_mask)
        
        final_image = self.crop_to_content(masked_image)
        
        if self.config.get("debug_mode", False):
            cv2.imwrite("last_detection_debug_fallback.png", final_image)
        
        gray_image = cv2.cvtColor(final_image, cv2.COLOR_BGR2GRAY)
        denoised = cv2.medianBlur(gray_image, 3)
        return denoised

    def run_ocr(self):
        try:
            img = self.get_monitor_screenshot()
            if img is None: 
                return ""
            
            if self.config.get("debug_mode", False):
                cv2.imwrite("last_screenshot_debug_original.png", img)

            optimized_img = self.auto_find_quest_text(img)
            
            ocr_lang = self.config.get("ocr_language", "deu+eng")
            ocr_psm = self.config.get("ocr_psm", 6)
            
            whitelist = self.config.get("ocr_whitelist", 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzäöüÄÖÜß0123456789.,?!:;\'"()[]-/')

            config = f'--oem 3 --psm {ocr_psm} -l {ocr_lang} -c tessedit_char_whitelist="{whitelist}"'
            
            raw_text = pytesseract.image_to_string(optimized_img, config=config)
            
            lines = raw_text.split('\n')
            
            cleaned_lines = self._filter_recognized_lines(lines)

            clean_output = ' '.join(cleaned_lines)
            clean_output = re.sub(r'\s+', ' ', clean_output).strip()
            
            clean_output = re.sub(r'(?:l|I|1)oo|o(?:l|I|1)|oo(?:l|I|1)', '', clean_output, flags=re.IGNORECASE) 
            clean_output = re.sub(r'oo|Oo|oO|Solo|solo|NYZ B|„Aa 1', '', clean_output)
            clean_output = re.sub(r'‘', "'", clean_output)
            
            if len(clean_output) < 10:
                return ""
            
            try:
                with open("last_recognized_text.txt", "w", encoding="utf-8") as f:
                    f.write("--- RAW TESSERACT OUTPUT ---\n")
                    f.write(raw_text)
                    f.write("\n\n--- FILTERED OUTPUT (SEND TO AI) ---\n")
                    f.write(clean_output)
            except: pass
            
            return clean_output
        except Exception as e:
            log_message(f"OCR Fehler: {e}")
            return ""
