/* VoiceOverApp UI – Vanilla JS, komplett lokal */
"use strict";

const $ = (id) => document.getElementById(id);
let CFG = null;
let pollTimer = null;

/* ---------------------------------------------------------------- Setup */
async function loadConfig() {
  const r = await fetch("/api/config");
  const data = await r.json();
  CFG = data;
  const c = data.config;

  // Stimmen
  const selVoice = $("in-voice");
  selVoice.innerHTML = "";
  const defOpt = document.createElement("option");
  defOpt.value = data.default_profile;
  defOpt.textContent = "★ DEFAULT BEST NARRATOR (" +
      (data.profiles.find(p => p.id === data.default_profile) || {}).label + ")";
  selVoice.appendChild(defOpt);
  for (const p of data.profiles) {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.label + "  [" + p.speaker + "]";
    selVoice.appendChild(o);
  }
  selVoice.value = c.voice_profile || data.default_profile;

  // Presets
  const selPreset = $("in-preset");
  selPreset.innerHTML = "";
  for (const [id, p] of Object.entries(data.presets)) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = p.label;
    selPreset.appendChild(o);
  }
  selPreset.value = c.preset || "deep_documentary";
  updatePresetDesc();

  $("in-language").value = c.language || "German";
  $("in-speed").value = c.speed || 1.0;
  $("in-speed-val").textContent = Number(c.speed || 1).toFixed(2) + "×";
  $("in-emotion").value = c.emotion || "AUTO";
  $("in-intensity").value = String(c.intensity || "AUTO");
  $("in-pause").value = c.pause_style || "auto";
  $("in-vol").value = c.volume_db || 0;
  $("in-vol-val").textContent = (c.volume_db || 0) + " dB";
  $("in-model").value = (c.advanced && c.advanced.prefer_model_size) || "auto";
  const qHi = !c.advanced || Number(c.advanced.wav_bit_depth || 24) === 24;
  $("in-quality").value = qHi ? "hi" : "std";

  renderHardware(data.hardware);
}

function updatePresetDesc() {
  if (!CFG) return;
  const p = CFG.presets[$("in-preset").value];
  if (p) $("preset-desc").textContent = p.description || "";
}

function renderHardware(hw) {
  $("hw-info").textContent = JSON.stringify(hw, null, 2);
  const badge = $("hw-badge");
  if (!hw) { badge.textContent = "Hardware ?"; return; }
  if (hw.mode === "gpu") {
    badge.textContent = "GPU: " + (hw.gpu_name || "CUDA") +
      " (" + hw.gpu_vram_total_gb + " GB)";
    badge.className = "badge ok";
  } else if (hw.mode === "gpu_conservative") {
    badge.textContent = "GPU (schonend): " + (hw.gpu_name || "CUDA");
    badge.className = "badge warn";
  } else {
    badge.textContent = "CPU-Modus (langsam)";
    badge.className = "badge warn";
  }
}

/* ------------------------------------------------------------- Status */
async function pollStatus() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();
    $("btn-start").disabled = !!s.running;
    $("btn-stop").disabled = !s.running;

    if (s.running || s.phase !== "idle") {
      const lines = [];
      if (s.files_total > 0) {
        lines.push(`Datei ${s.file_index || 0} / ${s.files_total}`);
        if (s.current_file) lines.push(s.current_file);
      }
      if (s.total_segments > 0)
        lines.push(`Segment ${s.current_segment} / ${s.total_segments}`);
      const phaseTxt = {
        idle: "", tts: "TTS + Qualitätsprüfung", assembling: "Zusammenfügen",
        speed: "Tempo", mastering: "YouTube-Master", done: "Fertig",
        benchmark_system: "System-Benchmark läuft …",
        benchmark_voices: "Stimmen-Benchmark läuft …",
        benchmark_done: "Benchmark abgeschlossen",
      }[s.phase] || s.phase;
      if (phaseTxt) lines.push(phaseTxt);
      if (s.last_error) lines.push("Fehler: " + s.last_error);
      if (s.last_summary && !s.running) {
        const sum = s.last_summary;
        if (sum.completed !== undefined)
          lines.push(`Bericht: ${sum.completed} ✓ / ${sum.failed} ✗ ` +
                     (sum.report ? "(output/" + sum.report.split(/[\\/]/).pop() + ")" : ""));
      }
      $("progress-lines").innerHTML =
          lines.map(l => "<div>" + escapeHtml(l) + "</div>").join("");
    }
    $("bar-overall").style.width = (s.overall_percent || 0) + "%";
    $("bar-tts").style.width = (s.tts_percent || 0) + "%";
    $("p-overall").textContent = (s.overall_percent || 0) + " %";
    $("p-tts").textContent = (s.tts_percent || 0) + " %";
    $("p-qc").textContent = (s.qc_percent || 0) + " %";

    $("events").innerHTML = (s.events || []).map(e =>
        `<div><span class="t">${e.t}</span>${escapeHtml(e.phase || "")}</div>`
    ).join("");

    if (s.cache) $("cache-badge").textContent =
        "Cache: " + s.cache.segments + " Seg (" + s.cache.size_mb + " MB)";
    const eb = $("engine-badge");
    if (s.engine) {
      eb.textContent = "Qwen3-TTS " + (s.model_size_effective || "?") +
                       (s.engine.loaded ? " ✓" : "");
      eb.className = "badge " + (s.engine.loaded ? "ok" : "");
    } else {
      eb.textContent = "Engine: wird beim Start geladen";
      eb.className = "badge";
    }
    if (!s.running) await loadFiles();
  } catch (e) { /* Server kurzzeitig nicht erreichbar */ }
}

