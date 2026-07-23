"use strict";

const COVER_PLACEHOLDER =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="230" height="150"><rect width="100%" height="100%" fill="#0b1220"/><text x="50%" y="50%" fill="#334155" font-family="sans-serif" font-size="14" text-anchor="middle" dominant-baseline="middle">sem capa</text></svg>'
  );

// --- ponte de eventos empurrados pelo Python ---
window.pushEvent = function (name, payload) {
  const handlers = window._handlers[name] || [];
  handlers.forEach((h) => h(payload));
};
window._handlers = {};
function on(name, fn) {
  (window._handlers[name] = window._handlers[name] || []).push(fn);
}

function api() {
  return window.pywebview && window.pywebview.api;
}

// --- ícones (SVG inline estilo linha, sem CDN) ---
const _SVG = (p) =>
  `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICON = {
  book: _SVG('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>'),
  download: _SVG('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
  check: _SVG('<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>'),
  alert: _SVG('<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'),
};

// --- job de listagem de capítulos em andamento (para tratar erro no seletor) ---
let currentChaptersJob = null;

// --- navegação ---
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("view-" + btn.dataset.view).classList.add("active");
    if (btn.dataset.view === "library") loadLibrary();
    if (btn.dataset.view === "dashboard") loadDashboard();
    if (btn.dataset.view === "downloads") loadQueue();
    if (btn.dataset.view === "tools") loadDownloadDir();
  });
});

// --- log ao vivo ---
const logEl = () => document.getElementById("log");
on("log", (p) => {
  const el = logEl();
  el.textContent += p.line + "\n";
  el.scrollTop = el.scrollHeight;
});
on("job_started", (p) => { logEl().textContent += `\n=== ${p.label} ===\n`; });
on("job_done", (p) => {
  logEl().textContent += `[ok] ${p.label} concluído.\n`;
  logEl().scrollTop = logEl().scrollHeight;
});
// #9 Recuperação: erro amigável
on("job_error", (p) => {
  logEl().textContent += `[erro] ${p.label}: ${p.error}\n`;
  logEl().scrollTop = logEl().scrollHeight;
  if (p.job_id === currentChaptersJob) {
    document.getElementById("chapters-summary").textContent =
      "Falha ao carregar capítulos — verifique a conexão e tente novamente.";
    currentChaptersJob = null;
  }
});

// --- progresso ---
on("progress", (p) => {
  const pct = p.total ? Math.round((p.current / p.total) * 100) : 0;
  document.getElementById("progress-bar").style.width = pct + "%";
  document.getElementById("progress-text").textContent = `${p.label}: ${p.current}/${p.total} (${pct}%)`;
});

// --- busca ---
document.getElementById("btn-search").addEventListener("click", async () => {
  const q = document.getElementById("q").value.trim();
  const mt = document.getElementById("media-type").value;
  if (!q) return;
  document.getElementById("search-results").innerHTML = '<p class="muted">Buscando…</p>';
  await api().search(q, mt);
});
// #7 Eficiência: Enter no campo de busca dispara a busca
document.getElementById("q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("btn-search").click();
});
on("search_results", (p) => {
  const box = document.getElementById("search-results");
  if (!p.results.length) { box.innerHTML = '<p class="muted">Nenhum resultado.</p>'; return; }
  box.innerHTML = "";
  p.results.forEach((r) => {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<h3>${r.title || r.series_name || "Sem título"}</h3>
      <div style="margin:6px 0 12px"><span class="pill">${r.source || "?"} · ${r.format_type || r.format || "?"}</span></div>
      <button class="btn success" style="width:100%">Baixar série →</button>`;
    div.querySelector("button").addEventListener("click", () => openChapters(r.title || r.series_name, r.source || "mangadex", mtOf()));
    box.appendChild(div);
  });
});
function mtOf() { return document.getElementById("media-type").value; }
function goTo(view) {
  const navBtn = document.querySelector(`.nav-item[data-view="${view}"]`);
  if (navBtn) { navBtn.click(); return; }
  // Views sem item de navegação (ex.: seletor de capítulos, aberto a partir da busca)
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById("view-" + view).classList.add("active");
}

// --- seletor de capítulos ---
let chaptersState = { series: null, source: "mangadex", media: "manga", available: [], downloaded: [], byLang: {} };

