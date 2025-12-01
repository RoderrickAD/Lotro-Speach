import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import os
import keyboard
from core import CoreEngine # NEUE IMPORT
from utils import save_config, log_message

# --- LOTRO FARBPALETTE ---
COLOR_BG_MAIN = "#191b1e"       # Sehr dunkles Grau (Hintergrund)
COLOR_BG_FRAME = "#25282d"      # Etwas helleres Grau (Container)
COLOR_TEXT_GOLD = "#d4af37"     # LOTRO Gold (Titel/Wichtige Infos)
COLOR_TEXT_SILVER = "#e6e6e6"   # Silber (Normaler Text - Erhöhter Kontrast)
COLOR_BTN_BG = "#3d424b"        # Button Hintergrund
COLOR_BTN_FG = "#d4af37"        # Button Text (Gold)
COLOR_ENTRY_BG = "#0f0f0f"      # Eingabefelder Schwarz
COLOR_ACCENT = "#782221"        # Dunkelrot (für Fehler/Wichtige Info)
COLOR_STATUS_READY = "#4caf50"  # Grün
COLOR_STATUS_SCAN = "#d4af37"   # Gold
COLOR_STATUS_TTS = "#4facfe"    # Blau

FONT_UI = ("Georgia", 11)       
FONT_TITLE = ("Georgia", 22, "bold")
FONT_BOLD = ("Georgia", 11, "bold")
FONT_MONO = ("Consolas", 10)

class LotroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LOTRO Voice Companion 2.0")
        
        self.root.geometry("1000x800")
        self.root.resizable(False, False) 
        self.root.configure(bg=COLOR_BG_MAIN)
        
        self.setup_styles()
        
        self.engine = CoreEngine() # INSTANZ DER NEUEN CORE ENGINE
        self.running = False
        self.hotkey_hook = None
        self.old_log_content = "" 

        main_pad_frame = ttk.Frame(root, padding="15 15 15 15")
        main_pad_frame.pack(expand=True, fill="both")

        self.notebook = ttk.Notebook(main_pad_frame)
        self.notebook.pack(expand=True, fill="both")

        self.tab_main = self.create_tab_frame(self.notebook)
        self.tab_settings = self.create_tab_frame(self.notebook)

        self.notebook.add(self.tab_main, text="  Scannen & Status  ")
        self.notebook.add(self.tab_settings, text="  Einstellungen  ")

        self.setup_main_tab()
        self.setup_settings_tab()

        self.load_settings_to_ui()
        self.register_hotkey()
        self.update_log_preview()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        style.configure("TNotebook", background=COLOR_BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", 
                        background=COLOR_BTN_BG, 
                        foreground=COLOR_TEXT_SILVER, 
                        font=FONT_BOLD, 
                        padding=[15, 5])
        style.map("TNotebook.Tab", 
                  background=[("selected", COLOR_BG_FRAME)], 
                  foreground=[("selected", COLOR_TEXT_GOLD)])

        style.configure("TFrame", background=COLOR_BG_FRAME)
        style.configure("TLabel", background=COLOR_BG_FRAME, foreground=COLOR_TEXT_SILVER, font=FONT_UI)
        style.configure("Header.TLabel", foreground=COLOR_TEXT_GOLD, font=FONT_TITLE)
        style.configure("LogHeader.TLabel", foreground=COLOR_TEXT_GOLD, font=FONT_BOLD)
        style.configure("Check.TCheckbutton", background=COLOR_BG_FRAME, foreground=COLOR_TEXT_SILVER, font=FONT_UI)
        
        style.configure("Status.TLabel", 
                        background=COLOR_ENTRY_BG, 
                        foreground=COLOR_STATUS_READY, 
                        font=("Georgia", 14, "bold"),
                        padding=[10, 10], 
                        anchor="center") 

    def create_tab_frame(self, parent):
        frame = ttk.Frame(parent, padding="10 10 10 10")
        frame.pack(fill="both", expand=True)
        return frame

    def create_lotro_button(self, parent, text, command, bg_color=COLOR_BTN_BG):
        btn = tk.Button(parent, 
                        text=text, 
                        command=command,
                        bg=bg_color,
                        fg=COLOR_BTN_FG,
                        font=FONT_BOLD,
                        activebackground=COLOR_TEXT_GOLD,
                        activeforeground=COLOR_BG_MAIN,
                        relief="ridge",
                        bd=3,
                        padx=15,
                        pady=8,
                        cursor="hand2")
        return btn

    def setup_main_tab(self):
        self.tab_main.grid_columnconfigure(0, weight=3)
        self.tab_main.grid_columnconfigure(1, weight=1)
        self.tab_main.grid_rowconfigure(0, weight=1)

        left_frame = ttk.Frame(self.tab_main, style="TFrame")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(left_frame, text="Erkannter Quest-Text:", style="Header.TLabel").grid(row=0, column=0, sticky="w", pady=(5, 5), padx=15)
        
        self.txt_preview = tk.Text(left_frame, height=35, bg=COLOR_ENTRY_BG, fg=COLOR_TEXT_SILVER, 
                                   insertbackground="white", font=("Georgia", 13), relief="flat", padx=10, pady=10)
        self.txt_preview.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        self.txt_preview.config(state="disabled")

        right_frame = ttk.Frame(self.tab_main, style="TFrame")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        control_frame = ttk.Frame(right_frame, style="TFrame")
        control_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        
        ttk.Label(control_frame, text="Status & Steuerung", foreground=COLOR_TEXT_GOLD, font=FONT_BOLD).pack(pady=(10, 5))
        
        self.lbl_status = ttk.Label(control_frame, text="Status: Bereit (Warte auf Taste...)", style="Status.TLabel") 
        self.lbl_status.pack(fill="x", pady=10, padx=10)

        self.btn_action = self.create_lotro_button(control_frame, "🔊 HOTKEY-Scan Auslösen", self.run_once_manual)
        self.btn_action.pack(fill="x", pady=10, padx=10)
        
        self.lbl_hotkey = ttk.Label(control_frame, text=f"Hotkey: {self.engine.config.get('hotkey', 'ctrl+alt+s')}", 
                                    foreground=COLOR_ACCENT)
        self.lbl_hotkey.pack(pady=(5, 10))

        ttk.Label(right_frame, text="System-Log Vorschau:", style="LogHeader.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 5), padx=10)
        
        self.log_widget = scrolledtext.ScrolledText(right_frame, state='disabled', height=18, bg=COLOR_ENTRY_BG, fg="#a0a0a0", font=FONT_MONO, relief="flat")
        self.log_widget.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 15))


    def setup_settings_tab(self):
        canvas = tk.Canvas(self.tab_settings, bg=COLOR_BG_FRAME, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_settings, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style="TFrame")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=880) 
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True) 
        scrollbar.pack(side="right", fill="y")
        
        def create_entry(parent_frame, label_text, show=None):
            ttk.Label(parent_frame, text=label_text).pack(anchor="w", pady=(10, 2), padx=15)
            entry = tk.Entry(parent_frame, bg=COLOR_ENTRY_BG, fg=COLOR_TEXT_SILVER, insertbackground="white", font=FONT_MONO, relief="flat", bd=5)
            if show: entry.config(show=show)
            entry.pack(fill="x", pady=2, ipady=3, padx=15)
            return entry
        
        def create_text_field(parent_frame, label_text):
            ttk.Label(parent_frame, text=label_text).pack(anchor="w", pady=(10, 2), padx=15)
            text_field = tk.Text(parent_frame, height=3, bg=COLOR_ENTRY_BG, fg=COLOR_TEXT_SILVER, insertbackground="white", font=FONT_MONO, relief="flat", bd=5, padx=5, pady=5)
            text_field.pack(fill="x", pady=2, padx=15)
            return text_field

        api_frame = tk.LabelFrame(scrollable_frame, text="ElevenLabs API & Audio Konfiguration", bg=COLOR_BG_FRAME, fg=COLOR_TEXT_GOLD, font=FONT_BOLD, padx=5, pady=5)
        api_frame.pack(fill="x", pady=(10, 15), padx=5)

        self.ent_api_key = create_entry(api_frame, "ElevenLabs API Key:", show="*")
        self.ent_delay = create_entry(api_frame, "Verzögerung vor Audio-Wiedergabe (Sekunden):")
        self.ent_hotkey = create_entry(api_frame, "Globaler Hotkey (z.B. ctrl+alt+s):")
        
        ocr_frame = tk.LabelFrame(scrollable_frame, text="OCR & Pfad Konfiguration", bg=COLOR_BG_FRAME, fg=COLOR_TEXT_GOLD, font=FONT_BOLD, padx=5, pady=5)
        ocr_frame.pack(fill="x", pady=(15, 15), padx=5)

        self.ent_tesseract = create_entry(ocr_frame, "Pfad zu Tesseract.exe:")
        self.ent_logpath = create_entry(ocr_frame, "Pfad zur LOTRO Script.log:")
        
        ttk.Label(ocr_frame, text="Monitor Auswahl:").pack(anchor="w", pady=(10, 2), padx=15)
        self.cmb_monitor = ttk.Combobox(ocr_frame, values=["1", "2", "3", "4"], state="readonly", font=FONT_UI)
        self.cmb_monitor.pack(fill="x", pady=2, ipady=3, padx=15)
        self.cmb_monitor.set("1")

        ocr_advanced_frame = tk.LabelFrame(scrollable_frame, text="OCR Detail-Konfiguration (Nur für Experten)", bg=COLOR_BG_FRAME, fg=COLOR_TEXT_GOLD, font=FONT_BOLD, padx=5, pady=5)
        ocr_advanced_frame.pack(fill="x", pady=(15, 15), padx=5)
        
        self.ent_ocr_lang = create_entry(ocr_advanced_frame, "Tesseract Sprachen (z.B. deu+eng):")
        self.ent_ocr_psm = create_entry(ocr_advanced_frame, "Tesseract PSM Modus (Standard: 6):")
        self.txt_ocr_whitelist = create_text_field(ocr_advanced_frame, "Tesseract Whitelist (Erlaubte Zeichenkette):")

        self.var_debug = tk.BooleanVar()
        ttk.Checkbutton(scrollable_frame, text="Debug-Bilder (Screenshots/Verarbeitung) speichern", 
                        variable=self.var_debug, style="Check.TCheckbutton").pack(anchor="w", pady=15, padx=15)
        
        self.create_lotro_button(scrollable_frame, "💾 Einstellungen Speichern & Stimmen aktualisieren", self.save_settings).pack(pady=(10, 30), fill="x", padx=5)


    # --- FUNKTIONEN ---
    
    def log(self, msg):
        log_message(msg)
    
    def update_log_preview(self):
        try:
            with open("app.log", "r", encoding="utf-8") as f:
                current_content = f.read()
            
            if current_content != self.old_log_content:
                self.log_widget.config(state='normal')
                lines = current_content.split('\n')
                display_content = '\n'.join(lines[-50:])
                
                self.log_widget.delete(1.0, tk.END)
                self.log_widget.insert(tk.END, display_content)
                self.log_widget.see(tk.END)
                self.log_widget.config(state='disabled')
                self.old_log_content = current_content
                
        except FileNotFoundError:
            pass 
        except Exception as e:
            self.log_widget.config(state='normal')
            self.log_widget.insert(tk.END, f"\nFehler beim Lesen der Log-Datei: {e}")
            self.log_widget.config(state='disabled')

        self.root.after(1000, self.update_log_preview)


    def load_settings_to_ui(self):
        cfg = self.engine.config
        
        fields = [self.ent_api_key, self.ent_tesseract, self.ent_logpath, self.ent_hotkey, self.ent_delay, self.ent_ocr_lang, self.ent_ocr_psm]
        for field in fields:
            field.delete(0, tk.END)
        self.txt_ocr_whitelist.delete(1.0, tk.END)

        self.ent_api_key.insert(0, cfg.get("api_key", ""))
        self.ent_tesseract.insert(0, cfg.get("tesseract_path", ""))
        self.ent_logpath.insert(0, cfg.get("lotro_log_path", ""))
        self.ent_hotkey.insert(0, cfg.get("hotkey", "ctrl+alt+s"))
        self.ent_delay.insert(0, str(cfg.get("audio_delay", 0.5)))
        self.cmb_monitor.set(str(cfg.get("monitor_index", 1)))
        self.var_debug.set(cfg.get("debug_mode", False))
        
        self.ent_ocr_lang.insert(0, cfg.get("ocr_language", "deu+eng"))
        self.ent_ocr_psm.insert(0, str(cfg.get("ocr_psm", 6)))
        self.txt_ocr_whitelist.insert(1.0, cfg.get("ocr_whitelist", 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzäöüÄÖÜß0123456789.,?!:;\'"()[]-/'))
        
        self.lbl_hotkey.config(text=f"Hotkey: {cfg.get('hotkey', 'ctrl+alt+s')}")

    def save_settings(self):
        cfg = self.engine.config
        
        cfg["api_key"] = self.ent_api_key.get().strip()
        cfg["tesseract_path"] = self.ent_tesseract.get().strip()
        cfg["lotro_log_path"] = self.ent_logpath.get().strip()
        cfg["hotkey"] = self.ent_hotkey.get().strip()
        cfg["ocr_language"] = self.ent_ocr_lang.get().strip()
        cfg["ocr_whitelist"] = self.txt_ocr_whitelist.get(1.0, tk.END).strip()

        try:
            cfg["audio_delay"] = float(self.ent_delay.get().strip())
            cfg["monitor_index"] = int(self.cmb_monitor.get())
            cfg["debug_mode"] = self.var_debug.get()
            cfg["ocr_psm"] = int(self.ent_ocr_psm.get().strip())
        except ValueError:
            messagebox.showerror("Fehler", "Zahlenformat (Verzögerung/Monitor/PSM) ist falsch.")
            return

        save_config(cfg)
        self.engine.config = cfg
        # Konfigurationen in den Services aktualisieren
        self.engine.ocr_extractor.config = cfg
        self.engine.ocr_extractor.pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_path"]
        self.engine.tts_service.config = cfg
        
        self.register_hotkey()
        
        threading.Thread(target=self.engine.fetch_voices).start() 
        messagebox.showinfo("Gespeichert", "Einstellungen wurden übernommen und Stimmen werden aktualisiert.")

    def register_hotkey(self):
        hk = self.engine.config.get("hotkey", "ctrl+alt+s")
        if self.hotkey_hook:
            try: keyboard.remove_hotkey(self.hotkey_hook)
            except: pass
        try:
            self.hotkey_hook = keyboard.add_hotkey(hk, lambda: self.root.after(0, self.run_once_manual))
            self.log(f"Hotkey aktiviert ({hk})")
        except: self.log(f"Hotkey Fehler: Konnte '{hk}' nicht registrieren.")

    def run_once_manual(self):
        """ Scannt und liest vor (Einmalig) """
        self.lbl_status.config(text="Status: Scanne...", style="Status.TLabel", foreground=COLOR_STATUS_SCAN) 
        self.log("Manuelle Scan-Anforderung erhalten.")
        threading.Thread(target=self.process_pipeline, daemon=True).start()

    def process_pipeline(self):
        """ Führt die Pipeline (OCR -> TTS) im Hintergrund aus. """
        try:
            # Führt die gesamte Pipeline aus
            txt = self.engine.run_pipeline()
            
            if not txt or len(txt) < 5:
                self.log("Kein Text gefunden (OCR-Ergebnis zu kurz oder leer).")
                self.root.after(0, lambda: self.lbl_status.config(text="Status: Kein Text gefunden", style="Status.TLabel", foreground=COLOR_ACCENT)) 
                self.root.after(0, lambda: self.update_text_preview("--- Kein verwertbarer Dialogtext gefunden ---"))
                return
            
            self.log(f"Erkannt: {txt[:70]}{'...' if len(txt) > 70 else ''}")
            self.root.after(0, lambda: self.update_text_preview(txt))
            self.root.after(0, lambda: self.lbl_status.config(text="Status: Fertig (Bereit)", style="Status.TLabel", foreground=COLOR_STATUS_READY))
            
        except Exception as e:
            self.log(f"FEHLER in der Pipeline: {e}")
            self.root.after(0, lambda: self.lbl_status.config(text="Status: FEHLER", style="Status.TLabel", foreground=COLOR_ACCENT))

    def update_text_preview(self, txt):
        """ Aktualisiert das Text-Widget (muss im Haupt-Thread laufen) """
        self.txt_preview.config(state="normal")
        self.txt_preview.delete(1.0, tk.END)
        self.txt_preview.insert(tk.END, txt)
        self.txt_preview.config(state="disabled")

if __name__ == "__main__":
    # Stelle sicher, dass die Konfigurationsdatei existiert, bevor die App startet
    from utils import load_config
    load_config() 
    root = tk.Tk()
    app = LotroApp(root)
    root.mainloop()
