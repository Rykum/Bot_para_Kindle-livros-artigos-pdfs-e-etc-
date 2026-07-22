"use strict";

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

// --- navegação ---
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("view-" + btn.dataset.view).classList.add("active");
    if (btn.dataset.view === "library") loadLibrary();
    if (btn.dataset.view === "dashboard") loadDashboard();
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
on("job_error", (p) => { logEl().textContent += `❌ Erro: ${p.error}\n`; });

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
    div.querySelector("button").addEventListener("click", () => {
      api().download_series(r.title || r.series_name, mtOf(), r.source || "mangadex");
      goTo("downloads");
    });
    box.appendChild(div);
  });
});
function mtOf() { return document.getElementById("media-type").value; }
function goTo(view) { document.querySelector(`.nav-item[data-view="${view}"]`).click(); }

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
    div.innerHTML = `<h3>${s.title}</h3>
      <p class="muted">${s.is_complete ? "✅ Completa" : "⏳ " + pct + "%"}</p>
      <div class="progress"><div class="progress-bar" style="width:${pct}%"></div></div>
      <p class="muted">${s.chapters_downloaded}/${s.total_chapters_registered} caps</p>`;
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
document.getElementById("btn-cache").addEventListener("click", async () => {
  const r = await api().clear_cache();
  alert(`Cache removido: ${r.removed} arquivo(s)`);
});
document.getElementById("btn-graph").addEventListener("click", () => { api().graph_status(); goTo("downloads"); });

// --- init ---
window.addEventListener("pywebviewready", () => {
  document.getElementById("conn-state").textContent = "Pronto";
  loadDashboard();
});
