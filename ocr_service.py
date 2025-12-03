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
        
        # Tesseract Initialisierung
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

    def crop_to_text_content(self, binary_img):
        """Schneidet leere Ränder weg."""
        inverted = cv2.bitwise_not(binary_img)
        contours, _ = cv2.findContours(inverted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours: return binary_img 

        min_x = binary_img.shape[1]
        min_y = binary_img.shape[0]
        max_x = 0
        max_y = 0

        found = False
        for c in contours:
            if cv2.contourArea(c) < 50: continue
            x, y, w, h = cv2.boundingRect(c)
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)
            found = True

        if not found: return binary_img

        padding = 10
        min_x = max(0, min_x - padding)
        min_y = max(0, min_y - padding)
        max_x = min(binary_img.shape[1], max_x + padding)
        max_y = min(binary_img.shape[0], max_y + padding)

        return binary_img[min_y:max_y, min_x:max_x]

    def find_text_region(self, img):
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
            
            # --- ÄNDERUNG HIER: PADDING RECHTS ERHÖHT ---
            # Vorher: padding = 10 für alle Seiten
            # Jetzt: Speziell rechts (+50) und unten (+20) mehr Platz lassen
            padding_top_left = 10
            padding_right = 50   # 50 Pixel mehr Platz nach rechts!
            padding_bottom = 20  # Etwas mehr Platz nach unten

            final_x1 = max(0, final_x1 - padding_top_left)
            final_y1 = max(0, final_y1 - padding_top_left)
            
            # Hier geben wir rechts ordentlich was dazu
            final_x2 = min(w_img, final_x2 + padding_right)
            final_y2 = min(h_img, final_y2 + padding_bottom)

            w_final = final_x2 - final_x1
            h_final = final_y2 - final_y1

            dialog_region = img[final_y1:final_y2, final_x1:final_x2]
            
            if w_final < 50 or h_final < 50: return None, None
            
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

        if self.config.get("debug_mode", False):
            try: 
                (x, y, w, h) = coords
                debug_full = img.copy()
                cv2.rectangle(debug_full, (x, y), (x + w, y + h), (0, 0, 255), 3) 
                cv2.imwrite("debug_detection_view.png", debug_full)
            except: pass

        processed_img = self.isolate_text_colors(cropped_img)
        
        # crop_to_text_content schneidet überschüssigen Rand sowieso wieder weg,
        # daher ist das extra Padding oben sicher!
        processed_img = self.crop_to_text_content(processed_img)

        # Upscaling
        processed_img = cv2.resize(processed_img, None, fx=4.0, fy=3.0, interpolation=cv2.INTER_LINEAR)
        _, processed_img = cv2.threshold(processed_img, 127, 255, cv2.THRESH_BINARY)

        if self.config.get("debug_mode", False):
            try: cv2.imwrite("debug_ocr_input.png", processed_img)
            except: pass

        psm = self.config.get("ocr_psm", 11)
        lang = self.config.get("ocr_language", "deu") 
        whitelist = self.config.get("ocr_whitelist", "")
        
        custom_config = f'--psm {psm} -c preserve_interword_spaces=1'
        if whitelist and len(whitelist) > 5:
            custom_config += f' -c tessedit_char_whitelist="{whitelist}"'
            
        try:
            txt = pytesseract.image_to_string(processed_img, lang=lang, config=custom_config)
            result = txt.strip()
            
            if self.config.get("debug_mode", False):
                try:
                    with open("debug_ocr_text.txt", "w", encoding="utf-8") as f:
                        f.write(f"--- OCR ROHDATEN ---\nConfig: {custom_config}\nErgebnis:\n{result}")
                except: pass

            if not result: return "Kein Text gefunden"
            
            result = " ".join(result.split())
            return result
        except Exception as e:
            log_message(f"OCR Fehler: {e}")
            return "Kein Text gefunden"