async function loadFiles() {
  const r = await fetch("/api/files");
  const d = await r.json();
  $("list-input").innerHTML = d.files.length
      ? d.files.map(f => `<li><span>${escapeHtml(f.name)}</span><span class="sz">${fmtSize(f.size)}</span></li>`).join("")
      : '<li><span class="sub">leer – .txt hierher ziehen</span></li>';
  $("list-output").innerHTML = d.outputs.length
      ? d.outputs.map(f => `<li><a href="/files/output/${encodeURIComponent(f.name)}" target="_blank">${escapeHtml(f.name)}</a><span class="sz">${fmtSize(f.size)}</span></li>`).join("")
      : '<li><span class="sub">noch keine Ausgaben</span></li>';
}

/* ------------------------------------------------------------ Aktionen */
async function start() {
  const payload = {
    language: $("in-language").value,
    voice_profile: $("in-voice").value,
    preset: $("in-preset").value,
    speed: Number($("in-speed").value),
    emotion: $("in-emotion").value,
    intensity: $("in-intensity").value,
    pause_style: $("in-pause").value,
    volume_db: Number($("in-vol").value),
  };
  const r = await fetch("/api/start", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const d = await r.json();
  if (!d.ok && d.error) alert(d.error);
}

async function saveAdvanced() {
  const hi = $("in-quality").value === "hi";
  const payload = {
    emotion: $("in-emotion").value,
    intensity: $("in-intensity").value,
    pause_style: $("in-pause").value,
    volume_db: Number($("in-vol").value),
    advanced: { prefer_model_size: $("in-model").value },
  };
  if (hi) payload.advanced.wav_bit_depth = 24, payload.advanced.mp3_bitrate = "320k";
  else payload.advanced.wav_bit_depth = 16, payload.advanced.mp3_bitrate = "192k";
  await fetch("/api/config", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
}

async function stopRun() {
  if (!confirm("Aktuelle Verarbeitung abbrechen?\nFertige Segmente bleiben erhalten (Resume).")) return;
  await fetch("/api/stop", {method: "POST"});
}

async function benchmark(kind, message) {
  const quick = !confirm(message ||
      ((kind === "system" ? "Systemtest starten?" : "Stimmen-Benchmark starten?") +
      "\n\nOK = vollständiger Test, Abbrechen = Schnelltest."));
  const r = await fetch("/api/benchmark", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({type: kind, quick}),
  });
  const d = await r.json();
  if (!d.ok) alert("Benchmark nicht gestartet (läuft schon etwas?).");
  setTimeout(loadBenchAudio, 3000);
}

async function loadBenchAudio() {
  try {
    const r = await fetch("/files/benchmark/test_de.wav");
    if (!r.ok) return;
    $("bench-audio").classList.remove("hidden");
    const files = ["test_de.wav", "test_en.wav", "test_longform.wav"];
    $("bench-files").innerHTML = files.map(f =>
        `<div><div class="sub mono">${f}</div><audio controls preload="none" src="/files/benchmark/${f}"></audio></div>`).join("");
  } catch (e) {}
}

/* ------------------------------------------------------ Aussprache */
async function loadPron() {
  const r = await fetch("/api/pronunciation");
  const d = await r.json();
  const tbody = $("pron-table").querySelector("tbody");
  tbody.innerHTML = "";
  for (const [term, value] of Object.entries(d.user || {}).sort()) {
    const v = typeof value === "object" ? (value.de || "") + " / " + (value.en || "") : value;
    tbody.innerHTML += `<tr><td>${escapeHtml(term)}</td><td>${escapeHtml(v)}</td><td class="src">Benutzer</td>` +
        `<td><button data-term="${escapeHtml(term)}" class="pron-del">✕</button></td></tr>`;
  }
  if (!Object.keys(d.user || {}).length)
    tbody.innerHTML = '<tr><td colspan="4" class="sub">Noch keine eigenen Einträge. Eingebaute Wörterbuch-Ebene: ' +
        d.builtin_count + ' Begriffe.</td></tr>';
  tbody.querySelectorAll(".pron-del").forEach(btn => {
    btn.onclick = async () => {
      if (!confirm('Eintrag "' + btn.dataset.term + '" löschen?')) return;
      await fetch("/api/pronunciation", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({action: "delete", term: btn.dataset.term}),
      });
      loadPron();
    };
  });
}

