/* ═══════════════════════════════════════════════════════════════
   ClassMatcher – Frontend
   ═══════════════════════════════════════════════════════════════ */

"use strict";

// ──────────────────────────────────────────────────────────────────
// Anwendungs-Zustand
// ──────────────────────────────────────────────────────────────────

const state = {
  mode:           "klasse5",  // "klasse5" | "klasse8"
  students:       [],      // alle Schüler:innen
  classes:        [],      // [{id, name, track, students:[…]}]
  stats:          [],      // [{classId, total, boys, girls, …}]
  pendingWishes:  [],      // offene Fuzzy-Matches
  dontBeWith:     [],      // [{a, b, label}]
  lockedStudents: {},      // {studentId: classId}
  params: {
    maxClassSize:           30,
    minClassSize:           22,
    weightFriendWish:        7,
    weightGenderBalance:     2,
    weightMusicSplit:       50,
    weightProfileCluster:   50,
    multiStart:              5,
    autoRefine:              2,
  },
  view:           "upload",  // "upload" | "loading" | "board"
  dragStudentId:  null,
  dragSourceClass: null,
};

// ──────────────────────────────────────────────────────────────────
// API-Hilfsfunktionen
// ──────────────────────────────────────────────────────────────────

const api = {
  async upload(file, mode) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", mode || "klasse5");
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    return r.json();
  },
  async assign() {
    const r = await fetch("/api/assign", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ lockedStudents: state.lockedStudents }),
    });
    return r.json();
  },
  async setParams(p) {
    await fetch("/api/params", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(p),
    });
  },
  async getPendingWishes() {
    const r = await fetch("/api/pending-wishes");
    return r.json();
  },
  async resolveWish(studentId, token, matchedId) {
    const r = await fetch("/api/resolve-wish", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ studentId, token, matchedId }),
    });
    return r.json();
  },
  async setDontBeWith(pairs) {
    await fetch("/api/dont-be-with", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ pairs }),
    });
  },
  async moveStudent(studentId, classId) {
    await fetch("/api/move-student", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ studentId, classId }),
    });
  },
  async unlockStudent(studentId) {
    await fetch("/api/unlock-student", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ studentId }),
    });
  },
  async clearLocks() {
    await fetch("/api/clear-locks", { method: "POST" });
  },
  async saveState() {
    const r = await fetch("/api/save-state");
    return r.json();
  },
  async loadState(data) {
    const r = await fetch("/api/load-state", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(data),
    });
    return r.json();
  },
  async renameClass(classId, name) {
    await fetch("/api/rename-class", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ classId, name }),
    });
  },
  async refineFriends() {
    const r = await fetch("/api/refine-friends", { method: "POST" });
    return r.json();
  },
  async checkUpdate() {
    const r = await fetch("/api/check-update");
    return r.json();
  },
  async downloadUpdate(downloadUrl) {
    const r = await fetch("/api/download-update", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ download_url: downloadUrl }),
    });
    return r.json();
  },
};

// ──────────────────────────────────────────────────────────────────
// Hilfsfunktionen
// ──────────────────────────────────────────────────────────────────

function trackClass(trackId) {
  if (!trackId) return "other";
  if (trackId.startsWith("5x") || trackId === "8x") return "5x";
  if (trackId.startsWith("5y") || trackId === "8y") return "5y";
  if (trackId.startsWith("5z") || trackId === "8z") return "5z";
  return "other";
}

function trackLabel(track) {
  if (state.mode === "klasse8") {
    return { "5x": "Musik-Klasse", "5y": "Bili-Klasse", "5z": "Normalklasse" }[track] || track;
  }
  return { "5x": "Musikzug", "5y": "Bili-Klasse", "5z": "Normalzug" }[track] || track;
}

function trackBadgeClass(track) {
  return "track-" + track.replace(/[^a-z0-9]/gi, "");
}

