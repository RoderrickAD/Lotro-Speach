import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk  # pip install Pillow
import threading
import os
import cv2
import numpy as np
import keyboard
from core import CoreEngine
from utils import save_config, log_message

# --- LOTRO THEME COLORS ---
COLOR_BG_DARK = "#1a1110"
COLOR_BG_PANEL = "#2b221b"
COLOR_TEXT_GOLD = "#c5a059"
COLOR_TEXT_DIM = "#8c7b70"
COLOR_ACCENT_RED = "#5c1815"
COLOR_INPUT_BG = "#0f0a08"

FONT_TITLE = ("Georgia", 16, "bold")
FONT_UI = ("Georgia", 11)
FONT_BOLD = ("Georgia", 11, "bold")

class LotroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Der Vorleser von Mittelerde - Companion 2.0")
        self.root.geometry("1100x800")
        self.root.configure(bg=COLOR_BG_DARK)
        
        if os.path.exists("app_icon.ico"):
            self.root.iconbitmap("app_icon.ico")

        self.engine = CoreEngine()
        self.running = False
        self.hotkey_hook = None
        
        # Hintergrund
        self.bg_photo = None
        self.setup_background()
        self.setup_styles()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=15, pady=15)

        self.tab_status = self.create_tab(self.notebook, "Das Auge (Status)")
        self.tab_calib = self.create_tab(self.notebook, "Die Schmiede (Kalibrierung)")
        self.tab_settings = self.create_tab(self.notebook, "Die Schriften (Einstellungen)")

        self.setup_status_tab()
        self.setup_calibration_tab()
        self.setup_settings_tab()

        self.load_settings_to_ui()
        self.register_hotkey()

        # Variablen für Kalibrierung
        self.calib_img_raw = None
        self.calib_click_count = 0
        self.calib_clicks = []
        self.calib_photo = None

    def setup_background(self):
        bg_path = "background.png"
        if os.path.exists(bg_path):
            try:
                image = Image.open(bg_path)
                image = image.point(lambda p: p * 0.4) 
                self.bg_image_raw = image 
                self.bg_label = tk.Label(self.root, bg=COLOR_BG_DARK)
                self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                self.root.bind("<Configure>", self.resize_background)
            except: pass

    def resize_background(self, event):
        if hasattr(self, 'bg_image_raw'):
            if event.width > 0 and event.height > 0:
                resized = self.bg_image_raw.resize((event.width, event.height), Image.Resampling.LANCZOS)
                self.bg_photo = ImageTk.PhotoImage(resized)
                self.bg_label.config(image=self.bg_photo)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background=COLOR_BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=COLOR_BG_PANEL, foreground=COLOR_TEXT_DIM, font=FONT_BOLD, padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", COLOR_ACCENT_RED)], foreground=[("selected", COLOR_TEXT_GOLD)])
        style.configure("TFrame", background=COLOR_BG_PANEL)
        style.configure("TLabel", background=COLOR_BG_PANEL, foreground=COLOR_TEXT_GOLD, font=FONT_UI)
        style.configure("Header.TLabel", font=FONT_TITLE, foreground=COLOR_TEXT_GOLD)

    def create_tab(self, parent, title):
        frame = ttk.Frame(parent, style="TFrame")
        parent.add(frame, text=title)
        return frame
    
    def create_entry(self, parent, show=None):
        entry = tk.Entry(parent, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_GOLD, insertbackground=COLOR_TEXT_GOLD, font=("Consolas", 10), relief="flat", bd=4)
        if show: entry.config(show=show)
        return entry

    # --- TAB 1: STATUS ---
    def setup_status_tab(self):
        self.lbl_status = ttk.Label(self.tab_status, text="Warte auf Zeichen...", font=("Georgia", 14, "italic"))
        self.lbl_status.pack(pady=15)

        self.txt_preview = tk.Text(self.tab_status, bg=COLOR_INPUT_BG, fg="#e0d5c1", font=("Georgia", 13), relief="flat", height=15, padx=10, pady=10)
        self.txt_preview.pack(fill="both", expand=True, padx=20)
        self.txt_preview.insert("1.0", "\n   Noch wurde kein Text entrissen...\n")
        self.txt_preview.config(state="disabled")

        btn = tk.Button(self.tab_status, text="Macht entfesseln (Scan)", command=self.run_once_manual, bg=COLOR_ACCENT_RED, fg=COLOR_TEXT_GOLD, font=FONT_BOLD)
        btn.pack(pady=20, ipadx=20, ipady=5)

    # --- TAB 2: KALIBRIERUNG (NEU) ---
    def setup_calibration_tab(self):
        # Linke Seite: Canvas (Bild)
        # Rechte Seite: Steuerung
        
        frame_controls = ttk.Frame(self.tab_calib, padding=10)
        frame_controls.pack(side="right", fill="y")
        
        frame_canvas = ttk.Frame(self.tab_calib)
        frame_canvas.pack(side="left", fill="both", expand=True)

        # Canvas mit Scrollbars
        self.calib_canvas = tk.Canvas(frame_canvas, bg="black", cursor="cross")
        v_scroll = ttk.Scrollbar(frame_canvas, orient="vertical", command=self.calib_canvas.yview)
        h_scroll = ttk.Scrollbar(frame_canvas, orient="horizontal", command=self.calib_canvas.xview)
        
        self.calib_canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.calib_canvas.pack(side="left", fill="both", expand=True)
        
        self.calib_canvas.bind("<Button-1>", self.on_canvas_click)

        # Controls Rechts
        ttk.Label(frame_controls, text="1. Bild Erfassen", style="Header.TLabel").pack(anchor="w", pady=(0,5))
        tk.Button(frame_controls, text="Screenshot aufnehmen (3s Timer)", command=self.take_calibration_screenshot, bg=COLOR_TEXT_GOLD, fg="black").pack(fill="x", pady=5)
        
        ttk.Label(frame_controls, text="2. Ecken markieren", style="Header.TLabel").pack(anchor="w", pady=(15,5))
        self.lbl_instruction = ttk.Label(frame_controls, text="Klicke: Oben Links", foreground="#ffffff")
        self.lbl_instruction.pack(pady=5)
        
        tk.Button(frame_controls, text="Auswahl zurücksetzen", command=self.reset_clicks, bg=COLOR_ACCENT_RED, fg="white").pack(fill="x", pady=5)
        tk.Button(frame_controls, text="Templates speichern", command=self.save_templates_from_clicks, bg="#4caf50", fg="white").pack(fill="x", pady=5)

        ttk.Label(frame_controls, text="3. Ränder (Padding)", style="Header.TLabel").pack(anchor="w", pady=(15,5))
        
        # Padding Inputs
        def create_pad_input(label_txt, attr_name):
            frm = ttk.Frame(frame_controls)
            frm.pack(fill="x", pady=2)
            ttk.Label(frm, text=label_txt, width=12).pack(side="left")
            spin = tk.Spinbox(frm, from_=0, to=200, width=5, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_GOLD, buttonbackground=COLOR_BG_PANEL)
            spin.pack(side="right")
            setattr(self, attr_name, spin)
            return spin

        create_pad_input("Oben:", "spin_top")
        create_pad_input("Unten:", "spin_bottom")
        create_pad_input("Links:", "spin_left")
        create_pad_input("Rechts:", "spin_right") # Das ist das wichtige!

        tk.Button(frame_controls, text="Einstellungen speichern & Testen", command=self.save_and_test_ocr, bg=COLOR_TEXT_GOLD, fg="black").pack(fill="x", pady=20)

    def take_calibration_screenshot(self):
        # Fenster minimieren, warten, Screenshot machen, Fenster wiederherstellen
        self.root.iconify()
        self.root.after(3000, self._do_screenshot)

    def _do_screenshot(self):
        with mss.mss() as sct:
            mon_idx = int(self.cmb_monitor.get())
            if mon_idx < 1 or mon_idx >= len(sct.monitors): mon_idx = 1
            sct_img = sct.grab(sct.monitors[mon_idx])
            img = np.array(sct_img)
            self.calib_img_raw = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR) # Für Verarbeitung
            
            # Für Anzeige in Tkinter (RGB)
            img_rgb = cv2.cvtColor(self.calib_img_raw, cv2.COLOR_BGR2RGB)
            im_pil = Image.fromarray(img_rgb)
            self.calib_photo = ImageTk.PhotoImage(im_pil)

            self.calib_canvas.config(scrollregion=(0,0, im_pil.width, im_pil.height))
            self.calib_canvas.create_image(0, 0, image=self.calib_photo, anchor="nw")
            
        self.root.deiconify()
        self.reset_clicks()
        messagebox.showinfo("Bereit", "Screenshot geladen. Klicke jetzt nacheinander auf die 4 Ecken des Quest-Fensters.")

    def on_canvas_click(self, event):
        if self.calib_img_raw is None: return
        if self.calib_click_count >= 4: return

        # Koordinaten unter Berücksichtigung des Scrollens
        canvas_x = self.calib_canvas.canvasx(event.x)
        canvas_y = self.calib_canvas.canvasy(event.y)
        
        self.calib_clicks.append((int(canvas_x), int(canvas_y)))
        self.calib_click_count += 1
        
        # Zeichnen
        r = 5
        self.calib_canvas.create_oval(canvas_x-r, canvas_y-r, canvas_x+r, canvas_y+r, fill="red", outline="yellow", width=2)
        self.calib_canvas.create_text(canvas_x+10, canvas_y-10, text=str(self.calib_click_count), fill="yellow", font=("Arial", 14, "bold"))

        labels = ["Oben Rechts", "Unten Rechts", "Unten Links", "Fertig! Speichern drücken."]
        if self.calib_click_count < 4:
            self.lbl_instruction.config(text=f"Klicke: {labels[self.calib_click_count-1]}")
        else:
            self.lbl_instruction.config(text="Fertig! Jetzt 'Templates speichern' klicken.")

    def reset_clicks(self):
        self.calib_clicks = []
        self.calib_click_count = 0
        self.lbl_instruction.config(text="Klicke: Oben Links")
        # Bild neu zeichnen (löscht Markierungen)
        if self.calib_photo:
            self.calib_canvas.delete("all")
            self.calib_canvas.create_image(0, 0, image=self.calib_photo, anchor="nw")

    def save_templates_from_clicks(self):
        if len(self.calib_clicks) != 4:
            messagebox.showerror("Fehler", "Bitte genau 4 Ecken markieren!")
            return
            
        try:
            template_dir = "templates"
            if not os.path.exists(template_dir): os.makedirs(template_dir)
            
            names = ["top_left.png", "top_right.png", "bottom_right.png", "bottom_left.png"]
            crop_size = 25
            half = crop_size // 2
            
            img_gray = cv2.cvtColor(self.calib_img_raw, cv2.COLOR_BGR2GRAY)
            
            for i, (x, y) in enumerate(self.calib_clicks):
                # Bounds check
                y1 = max(0, y - half)
                y2 = min(img_gray.shape[0], y + half)
                x1 = max(0, x - half)
                x2 = min(img_gray.shape[1], x + half)
                
                crop = img_gray[y1:y2, x1:x2]
                path = os.path.join(template_dir, names[i])
                cv2.imwrite(path, crop)
                
            # Templates im Engine neu laden
            self.engine.ocr_extractor.templates = self.engine.ocr_extractor._load_templates()
            messagebox.showinfo("Erfolg", "Templates wurden gespeichert und geladen!")
            
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    def save_and_test_ocr(self):
        # Config speichern
        cfg = self.engine.config
        try:
            cfg["padding_top"] = int(self.spin_top.get())
            cfg["padding_bottom"] = int(self.spin_bottom.get())
            cfg["padding_left"] = int(self.spin_left.get())
            cfg["padding_right"] = int(self.spin_right.get())
            
            save_config(cfg)
            self.engine.ocr_extractor.config = cfg # Update live
            
            # TESTLAUF
            txt = self.engine.run_pipeline() # Führt OCR (und TTS, Achtung) aus
            
            # Zeige Ergebnis im Status Tab
            self.update_ui_text(f"--- TESTERGEBNIS ---\n{txt}")
            self.notebook.select(self.tab_status) # Wechsel zum Status Tab
            
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    # --- TAB 3: EINSTELLUNGEN ---
    def setup_settings_tab(self):
        scrollable_frame = ttk.Frame(self.tab_settings)
        scrollable_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ttk.Label(scrollable_frame, text="Die Stimme (ElevenLabs API Key)", style="Header.TLabel").pack(anchor="w")
        self.ent_api_key = self.create_entry(scrollable_frame, show="*")
        self.ent_api_key.pack(fill="x", pady=5)

        ttk.Label(scrollable_frame, text="Tesseract Pfad", style="Header.TLabel").pack(anchor="w", pady=(15,0))
        self.ent_tesseract = self.create_entry(scrollable_frame)
        self.ent_tesseract.pack(fill="x", pady=5)
        
        ttk.Label(scrollable_frame, text="Monitor ID", style="Header.TLabel").pack(anchor="w", pady=(15,0))
        self.cmb_monitor = ttk.Combobox(scrollable_frame, values=["1", "2", "3"], state="readonly")
        self.cmb_monitor.pack(fill="x", pady=5)

        ttk.Label(scrollable_frame, text="Hotkey", style="Header.TLabel").pack(anchor="w", pady=(15,0))
        self.ent_hotkey = self.create_entry(scrollable_frame)
        self.ent_hotkey.pack(fill="x", pady=5)
        
        self.var_debug = tk.BooleanVar()
        tk.Checkbutton(scrollable_frame, text="Debug Modus", variable=self.var_debug, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD).pack(anchor="w", pady=15)
        
        tk.Button(scrollable_frame, text="Einstellungen Speichern", command=self.save_settings, bg=COLOR_TEXT_GOLD, fg="black").pack(fill="x", pady=20)

    def load_settings_to_ui(self):
        cfg = self.engine.config
        self.ent_api_key.insert(0, cfg.get("api_key", ""))
        self.ent_tesseract.insert(0, cfg.get("tesseract_path", ""))
        self.ent_hotkey.insert(0, cfg.get("hotkey", "ctrl+alt+s"))
        self.cmb_monitor.set(str(cfg.get("monitor_index", 1)))
        self.var_debug.set(cfg.get("debug_mode", False))
        
        # Load Paddings
        self.spin_top.delete(0, "end"); self.spin_top.insert(0, cfg.get("padding_top", 10))
        self.spin_bottom.delete(0, "end"); self.spin_bottom.insert(0, cfg.get("padding_bottom", 20))
        self.spin_left.delete(0, "end"); self.spin_left.insert(0, cfg.get("padding_left", 10))
        self.spin_right.delete(0, "end"); self.spin_right.insert(0, cfg.get("padding_right", 50))

    def save_settings(self):
        cfg = self.engine.config
        cfg["api_key"] = self.ent_api_key.get().strip()
        cfg["tesseract_path"] = self.ent_tesseract.get().strip()
        cfg["hotkey"] = self.ent_hotkey.get().strip()
        try:
            cfg["monitor_index"] = int(self.cmb_monitor.get())
            cfg["debug_mode"] = self.var_debug.get()
        except: pass
        
        save_config(cfg)
        self.engine.config = cfg
        self.engine.ocr_extractor.config = cfg
        self.engine.ocr_extractor.pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_path"]
        self.register_hotkey()
        messagebox.showinfo("Gespeichert", "Einstellungen übernommen.")

    def register_hotkey(self):
        hk = self.engine.config.get("hotkey", "ctrl+alt+s")
        if self.hotkey_hook:
            try: keyboard.remove_hotkey(self.hotkey_hook)
            except: pass
        try:
            self.hotkey_hook = keyboard.add_hotkey(hk, lambda: self.root.after(0, self.run_once_manual))
        except: pass

    def run_once_manual(self):
        self.lbl_status.config(text="Das Auge sieht...", foreground=COLOR_TEXT_GOLD)
        threading.Thread(target=self.process_pipeline, daemon=True).start()

    def process_pipeline(self):
        try:
            txt = self.engine.run_pipeline()
            if not txt:
                self.root.after(0, lambda: self.update_status("Kein Text.", error=True))
                return
            self.root.after(0, lambda: self.update_ui_text(txt))
            self.root.after(0, lambda: self.update_status("Fertig.", done=True))
        except Exception as e:
            self.root.after(0, lambda: self.update_status(f"Fehler: {e}", error=True))

    def update_ui_text(self, txt):
        self.txt_preview.config(state="normal")
        self.txt_preview.delete(1.0, tk.END)
        self.txt_preview.insert(tk.END, txt)
        self.txt_preview.config(state="disabled")

    def update_status(self, text, error=False, done=False):
        color = COLOR_ACCENT_RED if error else (COLOR_TEXT_GOLD if not done else "#4caf50")
        self.lbl_status.config(text=text, foreground=color)

if __name__ == "__main__":
    from utils import load_config
    load_config() 
    root = tk.Tk()
    app = LotroApp(root)
    root.mainloop()
