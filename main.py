import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk 
import threading
import os
import cv2
import numpy as np
import keyboard
import ctypes
from core import CoreEngine
from utils import save_config, log_message

# --- LOTRO THEME COLORS ---
COLOR_BG_DARK = "#1a1110"       # Hintergrund Schwarz/Braun
COLOR_BG_PANEL = "#2b221b"      # Panel Farbe (Leder)
COLOR_TEXT_GOLD = "#c5a059"     # Schrift Gold
COLOR_TEXT_DIM = "#8c7b70"      # Schrift Dunkel
COLOR_ACCENT_RED = "#5c1815"    # Akzent Rot
COLOR_ACCENT_GREEN = "#3a4f32"  # Akzent Grün
COLOR_INPUT_BG = "#0f0a08"      # Input Feld Hintergrund

FONT_TITLE = ("Georgia", 16, "bold")
FONT_UI = ("Georgia", 11)
FONT_BOLD = ("Georgia", 11, "bold")

# --- ICON FIX FÜR TASKLEISTE ---
try:
    myappid = 'lotro.voice.companion.v2'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

class DraggableRect:
    """Klasse für die verschiebbaren Rahmen in der Kalibrierung."""
    def __init__(self, canvas, x, y, size, name, label_text):
        self.canvas = canvas
        self.name = name
        self.x = x
        self.y = y
        self.w = size
        self.h = size
        
        self.tag_root = f"item_{name}"
        self.tag_rect = f"rect_{name}"
        self.tag_handle = f"handle_{name}"
        
        self.draw()

    def draw(self):
        self.canvas.delete(self.tag_root)
        # Rahmen
        self.canvas.create_rectangle(self.x, self.y, self.x+self.w, self.y+self.h, 
                                     outline=COLOR_TEXT_GOLD, width=3, 
                                     fill="gray25", stipple="gray25", 
                                     tags=(self.tag_root, self.tag_rect))
        
        # Resize Handle (unten rechts)
        handle_sz = 15
        self.canvas.create_rectangle(self.x+self.w-handle_sz, self.y+self.h-handle_sz, 
                                     self.x+self.w, self.y+self.h, 
                                     fill="red", outline="white", 
                                     tags=(self.tag_root, self.tag_handle))
        
        # Fadenkreuz (Mitte)
        cx, cy = self.x + self.w/2, self.y + self.h/2
        self.canvas.create_line(cx, self.y, cx, self.y+self.h, fill=COLOR_ACCENT_RED, dash=(2,2), tags=self.tag_root)
        self.canvas.create_line(self.x, cy, self.x+self.w, cy, fill=COLOR_ACCENT_RED, dash=(2,2), tags=self.tag_root)
        
        # Label
        self.canvas.create_text(self.x, self.y-12, text=self.name.replace("_", " ").title(), 
                                fill=COLOR_TEXT_GOLD, anchor="sw", font=("Arial", 10, "bold"), 
                                tags=self.tag_root)

    def move(self, dx, dy):
        self.x += dx
        self.y += dy
        self.canvas.move(self.tag_root, dx, dy)

    def resize(self, new_w, new_h):
        self.w = max(20, new_w)
        self.h = max(20, new_h)
        self.draw() 

    def highlight(self, active=True):
        color = "white" if active else COLOR_TEXT_GOLD
        self.canvas.itemconfig(self.tag_rect, outline=color)

class LotroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Der Vorleser von Mittelerde - Companion 2.0")
        self.root.geometry("1200x950")
        self.root.configure(bg=COLOR_BG_DARK)
        
        # Icon laden
        if os.path.exists("app_icon.ico"):
            self.root.iconbitmap("app_icon.ico")
            try:
                icon_img = tk.PhotoImage(file="app_icon.ico")
                self.root.iconphoto(True, icon_img)
            except: pass

        self.engine = CoreEngine()
        self.running = False
        self.hotkey_hook = None
        
        self.bg_photo = None
        self.setup_background()
        self.setup_styles()

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=15, pady=15)

        self.tab_status = self.create_tab(self.notebook, "Das Auge (Status & Vision)")
        self.tab_calib = self.create_tab(self.notebook, "Die Schmiede (Kalibrierung)")
        self.tab_settings = self.create_tab(self.notebook, "Die Schriften (Einstellungen)")

        self.setup_status_tab()
        self.setup_calibration_tab()
        self.setup_settings_tab()

        self.load_settings_to_ui()
        self.register_hotkey()

        # Variablen
        self.calib_img_raw = None
        self.template_rects = {} 
        self.active_rect = None
        self.action_mode = None
        self.last_mouse = (0, 0)
        self.debug_photo_1 = None
        self.debug_photo_2 = None

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
    
    def create_lotro_button(self, parent, text, command, color=COLOR_ACCENT_RED):
        btn = tk.Button(parent, text=text, command=command, bg=color, fg="#dcd3c5", font=FONT_BOLD, relief="ridge", bd=3, padx=10, pady=5, cursor="hand2")
        return btn

    # --- TAB 1: STATUS ---
    def setup_status_tab(self):
        top_frame = ttk.Frame(self.tab_status)
        top_frame.pack(fill="x", pady=10, padx=10)
        
        self.lbl_status = ttk.Label(top_frame, text="Warte auf Zeichen...", font=("Georgia", 14, "italic"))
        self.lbl_status.pack(side="left")
        
        self.create_lotro_button(top_frame, "Macht entfesseln (Scan)", self.run_once_manual).pack(side="right")

        text_frame = ttk.Frame(self.tab_status)
        text_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        ttk.Label(text_frame, text="Erkannte Runen:", style="Header.TLabel").pack(anchor="w")
        self.txt_preview = tk.Text(text_frame, bg=COLOR_INPUT_BG, fg="#e0d5c1", font=("Georgia", 12), relief="flat", height=8, padx=10, pady=10)
        self.txt_preview.pack(fill="both", expand=True)
        self.txt_preview.insert("1.0", "\n   Noch wurde kein Text entrissen...\n")
        self.txt_preview.config(state="disabled")

        debug_frame = ttk.Frame(self.tab_status)
        debug_frame.pack(fill="x", padx=20, pady=10)
        
        f1 = ttk.Frame(debug_frame)
        f1.pack(side="left", expand=True, fill="both", padx=(0,5))
        ttk.Label(f1, text="Das Blickfeld (Erkennung):").pack(anchor="w")
        self.lbl_debug_1 = tk.Label(f1, bg="black", text="Kein Bild", fg="gray", height=12)
        self.lbl_debug_1.pack(fill="both", expand=True)

        f2 = ttk.Frame(debug_frame)
        f2.pack(side="right", expand=True, fill="both", padx=(5,0))
        ttk.Label(f2, text="Die Lesung (Filter / KI Input):").pack(anchor="w")
        self.lbl_debug_2 = tk.Label(f2, bg="black", text="Kein Bild", fg="gray", height=12)
        self.lbl_debug_2.pack(fill="both", expand=True)

    def load_debug_images(self):
        def load(path, label):
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    target_h = 200
                    aspect = img.width / img.height
                    target_w = int(target_h * aspect)
                    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    label.config(image=photo, text="", width=0, height=0)
                    return photo
                except: pass
            return None
        self.debug_photo_1 = load("debug_detection_view.png", self.lbl_debug_1)
        self.debug_photo_2 = load("debug_ocr_input.png", self.lbl_debug_2)

    # --- TAB 2: KALIBRIERUNG ---
    def setup_calibration_tab(self):
        paned = ttk.PanedWindow(self.tab_calib, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        frame_canvas = ttk.Frame(paned)
        frame_controls = ttk.Frame(paned, padding=(10, 0, 0, 0))
        paned.add(frame_canvas, weight=3)
        paned.add(frame_controls, weight=1)

        self.calib_canvas = tk.Canvas(frame_canvas, bg="black", cursor="cross")
        v_scroll = ttk.Scrollbar(frame_canvas, orient="vertical", command=self.calib_canvas.yview)
        h_scroll = ttk.Scrollbar(frame_canvas, orient="horizontal", command=self.calib_canvas.xview)
        self.calib_canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.calib_canvas.pack(side="left", fill="both", expand=True)
        
        self.calib_canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.calib_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.calib_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        ttk.Label(frame_controls, text="1. Bild Erfassen", style="Header.TLabel").pack(anchor="w")
        self.create_lotro_button(frame_controls, "Screenshot (3s)", self.take_calibration_screenshot, color=COLOR_TEXT_GOLD).pack(fill="x", pady=5)
        
        ttk.Label(frame_controls, text="2. Templates setzen", style="Header.TLabel").pack(anchor="w", pady=(20,5))
        self.create_lotro_button(frame_controls, "Rahmen Reset", self.spawn_default_rects, color=COLOR_ACCENT_RED).pack(fill="x", pady=5)
        self.create_lotro_button(frame_controls, "Templates speichern", self.save_templates_from_rects, color=COLOR_ACCENT_GREEN).pack(fill="x", pady=5)

        ttk.Label(frame_controls, text="3. Ränder (Padding)", style="Header.TLabel").pack(anchor="w", pady=(20,5))
        def create_pad_input(label_txt, attr_name):
            frm = ttk.Frame(frame_controls)
            frm.pack(fill="x", pady=2)
            ttk.Label(frm, text=label_txt, width=8).pack(side="left")
            spin = tk.Spinbox(frm, from_=0, to=200, width=5, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_GOLD, buttonbackground=COLOR_BG_PANEL, relief="flat")
            spin.pack(side="right")
            setattr(self, attr_name, spin)
        
        create_pad_input("Oben:", "spin_top")
        create_pad_input("Unten:", "spin_bottom")
        create_pad_input("Links:", "spin_left")
        create_pad_input("Rechts:", "spin_right")

        self.create_lotro_button(frame_controls, "Speichern & Testen", self.save_and_test_ocr, color=COLOR_TEXT_GOLD).pack(fill="x", pady=30)

    # --- MAUS LOGIK ---
    def on_mouse_down(self, event):
        if not self.calib_img_raw is None:
            cx = self.calib_canvas.canvasx(event.x)
            cy = self.calib_canvas.canvasy(event.y)
            clicked_items = self.calib_canvas.find_overlapping(cx-2, cy-2, cx+2, cy+2)
            
            if not clicked_items: return

            for item_id in reversed(clicked_items):
                tags = self.calib_canvas.gettags(item_id)
                if not tags: continue
                
                for name, rect in self.template_rects.items():
                    if rect.tag_handle in tags:
                        self.active_rect = rect
                        self.action_mode = 'resize'
                        self.last_mouse = (cx, cy)
                        rect.highlight(True)
                        return
                    elif rect.tag_rect in tags or rect.tag_root in tags:
                        self.active_rect = rect
                        self.action_mode = 'move'
                        self.last_mouse = (cx, cy)
                        rect.highlight(True)
                        return

    def on_mouse_drag(self, event):
        if self.active_rect and self.action_mode:
            cx = self.calib_canvas.canvasx(event.x)
            cy = self.calib_canvas.canvasy(event.y)
            dx = cx - self.last_mouse[0]
            dy = cy - self.last_mouse[1]
            
            if self.action_mode == 'move':
                self.active_rect.move(dx, dy)
            elif self.action_mode == 'resize':
                self.active_rect.resize(self.active_rect.w + dx, self.active_rect.h + dy)
            
            self.last_mouse = (cx, cy)

    def on_mouse_up(self, event):
        if self.active_rect:
            self.active_rect.highlight(False)
        self.active_rect = None
        self.action_mode = None

    def take_calibration_screenshot(self):
        self.root.iconify()
        self.root.after(3000, self._do_screenshot)

    def _do_screenshot(self):
        with mss.mss() as sct:
            try: mon_idx = int(self.cmb_monitor.get())
            except: mon_idx = 1
            if mon_idx < 1 or mon_idx >= len(sct.monitors): mon_idx = 1
            
            sct_img = sct.grab(sct.monitors[mon_idx])
            img = np.array(sct_img)
            self.calib_img_raw = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            img_rgb = cv2.cvtColor(self.calib_img_raw, cv2.COLOR_BGR2RGB)
            im_pil = Image.fromarray(img_rgb)
            self.calib_photo = ImageTk.PhotoImage(im_pil)

            self.calib_canvas.config(scrollregion=(0,0, im_pil.width, im_pil.height))
            self.calib_canvas.delete("all")
            self.calib_canvas.create_image(0, 0, image=self.calib_photo, anchor="nw")
            
        self.root.deiconify()
        self.spawn_default_rects()
        messagebox.showinfo("Bereit", "Verschiebe nun die goldenen Rahmen.")

    def spawn_default_rects(self):
        if self.calib_img_raw is None: return
        self.template_rects = {} 
        self.calib_canvas.delete("all")
        self.calib_canvas.create_image(0, 0, image=self.calib_photo, anchor="nw")

        h, w = self.calib_img_raw.shape[:2]
        size = 40
        mid_x, mid_y = w // 2, h // 2
        
        self.template_rects["top_left"] = DraggableRect(self.calib_canvas, mid_x - 200, mid_y - 150, size, "top_left", "Oben Links")
        self.template_rects["top_right"] = DraggableRect(self.calib_canvas, mid_x + 200, mid_y - 150, size, "top_right", "Oben Rechts")
        self.template_rects["bottom_left"] = DraggableRect(self.calib_canvas, mid_x - 200, mid_y + 150, size, "bottom_left", "Unten Links")
        self.template_rects["bottom_right"] = DraggableRect(self.calib_canvas, mid_x + 200, mid_y + 150, size, "bottom_right", "Unten Rechts")

    def save_templates_from_rects(self):
        if not self.calib_img_raw is None and len(self.template_rects) == 4:
            try:
                template_dir = "templates"
                if not os.path.exists(template_dir): os.makedirs(template_dir)
                
                img_gray = cv2.cvtColor(self.calib_img_raw, cv2.COLOR_BGR2GRAY)
                
                for name, rect in self.template_rects.items():
                    x, y, w, h = int(rect.x), int(rect.y), int(rect.w), int(rect.h)
                    x = max(0, x); y = max(0, y)
                    w = min(w, img_gray.shape[1] - x)
                    h = min(h, img_gray.shape[0] - y)
                    
                    crop = img_gray[y:y+h, x:x+w]
                    cv2.imwrite(os.path.join(template_dir, f"{name}.png"), crop)
                
                self.engine.ocr_extractor.templates = self.engine.ocr_extractor._load_templates()
                messagebox.showinfo("Erfolg", "Templates gespeichert!")
            except Exception as e:
                messagebox.showerror("Fehler", str(e))

    def save_and_test_ocr(self):
        cfg = self.engine.config
        try:
            cfg["padding_top"] = int(self.spin_top.get())
            cfg["padding_bottom"] = int(self.spin_bottom.get())
            cfg["padding_left"] = int(self.spin_left.get())
            cfg["padding_right"] = int(self.spin_right.get())
            
            save_config(cfg)
            self.engine.ocr_extractor.config = cfg
            
            # --- UPDATE: Tuple return ---
            txt, src = self.engine.run_pipeline(skip_audio=True)
            self.update_ui_text(f"--- TEST ({src}) ---\n{txt}")
            
            self.load_debug_images()
            self.notebook.select(self.tab_status)
            
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    # --- TAB 3: EINSTELLUNGEN ---
    def setup_settings_tab(self):
        sf = ttk.Frame(self.tab_settings, padding=20)
        sf.pack(fill="both", expand=True)
        
        # --- TTS SECTION ---
        ttk.Label(sf, text="Die Stimme (Audio Engine)", style="Header.TLabel").pack(anchor="w")
        self.var_tts_provider = tk.StringVar(value="elevenlabs")
        
        # 1. ElevenLabs
        f_el = ttk.Frame(sf); f_el.pack(fill="x", pady=5)
        tk.Radiobutton(f_el, text="ElevenLabs (Cloud, Premium)", variable=self.var_tts_provider, value="elevenlabs", 
                       bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD, selectcolor=COLOR_INPUT_BG, activebackground=COLOR_BG_PANEL, activeforeground=COLOR_TEXT_GOLD).pack(anchor="w")
        f_el_in = ttk.Frame(f_el, padding=(20, 0)); f_el_in.pack(fill="x")
        ttk.Label(f_el_in, text="API Key:").pack(side="left")
        self.ent_api_key = self.create_entry(f_el_in, show="*"); self.ent_api_key.pack(side="left", fill="x", expand=True, padx=5)

        # 2. Coqui XTTS
        f_xtts = ttk.Frame(sf); f_xtts.pack(fill="x", pady=5)
        tk.Radiobutton(f_xtts, text="Coqui XTTS (Lokal, KI-Voice Cloning, Schwer)", variable=self.var_tts_provider, value="xtts",
                       bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD, selectcolor=COLOR_INPUT_BG, activebackground=COLOR_BG_PANEL, activeforeground=COLOR_TEXT_GOLD).pack(anchor="w")
        f_xtts_in = ttk.Frame(f_xtts, padding=(20, 0)); f_xtts_in.pack(fill="x")
        ttk.Label(f_xtts_in, text="Stimme (.wav):").pack(side="left")
        self.cmb_xtts_voice = ttk.Combobox(f_xtts_in, state="readonly", width=30); self.cmb_xtts_voice.pack(side="left", padx=5)
        tk.Button(f_xtts_in, text="Scan", command=self.refresh_xtts_voices, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_DIM, relief="flat", font=("Arial", 8)).pack(side="left")

        # 3. Local System
        f_sys = ttk.Frame(sf); f_sys.pack(fill="x", pady=5)
        tk.Radiobutton(f_sys, text="Windows Systemstimme (Lokal, Schnell)", variable=self.var_tts_provider, value="local",
                       bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD, selectcolor=COLOR_INPUT_BG, activebackground=COLOR_BG_PANEL, activeforeground=COLOR_TEXT_GOLD).pack(anchor="w")
        f_loc_in = ttk.Frame(f_sys, padding=(20, 0)); f_loc_in.pack(fill="x")
        ttk.Label(f_loc_in, text="Stimme:").pack(side="left")
        self.cmb_local_voice = ttk.Combobox(f_loc_in, state="readonly", width=40); self.cmb_local_voice.pack(side="left", padx=5)

        # --- KI OCR SECTION ---
        ttk.Label(sf, text="Der Gelehrte (Google Gemini AI OCR)", style="Header.TLabel").pack(anchor="w", pady=(20,0))
        f_gem = ttk.Frame(sf); f_gem.pack(fill="x", pady=5)
        ttk.Label(f_gem, text="API Key:").pack(side="left")
        self.ent_gemini_key = self.create_entry(f_gem, show="*"); self.ent_gemini_key.pack(side="left", fill="x", expand=True, padx=5)
        
        frm_ai = ttk.Frame(sf); frm_ai.pack(fill="x", pady=5)
        self.var_use_ai = tk.BooleanVar()
        tk.Checkbutton(frm_ai, text="Nutze Google Gemini AI statt EasyOCR", variable=self.var_use_ai, 
                       bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD, selectcolor=COLOR_INPUT_BG, activebackground=COLOR_BG_PANEL, activeforeground=COLOR_TEXT_GOLD).pack(side="left")
        
        frm_mdl = ttk.Frame(sf); frm_mdl.pack(fill="x", pady=2)
        ttk.Label(frm_mdl, text="Modell:").pack(side="left")
        self.cmb_gemini_model = ttk.Combobox(frm_mdl, 
                                             values=["models/gemini-2.5-flash", "models/gemini-2.0-flash", "models/gemini-1.5-flash", "models/gemini-2.0-flash-exp"], 
                                             width=30, state="readonly")
        self.cmb_gemini_model.pack(side="left", padx=10)
        self.create_lotro_button(frm_mdl, "Laden", self.fetch_gemini_models, color=COLOR_BG_PANEL).pack(side="left")

        # --- OTHER ---
        ttk.Label(sf, text="Sonstiges (Pfad & Hotkey)", style="Header.TLabel").pack(anchor="w", pady=(20,0))
        f_ot = ttk.Frame(sf); f_ot.pack(fill="x", pady=5)
        ttk.Label(f_ot, text="Monitor:").pack(side="left")
        self.cmb_monitor = ttk.Combobox(f_ot, values=["1", "2", "3"], width=3, state="readonly"); self.cmb_monitor.pack(side="left", padx=5)
        ttk.Label(f_ot, text="Hotkey:").pack(side="left")
        self.ent_hotkey = self.create_entry(f_ot); self.ent_hotkey.pack(side="left", fill="x", expand=True, padx=5)
        
        self.var_debug = tk.BooleanVar()
        tk.Checkbutton(sf, text="Debug Modus", variable=self.var_debug, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD, selectcolor=COLOR_INPUT_BG, activebackground=COLOR_BG_PANEL, activeforeground=COLOR_TEXT_GOLD).pack(anchor="w", pady=15)
        
        self.create_lotro_button(sf, "In Stein meißeln (Speichern)", self.save_settings, color=COLOR_TEXT_GOLD).pack(fill="x", pady=30)

    def fetch_gemini_models(self):
        key = self.ent_gemini_key.get().strip()
        if not key: messagebox.showerror("Fehler", "Bitte erst einen API Key eingeben."); return
        try:
            models = self.engine.ocr_extractor.fetch_available_models(key)
            if models:
                self.cmb_gemini_model['values'] = models
                self.cmb_gemini_model.set(models[0])
                messagebox.showinfo("Erfolg", f"{len(models)} Modelle gefunden.")
            else: messagebox.showwarning("Info", "Keine passenden Modelle gefunden.")
        except Exception as e: messagebox.showerror("Fehler", str(e))

    def refresh_xtts_voices(self):
        files = self.engine.tts_service.get_available_xtts_voices()
        if files:
            self.cmb_xtts_voice['values'] = files
            curr = self.engine.config.get("xtts_reference_wav", "")
            self.cmb_xtts_voice.set(curr if curr in files else files[0])
        else: self.cmb_xtts_voice['values'] = ["(Leer)"]; self.cmb_xtts_voice.current(0)

    def load_settings_to_ui(self):
        c = self.engine.config
        # API Keys
        self.ent_api