function statsFor(classId) {
  return state.stats.find(s => s.classId === classId) || {};
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function modeSubtitle(count) {
  const label = state.mode === "klasse8" ? "Klasse 8 mischen" : "Klasse 5 einteilen";
  return `${count} Schüler:innen · ${label}`;
}

// ──────────────────────────────────────────────────────────────────
// Views
// ──────────────────────────────────────────────────────────────────

function showView(v) {
  state.view = v;
  document.getElementById("upload-view").classList.toggle("hidden", v !== "upload");
  document.getElementById("loading-view").classList.toggle("hidden", v !== "loading");
  document.getElementById("board-view").classList.toggle("hidden", v !== "board");

  const afterUpload = v === "board";
  document.getElementById("btn-reassign").classList.toggle("hidden", !afterUpload);
  document.getElementById("btn-refine-friends").classList.toggle("hidden", !afterUpload);
  document.getElementById("btn-clear-locks").classList.toggle("hidden", !afterUpload);
  document.getElementById("btn-save").classList.toggle("hidden", !afterUpload);
  document.getElementById("btn-print").classList.toggle("hidden", !afterUpload);
  document.getElementById("sidebar").classList.toggle("hidden", !afterUpload);
}

// ──────────────────────────────────────────────────────────────────
// Board rendern
// ──────────────────────────────────────────────────────────────────

function renderBoard() {
  const board = document.getElementById("board");
  board.innerHTML = "";

  const row = document.createElement("div");
  row.className = "classes-row";
  board.appendChild(row);

  for (const cls of state.classes) {
    row.appendChild(renderClassCol(cls));
  }
}

function renderClassCol(cls) {
  const st   = statsFor(cls.id);
  const col  = document.createElement("div");
  col.className = "class-col";
  col.dataset.classId = cls.id;

  let extraStats = "";
  if (state.mode === "klasse8") {
    const cntBili   = cls.students.filter(s => s.bili).length;
    const cntLatein = cls.students.filter(s => s.latein).length;
    const cntMusik  = cls.students.filter(s => s.profil === "Musik").length;
    extraStats = `
      <span class="stat-item stat-lang-l" title="Latein als 2. Fremdsprache">L&nbsp;${cntLatein}</span>
      ${cntBili  ? `<span class="stat-item stat-lang-f" title="Bili-Zug">Bili&nbsp;${cntBili}</span>` : ""}
      ${cntMusik ? `<span class="stat-item" style="color:#be185d;font-weight:600" title="Musik-Profil">Mu&nbsp;${cntMusik}</span>` : ""}`;
  } else {
    const countF = cls.students.filter(s => s.fremdsprache2 === "F").length;
    const countL = cls.students.filter(s => s.fremdsprache2 === "L").length;
    extraStats = `
      <span class="stat-item stat-lang-f" title="Französisch">F&nbsp;${countF}</span>
      <span class="stat-item stat-lang-l" title="Latein">L&nbsp;${countL}</span>`;
  }

  const wishInfo = st.total_wishes > 0
    ? `<span class="stat-item ${st.fulfilled_wishes === st.total_wishes ? "stat-good" : ""}">
         ♥ ${st.fulfilled_wishes}/${st.total_wishes}
       </span>`
    : "";

  const violInfo = st.violations > 0
    ? `<span class="stat-item stat-warn">⚠ ${st.violations} Verstoß</span>` : "";

  col.innerHTML = `
    <div class="class-header">
      <div class="class-name-row">
        <span class="class-name"
              data-class-id="${cls.id}"
              title="Klicken zum Umbenennen">${cls.name}</span>
      </div>
      <div class="class-stats">
        <span class="stat-item">${st.total || 0} Schüler</span>
        <span class="stat-item stat-boys">♂${st.boys || 0}</span>
        <span class="stat-item stat-girls">♀${st.girls || 0}</span>
        ${extraStats}
        ${wishInfo}
        ${violInfo}
      </div>
    </div>
    <div class="student-list" data-class-id="${cls.id}"></div>
  `;

  const list = col.querySelector(".student-list");
  const sorted = [...cls.students].sort((a, b) => a.name.localeCompare(b.name, "de"));
  for (const s of sorted) {
    list.appendChild(renderStudentCard(s, cls.id));
  }

  // Klasse umbenennen (contenteditable)
  const nameEl = col.querySelector(".class-name");
  nameEl.addEventListener("click", () => {
    nameEl.contentEditable = "true";
    nameEl.focus();
    const range = document.createRange();
    range.selectNodeContents(nameEl);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
  });
  nameEl.addEventListener("blur", async () => {
    nameEl.contentEditable = "false";
    const newName = nameEl.textContent.trim();
    if (newName) {
      await api.renameClass(cls.id, newName);
      // Name im State aktualisieren
      const found = state.classes.find(c => c.id === cls.id);
      if (found) found.name = newName;
    }
  });
  nameEl.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); nameEl.blur(); }
    if (e.key === "Escape") {
      nameEl.contentEditable = "false";
      nameEl.textContent = cls.name;
    }
  });

  // Drag-&-Drop auf die Liste
  setupDropZone(list);

  return col;
}

const TRACK_LABELS = { "5x": "Musik", "5y": "Bili", "5z": "Normal" };
const PROFIL_LONG  = { "5x": "Musikzug", "5y": "Bili-Klasse", "5z": "Normalzug" };
const LANG_LABELS  = { "F": "Franzö.", "L": "Latein" };

const PROFIL8_SHORT = {
  "Naturwissenschaft und Technik (NWT)": "NWT",
  "Spanisch": "Span",
  "IMP":      "IMP",
  "Musik":    "Musik",
};
const PROFIL8_CLASS = {
  "Naturwissenschaft und Technik (NWT)": "nwt",
  "Spanisch": "sp",
  "IMP":      "imp",
  "Musik":    "musik",
};

