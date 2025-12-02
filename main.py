import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk  # Benötigt: pip install Pillow
import threading
import os
import keyboard
from core import CoreEngine
from utils import save_config, log_message

# --- LOTRO THEME COLORS ---
COLOR_BG_DARK = "#1a1110"       # Sehr dunkles Braun/Schwarz (Mordor)
COLOR_BG_PANEL = "#2b221b"      # Dunkles Leder
COLOR_TEXT_GOLD = "#c5a059"     # Der Eine Ring Gold
COLOR_TEXT_DIM = "#8c7b70"      # Altpapier Grau
COLOR_ACCENT_RED = "#5c1815"    # Dunkelrot
COLOR_INPUT_BG = "#0f0a08"      # Fast Schwarz für Eingabefelder

FONT_TITLE = ("Georgia", 20, "bold")
FONT_UI = ("Georgia", 11)
FONT_TEXT = ("Georgia", 12)
FONT_MONO = ("Consolas", 10)

class LotroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Der Vorleser von Mittelerde")
        self.root.geometry("900x700")
        self.root.configure(bg=COLOR_BG_DARK)
        
        # Icon laden (falls vorhanden)
        if os.path.exists("app_icon.ico"):
            self.root.iconbitmap("app_icon.ico")

        self.engine = CoreEngine()
        self.running = False
        self.hotkey_hook = None
        
        # Hintergrundbild laden
        self.bg_photo = None
        self.setup_background()

        # Styling
        self.setup_styles()

        # Haupt-Container (Canvas für Transparenz-Effekte wäre kompliziert, wir nutzen Frames)
        # Wir nutzen ein Notebook (Tabs) aber stylen es dunkel
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=20, pady=20)

        self.tab_status = self.create_tab(self.notebook, "Das Auge (Status)")
        self.tab_settings = self.create_tab(self.notebook, "Die Schriften (Einstellungen)")

        self.setup_status_tab()
        self.setup_settings_tab()

        self.load_settings_to_ui()
        self.register_hotkey()

    def setup_background(self):
        """Versucht background.png zu laden und als Hintergrund zu setzen."""
        bg_path = "background.png"
        if os.path.exists(bg_path):
            try:
                # Bild laden und auf Fenstergröße skalieren (initial)
                image = Image.open(bg_path)
                # Wir machen es etwas dunkler für bessere Lesbarkeit
                image = image.point(lambda p: p * 0.5) 
                self.bg_image_raw = image # Original behalten zum Resizen
                
                self.bg_label = tk.Label(self.root, bg=COLOR_BG_DARK)
                self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
                
                # Bind resize event
                self.root.bind("<Configure>", self.resize_background)
            except Exception as e:
                print(f"Hintergrund konnte nicht geladen werden: {e}")

    def resize_background(self, event):
        if hasattr(self, 'bg_image_raw'):
            new_width = event.width
            new_height = event.height
            if new_width > 0 and new_height > 0:
                resized = self.bg_image_raw.resize((new_width, new_height), Image.Resampling.LANCZOS)
                self.bg_photo = ImageTk.PhotoImage(resized)
                self.bg_label.config(image=self.bg_photo)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Tabs Style
        style.configure("TNotebook", background=COLOR_BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", 
                        background=COLOR_BG_PANEL, 
                        foreground=COLOR_TEXT_DIM, 
                        font=("Georgia", 10, "bold"),
                        padding=[15, 8],
                        borderwidth=0)
        style.map("TNotebook.Tab", 
                  background=[("selected", COLOR_ACCENT_RED)], 
                  foreground=[("selected", COLOR_TEXT_GOLD)])

        # Frame Style
        style.configure("TFrame", background=COLOR_BG_PANEL)
        
        # Label Style
        style.configure("TLabel", background=COLOR_BG_PANEL, foreground=COLOR_TEXT_GOLD, font=FONT_UI)
        style.configure("Header.TLabel", font=FONT_TITLE, foreground=COLOR_TEXT_GOLD)
        
        # Button Style (Goldener Rahmen simuliert durch Farben)
        style.configure("TButton", 
                        background=COLOR_BG_DARK, 
                        foreground=COLOR_TEXT_GOLD, 
                        font=("Georgia", 11, "bold"),
                        borderwidth=2,
                        focuscolor=COLOR_TEXT_GOLD)
        style.map("TButton", 
                  background=[('active', COLOR_ACCENT_RED)], 
                  foreground=[('active', 'white')])

    def create_tab(self, parent, title):
        frame = ttk.Frame(parent, style="TFrame")
        parent.add(frame, text=title)
        return frame

    def create_gold_border_entry(self, parent, variable=None, show=None):
        """Erstellt ein Eingabefeld mit 'goldenem' Look"""
        entry = tk.Entry(parent, 
                         bg=COLOR_INPUT_BG, 
                         fg=COLOR_TEXT_GOLD, 
                         insertbackground=COLOR_TEXT_GOLD, 
                         font=FONT_MONO, 
                         relief="flat", 
                         bd=5,
                         textvariable=variable)
        if show: entry.config(show=show)
        return entry

    # --- TAB 1: STATUS ---
    def setup_status_tab(self):
        # Layout: Oben Status-Text, Mitte Großes Textfeld, Unten Button
        self.tab_status.grid_columnconfigure(0, weight=1)
        self.tab_status.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ttk.Frame(self.tab_status, padding="10 20 10 10")
        header_frame.grid(row=0, column=0, sticky="ew")
        
        self.lbl_status = ttk.Label(header_frame, text="Das Auge ruht... (Warte auf Hotkey)", font=("Georgia", 14, "italic"))
        self.lbl_status.pack()

        # Text Area (Das Pergament)
        text_frame = ttk.Frame(self.tab_status, padding="20 0 20 20")
        text_frame.grid(row=1, column=0, sticky="nsew")
        
        self.txt_preview = tk.Text(text_frame, 
                                   bg=COLOR_INPUT_BG, 
                                   fg="#e0d5c1", # Helles Pergament-Weiß für Lesbarkeit
                                   font=("Georgia", 14), 
                                   wrap="word", 
                                   relief="flat", 
                                   padx=15, pady=15,
                                   bd=0)
        self.txt_preview.pack(expand=True, fill="both")
        self.txt_preview.insert("1.0", "\n\n   Noch wurde kein Text aus den Schatten Mittelerdes entrissen...\n")
        self.txt_preview.config(state="disabled")

        # Manueller Button
        btn_frame = ttk.Frame(self.tab_status, padding="0 0 0 20")
        btn_frame.grid(row=2, column=0)
        
        self.btn_scan = tk.Button(btn_frame, 
                                  text="Macht entfesseln (Scan)", 
                                  command=self.run_once_manual,
                                  bg=COLOR_ACCENT_RED,
                                  fg=COLOR_TEXT_GOLD,
                                  font=("Georgia", 12, "bold"),
                                  relief="ridge",
                                  bd=3,
                                  padx=20, pady=8,
                                  cursor="hand2",
                                  activebackground=COLOR_TEXT_GOLD,
                                  activeforeground="black")
        self.btn_scan.pack()

    # --- TAB 2: EINSTELLUNGEN ---
    def setup_settings_tab(self):
        # Ein Canvas für Scrolling, falls es auf kleinen Bildschirmen eng wird
        canvas = tk.Canvas(self.tab_settings, bg=COLOR_BG_PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_settings, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=800)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=20, pady=20)
        scrollbar.pack(side="right", fill="y")

        # --- SEKTION 1: DIE STIMME (API) ---
        lbl_sec1 = ttk.Label(scrollable_frame, text="Die Stimme (ElevenLabs)", style="Header.TLabel")
        lbl_sec1.pack(anchor="w", pady=(10, 10))

        ttk.Label(scrollable_frame, text="Geheimer Schlüssel (API Key):").pack(anchor="w")
        self.ent_api_key = self.create_gold_border_entry(scrollable_frame, show="*")
        self.ent_api_key.pack(fill="x", pady=(0, 15))

        # --- SEKTION 2: DAS AUGE (OCR) ---
        lbl_sec2 = ttk.Label(scrollable_frame, text="Das Auge (OCR Einstellungen)", style="Header.TLabel")
        lbl_sec2.pack(anchor="w", pady=(10, 10))

        ttk.Label(scrollable_frame, text="Pfad zu Tesseract (Die Seher-Linse):").pack(anchor="w")
        self.ent_tesseract = self.create_gold_border_entry(scrollable_frame)
        self.ent_tesseract.pack(fill="x", pady=(0, 10))
        
        # Einfacher Monitor-Wähler
        frame_mon = ttk.Frame(scrollable_frame)
        frame_mon.pack(fill="x", pady=5)
        ttk.Label(frame_mon, text="Welchen Monitor beobachtet das Auge?").pack(side="left")
        self.cmb_monitor = ttk.Combobox(frame_mon, values=["1", "2", "3", "4"], width=5, font=FONT_UI, state="readonly")
        self.cmb_monitor.pack(side="left", padx=10)
        
        # --- SEKTION 3: MAGIE (Steuerung) ---
        lbl_sec3 = ttk.Label(scrollable_frame, text="Magie (Steuerung)", style="Header.TLabel")
        lbl_sec3.pack(anchor="w", pady=(20, 10))

        ttk.Label(scrollable_frame, text="Zauberspruch (Hotkey, z.B. ctrl+alt+s):").pack(anchor="w")
        self.ent_hotkey = self.create_gold_border_entry(scrollable_frame)
        self.ent_hotkey.pack(fill="x", pady=(0, 10))

        # Checkbox für Debug
        self.var_debug = tk.BooleanVar()
        chk = tk.Checkbutton(scrollable_frame, 
                             text="Visionen aufzeichnen (Debug Bilder speichern)", 
                             variable=self.var_debug,
                             bg=COLOR_BG_PANEL, 
                             fg=COLOR_TEXT_DIM,
                             selectcolor=COLOR_BG_DARK,
                             activebackground=COLOR_BG_PANEL,
                             activeforeground=COLOR_TEXT_GOLD,
                             font=FONT_UI)
        chk.pack(anchor="w", pady=10)

        # SPEICHERN BUTTON
        self.btn_save = tk.Button(scrollable_frame, 
                                  text="In Stein meißeln (Speichern)", 
                                  command=self.save_settings,
                                  bg=COLOR_TEXT_GOLD,
                                  fg="black",
                                  font=("Georgia", 12, "bold"),
                                  relief="raised",
                                  bd=3,
                                  padx=20, pady=10,
                                  cursor="hand2")
        self.btn_save.pack(pady=30, fill="x")

    # --- LOGIK ---
    def load_settings_to_ui(self):
        cfg = self.engine.config
        self.ent_api_key.insert(0, cfg.get("api_key", ""))
        self.ent_tesseract.insert(0, cfg.get("tesseract_path", ""))
        self.ent_hotkey.insert(0, cfg.get("hotkey", "ctrl+alt+s"))
        self.cmb_monitor.set(str(cfg.get("monitor_index", 1)))
        self.var_debug.set(cfg.get("debug_mode", False))

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
        # Services neu laden
        self.engine.ocr_extractor.config = cfg
        self.engine.ocr_extractor.pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_path"]
        self.engine.tts_service.config = cfg
        
        self.register_hotkey()
        threading.Thread(target=self.engine.fetch_voices).start() 
        messagebox.showinfo("Erfolg", "Die Schriften wurden aktualisiert.")

    def register_hotkey(self):
        hk = self.engine.config.get("hotkey", "ctrl+alt+s")
        if self.hotkey_hook:
            try: keyboard.remove_hotkey(self.hotkey_hook)
            except: pass
        try:
            self.hotkey_hook = keyboard.add_hotkey(hk, lambda: self.root.after(0, self.run_once_manual))
            self.lbl_status.config(text=f"Das Auge wacht auf Zeichen: {hk}")
        except:
            self.lbl_status.config(text=f"Warnung: Zauberspruch '{hk}' konnte nicht gewirkt werden.")

    def run_once_manual(self):
        self.lbl_status.config(text="Das Auge sieht...", foreground=COLOR_TEXT_GOLD)
        self.btn_scan.config(state="disabled", bg="#333333")
        threading.Thread(target=self.process_pipeline, daemon=True).start()

    def process_pipeline(self):
        try:
            txt = self.engine.run_pipeline()
            if not txt or len(txt) < 5:
                self.root.after(0, lambda: self.update_status("Keine Schrift erkannt.", error=True))
                return
            
            self.root.after(0, lambda: self.update_ui_text(txt))
            self.root.after(0, lambda: self.update_status("Die Stimme spricht...", done=True))
            
        except Exception as e:
            self.root.after(0, lambda: self.update_status(f"Dunkle Magie (Fehler): {str(e)}", error=True))
        finally:
            self.root.after(2000, lambda: self.btn_scan.config(state="normal", bg=COLOR_ACCENT_RED))

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