function langPrimary() { return document.getElementById("lang-primary").value; }
function langFallback() { return document.getElementById("lang-fallback").value || null; }

async function openChapters(series, source, media) {
  chaptersState.series = series; chaptersState.source = source; chaptersState.media = media || "manga";
  document.getElementById("chapters-title").textContent = series;
  document.getElementById("chapters-summary").textContent = "Carregando capítulos…";
  document.getElementById("chapter-grid").innerHTML = "";
  goTo("chapters");
  await api().list_chapters(series, chaptersState.media, source, langPrimary(), langFallback())
    .then((ack) => { currentChaptersJob = ack && ack.job_id; });
}
on("chapters_list", (d) => {
  chaptersState.available = d.available || [];
  chaptersState.downloaded = d.downloaded || [];
  chaptersState.byLang = d.by_language || {};
  const nums = chaptersState.available;
  const missing = (d.missing || []).length;
  const min = nums.length ? Math.min(...nums) : 0;
  const max = nums.length ? Math.max(...nums) : 0;
  document.getElementById("chapters-summary").textContent = nums.length
    ? `Capítulos ${min}–${max} · ${nums.length} disponíveis · ${d.downloaded.length} baixados · faltam ${missing}`
    : "Nenhum capítulo encontrado neste idioma.";
  // Campos de intervalo passam a refletir o range REAL da série (não limita a nada).
  const from = document.getElementById("range-from"), to = document.getElementById("range-to");
  from.min = to.min = min; from.max = to.max = max;
  from.placeholder = String(min); to.placeholder = String(max);
  from.value = ""; to.value = "";
  renderQuickRanges(min, max);
  renderChapterGrid();
});

// Faixas rápidas geradas a partir da quantidade REAL de capítulos.
function renderQuickRanges(min, max) {
  const box = document.getElementById("quick-ranges");
  if (!box) return;
  box.innerHTML = "";
  if (!chaptersState.available.length) return;
  const lbl = document.createElement("span");
  lbl.className = "muted"; lbl.textContent = "Faixas rápidas:";
  box.appendChild(lbl);
  const BLOCK = 50;
  const lo = Math.floor(min), hi = Math.ceil(max);
  if (hi - lo + 1 <= BLOCK) {
    addRangeChip(box, lo, hi, `${min}–${max} (todos)`);
  } else {
    for (let start = lo; start <= hi; start += BLOCK) {
      const end = Math.min(start + BLOCK - 1, hi);
      addRangeChip(box, start, end, `${start}–${end}`);
    }
  }
}
function addRangeChip(box, from, to, text) {
  const chip = document.createElement("button");
  chip.className = "range-chip"; chip.textContent = text;
  chip.addEventListener("click", () => {
    document.querySelectorAll("#chapter-grid input:not([disabled])").forEach((el) => {
      const num = parseFloat(el.dataset.num);
      el.checked = num >= from && num <= to;
    });
    updateSelectedCount();
  });
  box.appendChild(chip);
}

function renderChapterGrid() {
  const grid = document.getElementById("chapter-grid");
  grid.innerHTML = "";
  const done = new Set(chaptersState.downloaded);
  chaptersState.available.forEach((num) => {
    const isDone = done.has(num);
    const langs = (chaptersState.byLang[num] || chaptersState.byLang[Number(num).toFixed(1)] || chaptersState.byLang[String(num)] || []).join(", ");
    const chip = document.createElement("label");
    chip.className = "chapter-chip" + (isDone ? " done" : "");
    chip.innerHTML = `<input type="checkbox" ${isDone ? "checked disabled" : ""} data-num="${num}"><span>Cap ${num}</span><span class="lang">${langs}</span>`;
    if (!isDone) chip.querySelector("input").addEventListener("change", updateSelectedCount);
    grid.appendChild(chip);
  });
  updateSelectedCount();
}

function selectedChapters() {
  return Array.from(document.querySelectorAll("#chapter-grid input:checked:not([disabled])"))
    .map((el) => parseFloat(el.dataset.num));
}
function updateSelectedCount() {
  const n = selectedChapters().length;
  const btn = document.getElementById("btn-download-selected");
  btn.textContent = `Baixar selecionados (${n})`;
  btn.disabled = n === 0;  // Nielsen #5: prevenção de erro
}