function buildBadgesHtml(student) {
  if (state.mode === "klasse8") {
    const profil      = student.profil || "";
    const profilShort = PROFIL8_SHORT[profil] || profil;
    const profilCls   = PROFIL8_CLASS[profil] || "other";
    const profBadge   = profil
      ? `<span class="badge badge-${profilCls}" title="${profil}">${profilShort}</span>`
      : "";
    const biliBadge   = student.bili
      ? `<span class="badge badge-bili" title="Bili-Zug">Bili</span>`
      : "";
    const latBadge    = student.latein
      ? `<span class="badge badge-L" title="Latein als 2. Fremdsprache">Latein</span>`
      : "";
    return `<div class="card-badges">${profBadge}${biliBadge}${latBadge}</div>`;
  }

  const track     = trackClass(student.profil);
  const trackLabel = TRACK_LABELS[track] || track;
  const lang      = student.fremdsprache2 || "";
  const langLabel = LANG_LABELS[lang] || lang;

  const trackBadge = `<span class="badge badge-${track}">${trackLabel}</span>`;
  const langBadge  = lang
    ? `<span class="badge badge-${lang}">${langLabel}</span>`
    : "";

  return `<div class="card-badges">${trackBadge}${langBadge}</div>`;
}

function buildWishHtml(wishInfo) {
  if (!wishInfo || wishInfo.length === 0) return "";
  const parts = wishInfo.map(w => {
    if (w.fulfilled) {
      return `<span class="wish-tag wish-ok" title="Wunsch erfüllt">✓ ${w.friendName}</span>`;
    } else {
      const cls = w.friendClass ? ` → ${w.friendClass}` : "";
      return `<span class="wish-tag wish-miss" title="Wunsch nicht erfüllt">✗ ${w.friendName}${cls}</span>`;
    }
  });
  return `<div class="wish-row">${parts.join("")}</div>`;
}

function renderStudentCard(student, classId) {
  const card = document.createElement("div");
  card.className = "student-card";
  card.dataset.studentId = student.id;
  card.dataset.classId   = classId;
  card.draggable = true;

  const locked = !!state.lockedStudents[student.id];
  if (locked) card.classList.add("locked");

  const gClass = student.geschlecht === "m" ? "m"
               : student.geschlecht === "w" ? "w" : "x";

  const lockBtn = locked
    ? `<span class="lock-icon" data-student-id="${student.id}" title="Sperre aufheben">🔒</span>`
    : "";

  const badgesHtml = buildBadgesHtml(student);
  const wishHtml   = buildWishHtml(student.wishInfo);

  card.innerHTML = `
    <span class="gender-dot ${gClass}"></span>
    <div class="student-info">
      <div class="student-name-row">
        <span class="student-name">${student.displayName}</span>
        ${badgesHtml}
      </div>
      ${wishHtml}
    </div>
    ${lockBtn}
  `;

  // Lock aufheben
  const lockEl = card.querySelector(".lock-icon");
  if (lockEl) {
    lockEl.addEventListener("click", async e => {
      e.stopPropagation();
      const sid = lockEl.dataset.studentId;
      delete state.lockedStudents[sid];
      await api.unlockStudent(sid);
      await doAssign();
    });
  }

  // Drag-Events
  card.addEventListener("dragstart", e => {
    state.dragStudentId   = student.id;
    state.dragSourceClass = classId;
    card.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", student.id);
  });

  card.addEventListener("dragend", () => {
    card.classList.remove("dragging");
    document.querySelectorAll(".drop-placeholder").forEach(el => el.remove());
    document.querySelectorAll(".class-col.drag-over").forEach(el => el.classList.remove("drag-over"));
  });

  return card;
}

// ──────────────────────────────────────────────────────────────────
// Hilfsfunktionen für sofortige Client-seitige Neuberechnung nach Drag
// ──────────────────────────────────────────────────────────────────

function recomputeWishInfo() {
  const sidToClsId   = {};
  const sidToClsName = {};
  for (const cls of state.classes) {
    for (const s of cls.students) {
      sidToClsId[s.id]   = cls.id;
      sidToClsName[s.id] = cls.name;
    }
  }
  for (const cls of state.classes) {
    for (const s of cls.students) {
      if (!s.wishInfo || s.wishInfo.length === 0) continue;
      s.wishInfo = s.wishInfo.map(w => {
        const fulfilled = sidToClsId[w.friendId] === cls.id;
        return { ...w, fulfilled, friendClass: fulfilled ? null : (sidToClsName[w.friendId] || null) };
      });
    }
  }
}

function recomputeStats() {
  for (const cls of state.classes) {
    const stat = state.stats.find(s => s.classId === cls.id);
    if (!stat) continue;
    stat.total  = cls.students.length;
    stat.boys   = cls.students.filter(s => s.geschlecht === "m").length;
    stat.girls  = cls.students.filter(s => s.geschlecht === "w").length;
    let totalW = 0, fulfilledW = 0;
    for (const s of cls.students) {
      for (const w of s.wishInfo || []) {
        totalW++;
        if (w.fulfilled) fulfilledW++;
      }
    }
    stat.total_wishes     = totalW;
    stat.fulfilled_wishes = fulfilledW;
    const sidSet = new Set(cls.students.map(s => s.id));
    let violations = 0;
    for (const pair of state.dontBeWith) {
      if (sidSet.has(pair.a) && sidSet.has(pair.b)) violations++;
    }
    stat.violations = violations;
  }
}

