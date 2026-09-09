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
from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, W, X, Y, filedialog, messagebox, ttk
import tkinter as tk

from .. import paths
from ..security.identity_lock import check_identity, load_production
from ..voices.registry import VoiceRegistry
from .backend import BackendLauncher, JobResult, parse_progress_event
from .helpers import format_duration, format_eta, stage_label, text_stats
from .voice_view import default_voice, voice_rows

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

        container = ttk.Frame(self)
        container.pack(fill=BOTH, expand=True, padx=16, pady=8)
        # Scroll-Fähigkeit wäre overkill; feste Spalte

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
        ttk.Combobox(row1, textvariable=self.format_var, width=10,
                     state="readonly",
                     values=["WAV + MP3", "nur WAV"]).pack(side=LEFT,
                                                           padx=8)
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

        # START
        self.start_btn = ttk.Button(container, text="VOICE-OVER ERSTELLEN",
                                    style="Big.TButton",
                                    command=self.start_job)
        self.start_btn.pack(fill=X, pady=(2, 8))

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
        self.qc_label.pack(anchor=W, padx=10, pady=(0, 8))

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
        rows = voice_rows(self.lang_var.get(), self.registry)
        for group, title in (("male", "Männlich"), ("female", "Weiblich")):
            frame = ttk.Frame(self.voice_card)
            frame.pack(fill=X, padx=8, pady=(6 if group == "male" else 2,
                                             8 if group == "female" else 2))
            ttk.Label(frame, text=title,
                      style="Muted.TLabel").pack(anchor=W)
            inner = ttk.Frame(frame)
            inner.pack(fill=X)
            for row in [r for r in rows if r["gender"] == group]:
                self._add_voice_button(inner, row)

    def _add_voice_button(self, parent, row):
        text = row["label"]
        if row["status"]:
            text += f"   ·   {row['status']}"
        btn = ttk.Radiobutton(parent, text=text, value=row["voice_id"],
                              variable=self.voice_var)
        btn.pack(side=LEFT, padx=(0, 18))
        if row.get("available") is False:
            btn.state(["disabled"])

    def _update_outmode_state(self):
        self.outmode_box.config(
            state="readonly" if self.split_var.get() else "disabled")

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
            messagebox.showerror(
                "Stimme nicht verfügbar",
                f"Stimme ‚{entry.display_name}‘ ist in der installierten "
                "Modellversion nicht verfügbar (§13).")
            return
        formats = ["wav"] + (["mp3"] if self.format_var.get() != "nur WAV"
                             else [])
        mode_map = {"Gesamtdatei (Standard)": "full",
                    "Nur Parts (Part_001…)": "parts",
                    "Parts + Gesamtdatei (FullScript)": "parts_plus_full"}
        spec = {"text": text,
                "language": self.lang_var.get(),
                "voice_id": voice_id,
                "speed": float(self.speed_var.get()),
                "output_dir": self.outdir_var.get(),
                "formats": formats,
                "splitting_enabled": bool(self.split_var.get()),
                "output_mode": mode_map.get(self.outmode_var.get(),
                                            "full")}
        self._set_running_ui(True)
        self.job_start = time.perf_counter()
        self.progress["value"] = 0
        self.stage_label.config(text="Backend wird gestartet …")
        self.seg_label.config(text="")
        self.qc_label.config(text="")
        self.launcher = BackendLauncher(on_event=self._on_event,
                                        on_state=lambda s: self._post(
                                            self.stage_label.config,
                                            text=s),
                                        on_done=self._on_done)
        try:
            self.launcher.start(spec)
        except Exception as e:                           # noqa: BLE001
            self._set_running_ui(False)
            messagebox.showerror("Start fehlgeschlagen", str(e))

    def _set_running_ui(self, running: bool):
        if running:
            self.start_btn.config(text="LÄUFT …", state="disabled")
        else:
            self.start_btn.config(text="VOICE-OVER ERSTELLEN",
                                  state="normal")

    # ------------------------------------------------------------- Events
    def _on_event(self, evt: dict):
        p = parse_progress_event(evt)
        kind = evt.get("event")

        def apply():
            if p.get("stage"):
                self.stage_label.config(
                    text=stage_label(p["stage"]) +
                         (f" – {p['detail']}" if p.get("detail") else ""))
            if p.get("percent") is not None:
                self.progress["value"] = max(0, min(100, p["percent"]))
                eta = format_eta(time.perf_counter() - self.job_start,
                                 p["percent"])
                self.seg_label.config(
                    text=(f"Segment {p.get('segment')}/"
                          f"{p.get('segments_total')}"
                          if p.get("segment") else "")
                         + (f"   ·   Restzeit ≈ {eta}" if eta else ""))
            if p.get("qc") is not None:
                self.qc_label.config(text=f"QC: {p['qc']} %")
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
            if result.ok:
                s = result.summary
                self.progress["value"] = 100
                self.stage_label.config(text="Fertig.")
                self.seg_label.config(
                    text=f"Voice: {s.get('voice')} · Sprache: "
                         f"{s.get('language')} · Segmente: "
                         f"{s.get('segments')} · Regenerationen: "
                         f"{s.get('regenerations')} · Fehler: "
                         f"{s.get('failed')} · QC: {s.get('qc')} · Dauer: "
                         f"{format_duration(s.get('duration_s') or elapsed)}")
                self.last_summary = s
                self.last_wav = s.get("wav") or ""
                self.last_mp3 = s.get("mp3") or ""
                self.btn_wav.config(state="normal" if self.last_wav else
                                    "disabled")
                self.btn_mp3.config(state="normal" if self.last_mp3 else
                                    "disabled")
                if result.summary:
                    # done-Event enthält Report-Pfad
                    pass
                if not self.last_report:
                    self.last_report = _find_report(self.outdir_var.get())
                self.btn_report.config(state="normal" if self.last_report
                                       else "disabled")
                messagebox.showinfo(
                    "Fertig",
                    f"Status: Erfolgreich\nVoice: {s.get('voice')}\n"
                    f"Segmente: {s.get('segments')}\n"
                    f"QC: {s.get('qc')}\nFehler: {s.get('failed')}")
            else:
                self.progress["value"] = 0
                self.stage_label.config(text="Fehler.")
                detail = (result.detail or "")[:1500]
                messagebox.showerror(
                    "Auftrag fehlgeschlagen",
                    f"{result.error}\n\nTechnische Details:\n{detail}")
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
