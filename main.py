import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk 
import threading
import os
import cv2
import numpy as np
import keyboard
from core import CoreEngine
from utils import save_config, log_message

COLOR_BG_DARK = "#1a1110"; COLOR_BG_PANEL = "#2b221b"; COLOR_TEXT_GOLD = "#c5a059"
COLOR_TEXT_DIM = "#8c7b70"; COLOR_ACCENT_RED = "#5c1815"; COLOR_INPUT_BG = "#0f0a08"
FONT_TITLE = ("Georgia", 16, "bold"); FONT_UI = ("Georgia", 11); FONT_BOLD = ("Georgia", 11, "bold")

class DraggableRect:
    def __init__(self, canvas, x, y, size, name, label_text):
        self.canvas = canvas; self.name = name; self.x = x; self.y = y; self.w = size; self.h = size
        self.tag_root = f"item_{name}"; self.tag_rect = f"rect_{name}"; self.tag_handle = f"handle_{name}"
        self.draw()
    def draw(self):
        self.canvas.delete(self.tag_root)
        self.canvas.create_rectangle(self.x, self.y, self.x+self.w, self.y+self.h, outline=COLOR_TEXT_GOLD, width=3, fill="gray25", stipple="gray25", tags=(self.tag_root, self.tag_rect))
        handle_sz = 15; self.canvas.create_rectangle(self.x+self.w-handle_sz, self.y+self.h-handle_sz, self.x+self.w, self.y+self.h, fill="red", outline="white", tags=(self.tag_root, self.tag_handle))
        cx, cy = self.x + self.w/2, self.y + self.h/2
        self.canvas.create_line(cx, self.y, cx, self.y+self.h, fill=COLOR_ACCENT_RED, dash=(2,2), tags=self.tag_root)
        self.canvas.create_line(self.x, cy, self.x+self.w, cy, fill=COLOR_ACCENT_RED, dash=(2,2), tags=self.tag_root)
        self.canvas.create_text(self.x, self.y-12, text=self.name.replace("_", " ").title(), fill=COLOR_TEXT_GOLD, anchor="sw", font=("Arial", 10, "bold"), tags=self.tag_root)
    def move(self, dx, dy): self.x += dx; self.y += dy; self.canvas.move(self.tag_root, dx, dy)
    def resize(self, new_w, new_h): self.w = max(20, new_w); self.h = max(20, new_h); self.draw() 
    def highlight(self, active=True): self.canvas.itemconfig(self.tag_rect, outline="white" if active else COLOR_TEXT_GOLD)

