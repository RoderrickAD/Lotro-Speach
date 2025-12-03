import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk 
import threading
import os
import cv2
import numpy as np
import keyboard
import ctypes # WICHTIG FÜR TASKLEISTEN ICON
from core import CoreEngine
from utils import save_config, log_message

# --- LOTRO THEME PALETTE ---
# Wir nutzen warme, dunkle Töne passend zur Leder/Karten-Optik
COLOR_BG_MAIN = "#000000"       # Schwarz hinter dem Bild
COLOR_PANEL_BG = "#1e1612"      # Sehr dunkles Lederbraun (für Container)
COLOR_TEXT_GOLD = "#e3bd76"     # Faded Gold (wie auf der Karte)
COLOR_TEXT_PALE = "#dcd3c5"     # Pergament-Weiß (für Lesbarkeit)
COLOR_ACCENT_RED = "#6e1814"    # Mordor Rot (für Buttons/Highlights)
COLOR_ACCENT_GREEN = "#3a4f32"  # Elben Grün (für Erfolg)
COLOR_INPUT_BG = "#120c09"      # Fast Schwarz (für Eingabefelder)

FONT_TITLE = ("Georgia", 18, "bold")
FONT_UI = ("Georgia", 11)
FONT_BOLD = ("Georgia", 11, "bold")
FONT_MONO = ("Consolas", 10)

# --- ICON FIX FÜR WINDOWS TASKLEISTE ---
try:
    myappid = 'lotro.voice.companion.v2' # Eindeutige ID
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

class DraggableRect:
    """Zeichnet die goldenen Rahmen für die Kalibrierung."""
    def __init__(self, canvas, x, y, size, name, label_text):
        self.canvas = canvas; self.name = name; self.x = x; self.y = y; self.w = size; self.h = size
        self.tag_root = f"item_{name}"; self.tag_rect = f"rect_{name}"; self.tag_handle = f"handle_{name}"
        self.draw()

    def draw(self):
        self.canvas.delete(self.tag_root)
        # Rahmen mit halbtransparentem Look (stipple)
        self.canvas.create_rectangle(self.x, self.y, self.x+self.w, self.y+self.h, 
                                     outline=COLOR_TEXT_GOLD, width=2, 
                                     fill="gray25", stipple="gray25", tags=(self.tag_root, self.tag_rect))
        # Griff
        handle_sz = 12
        self.canvas.create_rectangle(self.x+self.w-handle_sz, self.y+self.h-handle_sz, self.x+self.w, self.y+self.h, 
                                     fill=COLOR_ACCENT_RED, outline=COLOR_TEXT_GOLD, tags=(self.tag_root, self.tag_handle))
        # Fadenkreuz
        cx, cy = self.x + self.w/2, self.y + self.h/2
        self.canvas.create_line(cx, self.y, cx, self.y+self.h, fill=COLOR_ACCENT_RED, dash=(2,2), tags=self.tag_root)
        self.canvas.create_line(self.x, cy, self.x+self.w, cy, fill=COLOR_ACCENT_RED, dash=(2,2), tags=self.tag_root)
        # Label
        self.canvas.create_text(self.x, self.y-15, text=self.name.replace("_", " ").title(), 
                                fill=COLOR_TEXT_GOLD, anchor="sw", font=("Georgia", 10, "bold"), tags=self.tag_root)

    def move(self, dx, dy): self.x += dx; self.y += dy; self.canvas.move(self.tag_root, dx, dy)
    def resize(self, new_w, new_h): self.w = max(20, new_w); self.h = max(20, new_h); self.draw() 
    def highlight(self, active=True): self.canvas.itemconfig(self.tag_rect, outline="white" if active else COLOR_TEXT_GOLD)
    def contains(self, x, y): return self.x <= x <= self.x+self.w and self.y <= y <= self.y+self.h
    def on_handle(self, x, y): return (self.x+self.w-12 <= x <= self.x+self.w) and (self.y+self.h-12 <= y <= self.y+self.h)


class LotroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Der Vorleser von Mittelerde")
        self.root.geometry("1150x950")
        self.root.configure(bg=COLOR_BG_MAIN)
        
        # --- ICON SETUP (Taskleiste & Fenster) ---
        if os.path.exists("app_icon.ico"):
            # 1. Bitmap für Fenster-Header (Windows Standard)
            self.root.iconbitmap("app_icon.ico")
            # 2. PhotoImage für Taskleiste & Fenster (Modern)
            try:
                icon_img = tk.PhotoImage(file="app_icon.ico")
                self.root.iconphoto(True, icon_img)
            except: pass # Falls Format nicht unterstützt wird

        self.engine = CoreEngine()
        self.running = False
        self.hotkey_hook = None
        
        # Hintergrund laden
        self.bg_photo = None
        self.setup_background()
        
        # Styling anwenden
        self.setup_styles()

        # Haupt-Container (Notebook)
        # Wir geben Padding, damit man den Hintergrund an den Rändern sieht
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=25, pady=25)

        # Tabs erstellen
        self.tab_status = self.create_tab(self.notebook, "Das Auge")
        self.tab_calib = self.create_tab(self.notebook, "Die Schmiede")
        self.tab_settings = self.create_tab(self.notebook, "Die Schriften")

        # Inhalte füllen
        self.setup_status_tab()
        self.setup_calibration_tab()
        self.setup_settings_tab()

        self.load_settings_to_ui()
        self.register_hotkey()

        # Variablen für Kalibrierung & Debug
        self.calib_img_raw = None
        self.template_rects = {} 
        self.active_rect = None
        self.action_mode = None
        self.last_mouse = (0, 0)
        self.debug_photo_1 = None
        self.debug_photo_2 = None

    def setup_background(self):
        """Lädt background.png und setzt es als Hintergrund."""
        bg_path = "background.png"
        if os.path.exists(bg_path):
            try:
                # Bild laden und etwas abdunkeln, damit Text besser lesbar ist
                image = Image.open(bg_path)
                # Abdunkeln (Faktor 0.5 = 50% Helligkeit)
                image = image.point(lambda p: p * 0.5) 
                self.bg_image_raw = image 
                
                self.bg_label = tk.Label(self.root, bg=COLOR_BG_MAIN)
                self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                
                # Resize Event binden
                self.root.bind("<Configure>", self.resize_background)
            except Exception as e:
                print(f"Hintergrund-Fehler: {e}")

    def resize_background(self, event):
        if hasattr(self, 'bg_image_raw'):
            if event.width > 0 and event.height > 0:
                # High-Quality Resize
                resized = self.bg_image_raw.resize((event.width, event.height), Image.Resampling.LANCZOS)
                self.bg_photo = ImageTk.PhotoImage(resized)
                self.bg_label.config(image=self.bg_photo)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Notebook (Tabs) transparent wirken lassen (nimmt BG Panel Farbe)
        style.configure("TNotebook", background=COLOR_PANEL_BG, borderwidth=0)
        style.configure("TNotebook.Tab", 
                        background="#110b09", # Noch dunkler für inaktive Tabs
                        foreground=COLOR_TEXT_DIM, 
                        font=("Georgia", 11), 
                        padding=[15, 8],
                        borderwidth=0)
        style.map("TNotebook.Tab", 
                  background=[("selected", COLOR_PANEL_BG)], # Aktiver Tab verschmilzt mit Panel
                  foreground=[("selected", COLOR_TEXT_GOLD)])

        # Frames und Labels im LOTRO Look
        style.configure("TFrame", background=COLOR_PANEL_BG)
        style.configure("TLabel", background=COLOR_PANEL_BG, foreground=COLOR_TEXT_GOLD, font=FONT_UI)
        style.configure("Header.TLabel", font=FONT_TITLE, foreground=COLOR_TEXT_GOLD)
        
        # Scrollbars anpassen (Dunkel)
        style.configure("Vertical.TScrollbar", troughcolor=COLOR_INPUT_BG, background=COLOR_PANEL_BG, arrowcolor=COLOR_TEXT_GOLD, borderwidth=0)
        style.configure("Horizontal.TScrollbar", troughcolor=COLOR_INPUT_BG, background=COLOR_PANEL_BG, arrowcolor=COLOR_TEXT_GOLD, borderwidth=0)

    def create_tab(self, parent, title):
        # Ein Frame pro Tab
        frame = ttk.Frame(parent, style="TFrame")
        parent.add(frame, text=title)
        return frame
    
    def create_entry(self, parent, show=None):
        # Custom Entry Widget (Tkinter native, da ttk Entry schwer zu stylen ist)
        entry = tk.Entry(parent, 
                         bg=COLOR_INPUT_BG, 
                         fg=COLOR_TEXT_GOLD, 
                         insertbackground=COLOR_TEXT_GOLD, # Cursor Farbe
                         font=("Consolas", 10), 
                         relief="flat", 
                         bd=5) # Dickerer Rand für Tiefe
        if show: entry.config(show=show)
        return entry

    def create_lotro_button(self, parent, text, command, color=COLOR_ACCENT_RED):
        # Custom Button im LOTRO Stil
        btn = tk.Button(parent, 
                        text=text, 
                        command=command,
                        bg=color, 
                        fg=COLOR_TEXT_PALE,
                        font=FONT_BOLD,
                        relief="ridge", 
                        bd=3,
                        padx=15, pady=5,
                        activebackground=COLOR_TEXT_GOLD,
                        activeforeground="black",
                        cursor="hand2")
        return btn

    # --- TAB 1: DAS AUGE ---
    def setup_status_tab(self):
        # Layout Container
        main_pad = ttk.Frame(self.tab_status, padding=20)
        main_pad.pack(fill="both", expand=True)

        # Header Area
        top_frame = ttk.Frame(main_pad)
        top_frame.pack(fill="x", pady=(0, 15))
        
        self.lbl_status = ttk.Label(top_frame, text="Das Auge ruht... (Warte auf Zeichen)", font=("Georgia", 14, "italic"))
        self.lbl_status.pack(side="left")
        
        self.create_lotro_button(top_frame, "Macht entfesseln (Scan)", self.run_once_manual).pack(side="right")

        # Text Area (Das Pergament)
        ttk.Label(main_pad, text="Entzifferte Runen:", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        
        self.txt_preview = tk.Text(main_pad, 
                                   bg=COLOR_INPUT_BG, 
                                   fg=COLOR_TEXT_PALE, 
                                   font=("Georgia", 13), 
                                   relief="flat", 
                                   height=10, 
                                   padx=15, pady=15,
                                   selectbackground=COLOR_ACCENT_RED)
        self.txt_preview.pack(fill="both", expand=True)
        self.txt_preview.insert("1.0", "\n   Noch wurde kein Text aus den Schatten entrissen...\n")
        self.txt_preview.config(state="disabled")

        # Debug Bilder
        debug_frame = ttk.Frame(main_pad)
        debug_frame.pack(fill="x", pady=(20, 0))
        
        # Links: Detection
        f1 = ttk.Frame(debug_frame); f1.pack(side="left", expand=True, fill="both", padx=(0,10))
        ttk.Label(f1, text="Das Blickfeld:", font=FONT_BOLD).pack(anchor="w")
        self.lbl_debug_1 = tk.Label(f1, bg="black", text="Kein Bild", fg="gray", height=10) 
        self.lbl_debug_1.pack(fill="both", expand=True, pady=5)

        # Rechts: OCR Input
        f2 = ttk.Frame(debug_frame); f2.pack(side="right", expand=True, fill="both", padx=(10,0))
        ttk.Label(f2, text="Die Lesung:", font=FONT_BOLD).pack(anchor="w")
        self.lbl_debug_2 = tk.Label(f2, bg="black", text="Kein Bild", fg="gray", height=10)
        self.lbl_debug_2.pack(fill="both", expand=True, pady=5)

    def load_debug_images(self):
        def load(p, l):
            if os.path.exists(p):
                try:
                    img = Image.open(p)
                    # Fixed Height für UI Stabilität
                    target_h = 180
                    aspect = img.width / img.height
                    target_w = int(target_h * aspect)
                    
                    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    l.config(image=photo, text="", width=0, height=0)
                    return photo
                except: pass
            return None
        self.debug_photo_1 = load("debug_detection_view.png", self.lbl_debug_1)
        self.debug_photo_2 = load("debug_ocr_input.png", self.lbl_debug_2)

    # --- TAB 2: DIE SCHMIEDE ---
    def setup_calibration_tab(self):
        # Split Layout
        paned = ttk.PanedWindow(self.tab_calib, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        frame_canvas = ttk.Frame(paned)
        frame_controls = ttk.Frame(paned, padding=(10, 0, 0, 0)) # Padding links
        
        paned.add(frame_canvas, weight=3)
        paned.add(frame_controls, weight=1)

        # Canvas
        self.calib_canvas = tk.Canvas(frame_canvas, bg="black", cursor="cross", highlightthickness=0)
        v_scroll = ttk.Scrollbar(frame_canvas, orient="vertical", command=self.calib_canvas.yview)
        h_scroll = ttk.Scrollbar(frame_canvas, orient="horizontal", command=self.calib_canvas.xview)
        self.calib_canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.calib_canvas.pack(side="left", fill="both", expand=True)
        
        self.calib_canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.calib_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.calib_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # Controls
        ttk.Label(frame_controls, text="1. Erfassung", style="Header.TLabel").pack(anchor="w")
        self.create_lotro_button(frame_controls, "Screenshot (3s)", self.take_calibration_screenshot, color=COLOR_TEXT_GOLD).pack(fill="x", pady=5)
        
        ttk.Label(frame_controls, text="2. Templates", style="Header.TLabel").pack(anchor="w", pady=(20,5))
        self.create_lotro_button(frame_controls, "Rahmen Reset", self.spawn_default_rects, color=COLOR_ACCENT_RED).pack(fill="x", pady=5)
        self.create_lotro_button(frame_controls, "Templates speichern", self.save_templates_from_rects, color=COLOR_ACCENT_GREEN).pack(fill="x", pady=5)
        
        ttk.Label(frame_controls, text="3. Ränder", style="Header.TLabel").pack(anchor="w", pady=(20,5))
        def mk_pad(txt, attr):
            f = ttk.Frame(frame_controls); f.pack(fill="x", pady=2)
            ttk.Label(f, text=txt, width=8).pack(side="left")
            s = tk.Spinbox(f, from_=0, to=200, width=5, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_GOLD, buttonbackground=COLOR_BG_PANEL, relief="flat")
            s.pack(side="right"); setattr(self, attr, s)
        mk_pad("Oben:", "spin_top"); mk_pad("Unten:", "spin_bottom"); mk_pad("Links:", "spin_left"); mk_pad("Rechts:", "spin_right")
        
        self.create_lotro_button(frame_controls, "Testen (Stumm)", self.save_and_test_ocr, color=COLOR_TEXT_GOLD).pack(fill="x", pady=30)

    # --- MAUS LOGIK (Identisch, nur robuster) ---
    def on_mouse_down(self, e):
        if not self.calib_img_raw is None:
            cx = self.calib_canvas.canvasx(e.x); cy = self.calib_canvas.canvasy(e.y)
            items = self.calib_canvas.find_overlapping(cx-2, cy-2, cx+2, cy+2)
            if items:
                for i in reversed(items):
                    tags = self.calib_canvas.gettags(i)
                    if not tags: continue
                    for n, r in self.template_rects.items():
                        if r.tag_handle in tags: self.active_rect=r; self.action_mode='resize'; self.last_mouse=(cx,cy); r.highlight(True); return
                        elif r.tag_rect in tags or r.tag_root in tags: self.active_rect=r; self.action_mode='move'; self.last_mouse=(cx,cy); r.highlight(True); return
    def on_mouse_drag(self, e):
        if self.active_rect:
            cx = self.calib_canvas.canvasx(e.x); cy = self.calib_canvas.canvasy(e.y); dx = cx - self.last_mouse[0]; dy = cy - self.last_mouse[1]
            if self.action_mode=='move': self.active_rect.move(dx, dy)
            elif self.action_mode=='resize': self.active_rect.resize(self.active_rect.w+dx, self.active_rect.h+dy)
            self.last_mouse = (cx, cy)
    def on_mouse_up(self, e):
        if self.active_rect: self.active_rect.highlight(False)
        self.active_rect = None
    def take_calibration_screenshot(self): self.root.iconify(); self.root.after(3000, self._do_screenshot)
    def _do_screenshot(self):
        with mss.mss() as sct:
            try: m = int(self.cmb_monitor.get())
            except: m = 1
            if m < 1 or m >= len(sct.monitors): m = 1
            self.calib_img_raw = cv2.cvtColor(np.array(sct.grab(sct.monitors[m])), cv2.COLOR_BGRA2BGR)
            im = Image.fromarray(cv2.cvtColor(self.calib_img_raw, cv2.COLOR_BGR2RGB))
            self.calib_photo = ImageTk.PhotoImage(im); self.calib_canvas.config(scrollregion=(0,0, im.width, im.height)); self.calib_canvas.delete("all"); self.calib_canvas.create_image(0, 0, image=self.calib_photo, anchor="nw")
        self.root.deiconify(); self.spawn_default_rects(); messagebox.showinfo("Bereit", "Rahmen platzieren.")
    def spawn_default_rects(self):
        if self.calib_img_raw is None: return
        self.template_rects = {}; self.calib_canvas.delete("all"); self.calib_canvas.create_image(0, 0, image=self.calib_photo, anchor="nw")
        h, w = self.calib_img_raw.shape[:2]; sz = 40; mx, my = w//2, h//2
        self.template_rects["top_left"] = DraggableRect(self.calib_canvas, mx-200, my-150, sz, "top_left", "Oben Links")
        self.template_rects["top_right"] = DraggableRect(self.calib_canvas, mx+200, my-150, sz, "top_right", "Oben Rechts")
        self.template_rects["bottom_left"] = DraggableRect(self.calib_canvas, mx-200, my+150, sz, "bottom_left", "Unten Links")
        self.template_rects["bottom_right"] = DraggableRect(self.calib_canvas, mx+200, my+150, sz, "bottom_right", "Unten Rechts")
    def save_templates_from_rects(self):
        if self.calib_img_raw is None or len(self.template_rects)!=4: return
        try:
            d = "templates"; 
            if not os.path.exists(d): os.makedirs(d)
            gray = cv2.cvtColor(self.calib_img_raw, cv2.COLOR_BGR2GRAY)
            for n, r in self.template_rects.items():
                x, y, w, h = int(r.x), int(r.y), int(r.w), int(r.h)
                x=max(0,x); y=max(0,y); w=min(w, gray.shape[1]-x); h=min(h, gray.shape[0]-y)
                cv2.imwrite(os.path.join(d, f"{n}.png"), gray[y:y+h, x:x+w])
            self.engine.ocr_extractor.templates = self.engine.ocr_extractor._load_templates()
            messagebox.showinfo("Erfolg", "Templates gespeichert.")
        except Exception as e: messagebox.showerror("Fehler", str(e))
    def save_and_test_ocr(self):
        c = self.engine.config
        try:
            c["padding_top"]=int(self.spin_top.get()); c["padding_bottom"]=int(self.spin_bottom.get())
            c["padding_left"]=int(self.spin_left.get()); c["padding_right"]=int(self.spin_right.get())
            save_config(c); self.engine.ocr_extractor.config = c
            txt, src = self.engine.run_pipeline(skip_audio=True)
            self.update_ui_text(f"--- TEST ({src}) ---\n{txt}"); self.load_debug_images(); self.notebook.select(self.tab_status)
