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

// --- download em andamento (para o botão Cancelar) ---
let currentDownloadJob = null;
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
  logEl().textContent += `✅ ${p.label} concluído.\n`;
  logEl().scrollTop = logEl().scrollHeight;
  if (p.job_id === currentDownloadJob) {
    const r = p.result || {};
    if (r.cancelled) {
      document.getElementById("progress-text").textContent = "Download cancelado.";
      document.getElementById("progress-bar").style.width = "0%";
    } else if (r.total !== undefined) {
      const failed = (r.failed_chapters || []).length;
      document.getElementById("progress-text").textContent =
        `Download concluído: ${r.downloaded}/${r.total}` + (failed ? ` · ${failed} não vieram: ${r.failed_chapters.join(", ")}` : "");
    }
    currentDownloadJob = null;
    if (cancelBtn()) cancelBtn().disabled = false;
  }
});
// #9 Recuperação: erro amigável
on("job_error", (p) => {
  logEl().textContent += `⚠️ ${p.label}: ${p.error}\n`;
  logEl().scrollTop = logEl().scrollHeight;
  if (p.job_id === currentDownloadJob) {
    document.getElementById("progress-text").textContent = "Falhou — tente novamente.";
    currentDownloadJob = null;
    if (cancelBtn()) cancelBtn().disabled = false;
  }
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
      <p class="muted">${r.source || "?"} · ${r.format_type || r.format || "?"}</p>
      <button class="btn success">Baixar série</button>`;
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
  const missing = (d.missing || []).length;
  document.getElementById("chapters-summary").textContent =
    `${d.available.length} caps · ${d.downloaded.length} baixados · faltam ${missing}`;
  renderChapterGrid();
});

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
  const counts = items.reduce((a, i) => { a[i.status] = (a[i.status] || 0) + 1; return a; }, {});
  const cEl = document.getElementById("queue-counts");
  if (cEl) cEl.textContent =
    `${counts.queued || 0} na fila · ${counts.downloading || 0} baixando · ${counts.done || 0} ok · ${counts.failed || 0} falhou`;
  box.innerHTML = "";
  items.forEach((i) => {
    const chap = i.chapter_number == null ? "série completa" : "cap " + i.chapter_number;
    const div = document.createElement("div");
    div.className = "queue-item";
    div.innerHTML = `<span class="queue-badge ${i.status}">${i.status}</span>
      <span class="title">${i.series} · ${chap}</span>`;
    if (i.status === "failed") {
      const r = document.createElement("button");
      r.className = "btn"; r.textContent = "Re-tentar";
      r.addEventListener("click", () => api().retry_item(i.id).then(loadQueue));
      div.appendChild(r);
    }
    if (i.status === "queued" || i.status === "downloading") {
      const c = document.createElement("button");
      c.className = "btn warn"; c.textContent = "Cancelar";
      c.addEventListener("click", () => api().cancel_item(i.id).then(loadQueue));
      div.appendChild(c);
    }
    const rm = document.createElement("button");
    rm.className = "btn"; rm.textContent = "×";
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
      <p class="muted">${s.is_complete ? "✅ Completa" : "⏳ " + pct + "%"}</p>
      <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
      <p class="muted">${s.chapters_downloaded}/${s.total_chapters_registered} caps</p>
      <div class="form-row" style="margin-top:10px">
        <button class="btn">Status</button>
        <button class="btn success">Exportar</button>
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
    ["Séries", s.total_series], ["Itens baixados", s.total_downloaded],
    ["Coleções completas", s.complete_collections], ["Itens faltantes", s.missing_total],
  ];
  cards.forEach(([label, value]) => {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<div class="stat">${value}</div><p class="muted">${label}</p>`;
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

// --- cancelar download (feedback imediato + reset em job_done) ---
const cancelBtn = () => document.getElementById("btn-cancel");
if (cancelBtn()) {
  cancelBtn().addEventListener("click", () => {
    if (!currentDownloadJob) return;
    api().cancel_job(currentDownloadJob);
    document.getElementById("progress-text").textContent = "Cancelando…";
    cancelBtn().disabled = true;  // feedback imediato
  });
}

// --- init ---
window.addEventListener("pywebviewready", () => {
  document.getElementById("conn-state").textContent = "Pronto";
  restorePrefs();
  loadDashboard();
  loadQueue();
});