// ──────────────────────────────────────────────────────────────────
// Drag-&-Drop: Drop-Zone einrichten
// ──────────────────────────────────────────────────────────────────

function setupDropZone(listEl) {
  listEl.addEventListener("dragover", e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const col = listEl.closest(".class-col");
    col.classList.add("drag-over");

    // Placeholder anzeigen
    listEl.querySelectorAll(".drop-placeholder").forEach(el => el.remove());
    const ph = document.createElement("div");
    ph.className = "drop-placeholder";
    listEl.appendChild(ph);
  });

  listEl.addEventListener("dragleave", e => {
    if (!listEl.contains(e.relatedTarget)) {
      const col = listEl.closest(".class-col");
      col.classList.remove("drag-over");
      listEl.querySelectorAll(".drop-placeholder").forEach(el => el.remove());
    }
  });

  listEl.addEventListener("drop", async e => {
    e.preventDefault();
    const col = listEl.closest(".class-col");
    col.classList.remove("drag-over");
    listEl.querySelectorAll(".drop-placeholder").forEach(el => el.remove());

    const targetClassId = listEl.dataset.classId;
    const studentId     = state.dragStudentId;

    if (!studentId || !targetClassId) return;
    if (targetClassId === state.dragSourceClass) return;

    // Optimistisches Update: Schüler im State verschieben
    const src = state.classes.find(c => c.id === state.dragSourceClass);
    const dst = state.classes.find(c => c.id === targetClassId);
    if (!src || !dst) return;

    const idx = src.students.findIndex(s => s.id === studentId);
    if (idx === -1) return;

    const [moved] = src.students.splice(idx, 1);
    dst.students.push(moved);
    state.lockedStudents[studentId] = targetClassId;

    // Sofort alles client-seitig neu berechnen und rendern
    recomputeWishInfo();
    recomputeStats();
    renderBoard();

    // Lock auf Server setzen (kein SA-Neustart)
    await api.moveStudent(studentId, targetClassId);
  });
}

// ──────────────────────────────────────────────────────────────────
// Zuweisung durchführen
// ──────────────────────────────────────────────────────────────────

function applyAssignmentResult(result) {
  state.classes = result.classes;
  state.stats   = result.stats;
  showView("board");
  renderBoard();
}

async function doAssign(showLoading = true) {
  if (showLoading) showView("loading");
  try {
    const result = await api.assign();
    if (result.error) { alert("Fehler: " + result.error); return; }
    applyAssignmentResult(result);
  } catch (err) {
    alert("Verbindungsfehler: " + err.message);
    showView("board");
  }
}

// ──────────────────────────────────────────────────────────────────
// Fuzzy-Matches-Modal
// ──────────────────────────────────────────────────────────────────

async function openFuzzyModal() {
  const pending = await api.getPendingWishes();
  state.pendingWishes = pending;

  const list = document.getElementById("fuzzy-list");
  list.innerHTML = "";

  if (!pending.length) {
    list.innerHTML = '<p style="color:#64748b;text-align:center">Alle Wünsche wurden automatisch erkannt 🎉</p>';
    document.getElementById("fuzzy-modal").classList.remove("hidden");
    return;
  }

  for (const item of pending) {
    for (const p of item.pending) {
      const div = document.createElement("div");
      div.className = "fuzzy-item";

      const candidatesHtml = p.candidates.length
        ? p.candidates.map(c => `
            <div class="fuzzy-candidate" data-sid="${c.id}" data-token="${encodeURIComponent(p.token)}" data-parent-sid="${item.studentId}">
              ${c.name}
              <span class="fuzzy-score">${Math.round(c.score * 100)}%</span>
            </div>`).join("")
        : `<p style="font-size:12px;color:#94a3b8">Kein Treffer gefunden</p>`;

      div.innerHTML = `
        <div class="fuzzy-item-header">
          <div>
            <span class="fuzzy-student-name">${item.studentName}</span> wünscht sich:
            <span class="fuzzy-token">${p.token}</span>
          </div>
          <div class="fuzzy-original" style="margin-top:2px">
            Originaltext: „${item.originalText}"
          </div>
        </div>
        <div class="fuzzy-candidates">
          ${candidatesHtml}
          <div class="fuzzy-skip" data-token="${encodeURIComponent(p.token)}" data-parent-sid="${item.studentId}">
            ↷ Ignorieren
          </div>
        </div>
      `;

      // Kandidat auswählen
      div.querySelectorAll(".fuzzy-candidate").forEach(el => {
        el.addEventListener("click", async () => {
          div.querySelectorAll(".fuzzy-candidate").forEach(x => x.classList.remove("chosen"));
          el.classList.add("chosen");
          const token = decodeURIComponent(el.dataset.token);
          await api.resolveWish(el.dataset.parentSid, token, el.dataset.sid);
        });
      });

      // Ignorieren
      div.querySelector(".fuzzy-skip")?.addEventListener("click", async el => {
        const token = decodeURIComponent(el.currentTarget.dataset.token);
        await api.resolveWish(el.currentTarget.dataset.parentSid, token, null);
        div.style.opacity = ".4";
        div.style.pointerEvents = "none";
      });

      list.appendChild(div);
    }
  }

  document.getElementById("fuzzy-modal").classList.remove("hidden");
}

