"""VoiceOverApp – Desktop-GUI (tkinter/ttk, §27).

Echte Windows-App um die GESPERRTE Produktionspipeline: PDF hinein-
ziehen, Text prüfen, Sprache/Stimme wählen, erstellen, Fortschritt
beobachten, Ergebnis öffnen. Der Benutzer sieht kein PowerShell, kein
Python, keine Cache-Keys (§36).

VD-E ist Standard und als solches markiert (§10); die Referenz kann
über die GUI NIEMALS verändert werden (§11/§24). Produktionsparameter
sind GUI-seitig nicht bearbeitbar (§3/§25).
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from tkinter import (ALL, BOTH, BOTTOM, END, HORIZONTAL, LEFT, RIGHT, TOP, VERTICAL,
                     W, X, Y, Canvas, filedialog, messagebox, ttk)
import tkinter as tk

from .. import paths
from ..security.identity_lock import check_identity, load_production
from ..voices.registry import VoiceRegistry
from .backend import BackendLauncher, JobResult, parse_progress_event
from .helpers import format_duration, format_eta, stage_label, text_stats
from .voice_view import default_voice, voice_groups

try:                                    # Windows Drag & Drop (§28)
    import windnd                      # type: ignore
    _HAS_WINDND = True
except Exception:                       # macOS/Linux/Quelle ohne windnd
    _HAS_WINDND = False

ACCENT = "#4da3ff"
BG = "#10141b"
CARD = "#171d27"
FG = "#e8edf4"
MUTED = "#93a1b4"
FONTS_MAIN = ("Segoe UI", 10)
FONTS_H1 = ("Segoe UI", 16, "bold")
FONTS_MONO = ("Consolas", 10)


class VoiceOverApp(tk.Tk if tk else object):        # noqa: D101
    def __init__(self):
        super().__init__()
        self.title("VoiceOverApp")
        self.configure(bg=BG)
        self.geometry("980x940")
        self.minsize(860, 780)

        self.registry = VoiceRegistry()
        self.production = load_production()
        self.identity = check_identity(self.production)
        self.launcher: BackendLauncher | None = None
        self.job_start = 0.0
        self.last_summary: dict = {}
        self.last_wav = ""
        self.last_mp3 = ""
        self.last_report = ""
        self._build_style()
        self._build_ui()
        self._refresh_identity_badge()
        self._init_drag_drop()
        self._on_format_change()
        threading.Timer(0.2, self._startup_checks).start()

    # ------------------------------------------------------------- Style
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        for name in ("TFrame", "TLabelframe", "TLabelframe.Label"):
            style.configure(name, background=CARD, foreground=FG,
                            font=FONTS_MAIN)
        style.configure("Header.TFrame", background=BG)
        style.configure("Header.TLabel", background=BG, foreground=FG,
                        font=FONTS_H1)
        style.configure("Sub.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=CARD, foreground=FG,
                        font=FONTS_MAIN)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"),
                        padding=10)
        style.configure("TProgressbar", thickness=16,
                        background=ACCENT, fieldbackground="#0b0e13")
        style.configure("TRadiobutton", background=CARD, foreground=FG,
                        font=FONTS_MAIN, focuscolor=CARD)
        style.map("TRadiobutton", background=[("active", CARD)])

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        # Header
        head = ttk.Frame(self, style="Header.TFrame")
        head.pack(fill=X, padx=16, pady=(12, 4))
        ttk.Label(head, text="VoiceOverApp",
                  style="Header.TLabel").pack(side=LEFT)
        ttk.Label(head, text="  Lokale KI-Voice-over-Erstellung",
                  style="Sub.TLabel").pack(side=LEFT, pady=(6, 0))
        self.identity_badge = ttk.Label(head, text="", style="Sub.TLabel")
        self.identity_badge.pack(side=RIGHT, pady=(6, 0))

        # Scrollable main area. Header stays pinned above; the cards
        # (file/text/language/voice/options/start/progress/output) sit
        # inside an inner Frame on a Canvas. Vertical scrollbar +
        # mouse-wheel work on Windows; scrollregion auto-updates when
        # the inner Frame changes size (incl. language/voice rebuilds).
        outer = ttk.Frame(self)
        outer.pack(fill=BOTH, expand=True, padx=0, pady=0)
        self._vscroll = ttk.Scrollbar(outer, orient=VERTICAL)
        self._vscroll.pack(side=RIGHT, fill=Y)
        self._canvas = Canvas(outer, bg=BG, highlightthickness=0,
                              yscrollcommand=self._vscroll.set,
                              bd=0)
        self._canvas.pack(side=LEFT, fill=BOTH, expand=True, padx=(16, 0), pady=8)
        self._vscroll.config(command=self._canvas.yview)
        container = ttk.Frame(self._canvas, style="Card.TFrame")
        self._canvas_window = self._canvas.create_window((0, 0), window=container, anchor="nw")

        def _on_container_configure(_e=None):
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        def _on_canvas_configure(e):
            # Make inner frame match canvas width (horizontal scroll avoided)
            desired = max(e.width, 1)
            self._canvas.itemconfigure(self._canvas_window, width=desired)
        container.bind("<Configure>", _on_container_configure)
        self._canvas.bind("<Configure>", _on_canvas_configure)
        # Mouse wheel (Windows: <MouseWheel> delta=120 per notch; Linux: 4/5)
        def _on_wheel(e):
            if os.name == "nt":
                delta = -1 if e.delta > 0 else 1
                self._canvas.yview_scroll(delta, "units")
            else:
                if e.num == 4: self._canvas.yview_scroll(-1, "units")
                elif e.num == 5: self._canvas.yview_scroll(1, "units")
        self._canvas.bind_all("<MouseWheel>", _on_wheel, add="+")
        self._canvas.bind("<Button-4>", _on_wheel, add="+")
        self._canvas.bind("<Button-5>", _on_wheel, add="+")
        # Expose so rebuilders can scroll to top after voice list refresh
        self._scroll_container = container

        # DATEI
        file_card = ttk.Labelframe(container, text=" Datei ")
        file_card.pack(fill=X, pady=(0, 8))
        self.drop_label = tk.Label(
            file_card, text="PDF hierher ziehen  –  oder:",
            bg="#0d1117", fg=MUTED, font=FONTS_MAIN, padx=12, pady=18,
            relief="groove", borderwidth=2)
        self.drop_label.pack(fill=X, padx=8, pady=8)
        btns = ttk.Frame(file_card)
        btns.pack(fill=X, padx=8, pady=(0, 8))
        ttk.Button(btns, text="PDF auswählen",
                   command=self.pick_pdf).pack(side=LEFT)
        ttk.Button(btns, text="TXT auswählen",
                   command=self.pick_txt).pack(side=LEFT, padx=8)

        # TEXT
        text_card = ttk.Labelframe(container, text=" Text ")
        text_card.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.text_widget = tk.Text(text_card, height=9, bg="#0d1117",
                                   fg=FG, insertbackground=FG,
                                   font=FONTS_MONO, wrap="word",
                                   relief="flat", padx=10, pady=8)
        self.text_widget.pack(fill=BOTH, expand=True, padx=8, pady=8)
        self.text_widget.bind("<<Modified>>", self._on_text_changed)
        self.stats_label = ttk.Label(text_card, text="0 Zeichen · 0 Wörter",
                                     style="Muted.TLabel")
        self.stats_label.pack(anchor=W, padx=10, pady=(0, 8))

        # SPRACHE
        lang_card = ttk.Labelframe(container, text=" Sprache ")
        lang_card.pack(fill=X, pady=(0, 8))
        self.lang_var = tk.StringVar(value="German")
        ttk.Radiobutton(lang_card, text="Deutsch", value="German",
                        variable=self.lang_var,
                        command=self._on_language_change).pack(
            side=LEFT, padx=12, pady=8)
        ttk.Radiobutton(lang_card, text="English", value="English",
                        variable=self.lang_var,
                        command=self._on_language_change).pack(
            side=LEFT, padx=12)

        # STIMME (§6: abhängig von der gewählten Sprache, dynamisch)
        self.voice_card = ttk.Labelframe(container, text=" Stimme ")
        self.voice_card.pack(fill=X, pady=(0, 8))
        self.voice_var = tk.StringVar(value="vd_e")
        self._rebuild_voice_card()

        # OPTIONEN
        opt_card = ttk.Labelframe(container, text=" Optionen ")
        opt_card.pack(fill=X, pady=(0, 8))
        row1 = ttk.Frame(opt_card)
        row1.pack(fill=X, padx=8, pady=8)
        ttk.Label(row1, text="Geschwindigkeit",
                  style="Card.TLabel").pack(side=LEFT)
        self.speed_var = tk.StringVar(value="1.00")
        speed_box = ttk.Combobox(row1, textvariable=self.speed_var,
                                 width=6, state="readonly",
                                 values=[f"{x:.2f}" for x in
                                         (0.80, 0.90, 0.95, 1.00, 1.05,
                                          1.10, 1.20)])
        speed_box.pack(side=LEFT, padx=8)
        ttk.Label(row1, text="Ausgabeformat",
                  style="Card.TLabel").pack(side=LEFT, padx=(16, 0))
        self.format_var = tk.StringVar(value="WAV + MP3")
        fmt_box = ttk.Combobox(row1, textvariable=self.format_var, width=12,
                               state="readonly",
                               values=["WAV + MP3", "WAV only", "MP3 only"])
        fmt_box.pack(side=LEFT, padx=8)
        fmt_box.bind("<<ComboboxSelected>>",
                     lambda _e: self._on_format_change())

        # WAV-Bittiefe + MP3-Bitrate separat (nicht mehr vermischt)
        ttk.Label(row1, text="WAV", style="Muted.TLabel").pack(
            side=LEFT, padx=(12, 0))
        self.wav_bits_var = tk.StringVar(value="24 Bit")
        ttk.Combobox(row1, textvariable=self.wav_bits_var, width=6,
                     state="readonly",
                     values=["16 Bit", "24 Bit"]).pack(side=LEFT, padx=4)
        ttk.Label(row1, text="MP3", style="Muted.TLabel").pack(
            side=LEFT, padx=(8, 0))
        self.mp3_bitrate_var = tk.StringVar(value="320 kbps")
        self.mp3_bitrate_box = ttk.Combobox(
            row1, textvariable=self.mp3_bitrate_var, width=8,
            state="readonly", values=["128 kbps", "192 kbps", "320 kbps"])
        self.mp3_bitrate_box.pack(side=LEFT, padx=4)

        row1b = ttk.Frame(opt_card)
        row1b.pack(fill=X, padx=8, pady=(0, 6))
        self.split_var = tk.BooleanVar(value=False)
        self.split_check = ttk.Checkbutton(
            row1b, text="Manuelles Splitting (+++++-Marker im Text)",
            variable=self.split_var,
            command=self._update_outmode_state)
        self.split_check.pack(side=LEFT)
        ttk.Label(row1b, text="Ausgabemodus", style="Card.TLabel").pack(
            side=LEFT, padx=(18, 0))
        self.outmode_var = tk.StringVar(value="Gesamtdatei (Standard)")
        self.outmode_box = ttk.Combobox(
            row1b, textvariable=self.outmode_var, width=26,
            state="disabled",
            values=["Nur Parts (Part_001…)",
                    "Parts + Gesamtdatei (FullScript)"])
        self.outmode_box.pack(side=LEFT, padx=8)
        row2 = ttk.Frame(opt_card)
        row2.pack(fill=X, padx=8, pady=(0, 8))
        ttk.Label(row2, text="Ausgabeordner",
                  style="Card.TLabel").pack(side=LEFT)
        self.outdir_var = tk.StringVar(value=str(paths.OUTPUT_DIR))
        ttk.Entry(row2, textvariable=self.outdir_var).pack(
            side=LEFT, fill=X, expand=True, padx=8)
        ttk.Button(row2, text="…", width=3,
                   command=self.pick_outdir).pack(side=LEFT)

        # START + Abbrechen (Abbrechen nur sichtbar, wenn Job läuft)
        btn_row = ttk.Frame(container)
        btn_row.pack(fill=X, pady=(2, 8))
        self.start_btn = ttk.Button(btn_row, text="VOICE-OVER ERSTELLEN",
                                    style="Big.TButton",
                                    command=self.start_job)
        self.start_btn.pack(side=LEFT, fill=X, expand=True)
        self.cancel_btn = ttk.Button(btn_row, text="ABBRECHEN",
                                     command=self._cancel_job,
                                     state="disabled")
        self.cancel_btn.pack(side=RIGHT, padx=(8, 0))

        # FORTSCHRITT
        prog_card = ttk.Labelframe(container, text=" Fortschritt ")
        prog_card.pack(fill=X, pady=(0, 8))
        self.progress = ttk.Progressbar(prog_card, maximum=100)
        self.progress.pack(fill=X, padx=8, pady=(8, 2))
        self.stage_label = ttk.Label(prog_card, text="Bereit.",
                                     style="Card.TLabel")
        self.stage_label.pack(anchor=W, padx=10)
        self.seg_label = ttk.Label(prog_card, text="", style="Muted.TLabel")
        self.seg_label.pack(anchor=W, padx=10)
        self.qc_label = ttk.Label(prog_card, text="", style="Muted.TLabel")
        self.qc_label.pack(anchor=W, padx=10)
        self.heartbeat_label = ttk.Label(prog_card, text="", style="Muted.TLabel")
        self.heartbeat_label.pack(anchor=W, padx=10, pady=(0, 8))
        # Heartbeat ticker (updates segment elapsed/last-progress label every second while running)
        self._last_event_time = 0.0
        self._job_start_monotonic = 0.0
        self._segment_start_monotonic = 0.0
        self._heartbeat_after_id = None

        # AUSGABE
        out_card = ttk.Labelframe(container, text=" Ausgabe ")
        out_card.pack(fill=X, pady=(0, 8))
        obtns = ttk.Frame(out_card)
        obtns.pack(fill=X, padx=8, pady=8)
        self.btn_wav = ttk.Button(obtns, text="WAV öffnen",
                                  command=lambda: self.open_path(
                                      self.last_wav), state="disabled")
        self.btn_wav.pack(side=LEFT)
        self.btn_mp3 = ttk.Button(obtns, text="MP3 öffnen",
                                  command=lambda: self.open_path(
                                      self.last_mp3), state="disabled")
        self.btn_mp3.pack(side=LEFT, padx=8)
        self.btn_dir = ttk.Button(obtns, text="Ordner öffnen",
                                  command=lambda: self.open_path(
                                      self.outdir_var.get() or
                                      str(paths.OUTPUT_DIR)))
        self.btn_dir.pack(side=LEFT)
        self.btn_report = ttk.Button(obtns, text="Bericht öffnen",
                                     command=lambda: self.open_path(
                                         self.last_report),
                                     state="disabled")
        self.btn_report.pack(side=LEFT, padx=8)

    # ------------------------------------------------ Stimmen (dynamisch)
    def _on_language_change(self):
        """§6: Sprache zuerst – Stimmenliste und Standard neu aufbauen."""
        self.voice_var.set(default_voice(self.lang_var.get(),
                                         self.registry))
        self._rebuild_voice_card()
        self._update_stats()

    def _rebuild_voice_card(self):
        for child in self.voice_card.winfo_children():
            child.destroy()
        groups = voice_groups(self.lang_var.get(), self.registry)

        def _render_section(title: str, rows: list[dict], subtitle: str = ""):
            if not rows:
                return
            frame = ttk.Frame(self.voice_card)
            frame.pack(fill=X, padx=8, pady=(8, 0))
            header = ttk.Frame(frame)
            header.pack(fill=X)
            ttk.Label(header, text=title, style="Muted.TLabel",
                      font=("", 9, "bold")).pack(side=LEFT, anchor=W)
            if subtitle:
                # Long subtitle wraps to next line
                sub_lbl = ttk.Label(header, text=subtitle,
                                    style="Muted.TLabel", wraplength=680,
                                    justify="left")
                sub_lbl.pack(side=LEFT, padx=(8, 0), anchor=W)
            for gender, label in (("male", "Mannlich"),
                                  ("female", "Weiblich"),
                                  ("other", "Andere / Custom")):
                if gender == "other":
                    sub = [r for r in rows if r.get("gender") not in ("male", "female")]
                else:
                    sub = [r for r in rows if r["gender"] == gender]
                if not sub:
                    continue
                grp = ttk.Frame(frame)
                grp.pack(fill=X, padx=(10, 0), pady=(2, 0))
                ttk.Label(grp, text=label,
                          style="Muted.TLabel").pack(anchor=W)
                # Use a grid of rows (one voice per row) so long labels wrap instead of horizontally overflowing.
                inner = ttk.Frame(grp)
                inner.pack(fill=X, pady=(2, 0))
                inner.columnconfigure(1, weight=1)
                for idx, row in enumerate(sub):
                    self._add_voice_button(inner, row, idx)

        _render_section("▎ Gesperrte Produktionsstimme", groups["locked"],
                        "VD-E (nicht veränderbar)")
        _render_section("▎ Custom Voices (eingebaute Qwen-Sprecher)",
                        groups["custom"])
        _render_section("▎ Production Clone Voices",
                        groups["clone"],
                        "bestätigt oder im Archiv; deaktiviert, falls "
                        "die kanonische Referenz fehlt "
                        "(cache/voice_refs/<id>.wav)")
        if groups.get("candidates"):
            _render_section(
                "▎ Weitere Stimmen (Kandidaten / zurückgewiesen)",
                groups["candidates"],
                "nicht in den aktiven Produktionsbestand übernommen – "
                "nur zur Information, nicht auswählbar")
        # refresh scroll region after voice list change
        self.update_idletasks()
        try:
            self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except Exception:
            pass

    def _add_voice_button(self, parent, row, idx=0):
        # One voice per row: radio + display name + status chip.
        # Text wraps at column 1 weight so horizontal overflow is impossible.
        vid = row["voice_id"]
        rb = ttk.Radiobutton(parent, value=vid, variable=self.voice_var)
        rb.grid(row=idx, column=0, sticky="w", padx=(0, 6), pady=1)

        label_text = row["label"]
        status_text = row.get("status") or ""
        avail_note = row.get("availability_note") or ""
        # Combine name + status into one wrapped label
        display = label_text
        if status_text:
            display = display + "   [" + status_text + "]"
        lbl = ttk.Label(parent, text=display, style="Card.TLabel",
                        wraplength=680, justify="left")
        lbl.grid(row=idx, column=1, sticky="we", pady=1)
        if avail_note:
            nlbl = ttk.Label(parent, text=avail_note, style="Muted.TLabel",
                             wraplength=680, justify="left")
            nlbl.grid(row=idx, column=2, sticky="w", padx=(8, 0), pady=1)
        selectable = bool(row.get("selectable", row.get("available", True)))
        if not selectable:
            rb.state(["disabled"])
            lbl.state(["disabled"])
        # Clicking the label should also select if selectable
        def _select(_e=None, vid=vid, selectable=selectable):
            if selectable:
                self.voice_var.set(vid)
        lbl.bind("<Button-1>", _select)

    def _update_outmode_state(self):
        self.outmode_box.config(
            state="readonly" if self.split_var.get() else "disabled")

    def _on_format_change(self):
        """MP3-Bitrate/MP3-Button deaktivieren wenn kein MP3 erzeugt wird,
        und umgekehrt. (Keine stillen Alt-Dateien mehr anzeigen.)"""
        fmt = self.format_var.get()
        want_mp3 = fmt != "WAV only"
        want_wav = fmt != "MP3 only"
        # Bitrate-Box nur aktiv wenn MP3 erzeugt wird
        try:
            self.mp3_bitrate_box.config(
                state="readonly" if want_mp3 else "disabled")
        except Exception:
            pass
        # WAV-Button aktiv je nach Format
        # (Buttons werden erst in _set_running_ui/on_done konfiguriert; wir
        # deaktivieren hier vorab wenn das Format nicht passt.)
        if not want_wav:
            self.last_wav = ""
        if not want_mp3:
            self.last_mp3 = ""

    # ------------------------------------------------------------ Drag&Drop
    def _init_drag_drop(self):
        if not _HAS_WINDND:
            self.drop_label.config(
                text="PDF hierher ziehen (Windows) – oder Button nutzen:")
            return
        try:
            windnd.hook_dropfiles(self, func=self._on_drop)
        except Exception:                               # noqa: BLE001
            pass

    def _on_drop(self, files):
        if not files:
            return
        path = files[0]
        if isinstance(path, bytes):
            path = path.decode("mbcs" if os.name == "nt" else "utf-8",
                               "replace")
        self._load_document(path)

    # ------------------------------------------------------------- Dateien
    def pick_pdf(self):
        p = filedialog.askopenfilename(
            title="PDF auswählen", filetypes=[("PDF-Dateien", "*.pdf")])
        if p:
            self._load_document(p)

    def pick_txt(self):
        p = filedialog.askopenfilename(
            title="Textdatei auswählen",
            filetypes=[("Textdateien", "*.txt"), ("Alle Dateien", "*.*")])
        if p:
            self._load_document(p)

    def pick_outdir(self):
        d = filedialog.askdirectory(title="Ausgabeordner wählen")
        if d:
            self.outdir_var.set(d)

    def _load_document(self, path_str: str):
        path = Path(path_str)
        if not path.exists():
            messagebox.showerror("Fehler", f"Datei nicht gefunden:\n{path}")
            return
        suffix = path.suffix.lower()
        try:
            if suffix == ".pdf":
                from ..text.pdf_import import extract_pdf_text
                res = extract_pdf_text(path)
                self.text_widget.delete("1.0", END)
                self.text_widget.insert("1.0", res.text)
                self.stage_label.config(
                    text=f"PDF geladen: {path.name} ({res.pages} Seiten, "
                         f"{res.words} Wörter)")
            elif suffix in (".txt", ".md"):
                text = path.read_text(encoding="utf-8", errors="replace")
                self.text_widget.delete("1.0", END)
                self.text_widget.insert("1.0", text)
                self.stage_label.config(text=f"Text geladen: {path.name}")
            else:
                messagebox.showerror(
                    "Nicht unterstützt",
                    f"Dateityp {suffix or '(ohne)'} wird nicht "
                    "unterstützt (PDF/TXT).")
                return
            self._update_stats()
        except Exception as e:                           # noqa: BLE001
            messagebox.showerror("Import fehlgeschlagen", str(e))

    # -------------------------------------------------------------- Statistik
    def _on_text_changed(self, _evt=None):
        self.text_widget.edit_modified(False)
        self._update_stats()

    def _current_text(self) -> str:
        return self.text_widget.get("1.0", "end-1c")

    def _update_stats(self):
        stats = text_stats(self._current_text(), self.lang_var.get())
        self.stats_label.config(
            text=f"{stats['chars']} Zeichen · {stats['words']} Wörter · "
                 f"≈ {format_duration(stats['est_seconds'])} Sprache · "
                 f"≈ {stats['est_segments']} Segmente")

    # ----------------------------------------------------------- Identität
    def _refresh_identity_badge(self):
        if self.identity.ok:
            self.identity_badge.config(
                text="VD-E identitätsgesichert (SHA-256 OK)",
                foreground="#33d6a6")
        else:
            self.identity_badge.config(
                text="VD-E GESPERRT: " + self.identity.message,
                foreground="#ff5d73")

    def _startup_checks(self):
        """Modelle vorhanden? (§30) – nur Meldung, kein Download."""
        try:
            models = list((paths.MODELS_DIR).glob("Qwen3-TTS*"))
            if not models:
                self._post(self.stage_label.config,
                           text="Hinweis: keine lokalen Modelle in models/ "
                                "gefunden (install.ps1 ausführen).")
        except Exception:                               # noqa: BLE001
            pass

    def _post(self, fn, **kw):
        try:
            self.after(0, lambda: fn(**kw))
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- Job
    def start_job(self):
        if self.launcher and self.launcher.running:
            messagebox.showinfo("Läuft bereits",
                                "Es läuft bereits ein Auftrag (§16).")
            return
        text = self._current_text().strip()
        if not text:
            messagebox.showwarning("Kein Text",
                                   "Bitte zuerst ein PDF importieren oder "
                                   "Text eingeben.")
            return
        voice_id = self.voice_var.get()
        if voice_id == "vd_e" and not self.identity.ok:
            messagebox.showerror(
                "VD-E gesperrt",
                "Die geschützte VD-E-Referenz wurde verändert oder "
                "fehlt.\nVD-E ist deaktiviert (§24). Bitte eine andere "
                "Stimme wählen oder die Original-Referenz wiederherstellen.")
            return
        entry = self.registry.for_language(
            self.registry.get(voice_id), self.lang_var.get()) \
            if self.registry.get(voice_id) else None
        if entry and entry.available is False:
            note = entry.availability_note or (
                "Stimme ist in der installierten Modellversion nicht "
                "verfügbar (§13).")
            messagebox.showerror(
                "Stimme nicht verfügbar",
                f"Stimme ‚{entry.display_name}‘ ist derzeit nicht verfügbar.\n\n"
                + note)
            return
        # Ausgabeformat aus den neuen getrennten GUI-Feldern ableiten
        fmt_label = self.format_var.get()
        if fmt_label == "WAV only":
            output_format = "wav"
        elif fmt_label == "MP3 only":
            output_format = "mp3"
        else:
            output_format = "wav_mp3"
        # WAV-Bittiefe & MP3-Bitrate
        wav_bits = 24
        if "16" in self.wav_bits_var.get():
            wav_bits = 16
        mp3_br = "320k"
        br_txt = self.mp3_bitrate_var.get()
        for br in ("128", "192", "320"):
            if br in br_txt:
                mp3_br = f"{br}k"
                break

        mode_map = {"Gesamtdatei (Standard)": "full",
                    "Nur Parts (Part_001…)": "parts",
                    "Parts + Gesamtdatei (FullScript)": "parts_plus_full"}
        spec = {"text": text,
                "language": self.lang_var.get(),
                "voice_id": voice_id,
                "speed": float(self.speed_var.get()),
                "output_dir": self.outdir_var.get(),
                # Beides schicken – output_format hat Vorrang in Runner/Pipeline
                "formats": output_format,
                "output_format": output_format,
                "wav_bit_depth": wav_bits,
                "mp3_bitrate": mp3_br,
                "splitting_enabled": bool(self.split_var.get()),
                "output_mode": mode_map.get(self.outmode_var.get(),
                                            "full")}
        self._set_running_ui(True)
        self.job_start = time.perf_counter()
        self._job_start_monotonic = self.job_start
        self._segment_start_monotonic = self.job_start
        self._last_event_time = self.job_start
        self._last_progress_pct = 0
        self._current_stage = "startup"
        self._current_part = None
        self._current_parts_total = None
        self._current_segment = None
        self._current_segments_total = None
        self._current_detail = ""
        self.progress["value"] = 0
        self.stage_label.config(text="Backend wird gestartet …")
        self.seg_label.config(text="")
        self.qc_label.config(text="")
        self.heartbeat_label.config(text="")
        self._start_heartbeat()
        self.launcher = BackendLauncher(on_event=self._on_event,
                                        on_state=lambda s: self._post(
                                            self._on_state_msg, s),
                                        on_done=self._on_done)
        try:
            self.launcher.start(spec)
        except Exception as e:                           # noqa: BLE001
            self._set_running_ui(False)
            messagebox.showerror("Start fehlgeschlagen", str(e))

    def _set_running_ui(self, running: bool):
        if running:
            self.start_btn.config(text="LÄUFT …", state="disabled")
            self.cancel_btn.config(state="normal", text="ABBRECHEN")
        else:
            self.start_btn.config(text="VOICE-OVER ERSTELLEN",
                                  state="normal")
            self.cancel_btn.config(state="disabled")
            self._stop_heartbeat()

    # --- Cancel + Heartbeat / Runtime status --------------------------------
    def _cancel_job(self):
        if self.launcher and self.launcher.running:
            self.cancel_btn.config(state="disabled", text="ABBRUCH …")
            self.stage_label.config(text="Abgebrochen – Prozess wird beendet …")
            try:
                self.launcher.cancel()
            except Exception:
                pass

    def _on_state_msg(self, msg: str):
        # Called from backend's on_state callback (text updates)
        self.stage_label.config(text=msg)
        self._last_event_time = time.perf_counter()

    def _start_heartbeat(self):
        self._stop_heartbeat()
        def _tick():
            self._update_runtime_labels()
            self._heartbeat_after_id = self.after(1000, _tick)
        self._heartbeat_after_id = self.after(500, _tick)

    def _stop_heartbeat(self):
        if self._heartbeat_after_id:
            try: self.after_cancel(self._heartbeat_after_id)
            except Exception: pass
            self._heartbeat_after_id = None

    def _update_runtime_labels(self):
        if not self.launcher or not self.launcher.running:
            return
        now = time.perf_counter()
        total_elapsed = now - self._job_start_monotonic
        seg_elapsed = now - self._segment_start_monotonic
        since_last = now - self._last_event_time
        total_str = format_duration(total_elapsed)
        seg_str = format_duration(seg_elapsed)
        part_line = ""
        if self._current_parts_total and self._current_part:
            part_line = f"Part {self._current_part}/{self._current_parts_total}   ·   "
        seg_line = ""
        if self._current_segments_total:
            seg_line = (f"Segment {self._current_segment or 1}/"
                        f"{self._current_segments_total}   ·   ")
        # Stage in readable form + live counters
        stage_txt = stage_label(self._current_stage)
        if self._current_detail:
            stage_txt = stage_txt + " – " + self._current_detail
        self.stage_label.config(text=stage_txt)
        text_seg = f"{part_line}{seg_line}Segment-Laufzeit: {seg_str}   ·   Gesamt: {total_str}"
        self.seg_label.config(text=text_seg)
        # Stuck detection (no event for a while during active TTS)
        if self._current_stage in ("tts", "voice_load", "model_load",
                                   "assembling", "mastering", "speed"):
            if since_last > 20:
                self.heartbeat_label.config(
                    text=(f"Aktiver Schritt laeuft seit {seg_str} – "
                          f"letztes Fortschrittsereignis vor "
                          f"{int(since_last)} s. "
                          "GPU arbeitet (Prozess ist nicht eingefroren)."),
                    foreground="#c59a2f")
            elif since_last > 8:
                self.heartbeat_label.config(
                    text=f"Modellgenerierung laeuft – letzter Fortschritt vor {int(since_last)} s.",
                    foreground="#93a1b4")
            else:
                self.heartbeat_label.config(text="", foreground="#93a1b4")
        else:
            self.heartbeat_label.config(text="")

    # ------------------------------------------------------------- Events
    def _on_event(self, evt: dict):
        p = parse_progress_event(evt)
        kind = evt.get("event")

        def apply():
            now = time.perf_counter()
            self._last_event_time = now
            if p.get("stage"):
                self._current_stage = p["stage"]
                self._current_detail = p.get("detail") or ""
                # New stage resets segment timer
                self._segment_start_monotonic = now
            if kind == "stage":
                # Track part progress from events like stage="part" part=... parts=...
                if evt.get("part") is not None:
                    self._current_part = evt["part"]
                    self._current_parts_total = evt.get("parts")
                if p.get("detail"):
                    self._current_detail = p["detail"]
            if p.get("segment") is not None:
                self._current_segment = p["segment"]
                self._segment_start_monotonic = now
            if p.get("segments_total") is not None:
                self._current_segments_total = p["segments_total"]
            if p.get("percent") is not None:
                self._last_progress_pct = max(0, min(100, p["percent"]))
                self.progress["value"] = self._last_progress_pct
                eta = format_eta(now - self._job_start_monotonic,
                                 self._last_progress_pct)
                part_line = ""
                if self._current_parts_total and self._current_part:
                    part_line = f"Part {self._current_part}/{self._current_parts_total}   ·   "
                seg_line = ""
                if self._current_segments_total:
                    seg_line = (f"Segment {self._current_segment or 1}/"
                                f"{self._current_segments_total}   ·   ")
                label = (part_line + seg_line).rstrip(" ·")
                if eta:
                    label = label + (f"   ·   Restzeit ≈ {eta}" if label else f"Restzeit ≈ {eta}")
                self.seg_label.config(text=label)
            if p.get("qc") is not None:
                self.qc_label.config(text=f"QC: {p['qc']} %"
                                          + (f"   ·   Schritt: {self._current_detail}"
                                             if self._current_detail else ""))
            if kind == "identity_check":
                self.identity = check_identity(self.production)
                self._refresh_identity_badge()
        self._post_wrapper(apply)

    def _post_wrapper(self, fn):
        try:
            self.after(0, fn)
        except tk.TclError:
            pass

    def _on_done(self, result: JobResult):
        def apply():
            self._set_running_ui(False)
            elapsed = time.perf_counter() - self.job_start
            s = result.summary or {}
            # Determine effective status: runner marks ok only on full
            # success; backend mirrors that via summary.ok.
            failed_n = int(s.get("failed") or 0)
            parts_planned = int(s.get("parts_planned") or 1)
            parts_ok = int(s.get("parts_succeeded") or 0)
            has_full = bool(s.get("fullscript_built") or s.get("fullscript_wav"))
            is_incomplete = (not result.ok) and parts_ok > 0 and failed_n >= 0
            # Enable buttons for files that ACTUALLY exist.
            wav = s.get("wav") or ""
            mp3 = s.get("mp3") or ""
            if wav and not Path(wav).exists(): wav = ""
            if mp3 and not Path(mp3).exists(): mp3 = ""
            self.last_wav = wav
            self.last_mp3 = mp3
            self.last_summary = s
            if not self.last_report:
                self.last_report = _find_report(self.outdir_var.get())
            self.btn_wav.config(state="normal" if self.last_wav else "disabled")
            self.btn_mp3.config(state="normal" if self.last_mp3 else "disabled")
            self.btn_report.config(state="normal" if self.last_report else "disabled")

            parts_line = ""
            if s.get("parts_planned", 1) != 1 or s.get("output_mode") in ("parts","parts_plus_full"):
                parts_line = (f"\nParts: {parts_ok}/{parts_planned}  "
                              f"Fehlende Segmente: {int(s.get('failed_segments') or 0)}  "
                              f"Fehlgeschlagene Parts: {len(s.get('failed_parts') or [])}")
                if has_full: parts_line += "  FullScript: OK"
                else: parts_line += "  FullScript: NICHT erzeugt"

            if result.ok and failed_n == 0:
                self.progress["value"] = 100
                self.stage_label.config(text="Fertig.")
                self.seg_label.config(
                    text=f"Voice: {s.get('voice')} · Sprache: "
                         f"{s.get('language')} · Segmente: "
                         f"{s.get('segments')} · Regenerationen: "
                         f"{s.get('regenerations')} · Fehler: 0 · QC: "
                         f"{s.get('qc')} · Dauer: "
                         f"{format_duration(s.get('duration_s') or elapsed)}")
                messagebox.showinfo(
                    "Fertig",
                    f"Status: Erfolgreich\nVoice: {s.get('voice')}\n"
                    f"Segmente: {s.get('segments')}\nQC: {s.get('qc')}"
                    f"{parts_line}")
            elif is_incomplete:
                # Some audio produced but job not fully successful
                self.progress["value"] = 60
                self.stage_label.config(text="UNVOLLSTAENDIG.")
                self.seg_label.config(
                    text=f"Voice: {s.get('voice')} · Sprache: "
                         f"{s.get('language')} · Fehler: {failed_n} · QC: "
                         f"{s.get('qc')} · Dauer: "
                         f"{format_duration(s.get('duration_s') or elapsed)}"
                         f"{parts_line}")
                messagebox.showwarning(
                    "Auftrag unvollstaendig",
                    f"Status: {s.get('status','INCOMPLETE')}\n"
                    f"Voice: {s.get('voice')}\n"
                    f"Fehlgeschlagene Segmente/Parts: {failed_n}\n"
                    f"Teil-Ausgaben koennen bereits vorhanden sein, "
                    f"es wurde aber KEINE vollstaendige Gesamtdatei "
                    f"freigegeben.\n{parts_line}\n\n"
                    f"Details:\n{(result.error or '')}")
            else:
                self.progress["value"] = 0
                self.stage_label.config(text="Fehler.")
                detail = (result.detail or "")[:1500]
                messagebox.showerror(
                    "Auftrag fehlgeschlagen",
                    f"{result.error}\n{parts_line}\n\n"
                    f"Technische Details:\n{detail}")
        self._post_wrapper(apply)

    # -------------------------------------------------------------- Öffnen
    def open_path(self, path_str: str):
        if not path_str:
            return
        path = Path(path_str)
        if not path.exists():
            messagebox.showwarning("Nicht gefunden", str(path))
            return
        try:
            if os.name == "nt":
                os.startfile(str(path))                 # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:                           # noqa: BLE001
            messagebox.showerror("Öffnen fehlgeschlagen", str(e))


def _find_report(outdir: str) -> str:
    d = Path(outdir) if outdir else paths.OUTPUT_DIR
    reports = sorted(d.glob("report_*.md"))
    return str(reports[-1]) if reports else ""


def run() -> None:
    """Einstieg der Desktop-App (desktop.py / PyInstaller)."""
    try:
        app = VoiceOverApp()
        app.mainloop()
    except Exception:                                   # noqa: BLE001
        traceback.print_exc()
        try:
            from tkinter import messagebox
            messagebox.showerror("VoiceOverApp – Fehler",
                                  traceback.format_exc()[-1200:])
        except Exception:
            raise


if __name__ == "__main__":
    run()