async function addPron() {
  const term = $("pron-term").value.trim();
  const value = $("pron-value").value.trim();
  if (!term || !value) { alert("Begriff und Aussprache ausfüllen."); return; }
  await fetch("/api/pronunciation", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({action: "add", term, value,
                          language: $("pron-lang").value}),
  });
  $("pron-term").value = ""; $("pron-value").value = "";
  loadPron();
}

/* ---------------------------------------------------------- Cache */
async function clearCache(scope) {
  const label = scope === "all"
      ? "KOMPLETTEN Cache löschen?\n\nAlle zwischengespeicherten Segmente aller Projekte werden entfernt."
      : "Fehlgeschlagene Segment-Versuche aus dem Cache entfernen?";
  if (!confirm(label)) return;
  if (scope === "all" && !confirm("Sicher? Dieser Schritt kann nicht rückgängig gemacht werden.")) return;
  const r = await fetch("/api/cache/clear", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({scope, confirm: true}),
  });
  const d = await r.json();
  alert(d.ok ? "Entfernt: " + (d.removed || "?") : (d.error || "Fehler"));
}

/* ------------------------------------------------------ Phase 2 */
async function phase2Status() {
  try {
    const r = await fetch("/api/phase2/status");
    const s = await r.json();
    if (!s.has_run) {
      $("p2-status").textContent = "Noch kein Phase-2-Lauf. Starte den Vergleich, um Blindproben zu erzeugen.";
      return;
    }
    $("p2-status").textContent = s.picked
        ? "Auswahl gespeichert: Sample " + s.pick + " -> " + (s.mapping ? s.mapping[s.pick] : "?")
        : "Blindproben bereit (" + s.samples.length + "). Höre alle an und wähle deinen Favoriten.";
    if (s.samples.length) {
      $("p2-blind").classList.remove("hidden");
      const sel = $("p2-pick");
      sel.innerHTML = s.samples.map(l => '<option value="' + l + '">Sample ' + l + "</option>").join("");
      $("p2-samples").innerHTML = s.samples.map(l =>
          '<div><div class="sub mono">Sample ' + l + '</div><audio controls preload="none" src="/files/benchmark/phase2/blind/sample_' + l + '.wav"></audio></div>').join("");
    }
    if (s.picked) {
      $("p2-scores").classList.remove("hidden");
      $("btn-p2-apply").classList.remove("hidden");
      if (s.mapping) {
        const inv = {};
        for (const [k, v] of Object.entries(s.mapping)) inv[v] = k;
        let rows = "";
        for (const c of (s.scores || [])) {
          rows += "<tr><td><b>" + (inv[c.id] || "-") + "</b></td><td>" + escapeHtml(c.label || c.id) +
              "</td><td>" + escapeHtml(c.kind || "") + "</td><td>" + c.de_mean + "</td><td>" +
              c.naturalness + "</td><td>" + c.prosody_de + "</td><td>" + c.consistency +
              "</td><td>" + (c.f0_median || "-") + "</td></tr>";
        }
        $("p2-table").querySelector("tbody").innerHTML = rows;
        const rec = s.recommendation || {};
        $("p2-rec").textContent = "Automatische Empfehlung: " +
            (rec.recommended || "keine (Phase 1 bleibt Fallback)") +
            (rec.reason ? " — " + rec.reason : "");
        $("p2-reveal").textContent = "Zuordnung: " + JSON.stringify(s.mapping);
      }
    }
  } catch (e) { console.warn(e); }
}