class LotroApp:
    def __init__(self, root):
        self.root = root; self.root.title("Der Vorleser von Mittelerde - Companion 2.0"); self.root.geometry("1100x950"); self.root.configure(bg=COLOR_BG_DARK)
        if os.path.exists("app_icon.ico"): self.root.iconbitmap("app_icon.ico")
        self.engine = CoreEngine(); self.running = False; self.hotkey_hook = None
        self.setup_background(); self.setup_styles()
        self.notebook = ttk.Notebook(self.root); self.notebook.pack(expand=True, fill="both", padx=15, pady=15)
        self.tab_status = self.create_tab(self.notebook, "Das Auge (Status & Vision)")
        self.tab_calib = self.create_tab(self.notebook, "Die Schmiede (Kalibrierung)")
        self.tab_settings = self.create_tab(self.notebook, "Die Schriften (Einstellungen)")
        self.setup_status_tab(); self.setup_calibration_tab(); self.setup_settings_tab()
        self.load_settings_to_ui(); self.register_hotkey()
        self.calib_img_raw = None; self.template_rects = {}; self.active_rect = None; self.action_mode = None; self.last_mouse = (0, 0)
        self.debug_photo_1 = None; self.debug_photo_2 = None

    def setup_background(self):
        bg = "background.png"
        if os.path.exists(bg):
            try: self.bg_image_raw = Image.open(bg).point(lambda p: p * 0.4); self.bg_label = tk.Label(self.root, bg=COLOR_BG_DARK); self.bg_label.place(x=0, y=0, relwidth=1, relheight=1); self.root.bind("<Configure>", self.resize_background)
            except: pass
    def resize_background(self, event):
        if hasattr(self, 'bg_image_raw') and event.width > 0: self.bg_label.config(image=ImageTk.PhotoImage(self.bg_image_raw.resize((event.width, event.height), Image.Resampling.LANCZOS)))
    def setup_styles(self):
        s = ttk.Style(); s.theme_use('clam'); s.configure("TNotebook", background=COLOR_BG_DARK, borderwidth=0)
        s.configure("TNotebook.Tab", background=COLOR_BG_PANEL, foreground=COLOR_TEXT_DIM, font=FONT_BOLD, padding=[10, 5])
        s.map("TNotebook.Tab", background=[("selected", COLOR_ACCENT_RED)], foreground=[("selected", COLOR_TEXT_GOLD)])
        s.configure("TFrame", background=COLOR_BG_PANEL); s.configure("TLabel", background=COLOR_BG_PANEL, foreground=COLOR_TEXT_GOLD, font=FONT_UI); s.configure("Header.TLabel", font=FONT_TITLE, foreground=COLOR_TEXT_GOLD)
    def create_tab(self, p, t): f = ttk.Frame(p, style="TFrame"); p.add(f, text=t); return f
    def create_entry(self, p, show=None): e = tk.Entry(p, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_GOLD, insertbackground=COLOR_TEXT_GOLD, font=("Consolas", 10), relief="flat", bd=4); return e if not show else (e.config(show=show) or e)

    def setup_status_tab(self):
        top = ttk.Frame(self.tab_status); top.pack(fill="x", pady=10, padx=10)
        self.lbl_status = ttk.Label(top, text="Warte auf Zeichen...", font=("Georgia", 14, "italic")); self.lbl_status.pack(side="left")
        tk.Button(top, text="Macht entfesseln (Scan)", command=self.run_once_manual, bg=COLOR_ACCENT_RED, fg=COLOR_TEXT_GOLD, font=FONT_BOLD).pack(side="right")
        text_frame = ttk.Frame(self.tab_status); text_frame.pack(fill="both", expand=True, padx=20, pady=5)
        ttk.Label(text_frame, text="Erkannte Runen:", style="Header.TLabel").pack(anchor="w")
        self.txt_preview = tk.Text(text_frame, bg=COLOR_INPUT_BG, fg="#e0d5c1", font=("Georgia", 12), relief="flat", height=8, padx=10, pady=10); self.txt_preview.pack(fill="both", expand=True); self.txt_preview.config(state="disabled")
        debug_frame = ttk.Frame(self.tab_status); debug_frame.pack(fill="x", padx=20, pady=10)
        f1 = ttk.Frame(debug_frame); f1.pack(side="left", expand=True, fill="both", padx=(0,5))
        ttk.Label(f1, text="Das Blickfeld (Erkennung):").pack(anchor="w")
        self.lbl_debug_1 = tk.Label(f1, bg="black", text="Kein Bild", fg="gray", height=12); self.lbl_debug_1.pack(fill="both", expand=True)
        f2 = ttk.Frame(debug_frame); f2.pack(side="right", expand=True, fill="both", padx=(5,0))
        ttk.Label(f2, text="Die Lesung (Filter / KI Input):").pack(anchor="w")
        self.lbl_debug_2 = tk.Label(f2, bg="black", text="Kein Bild", fg="gray", height=12); self.lbl_debug_2.pack(fill="both", expand=True)

    def load_debug_images(self):
        def load(p, l):
            if os.path.exists(p):
                try:
                    img = Image.open(p); aspect = img.width/img.height; target_h = 200; target_w = int(target_h*aspect)
                    photo = ImageTk.PhotoImage(img.resize((target_w, target_h), Image.Resampling.LANCZOS))
                    l.config(image=photo, text="", width=0, height=0); return photo
                except: pass
            return None
        self.debug_photo_1 = load("debug_detection_view.png", self.lbl_debug_1); self.debug_photo_2 = load("debug_ocr_input.png", self.lbl_debug_2)

    def setup_calibration_tab(self):
        ctrl = ttk.Frame(self.tab_calib, padding=10); ctrl.pack(side="right", fill="y")
        cv = ttk.Frame(self.tab_calib); cv.pack(side="left", fill="both", expand=True)
        self.calib_canvas = tk.Canvas(cv, bg="black", cursor="cross")
        vs = ttk.Scrollbar(cv, orient="vertical", command=self.calib_canvas.yview); hs = ttk.Scrollbar(cv, orient="horizontal", command=self.calib_canvas.xview)
        self.calib_canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set); vs.pack(side="right", fill="y"); hs.pack(side="bottom", fill="x"); self.calib_canvas.pack(side="left", fill="both", expand=True)
        self.calib_canvas.bind("<ButtonPress-1>", self.on_mouse_down); self.calib_canvas.bind("<B1-Motion>", self.on_mouse_drag); self.calib_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        ttk.Label(ctrl, text="1. Bild Erfassen", style="Header.TLabel").pack(anchor="w")
        tk.Button(ctrl, text="Screenshot (3s)", command=self.take_calibration_screenshot, bg=COLOR_TEXT_GOLD, fg="black").pack(fill="x", pady=5)
        ttk.Label(ctrl, text="2. Templates setzen", style="Header.TLabel").pack(anchor="w", pady=(15,5))
        tk.Button(ctrl, text="Rahmen Reset", command=self.spawn_default_rects, bg=COLOR_ACCENT_RED, fg="white").pack(fill="x", pady=5)
        tk.Button(ctrl, text="Templates speichern", command=self.save_templates_from_rects, bg="#4caf50", fg="white").pack(fill="x", pady=5)
        ttk.Label(ctrl, text="3. Ränder (Padding)", style="Header.TLabel").pack(anchor="w", pady=(15,5))
        def mk_pad(txt, attr):
            f = ttk.Frame(ctrl); f.pack(fill="x", pady=2)
            ttk.Label(f, text=txt, width=12).pack(side="left")
            s = tk.Spinbox(f, from_=0, to=200, width=5, bg=COLOR_INPUT_BG, fg=COLOR_TEXT_GOLD, buttonbackground=COLOR_BG_PANEL)
            s.pack(side="right"); setattr(self, attr, s)
        mk_pad("Oben:", "spin_top"); mk_pad("Unten:", "spin_bottom"); mk_pad("Links:", "spin_left"); mk_pad("Rechts:", "spin_right")
        tk.Button(ctrl, text="Speichern & Testen", command=self.save_and_test_ocr, bg=COLOR_TEXT_GOLD, fg="black").pack(fill="x", pady=20)

    def on_mouse_down(self, e):
        if self.calib_img_raw is not None:
            cx = self.calib_canvas.canvasx(e.x); cy = self.calib_canvas.canvasy(e.y)
            items = self.calib_canvas.find_overlapping(cx-2, cy-2, cx+2, cy+2)
            if items:
                for i in reversed(items):
                    tags = self.calib_canvas.gettags(i)
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
            
            # --- UPDATE: Tuple return ---
            txt, src = self.engine.run_pipeline(skip_audio=True)
            self.update_ui_text(f"--- TEST ({src}) ---\n{txt}")
            
            self.load_debug_images(); self.notebook.select(self.tab_status)
        except Exception as e: messagebox.showerror("Fehler", str(e))

    def setup_settings_tab(self):
        sf = ttk.Frame(self.tab_settings); sf.pack(fill="both", expand=True, padx=20, pady=20)
        ttk.Label(sf, text="Die Stimme (ElevenLabs API Key)", style="Header.TLabel").pack(anchor="w")
        self.ent_api_key = self.create_entry(sf, show="*"); self.ent_api_key.pack(fill="x", pady=5)
        ttk.Label(sf, text="Der Gelehrte (Google Gemini AI OCR)", style="Header.TLabel").pack(anchor="w", pady=(15,0))
        ttk.Label(sf, text="API Key:").pack(anchor="w"); self.ent_gemini_key = self.create_entry(sf, show="*"); self.ent_gemini_key.pack(fill="x", pady=5)
        self.var_use_ai = tk.BooleanVar()
        tk.Checkbutton(sf, text="Nutze Google Gemini AI statt Tesseract", variable=self.var_use_ai, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD, selectcolor=COLOR_BG_DARK).pack(anchor="w", pady=5)
        ttk.Label(sf, text="Das Auge (Tesseract Pfad)", style="Header.TLabel").pack(anchor="w", pady=(15,0))
        self.ent_tesseract = self.create_entry(sf); self.ent_tesseract.pack(fill="x", pady=5)
        ttk.Label(sf, text="Monitor ID", style="Header.TLabel").pack(anchor="w", pady=(15,0)); self.cmb_monitor = ttk.Combobox(sf, values=["1", "2", "3"], state="readonly"); self.cmb_monitor.pack(fill="x", pady=5)
        ttk.Label(sf, text="Hotkey", style="Header.TLabel").pack(anchor="w", pady=(15,0)); self.ent_hotkey = self.create_entry(sf); self.ent_hotkey.pack(fill="x", pady=5)
        self.var_debug = tk.BooleanVar(); tk.Checkbutton(sf, text="Debug Modus", variable=self.var_debug, bg=COLOR_BG_PANEL, fg=COLOR_TEXT_GOLD, selectcolor=COLOR_BG_DARK).pack(anchor="w", pady=15)
        tk.Button(sf, text="Einstellungen Speichern", command=self.save_settings, bg=COLOR_TEXT_GOLD, fg="black").pack(fill="x", pady=20)

    def load_settings_to_ui(self):
        c = self.engine.config; self.ent_api_key.insert(0, c.get("api_key", ""))
        self.ent_gemini_key.insert(0, c.get("gemini_api_key", "")); self.var_use_ai.set(c.get("use_ai_ocr", False))
        self.ent_tesseract.insert(0, c.get("tesseract_path", "")); self.ent_hotkey.insert(0, c.get("hotkey", "ctrl+alt+s"))
        self.cmb_monitor.set(str(c.get("monitor_index", 1))); self.var_debug.set(c.get("debug_mode", False))
        self.spin_top.delete(0, "end"); self.spin_top.insert(0, c.get("padding_top", 10))
        self.spin_bottom.delete(0, "end"); self.spin_bottom.insert(0, c.get("padding_bottom", 20))
        self.spin_left.delete(0, "end"); self.spin_left.insert(0, c.get("padding_left", 10))
        self.spin_right.delete(0, "end"); self.spin_right.insert(0, c.get("padding_right", 50))

    def save_settings(self):
        c = self.engine.config; c["api_key"] = self.ent_api_key.get().strip()
        c["gemini_api_key"] = self.ent_gemini_key.get().strip(); c["use_ai_ocr"] = self.var_use_ai.get()
        c["tesseract_path"] = self.ent_tesseract.get().strip(); c["hotkey"] = self.ent_hotkey.get().strip()
        try: c["monitor_index"] = int(self.cmb_monitor.get()); c["debug_mode"] = self.var_debug.get()
        except: pass
        save_config(c); self.engine.config = c; self.engine.ocr_extractor.config = c
        self.engine.ocr_extractor.pytesseract.pytesseract.tesseract_cmd = c["tesseract_path"]
        self.register_hotkey(); messagebox.showinfo("Gespeichert", "Einstellungen übernommen.")

    def register_hotkey(self):
        hk = self.engine.config.get("hotkey", "ctrl+alt+s")
        try: keyboard.unhook_all_hotkeys()
        except: pass
        try: self.hotkey_hook = keyboard.add_hotkey(hk, lambda: self.root.after(0, self.run_once_manual))
        except: pass
        try: keyboard.add_hotkey("play/pause media", lambda: self.engine.tts_service.toggle_pause())
        except: pass

    def run_once_manual(self):
        self.lbl_status.config(text="Das Auge sieht...", foreground=COLOR_TEXT_GOLD)
        threading.Thread(target=self.process_pipeline, daemon=True).start()

    def process_pipeline(self):
        try:
            # --- UPDATE: Tuple return ---
            txt, src = self.engine.run_pipeline()
            if not txt:
                self.root.after(0, lambda: self.update_status("Kein Text.", error=True))
                return
            self.root.after(0, lambda: self.update_ui_text(txt))
            self.root.after(0, lambda: self.load_debug_images()) 
            self.root.after(0, lambda: self.update_status(f"Fertig (via {src}).", done=True))
        except Exception as e:
            self.root.after(0, lambda: self.update_status(f"Fehler: {e}", error=True))

    def update_ui_text(self, txt):
        self.txt_preview.config(state="normal"); self.txt_preview.delete(1.0, tk.END); self.txt_preview.insert(tk.END, txt); self.txt_preview.config(state="disabled")
    def update_status(self, text, error=False, done=False):
        color = COLOR_ACCENT_RED if error else (COLOR_TEXT_GOLD if not done else "#4caf50")
        self.lbl_status.config(text=text, foreground=color)

if __name__ == "__main__":
    from utils import load_config
    load_config() 
    root = tk.Tk()
    app = LotroApp(root)
    root.mainloop()