// ──────────────────────────────────────────────────────────────────
// Nicht-zusammen-Paare-Modal
// ──────────────────────────────────────────────────────────────────

function renderDontBeWithList() {
  const container = document.getElementById("dont-be-with-list");
  container.innerHTML = "";
  for (const pair of state.dontBeWith) {
    const item = document.createElement("div");
    item.className = "pair-item";
    item.innerHTML = `
      <span>${pair.label}</span>
      <button data-a="${pair.a}" data-b="${pair.b}" title="Entfernen">✕</button>
    `;
    item.querySelector("button").addEventListener("click", async e => {
      const a = e.currentTarget.dataset.a;
      const b = e.currentTarget.dataset.b;
      state.dontBeWith = state.dontBeWith.filter(p => !(p.a === a && p.b === b));
      await api.setDontBeWith(state.dontBeWith);
      renderDontBeWithList();
    });
    container.appendChild(item);
  }
}

function openPairModal() {
  document.getElementById("pair-a").value = "";
  document.getElementById("pair-b").value = "";
  document.getElementById("pair-a-id").value = "";
  document.getElementById("pair-b-id").value = "";
  document.getElementById("pair-a-results").classList.add("hidden");
  document.getElementById("pair-b-results").classList.add("hidden");
  document.getElementById("pair-modal").classList.remove("hidden");
}

function setupStudentSearch(inputId, hiddenId, resultsId) {
  const input   = document.getElementById(inputId);
  const hidden  = document.getElementById(hiddenId);
  const results = document.getElementById(resultsId);

  input.addEventListener("input", () => {
    const q = input.value.toLowerCase().trim();
    results.innerHTML = "";
    if (!q || q.length < 2) { results.classList.add("hidden"); return; }

    const matches = state.students
      .filter(s => s.displayName.toLowerCase().includes(q))
      .slice(0, 8);

    if (!matches.length) { results.classList.add("hidden"); return; }

    matches.forEach(s => {
      const opt = document.createElement("div");
      opt.className = "search-option";
      opt.textContent = s.displayName;
      opt.addEventListener("click", () => {
        input.value  = s.displayName;
        hidden.value = s.id;
        results.classList.add("hidden");
      });
      results.appendChild(opt);
    });
    results.classList.remove("hidden");
  });

  input.addEventListener("blur", () => {
    setTimeout(() => results.classList.add("hidden"), 150);
  });
}

// ──────────────────────────────────────────────────────────────────
// Parameter-Panel
// ──────────────────────────────────────────────────────────────────

function setupParams() {
  const debouncedUpdate = debounce(async () => {
    await api.setParams(state.params);
    await doAssign();
  }, 600);

  function bindSlider(id, key, outputId, suffix = "") {
    const slider = document.getElementById(id);
    const output = document.getElementById(outputId);
    if (!slider || !output) return;
    slider.value = state.params[key];
    output.textContent = state.params[key] + suffix;

    slider.addEventListener("input", () => {
      const val = Number(slider.value);
      state.params[key] = val;
      output.textContent = val + suffix;
      // Min darf Max nicht überschreiten und umgekehrt
      if (id === "p-minSize" && val > state.params.maxClassSize) {
        state.params.maxClassSize = val;
        const maxOut = document.getElementById("p-maxSize-val");
        const maxSld = document.getElementById("p-maxSize");
        if (maxOut) maxOut.textContent = val;
        if (maxSld) maxSld.value       = val;
      }
      if (id === "p-maxSize" && val < state.params.minClassSize) {
        state.params.minClassSize = val;
        const minOut = document.getElementById("p-minSize-val");
        const minSld = document.getElementById("p-minSize");
        if (minOut) minOut.textContent = val;
        if (minSld) minSld.value       = val;
      }
      debouncedUpdate();
    });
  }

  bindSlider("p-maxSize", "maxClassSize",         "p-maxSize-val");
  bindSlider("p-minSize", "minClassSize",         "p-minSize-val");
  bindSlider("p-friend",  "weightFriendWish",     "p-friend-val");
  bindSlider("p-gender",  "weightGenderBalance",  "p-gender-val");
  bindSlider("p-music",   "weightMusicSplit",     "p-music-val", "%");
  bindSlider("p-profile", "weightProfileCluster", "p-profile-val", "%");
}

// ──────────────────────────────────────────────────────────────────
// Modus-spezifische UI-Sichtbarkeit
// ──────────────────────────────────────────────────────────────────