async function phase2Run(quick) {
  const r = await fetch("/api/phase2/run", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({quick}),
  });
  const d = await r.json();
  if (!d.ok && d.error) { alert(d.error); return; }
  $("p2-status").textContent = "Phase-2-Vergleich läuft … (VoiceDesign-Modelle werden bei Bedarf geladen; das dauert einige Minuten)";
  const timer = setInterval(async () => {
    const s = await (await fetch("/api/phase2/status")).json();
    const st = await (await fetch("/api/status")).json();
    if (!st.running && s.has_run) { clearInterval(timer); phase2Status(); }
  }, 2500);
}

async function phase2Pauses() {
  await fetch("/api/phase2/run", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({probe: "pauses"}),
  });
  $("p2-status").textContent = "Pausen-Sonde läuft …";
}

async function phase2Pick() {
  const letter = $("p2-pick").value;
  const r = await fetch("/api/phase2/blind_pick", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({letter}),
  });
  const d = await r.json();
  if (!d.ok && d.error) { alert(d.error); return; }
  phase2Status();
  $("btn-p3-run").onclick = () => phase3Run(false);
  $("btn-p3-quick").onclick = () => phase3Run(true);
  $("btn-p3-pick").onclick = phase3Pick;
  $("btn-p3-apply").onclick = phase3Apply;
  phase3Status();
}

async function phase2Apply() {
  if (!confirm("Auswahl als Produktionsstimme übernehmen?\n(Die Konfiguration wird umgestellt; Phase-1-Ergebnisse bleiben gespeichert.)")) return;
  const r = await fetch("/api/phase2/apply", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({}),
  });
  const d = await r.json();
  if (d.ok) { alert("Übernommen: " + d.applied); phase2Status(); }
  else alert(d.error || "Fehler");
}

/* ------------------------------------------------------ Phase 3 */
async function phase3Status() {
  try {
    const s = await (await fetch("/api/phase3/status")).json();
    if (!s.has_run) { $("p3-status").textContent = "Noch kein Phase-3-Lauf."; return; }
    $("p3-status").textContent = s.picked
        ? "Auswahl gespeichert: Sample " + s.pick + " -> " + (s.mapping ? s.mapping[s.pick] : "?")
        : "Blindproben bereit (" + s.samples.length + "). Empfehlung (nur Info): " + (s.recommended || "—");
    if (s.samples.length) {
      $("p3-blind").classList.remove("hidden");
      $("p3-pick").innerHTML = s.samples.map(l => '<option value="' + l + '">Sample ' + l + "</option>").join("");
      $("p3-samples").innerHTML = s.samples.map(l =>
          '<div><div class="sub mono">Sample ' + l + '</div><audio controls preload="none" src="/files/benchmark/phase3/blind/sample_' + l + '.wav"></audio></div>').join("");
    }
    if (s.picked && s.variants && s.mapping) {
      $("p3-scores").classList.remove("hidden");
      $("btn-p3-apply").classList.remove("hidden");
      const inv = {}; for (const [k, v] of Object.entries(s.mapping)) inv[v] = k;
      let rows = "";
      for (const v of s.variants) {
        rows += "<tr><td><b>" + (inv[v.id] || "-") + "</b></td><td>" + v.id +
            "</td><td>" + (v.flags.tech ? "an" : "aus") + "</td><td>" +
            (v.flags.variation ? "an" : "aus") + "</td><td>" + v.composite +
            "</td><td>" + (v.voice_guard_ok ? "OK" : "ABWEICHUNG") + "</td></tr>";
      }
      $("p3-scores").querySelector("tbody").innerHTML = rows;
    }
  } catch (e) { console.warn(e); }
}
async function phase3Run(quick) {
  const r = await fetch("/api/phase3/run", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({quick}),
  });
  const d = await r.json();
  if (!d.ok && d.error) { alert(d.error); return; }
  $("p3-status").textContent = "Phase-3 läuft … (VD-E-Referenz wird geladen/gesperrt, dann 4 Varianten × Batterien)";
  const timer = setInterval(async () => {
    const st = await (await fetch("/api/status")).json();
    if (!st.running) { clearInterval(timer); phase3Status(); }
  }, 2500);
}
async function phase3Pick() {
  const r = await fetch("/api/phase3/blind_pick", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({letter: $("p3-pick").value}),
  });
  const d = await r.json();
  if (!d.ok && d.error) { alert(d.error); return; }
  phase3Status();
}
async function phase3Apply() {
  if (!confirm("Phase-3-Auswahl übernehmen?\nDie Stimme bleibt VD-E; es werden nur Fachwort- und Variations-Schalter gesetzt.")) return;
  const r = await fetch("/api/phase3/apply", {
    method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
  });
  const d = await r.json();
  if (d.ok) { alert("Übernommen: " + d.applied); phase3Status(); }
  else alert(d.error || "Fehler");
}