document.getElementById("btn-range-help").addEventListener("click", () => {
  alert(
    "Intervalo de capítulos\n\n" +
    'Marca automaticamente todos os capítulos de um número inicial ("de") até um final ("até").\n\n' +
    'Exemplo: de 1 até 50 seleciona os capítulos 1 a 50 — depois clique em "Baixar selecionados".\n\n' +
    'Você também pode marcar/desmarcar manualmente nas caixas abaixo, ou usar "Baixar tudo (faltantes)" ' +
    "para pegar todos os que ainda faltam."
  );
});
document.getElementById("btn-range-apply").addEventListener("click", () => {
  let from = parseFloat(document.getElementById("range-from").value);
  let to = parseFloat(document.getElementById("range-to").value);
  if (isNaN(from) || isNaN(to)) return;
  if (from > to) { const t = from; from = to; to = t; }  // corrige de>até
  document.querySelectorAll("#chapter-grid input:not([disabled])").forEach((el) => {
    const num = parseFloat(el.dataset.num);
    el.checked = num >= from && num <= to;
  });
  updateSelectedCount();
});

function startDownload(chapters) {
  api().enqueue(chaptersState.series, chapters, chaptersState.source, chaptersState.media,
                langPrimary(), langFallback());
  goTo("downloads");
  loadQueue();
}
document.getElementById("btn-download-all").addEventListener("click", () => startDownload(null));
document.getElementById("btn-download-selected").addEventListener("click", () => {
  const sel = selectedChapters();
  if (sel.length) startDownload(sel);
});
document.getElementById("btn-chapters-back").addEventListener("click", () => goTo("search"));

// --- fila de downloads ---
async function loadQueue() {
  const items = await api().queue_list();
  renderQueue(items || []);
}
on("queue_update", (p) => renderQueue((p && p.items) || []));

function renderQueue(items) {
  const box = document.getElementById("queue-list");
  if (!box) return;
  if (!items.some((i) => i.status === "downloading")) {
    document.getElementById("progress-text").textContent = "Sem download em andamento.";
    document.getElementById("progress-bar").style.width = "0%";
  }
  const counts = items.reduce((a, i) => { a[i.status] = (a[i.status] || 0) + 1; return a; }, {});
  const cEl = document.getElementById("queue-counts");
  if (cEl) cEl.textContent =
    `${counts.queued || 0} na fila · ${counts.downloading || 0} baixando · ${counts.done || 0} ok · ${counts.failed || 0} falhou`;
  box.innerHTML = "";
  if (!items.length) {
    box.innerHTML = '<div class="queue-empty">Fila vazia — busque uma série e escolha os capítulos para baixar.</div>';
    return;
  }
  items.forEach((i) => {
    const chap = i.chapter_number == null ? "série completa" : "capítulo " + i.chapter_number;
    const div = document.createElement("div");
    div.className = "queue-item";
    div.innerHTML = `<span class="queue-badge ${i.status}">${i.status}</span>
      <span class="title">${i.series} <small>· ${chap}</small></span>`;
    if (i.status === "failed") {
      const r = document.createElement("button");
      r.className = "btn sm"; r.textContent = "Re-tentar";
      r.addEventListener("click", () => api().retry_item(i.id).then(loadQueue));
      div.appendChild(r);
    }
    if (i.status === "queued" || i.status === "downloading") {
      const c = document.createElement("button");
      c.className = "btn sm warn"; c.textContent = "Cancelar";
      c.addEventListener("click", () => api().cancel_item(i.id).then(loadQueue));
      div.appendChild(c);
    }
    const rm = document.createElement("button");
    rm.className = "btn sm ghost"; rm.title = "Remover"; rm.textContent = "×";
    rm.addEventListener("click", () => api().remove_item(i.id).then(loadQueue));
    div.appendChild(rm);
    box.appendChild(div);
  });
}

let queuePaused = false;
document.getElementById("btn-queue-pause").addEventListener("click", async () => {
  queuePaused = !queuePaused;
  await (queuePaused ? api().pause_queue() : api().resume_queue());
  document.getElementById("btn-queue-pause").textContent = queuePaused ? "Retomar fila" : "Pausar fila";
  loadQueue();
});
document.getElementById("btn-queue-clear").addEventListener("click", () =>
  api().clear_finished().then(loadQueue));