function applyModeUI() {
  // Toggle-Knöpfe im Upload-View
  const b5 = document.getElementById("mode-klasse5");
  const b8 = document.getElementById("mode-klasse8");
  if (b5 && b8) {
    b5.classList.toggle("active", state.mode === "klasse5");
    b8.classList.toggle("active", state.mode === "klasse8");
    b5.setAttribute("aria-selected", state.mode === "klasse5");
    b8.setAttribute("aria-selected", state.mode === "klasse8");
  }
  // Sidebar-Sliders je nach mode anzeigen/verstecken
  document.querySelectorAll("[data-mode]").forEach(el => {
    const m = el.getAttribute("data-mode");
    el.classList.toggle("hidden", m !== state.mode);
  });
}

// ──────────────────────────────────────────────────────────────────
// Print
// ──────────────────────────────────────────────────────────────────

function buildPrintView() {
  const container = document.getElementById("print-content");
  container.innerHTML = "";

  const today = new Date().toLocaleDateString("de-DE", {
    day: "2-digit", month: "long", year: "numeric",
  });

  // Rückwärts-Map: studentId → Klassenname (für nicht erfüllte Wünsche)
  const sidToClass = {};
  for (const cls of state.classes) {
    for (const s of cls.students) {
      sidToClass[s.id] = cls.name;
    }
  }

  for (const cls of state.classes) {
    const st    = statsFor(cls.id);
    const track = trackClass(cls.track);
    const page  = document.createElement("div");
    page.className = "print-page";

    // Schüler nach Nachname sortiert
    const sorted = [...cls.students].sort((a, b) => a.name.localeCompare(b.name, "de"));

    const rows = sorted.map((s, i) => {
      const gClass = s.geschlecht === "m" ? "m" : s.geschlecht === "w" ? "w" : "x";

      let zugLabel, langLabel;
      if (state.mode === "klasse8") {
        zugLabel = (PROFIL8_SHORT[s.profil] || s.profil || "–")
                 + (s.bili ? " · Bili" : "");
        langLabel = s.latein ? "Latein" : "Französisch";
      } else {
        zugLabel = PROFIL_LONG[s.profil] || s.profil;
        langLabel = s.fremdsprache2 === "F" ? "Französisch"
                  : s.fremdsprache2 === "L" ? "Latein"
                  : s.fremdsprache2 || "–";
      }

      // Wunschfreunde: erfüllt und nicht erfüllt (mit Trennungsgrund)
      const wishes = (s.wishInfo || []);
      const wishParts = wishes.map(w => {
        if (w.fulfilled) {
          return `<span class="pt-wish-yes">✓ ${w.friendName}</span>`;
        }
        const cls = w.friendClass ? ` (${w.friendClass})` : "";
        const showReason = w.reason && w.reason !== w.friendClass;
        const reason = showReason ? ` <em class="pt-wish-reason">– ${w.reason}</em>` : "";
        return `<span class="pt-wish-no">✗ ${w.friendName}${cls}${reason}</span>`;
      });
      const wishCell = wishParts.length > 0
        ? `<td class="pt-wish">${wishParts.join(" ")}</td>`
        : `<td class="pt-wish-none">–</td>`;

      const nameOut = state.mode === "klasse8"
        ? `${s.name}, ${s.vorname}`
        : `${s.name}, ${s.rufname || s.vorname}`;

      return `
        <tr>
          <td class="pt-num">${i + 1}.</td>
          <td class="pt-name">
            <span class="print-dot ${gClass}"></span>${nameOut}
          </td>
          <td class="pt-zug">${zugLabel}</td>
          <td class="pt-lang">${langLabel}</td>
          ${wishCell}
        </tr>`;
    }).join("");

    const wishSummary = st.total_wishes > 0
      ? ` · ${st.fulfilled_wishes} von ${st.total_wishes} Wünschen erfüllt` : "";

    const yr = new Date().getFullYear();
    const headerLine = state.mode === "klasse8"
      ? `Klasse 8 · Schuljahr ${yr}/${yr + 1}`
      : `Klasse 5 · Schuljahr ${yr}/${yr + 1}`;

    const zugColTitle = state.mode === "klasse8" ? "Profil" : "Zug";

    page.innerHTML = `
      <div class="print-header">
        <div class="print-header-left">
          <img src="logo.png" alt="Schiller-Gymnasium" class="print-logo" />
          <div>
            <div class="print-class-name">${cls.name}</div>
            <div class="print-track-line">${trackLabel(track)}</div>
          </div>
        </div>
        <div class="print-header-right">
          Schiller-Gymnasium Offenburg<br>
          ${headerLine}<br>
          ${today}
        </div>
      </div>
      <div class="print-stats">
        <span>${st.total} Schüler:innen</span>
        <span>♂ ${st.boys} Jungen</span>
        <span>♀ ${st.girls} Mädchen</span>
        <span>${wishSummary}</span>
      </div>
      <table class="print-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Name, Vorname</th>
            <th>${zugColTitle}</th>
            <th>2. Fremdsprache</th>
            <th>Freundeswünsche</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
    container.appendChild(page);
  }
}

// ──────────────────────────────────────────────────────────────────
// Stand speichern / laden
// ──────────────────────────────────────────────────────────────────

async function saveStateToFile() {
  const data = await api.saveState();
  const date = new Date().toISOString().slice(0, 10);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `klassen-stand-${date}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

async function loadStateFromFile(file) {
  if (!file) return;
  const errorEl = document.getElementById("upload-error");
  errorEl.classList.add("hidden");
  showView("loading");

  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const result = await api.loadState(data);

    if (result.error) {
      errorEl.textContent = result.error;
      errorEl.classList.remove("hidden");
      showView("upload");
      return;
    }

    state.mode            = result.mode || data.mode || "klasse5";
    state.students        = await (await fetch("/api/students")).json();
    state.lockedStudents  = data.locked_students || {};
    state.dontBeWith      = data.dont_be_with    || [];
    state.params          = Object.assign({}, state.params, data.params || {});
    state.classes         = result.classes;
    state.stats           = result.stats;

    updateSubtitle(modeSubtitle(result.count));
    updateFuzzyBadge(result.pendingCount);
    applyModeUI();
    setupParams();
    renderDontBeWithList();
    showView("board");
    renderBoard();
  } catch (e) {
    errorEl.textContent = "Fehler beim Laden: " + e.message;
    errorEl.classList.remove("hidden");
    showView("upload");
  }
}

// ──────────────────────────────────────────────────────────────────
// Fuzzy-Badge aktualisieren
// ──────────────────────────────────────────────────────────────────

function updateFuzzyBadge(count) {
  const btn   = document.getElementById("btn-fuzzy");
  const badge = document.getElementById("fuzzy-badge");
  if (count > 0) {
    badge.textContent = count;
    btn.classList.remove("hidden");
  } else {
    btn.classList.add("hidden");
  }
}

// ──────────────────────────────────────────────────────────────────
// Header-Untertitel
// ──────────────────────────────────────────────────────────────────

function updateSubtitle(text) {
  document.getElementById("header-subtitle").textContent = text;
}

// ──────────────────────────────────────────────────────────────────
// Auto-Update-Banner
// ──────────────────────────────────────────────────────────────────

async function checkForUpdate() {
  let info;
  try {
    info = await api.checkUpdate();
  } catch {
    return;  // Netzfehler o.ä. – stillschweigend, kein Banner
  }
  if (!info || !info.update_available) return;

  const banner  = document.getElementById("update-banner");
  const textEl  = document.getElementById("update-banner-text");
  const actions = document.getElementById("update-banner-actions");

  textEl.textContent =
    `🔔 Version ${info.latest} verfügbar (Sie haben ${info.current}).`;
  if (info.notes) textEl.textContent += ` ${info.notes}`;

  const btn = document.createElement("button");
  btn.className = "btn btn-primary btn-sm";
  btn.textContent = "Jetzt herunterladen";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Lädt …";
    let res;
    try {
      res = await api.downloadUpdate(info.download_url);
    } catch {
      res = { ok: false, fallback_url: info.download_url };
    }
    actions.innerHTML = "";
    if (res.ok) {
      textEl.textContent =
        `✓ Heruntergeladen: ${res.path} — alte App schließen, neue Datei starten.`;
    } else {
      textEl.textContent = "Automatischer Download ging nicht (Proxy?). ";
      const link = document.createElement("a");
      link.href = res.fallback_url;
      link.textContent = "Hier direkt herunterladen";
      link.setAttribute("download", "");
      actions.appendChild(link);
    }
  });
  actions.appendChild(btn);

  document.getElementById("update-banner-close")
    .addEventListener("click", () => banner.classList.add("hidden"));

  banner.classList.remove("hidden");
}