/* ---------------------------------------------------------- Upload */
async function uploadFiles(fileList) {
  for (const f of fileList) {
    if (!f.name.toLowerCase().endsWith(".txt")) continue;
    const text = await f.text();
    await fetch("/api/upload", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name: f.name, content: text}),
    });
  }
  loadFiles();
}

/* ------------------------------------------------------------ Utils */
function escapeHtml(s) {
  return String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g,
      m => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
}
function fmtSize(n) {
  if (n > 1e6) return (n / 1e6).toFixed(1) + " MB";
  if (n > 1e3) return (n / 1e3).toFixed(0) + " KB";
  return n + " B";
}

/* ------------------------------------------------------------ Events */
window.addEventListener("DOMContentLoaded", () => {
  loadConfig().then(loadFiles).then(loadPron).then(loadBenchAudio).catch(console.error);
  pollTimer = setInterval(pollStatus, 1200);

  $("btn-start").onclick = start;
  $("btn-stop").onclick = stopRun;
  $("in-preset").onchange = updatePresetDesc;
  $("in-speed").oninput = e => $("in-speed-val").textContent = Number(e.target.value).toFixed(2) + "×";
  $("in-vol").oninput = e => $("in-vol-val").textContent = e.target.value + " dB";

  $("adv-toggle").onclick = () => {
    const body = $("adv-body");
    body.classList.toggle("hidden");
    $("adv-toggle").textContent = "4 · Erweiterte Einstellungen " +
        (body.classList.contains("hidden") ? "▸" : "▾");
    if (!body.classList.contains("hidden") && !$("hw-info").textContent)
      renderHardware(CFG ? CFG.hardware : null);
  };
  for (const id of ["in-emotion", "in-intensity", "in-pause", "in-vol", "in-model", "in-quality"])
    $(id).onchange = saveAdvanced;

  $("btn-sysbench").onclick = () => benchmark("system");
  $("btn-voicebench").onclick = () => benchmark("voices");
  $("btn-de-baseline").onclick = () =>
      benchmark("german_baseline", "Deutsche Baseline erzeugen?\n(Vorhandene Baseline bleibt geschützt.)");
  $("btn-de-ab").onclick = () =>
      benchmark("german_ab", "Deutsche A/B-Optimierung starten?\n\nOK = vollständiger Test, Abbrechen = Schnelltest.");
  $("btn-de-speakers").onclick = () =>
      benchmark("german_speakers", "Deutsch-Stimmen-Benchmark starten?\nErmittelt DEFAULT BEST GERMAN NARRATOR.");
  $("btn-hwrefresh").onclick = async () => {
    const r = await fetch("/api/hardware/refresh", {method: "POST"});
    renderHardware(await r.json());
  };
  $("pron-add").onclick = addPron;
  $("btn-p2-run").onclick = () => phase2Run(false);
  $("btn-p2-quick").onclick = () => phase2Run(true);
  $("btn-p2-pauses").onclick = phase2Pauses;
  $("btn-p2-pick").onclick = phase2Pick;
  $("btn-p2-apply").onclick = phase2Apply;
  phase2Status();
  $("btn-p3-run").onclick = () => phase3Run(false);
  $("btn-p3-quick").onclick = () => phase3Run(true);
  $("btn-p3-pick").onclick = phase3Pick;
  $("btn-p3-apply").onclick = phase3Apply;
  phase3Status();
  $("btn-cache-failed").onclick = () => clearCache("failed");
  $("btn-cache-all").onclick = () => clearCache("all");

  const dz = $("dropzone");
  dz.onclick = () => $("file-input").click();
  $("file-input").onchange = e => uploadFiles(e.target.files);
  ["dragenter", "dragover"].forEach(ev =>
      dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach(ev =>
      dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", e => uploadFiles(e.dataTransfer.files));
  window.addEventListener("dragover", e => e.preventDefault());
  window.addEventListener("drop", e => e.preventDefault());
});
