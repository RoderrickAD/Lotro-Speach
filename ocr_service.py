import pytesseract
import cv2
import numpy as np
import mss 
import mss.tools 
import os
import google.generativeai as genai
from PIL import Image
from utils import log_message

class OCRExtractor:
    def __init__(self, config):
        self.config = config
        
        tess_path = self.config.get("tesseract_path", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        pytesseract.pytesseract.tesseract_cmd = tess_path
        
        self.ai_model = None
        self._setup_ai()
        self.templates = self._load_templates()

    def _setup_ai(self):
        """Initialisiert die KI mit Key und gewähltem Modell."""
        key = self.config.get("gemini_api_key", "").strip()
        model_name = self.config.get("gemini_model_name", "models/gemini-1.5-flash") # Fallback
        
        if key:
            try:
                genai.configure(api_key=key)
                self.ai_model = genai.GenerativeModel(model_name)
                log_message(f"KI konfiguriert mit Modell: {model_name}")
            except Exception as e:
                log_message(f"Fehler bei KI-Start: {e}")

    def fetch_available_models(self, api_key):
        """Fragt Google nach allen verfügbaren Modellen."""
        try:
            genai.configure(api_key=api_key)
            models = []
            for m in genai.list_models():
                # Wir wollen nur Modelle, die Content generieren können (keine Embedding-Modelle)
                if 'generateContent' in m.supported_generation_methods:
                    models.append(m.name)
            models.sort()
            return models
        except Exception as e:
            log_message(f"Fehler beim Laden der Modell-Liste: {e}")
            return []

    def _load_templates(self):
        template_dir = os.path.join(os.getcwd(), "templates")
        templates = {}
        names = ["top_left", "top_right", "bottom_right", "bottom_left"]
        if not os.path.exists(template_dir): return None
        success = True
        for name in names:
            fp = os.path.join(template_dir, f"{name}.png")
            if os.path.exists(fp): templates[name] = cv2.imread(fp, cv2.IMREAD_GRAYSCALE) 
            else: success = False
        return templates if (success and len(templates) == 4) else None
    
    def get_monitor_screenshot(self):
        try:
            mon_idx = int(self.config.get("monitor_index", 1))
        except: mon_idx = 1
        try:
            with mss.mss() as sct:
                if mon_idx >= len(sct.monitors): mon_idx = 1
                return cv2.cvtColor(np.array(sct.grab(sct.monitors[mon_idx])), cv2.COLOR_BGRA2BGR)
        except: return None

    def isolate_text_colors(self, img):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask_yellow = cv2.inRange(hsv, np.array([15, 70, 70]), np.array([35, 255, 255]))
        mask_white = cv2.inRange(hsv, np.array([0, 0, 140]), np.array([180, 50, 255]))
        return cv2.bitwise_not(cv2.bitwise_or(mask_yellow, mask_white))

    def crop_to_text_content(self, binary_img):
        inverted = cv2.bitwise_not(binary_img)
        contours, _ = cv2.findContours(inverted, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours: return binary_img 
        min_x, min_y = binary_img.shape[1], binary_img.shape[0]; max_x = max_y = 0; found = False
        for c in contours:
            if cv2.contourArea(c) < 50: continue
            x, y, w, h = cv2.boundingRect(c)
            min_x = min(min_x, x); min_y = min(min_y, y); max_x = max(max_x, x + w); max_y = max(max_y, y + h); found = True
        if not found: return binary_img
        pad = 10
        return binary_img[max(0, min_y-pad):min(binary_img.shape[0], max_y+pad), max(0, min_x-pad):min(binary_img.shape[1], max_x+pad)]

    def find_text_region(self, img):
        h_img, w_img = img.shape[:2]
        if self.templates is None: return None, None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        positions = {}
        for key, templ in self.templates.items():
            res = cv2.matchTemplate(gray, templ, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= 0.60: positions[key] = max_loc 
            else: return None, None
        if len(positions) < 4: return None, None
        try:
            def get_c(k, p): return p[0] + self.templates[k].shape[1]//2, p[1] + self.templates[k].shape[0]//2
            c_tl = get_c("top_left", positions["top_left"]); c_tr = get_c("top_right", positions["top_right"])
            c_bl = get_c("bottom_left", positions["bottom_left"]); c_br = get_c("bottom_right", positions["bottom_right"])
            pt = int(self.config.get("padding_top", 10)); pb = int(self.config.get("padding_bottom", 20))
            pl = int(self.config.get("padding_left", 10)); pr = int(self.config.get("padding_right", 50))
            x1 = max(0, int(min(c_tl[0], c_bl[0]) - pl)); y1 = max(0, int(min(c_tl[1], c_tr[1]) - pt))
            x2 = min(w_img, int(max(c_tr[0], c_br[0]) + pr)); y2 = min(h_img, int(max(c_bl[1], c_br[1]) + pb))
            if (x2-x1) < 50 or (y2-y1) < 50: return None, None
            return img[y1:y2, x1:x2], (x1, y1, x2-x1, y2-y1)
        except: return None, None

    def run_ai_recognition(self, img_crop):
        if not self.ai_model: 
            self._setup_ai() 
            if not self.ai_model: return "Fehler: Kein Gemini API Key konfiguriert."
        try:
            rgb_img = cv2.cvtColor(img_crop, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_img)
            prompt = "Lies den Quest-Text aus diesem Bild. Gib NUR den Text zurück, ohne Einleitung. Ignoriere Interface-Elemente. Achte penibel auf deutsche Umlaute."
            response = self.ai_model.generate_content([prompt, pil_img])
            return response.text.strip()
        except Exception as e:
            log_message(f"KI Anfrage fehlgeschlagen: {e}")
            return f"Fehler: {e}"

    def run_ocr(self):
        img = self.get_monitor_screenshot()
        if img is None: return "Kein Text gefunden", "System"

        cropped_img, coords = self.find_text_region(img)
        if cropped_img is None:
            log_message("Kein Dialog-Template erkannt.")
            return "Kein Text gefunden", "System"

        if self.config.get("debug_mode", False):
            try:
                (x, y, w, h) = coords
                debug_full = img.copy()
                cv2.rectangle(debug_full, (x, y), (x+w, y+h), (0, 255, 0), 3)
                cv2.imwrite("debug_detection_view.png", debug_full)
                cv2.imwrite("debug_ocr_input.png", cropped_img)
            except: pass

        use_ai = self.config.get("use_ai_ocr", False)
        
        if use_ai:
            log_message(f"Starte KI-Erkennung ({self.config.get('gemini_model_name', 'Default')})...")
            return self.run_ai_recognition(cropped_img), "Gemini AI"
        else:
            processed_img = self.isolate_text_colors(cropped_img)
            processed_img = self.crop_to_text_content(processed_img)
            processed_img = cv2.resize(processed_img, None, fx=4.0, fy=3.0, interpolation=cv2.INTER_LINEAR)
            _, processed_img = cv2.threshold(processed_img, 127, 255, cv2.THRESH_BINARY)
            
            if self.config.get("debug_mode", False):
                try: cv2.imwrite("debug_ocr_input.png", processed_img)
                except: pass

            psm = self.config.get("ocr_psm", 6)
            lang = self.config.get("ocr_language", "deu+eng")
            custom_config = f'--psm {psm} -c preserve_interword_spaces=1'
            whitelist = self.config.get("ocr_whitelist", "")
            if whitelist and len(whitelist) > 5: custom_config += f' -c tessedit_char_whitelist="{whitelist}"'
            
            try:
                txt = pytesseract.image_to_string(processed_img, lang=lang, config=custom_config)
                return " ".join(txt.strip().split()), "Tesseract OCR"
            except Exception as e:
                log_message(f"Tesseract Fehler: {e}")
                return "Kein Text gefunden", "Fehler"