// --- biblioteca ---
async function loadLibrary() {
  const box = document.getElementById("library-cards");
  box.innerHTML = '<p class="muted">Carregando…</p>';
  const data = await api().library();
  if (!data.length) { box.innerHTML = '<p class="muted">Biblioteca vazia.</p>'; return; }
  box.innerHTML = "";
  data.forEach((s) => {
    const pct = Math.round(s.completion_percentage || 0);
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `
      <img class="cover" src="${COVER_PLACEHOLDER}" alt="capa" />
      <h3>${s.title}</h3>
      <p class="muted">${s.is_complete ? '<span style="color:var(--success)">Completa</span>' : pct + "% concluído"}</p>
      <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
      <p class="muted">${s.chapters_downloaded}/${s.total_chapters_registered} caps</p>
      <div class="actions" style="margin-top:12px">
        <button class="btn sm">Status</button>
        <button class="btn sm success">Exportar</button>
      </div>`;
    const [statusBtn, exportBtn] = div.querySelectorAll("button");
    statusBtn.addEventListener("click", async () => {
      const st = await api().series_status(s.title);
      alert(`${st.title}\nConclusão: ${Math.round(st.completion_percentage)}%\n` +
            `Baixados: ${st.chapters_downloaded}/${st.total_chapters_registered}\n` +
            `Faltando: ${st.missing_chapters.join(", ") || "nada"}`);
    });
    exportBtn.addEventListener("click", async () => {
      const r = await api().export_komga(s.title);
      alert(`Exportado para:\n${r.base_path}\nArquivos: ${r.exported} (pulados: ${r.skipped})`);
    });
    // Enriquecimento assíncrono da capa (não bloqueia o render)
    api().enrich_metadata(s.title).then((meta) => {
      if (meta && meta.cover_image) div.querySelector(".cover").src = meta.cover_image;
    });
    box.appendChild(div);
  });
}

// --- dashboard ---
async function loadDashboard() {
  const box = document.getElementById("dash-cards");
  box.innerHTML = '<p class="muted">Carregando…</p>';
  const s = await api().dashboard_stats();
  box.innerHTML = "";
  const cards = [
    [ICON.book, "Séries", s.total_series], [ICON.download, "Itens baixados", s.total_downloaded],
    [ICON.check, "Coleções completas", s.complete_collections], [ICON.alert, "Itens faltantes", s.missing_total],
  ];
  cards.forEach(([ico, label, value]) => {
    const div = document.createElement("div");
    div.className = "card stat-card";
    div.innerHTML = `${ico}<div class="stat">${value}</div><p class="muted">${label}</p>`;
    box.appendChild(div);
  });
}

// --- ferramentas ---
// #5 Prevenção de erro: confirmar limpar cache
document.getElementById("btn-cache").addEventListener("click", async () => {
  if (!confirm("Limpar todo o cache local de buscas e capítulos?")) return;
  const r = await api().clear_cache();
  alert(`Cache removido: ${r.removed} arquivo(s)`);
});
document.getElementById("btn-graph").addEventListener("click", () => { api().graph_status(); goTo("downloads"); });

// --- pasta de downloads ---
async function loadDownloadDir() {
  try {
    const p = await api().get_download_dir();
    document.getElementById("download-dir").textContent = p || "—";
  } catch (_) {}
}
document.getElementById("btn-choose-dir").addEventListener("click", async () => {
  const r = await api().choose_download_dir();
  if (r && r.path) {
    document.getElementById("download-dir").textContent = r.path;
  }
});

// #6 Reconhecer em vez de lembrar: persistir idioma/fonte/tipo
function persistPrefs() {
  localStorage.setItem("mb_prefs", JSON.stringify({
    lang: langPrimary(), fb: document.getElementById("lang-fallback").value,
    media: document.getElementById("media-type").value,
  }));
}
function restorePrefs() {
  try {
    const p = JSON.parse(localStorage.getItem("mb_prefs") || "{}");
    if (p.lang) document.getElementById("lang-primary").value = p.lang;
    if (p.fb !== undefined) document.getElementById("lang-fallback").value = p.fb;
    if (p.media) document.getElementById("media-type").value = p.media;
  } catch (_) {}
}
["lang-primary", "lang-fallback", "media-type"].forEach((id) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("change", persistPrefs);
});

// --- init ---
window.addEventListener("pywebviewready", () => {
  document.getElementById("conn-state").textContent = "Pronto";
  restorePrefs();
  loadDashboard();
  loadQueue();
  loadDownloadDir();
});