// ──────────────────────────────────────────────────────────────────
// Initialisierung
// ──────────────────────────────────────────────────────────────────

async function init() {
  applyModeUI();
  showView("upload");

  // App-Version vom Backend holen – Single Source of Truth ist app.py
  fetch("/api/version")
    .then(r => r.json())
    .then(d => {
      const el = document.getElementById("app-version");
      if (el && d.version) el.textContent = "v" + d.version;
    })
    .catch(() => {});

  // Auto-Update-Check (nicht-blockierend, scheitert still)
  checkForUpdate();

  // ── Mode-Toggle ───────────────────────────────────────────
  document.getElementById("mode-klasse5").addEventListener("click", () => {
    state.mode = "klasse5";
    applyModeUI();
  });
  document.getElementById("mode-klasse8").addEventListener("click", () => {
    state.mode = "klasse8";
    applyModeUI();
  });

  // ── Upload ────────────────────────────────────────────────
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const errorEl   = document.getElementById("upload-error");

  async function handleFile(file) {
    if (!file) return;
    errorEl.classList.add("hidden");
    showView("loading");

    const result = await api.upload(file, state.mode);
    if (result.error) {
      errorEl.textContent = result.error;
      errorEl.classList.remove("hidden");
      showView("upload");
      return;
    }

    state.mode     = result.mode || state.mode;
    state.students = await (await fetch("/api/students")).json();
    updateSubtitle(modeSubtitle(result.count));
    updateFuzzyBadge(result.pendingCount);

    applyModeUI();
    setupParams();
    await doAssign();
  }

  fileInput.addEventListener("change", e => handleFile(e.target.files[0]));

  dropZone.addEventListener("dragover", e => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
  dropZone.addEventListener("drop", e => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    handleFile(e.dataTransfer.files[0]);
  });

  // ── Neu zuweisen ─────────────────────────────────────────
  document.getElementById("btn-reassign").addEventListener("click", () => doAssign());

  // ── Freunde optimieren ───────────────────────────────────
  document.getElementById("btn-refine-friends").addEventListener("click", async () => {
    const btn = document.getElementById("btn-refine-friends");
    const before = state.stats.reduce((a, s) => a + (s.fulfilled_wishes || 0), 0);
    const total  = state.stats.reduce((a, s) => a + (s.total_wishes || 0), 0);
    btn.disabled = true;
    showView("loading");
    try {
      const result = await api.refineFriends();
      if (result.error) { alert("Fehler: " + result.error); showView("board"); return; }
      applyAssignmentResult(result);
      const after = state.stats.reduce((a, s) => a + (s.fulfilled_wishes || 0), 0);
      const delta = after - before;
      updateSubtitle(`Freundes-Refinement: ${after}/${total} Wünsche (${delta >= 0 ? "+" : ""}${delta})`);
    } catch (err) {
      alert("Verbindungsfehler: " + err.message);
      showView("board");
    } finally {
      btn.disabled = false;
    }
  });

  // ── Locks zurücksetzen ────────────────────────────────────
  document.getElementById("btn-clear-locks").addEventListener("click", async () => {
    state.lockedStudents = {};
    await api.clearLocks();
    await doAssign();
  });

  // ── Stand speichern ──────────────────────────────────────
  document.getElementById("btn-save").addEventListener("click", saveStateToFile);

  // ── Stand laden ───────────────────────────────────────────
  const loadSaveInput = document.getElementById("load-save-input");
  document.getElementById("btn-load-save").addEventListener("click", () => loadSaveInput.click());
  loadSaveInput.addEventListener("change", e => {
    loadStateFromFile(e.target.files[0]);
    loadSaveInput.value = "";
  });

  // ── Drucken ───────────────────────────────────────────────
  document.getElementById("btn-print").addEventListener("click", () => {
    buildPrintView();
    window.print();
  });

  // ── Fuzzy-Modal ───────────────────────────────────────────
  document.getElementById("btn-fuzzy").addEventListener("click", openFuzzyModal);
  document.getElementById("fuzzy-close").addEventListener("click", () =>
    document.getElementById("fuzzy-modal").classList.add("hidden")
  );
  document.getElementById("fuzzy-done").addEventListener("click", async () => {
    document.getElementById("fuzzy-modal").classList.add("hidden");
    const pending = await api.getPendingWishes();
    updateFuzzyBadge(pending.length);   // Anzahl Schüler mit offenen Wünschen
    await doAssign();
  });

  // ── Paare-Modal ───────────────────────────────────────────
  document.getElementById("btn-add-pair").addEventListener("click", openPairModal);
  document.getElementById("pair-close").addEventListener("click",  () =>
    document.getElementById("pair-modal").classList.add("hidden")
  );
  document.getElementById("pair-cancel").addEventListener("click", () =>
    document.getElementById("pair-modal").classList.add("hidden")
  );

  setupStudentSearch("pair-a", "pair-a-id", "pair-a-results");
  setupStudentSearch("pair-b", "pair-b-id", "pair-b-results");

  document.getElementById("pair-save").addEventListener("click", async () => {
    const aId   = document.getElementById("pair-a-id").value;
    const bId   = document.getElementById("pair-b-id").value;
    const aName = document.getElementById("pair-a").value.trim();
    const bName = document.getElementById("pair-b").value.trim();

    if (!aId || !bId) { alert("Bitte beide Schüler:innen auswählen."); return; }
    if (aId === bId)   { alert("Bitte zwei verschiedene Personen wählen."); return; }

    // Duplikat prüfen
    const exists = state.dontBeWith.some(
      p => (p.a === aId && p.b === bId) || (p.a === bId && p.b === aId)
    );
    if (exists) { alert("Dieses Paar ist bereits eingetragen."); return; }

    state.dontBeWith.push({ a: aId, b: bId, label: `${aName} ≠ ${bName}` });
    await api.setDontBeWith(state.dontBeWith);
    renderDontBeWithList();

    document.getElementById("pair-modal").classList.add("hidden");
    await doAssign();
  });

  // ── Hilfe-Modal ───────────────────────────────────────────
  document.getElementById("btn-help").addEventListener("click", () =>
    document.getElementById("help-modal").classList.remove("hidden")
  );
  document.getElementById("help-close").addEventListener("click", () =>
    document.getElementById("help-modal").classList.add("hidden")
  );
  document.getElementById("help-done").addEventListener("click", () =>
    document.getElementById("help-modal").classList.add("hidden")
  );

  // ── Modal schließen bei Klick außen ───────────────────────
  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", e => {
      if (e.target === overlay) overlay.classList.add("hidden");
    });
  });
}

document.addEventListener("DOMContentLoaded", init);
