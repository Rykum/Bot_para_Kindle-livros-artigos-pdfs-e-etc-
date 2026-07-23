#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface gráfica do Media Bot PT-BR.
Mostra o fluxo de busca, download, status e cache em uma janela única.
"""

from __future__ import annotations

import contextlib
import io
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from media_bot import MediaBot


class MediaBotGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Media Bot PT-BR")
        self.root.geometry("1180x760")
        self.root.minsize(1040, 680)

        self.queue: queue.Queue = queue.Queue()
        self._build_style()
        self._build_layout()
        self._poll_queue()

    def _build_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        self.root.configure(bg="#0f172a")
        style.configure("TFrame", background="#0f172a")
        style.configure("Card.TFrame", background="#111827", relief="flat")
        style.configure("TLabel", background="#0f172a", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#0f172a", foreground="#f8fafc", font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background="#0f172a", foreground="#94a3b8", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#111827", foreground="#f8fafc", font=("Segoe UI", 11, "bold"))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)
        style.map(
            "TButton",
            background=[("active", "#2563eb")],
            foreground=[("disabled", "#94a3b8")],
        )
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff")
        style.configure("Success.TButton", background="#0f766e", foreground="#ffffff")
        style.configure("Warning.TButton", background="#92400e", foreground="#ffffff")
        style.configure("Danger.TButton", background="#7f1d1d", foreground="#ffffff")
        style.configure("Treeview", background="#111827", foreground="#e5e7eb", fieldbackground="#111827", rowheight=28, bordercolor="#1f2937")
        style.configure("Treeview.Heading", background="#1f2937", foreground="#f8fafc", font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="Media Bot PT-BR", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Busca, download, status e cache em uma interface demonstrativa com log em tempo real.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        metrics = ttk.Frame(outer, style="Card.TFrame", padding=12)
        metrics.pack(fill="x", pady=(12, 12))
        ttk.Label(metrics, text="Resumo", style="Section.TLabel").pack(anchor="w")
        metrics_row = ttk.Frame(metrics, style="Card.TFrame")
        metrics_row.pack(fill="x", pady=(10, 0))
        self.metric_vars = {
            "series": tk.StringVar(value="Séries: -"),
            "cache": tk.StringVar(value="Cache: -"),
            "graph": tk.StringVar(value="Grafo: -"),
            "status": tk.StringVar(value="Estado: pronto"),
        }
        for index, key in enumerate(["series", "cache", "graph", "status"]):
            card = ttk.Frame(metrics_row, style="Card.TFrame", padding=12)
            card.grid(row=0, column=index, padx=6, sticky="ew")
            ttk.Label(
                card,
                textvariable=self.metric_vars[key],
                background="#111827",
                foreground="#e5e7eb",
                font=("Segoe UI", 11, "bold"),
            ).pack(anchor="w")
            metrics_row.columnconfigure(index, weight=1)

        self._refresh_metrics_async()

        pipeline = ttk.Frame(outer, style="Card.TFrame", padding=12)
        pipeline.pack(fill="x", pady=(0, 12))
        ttk.Label(pipeline, text="Processo", style="Section.TLabel").pack(anchor="w")
        self.pipeline_labels = {}
        pipeline_row = ttk.Frame(pipeline, style="Card.TFrame")
        pipeline_row.pack(fill="x", pady=(10, 0))
        for index, stage in enumerate(["Busca", "Filtro", "DB Check", "Download", "Register"]):
            badge = ttk.Label(pipeline_row, text=f"{index + 1}. {stage}", padding=(12, 8))
            badge.grid(row=0, column=index, padx=6, sticky="ew")
            self.pipeline_labels[stage] = badge
            pipeline_row.columnconfigure(index, weight=1)
        self._set_pipeline_stage("Busca")

        main = ttk.Frame(outer)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main, style="Card.TFrame", padding=12)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        left.configure(width=360)

        ttk.Label(left, text="Controles", style="Section.TLabel").pack(anchor="w")

        form = ttk.Frame(left, style="Card.TFrame")
        form.pack(fill="x", pady=(10, 12))

        ttk.Label(form, text="Consulta / Série").grid(row=0, column=0, sticky="w")
        self.query_var = tk.StringVar(value="Dandadan")
        ttk.Entry(form, textvariable=self.query_var, width=34).grid(row=1, column=0, sticky="ew", pady=(2, 8))

        ttk.Label(form, text="Tipo de mídia").grid(row=2, column=0, sticky="w")
        self.media_type_var = tk.StringVar(value="manga")
        ttk.Combobox(
            form,
            textvariable=self.media_type_var,
            values=["manga", "livro", "hq", "manhwa", "artigo"],
            state="readonly",
        ).grid(row=3, column=0, sticky="ew", pady=(2, 8))

        ttk.Label(form, text="Fonte").grid(row=4, column=0, sticky="w")
        self.source_var = tk.StringVar(value="mangadex")
        ttk.Combobox(
            form,
            textvariable=self.source_var,
            values=["mangadex", "archive", "gutenberg"],
            state="readonly",
        ).grid(row=5, column=0, sticky="ew", pady=(2, 8))

        form.columnconfigure(0, weight=1)

        buttons = ttk.Frame(left, style="Card.TFrame")
        buttons.pack(fill="x", pady=(0, 10))
        ttk.Button(buttons, text="Buscar", style="Accent.TButton", command=self.search).pack(fill="x", pady=4)
        ttk.Button(buttons, text="Baixar série completa", style="Success.TButton", command=self.download).pack(fill="x", pady=4)
        ttk.Button(buttons, text="Ver status", command=self.status).pack(fill="x", pady=4)
        ttk.Button(buttons, text="Biblioteca", command=self.library).pack(fill="x", pady=4)
        ttk.Button(buttons, text="Limpar cache", style="Warning.TButton", command=self.clear_cache).pack(fill="x", pady=4)
        ttk.Button(buttons, text="Status do grafo", command=self.graph_status).pack(fill="x", pady=4)

        ttk.Separator(left).pack(fill="x", pady=12)
        ttk.Label(left, text="Resultado do processo", style="Section.TLabel").pack(anchor="w")
        self.summary_var = tk.StringVar(value="Pronto para iniciar.")
        ttk.Label(left, textvariable=self.summary_var, wraplength=320, background="#111827", foreground="#cbd5e1").pack(fill="x", pady=(8, 0))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value="Progresso: 0/0")
        ttk.Progressbar(left, variable=self.progress_var, maximum=100).pack(fill="x", pady=(10, 4))
        ttk.Label(left, textvariable=self.progress_text_var, background="#111827", foreground="#94a3b8").pack(anchor="w")

        right = ttk.Frame(main, style="Card.TFrame", padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        top_right = ttk.Frame(right, style="Card.TFrame")
        top_right.grid(row=0, column=0, sticky="ew")
        top_right.columnconfigure(0, weight=1)
        top_right.columnconfigure(1, weight=1)

        ttk.Label(top_right, text="Resultados", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top_right, text="Log em tempo real", style="Section.TLabel").grid(row=0, column=1, sticky="w")

        result_frame = ttk.Frame(right, style="Card.TFrame")
        result_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(result_frame, columns=("source", "format", "url"), show="headings", height=10)
        self.tree.heading("source", text="Fonte")
        self.tree.heading("format", text="Formato")
        self.tree.heading("url", text="URL / Download")
        self.tree.column("source", width=120, anchor="w")
        self.tree.column("format", width=100, anchor="w")
        self.tree.column("url", width=520, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        log_frame = ttk.Frame(right, style="Card.TFrame")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        ttk.Label(log_frame, text="Processo", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.log_text = tk.Text(
            log_frame,
            height=14,
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.grid(row=1, column=1, sticky="ns")

        self._log("Interface carregada. Use a busca para iniciar o fluxo.")

    def _set_pipeline_stage(self, active_stage: str) -> None:
        for stage, label in self.pipeline_labels.items():
            if stage == active_stage:
                label.configure(background="#1d4ed8", foreground="#ffffff")
            else:
                label.configure(background="#1f2937", foreground="#cbd5e1")

    def _refresh_metrics_async(self) -> None:
        def worker():
            self.queue.put(("metrics", "Resumo", self._collect_metrics(), ""))

        threading.Thread(target=worker, daemon=True).start()

    def _collect_metrics(self) -> dict:
        metrics = {
            "series": "Séries: -",
            "cache": "Cache: -",
            "graph": "Grafo: -",
            "status": "Estado: pronto",
        }

        bot = None
        try:
            bot = MediaBot()
            metrics["series"] = f"Séries: {len(bot.library.list_all_series())}"

            cache_dir = Path(bot.cache.cache_dir)
            cache_count = len(list(cache_dir.glob("*.json"))) if cache_dir.exists() else 0
            metrics["cache"] = f"Cache: {cache_count} arquivo(s)"

            graph_path = Path(__file__).parent / "graphify-out" / "graph.json"
            if graph_path.exists():
                graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
                metrics["graph"] = f"Grafo: {len(graph_data.get('nodes', []))} nós / {len(graph_data.get('edges', []))} arestas"
            else:
                metrics["graph"] = "Grafo: indisponível"

            metrics["status"] = "Estado: pronto"
            return metrics
        except Exception as exc:
            metrics["status"] = f"Estado: erro ({exc})"
            return metrics
        finally:
            if bot is not None:
                bot.cleanup()

    def _log(self, message: str) -> None:
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for child in self.root.winfo_children():
            self._set_widget_state(child, state)
        self.root.config(cursor="watch" if busy else "")

    def _set_widget_state(self, widget, state: str) -> None:
        try:
            if isinstance(widget, ttk.Button):
                widget.configure(state=state)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._set_widget_state(child, state)

    def _run_worker(self, title: str, worker_fn):
        self._set_busy(True)
        self.summary_var.set(f"Executando: {title}")
        self._log(f"\n=== {title} ===")

        def worker():
            buffer = io.StringIO()
            try:
                with contextlib.redirect_stdout(buffer):
                    result = worker_fn()
                self.queue.put(("result", title, result, buffer.getvalue()))
            except Exception as exc:
                self.queue.put(("error", title, exc, buffer.getvalue()))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                title = item[1]
                payload = item[2]
                captured = item[3]

                if captured:
                    self._log(captured)

                if kind == "result":
                    self._on_worker_result(title, payload)
                elif kind == "progress":
                    self._on_progress_update(payload)
                elif kind == "metrics":
                    self._on_metrics_update(payload)
                else:
                    self._on_worker_error(title, payload)
        except queue.Empty:
            pass
        finally:
            self.root.after(120, self._poll_queue)

    def _on_worker_result(self, title: str, result) -> None:
        self._set_busy(False)
        self.summary_var.set(f"Concluído: {title}")
        self._log(f"[{title}] concluído com sucesso.")
        self._refresh_metrics_async()

        if isinstance(result, list):
            self._populate_results(result)
        elif isinstance(result, int):
            self._log(f"Resultado: {result}")
        elif result is not None:
            self._log(str(result))

    def _on_worker_error(self, title: str, error: Exception) -> None:
        self._set_busy(False)
        self.summary_var.set(f"Falha em: {title}")
        self._log(f"Erro em {title}: {error}")
        messagebox.showerror("Erro", f"Falha em {title}: {error}")
        self._refresh_metrics_async()

    def _on_metrics_update(self, metrics: dict) -> None:
        for key, value in metrics.items():
            if key in self.metric_vars:
                self.metric_vars[key].set(value)

    def _populate_results(self, results) -> None:
        self.tree.delete(*self.tree.get_children())
        for result in results:
            title = result.get("title") or result.get("series_name") or "Sem título"
            source = result.get("source", "unknown")
            format_type = result.get("format_type") or result.get("format") or "unknown"
            url = result.get("download_url") or result.get("url") or "-"
            self.tree.insert("", "end", values=(source, format_type, url), text=title)
        self._log(f"{len(results)} resultado(s) exibido(s) na tabela.")

    def _on_progress_update(self, payload) -> None:
        label, current, total = payload
        if total:
            percentage = max(0, min(100, (current / total) * 100))
            self.progress_var.set(percentage)
            self.progress_text_var.set(f"{label}: {current}/{total} ({percentage:.0f}%)")
        else:
            self.progress_text_var.set(f"{label}: {current}")

        self._set_pipeline_stage("Download")
        self._log(f"Progresso - {label}: {current}/{total}")

    def search(self):
        query = self.query_var.get().strip()
        if not query:
            messagebox.showwarning("Entrada inválida", "Informe um título para busca.")
            return

        self._set_pipeline_stage("Busca")
        self._run_worker(f"Busca: {query}", lambda: self._search_task(query))

    def _search_task(self, query: str):
        bot = MediaBot()
        try:
            return bot.search_series(query, media_type=self.media_type_var.get())
        finally:
            bot.cleanup()

    def download(self):
        series = self.query_var.get().strip()
        if not series:
            messagebox.showwarning("Entrada inválida", "Informe o nome da série para download.")
            return

        self._set_pipeline_stage("Download")
        source = self.source_var.get().strip() or "mangadex"
        media_type = self.media_type_var.get().strip() or "manga"
        self._run_worker(f"Download: {series}", lambda: self._download_task(series, media_type, source))

    def _download_task(self, series: str, media_type: str, source: str):
        bot = MediaBot()
        try:
            return bot.download_complete_series(
                series,
                media_type=media_type,
                source_name=source,
                progress_callback=self._emit_progress,
            )
        finally:
            bot.cleanup()

    def _emit_progress(self, label: str, current: int, total: int) -> None:
        self.queue.put(("progress", "progress", (label, current, total), ""))

    def status(self):
        series = self.query_var.get().strip()
        if not series:
            messagebox.showwarning("Entrada inválida", "Informe o nome da série para ver o status.")
            return

        self._set_pipeline_stage("DB Check")
        self._run_worker(f"Status: {series}", lambda: self._status_task(series))

    def _status_task(self, series: str):
        bot = MediaBot()
        try:
            return bot.check_collection_status(series)
        finally:
            bot.cleanup()

    def library(self):
        self._set_pipeline_stage("Register")
        self._run_worker("Biblioteca", self._library_task)

    def _library_task(self):
        bot = MediaBot()
        try:
            return bot.list_library()
        finally:
            bot.cleanup()

    def clear_cache(self):
        self._set_pipeline_stage("Filtro")
        self._run_worker("Limpar cache", self._clear_cache_task)

    def _clear_cache_task(self):
        bot = MediaBot()
        try:
            return bot.clear_cache()
        finally:
            bot.cleanup()

    def graph_status(self):
        self._set_pipeline_stage("DB Check")
        self._run_worker("Status do grafo", self._graph_status_task)

    def _graph_status_task(self):
        bot = MediaBot()
        try:
            return bot.print_graph_status()
        finally:
            bot.cleanup()


def main() -> None:
    root = tk.Tk()
    MediaBotGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()