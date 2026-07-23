#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo 4: Media Bot Principal (Refatorado)
Integra Scrapers, Database, Normalizer e DownloadManager em um fluxo coeso.
Substitui todos os mockups por implementação real.

Fluxo: Search -> Filter -> DB Check -> Download -> Register
"""

import os
import re
import time
import argparse
import json
from collections.abc import Mapping
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import urlparse
from sqlalchemy.exc import IntegrityError

# Imports dos módulos reais
from scrapers.mangadex_scraper import MangaDexScraper
from scrapers.archive_scraper import ArchiveOrgScraper
from scrapers.gutenberg_scraper import ProjectGutenbergScraper
from download_manager import DownloadManager
from database import db_manager, Series, MediaFile
from library_manager import LibraryManager
from normalizer import ContentNormalizer
from cache_manager import CacheManager


class MediaBot:
    """
    Bot principal para pesquisa e download de mídias em PT-BR.
    """

    def __init__(self, base_download_dir: str = "./downloads"):
        self.base_dir = Path(base_download_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Inicializa componentes
        self.library = LibraryManager()
        self.downloader = DownloadManager(str(self.base_dir))
        self.cache = CacheManager()
        self.normalizer = ContentNormalizer()
        
        # Inicializa scrapers disponíveis
        self.scrapers = [
            MangaDexScraper(),
            ArchiveOrgScraper(),
            ProjectGutenbergScraper()
        ]
        
        print(f"✅ Media Bot inicializado. Downloads em: {self.base_dir.absolute()}")

    def _serialize_result(self, result: Any) -> Dict[str, Any]:
        if is_dataclass(result):
            return asdict(result)
        if isinstance(result, dict):
            return result
        if isinstance(result, Mapping):
            return dict(result)
        return {'value': str(result)}

    def _resolve_scraper(self, source_name: str):
        normalized = source_name.strip().lower()
        for scraper in self.scrapers:
            candidate_names = {
                scraper.name.lower(),
                scraper.__class__.__name__.lower(),
                scraper.base_url.lower(),
            }
            if any(normalized == candidate or normalized in candidate for candidate in candidate_names):
                return scraper
        return None

    def _formats_for_media_type(self, media_type: str) -> Optional[List[str]]:
        media_type = (media_type or "").strip().lower()
        mapping = {
            'manga': ['cbz', 'cbr'],
            'manhwa': ['cbz', 'cbr'],
            'hq': ['cbz', 'cbr'],
            'comic': ['cbz', 'cbr'],
            'livro': ['pdf', 'epub'],
            'book': ['pdf', 'epub'],
            'artigo': ['pdf'],
            'article': ['pdf'],
        }
        return mapping.get(media_type)

    def _scraper_applicable(self, scraper, media_type: str) -> bool:
        media_type = (media_type or "").strip().lower()
        scraper_name = scraper.name.lower()

        if media_type in {"manga", "manhwa", "hq", "comic"}:
            return scraper_name in {"mangadex", "archive.org"}

        if media_type in {"livro", "book", "artigo", "article"}:
            return scraper_name in {"archive.org", "project gutenberg"}

        return True

    def _resolve_series_reference(self, scraper, series_title: str, media_type: str) -> str:
        """Resolve o título digitado para a URL/identificador real da fonte."""
        candidate = series_title.strip()
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate

        search_results = scraper.search(series_title, formats=self._formats_for_media_type(media_type))
        if search_results:
            return search_results[0].url

        return candidate

    def _sanitize_filename(self, value: str) -> str:
        return re.sub(r'[<>:\"/\\|?*]+', '_', value).strip().strip('.')

    def _format_chapter_label(self, chapter_number: float) -> str:
        try:
            if float(chapter_number).is_integer():
                return f"{int(chapter_number):04d}"
            return str(chapter_number).replace('.', '_')
        except (TypeError, ValueError):
            return str(chapter_number).replace('.', '_')

    def _download_mangadex_chapter(self, scraper: MangaDexScraper, chapter_data: Dict[str, Any],
                                   series_title: str, chapter_num: float,
                                   progress_callback: Optional[Any] = None,
                                   should_cancel: Optional[Any] = None) -> Dict[str, Any]:
        page_urls = chapter_data.get('page_urls') or []
        if not page_urls:
            return {
                'success': False,
                'error': 'MangaDex chapter has no page URLs',
            }

        chapter_label = self._format_chapter_label(chapter_num)
        filename = f"{self._sanitize_filename(series_title)}_cap_{chapter_label}.cbz"
        output_path = self.base_dir / filename

        try:
            with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for index, page_url in enumerate(page_urls, 1):
                    if should_cancel is not None and should_cancel():
                        raise RuntimeError("cancelled")
                    content = scraper.fetch_page(page_url, should_cancel=should_cancel)
                    suffix = Path(urlparse(page_url).path).suffix or '.jpg'
                    archive.writestr(f"{index:03d}{suffix}", content)

                    if progress_callback:
                        progress_callback(f"{series_title} cap. {chapter_label}", index, len(page_urls))

            file_hash = self.downloader.calculate_hash(str(output_path))
            file_size = output_path.stat().st_size
            return {
                'success': True,
                'filepath': str(output_path),
                'file_path': str(output_path),
                'size': file_size,
                'hash': file_hash,
                'error': None,
                'retries': 0,
                'resumed': False,
                'metadata': {
                    'format': 'cbz',
                    'size': file_size,
                    'sha256': file_hash,
                }
            }
        except Exception as exc:
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            cancelled = str(exc) == "cancelled"
            return {
                'success': False,
                'error': str(exc),
                'cancelled': cancelled,
            }

    def search_series(self, query: str, media_type: str = "manga") -> List[Dict[str, Any]]:
        """
        Busca série em todos os scrapers disponíveis.
        Retorna lista unificada de resultados.
        """
        print(f"\n🔍 Buscando por: '{query}' ({media_type})...")
        cache_key = f"search::{query.strip().lower()}::{media_type.strip().lower()}"
        cached_results = self.cache.get(cache_key, max_age_seconds=24 * 3600)
        if cached_results is not None:
            print("   💾 Resultado recuperado do cache.")
            return cached_results

        all_results = []
        formats = self._formats_for_media_type(media_type)
        
        for scraper in self.scrapers:
            if not self._scraper_applicable(scraper, media_type):
                continue

            try:
                results = scraper.search(query, formats=formats)
                if results:
                    print(f"   📚 {scraper.name}: {len(results)} resultado(s)")
                    all_results.extend(self._serialize_result(result) for result in results)
            except Exception as e:
                print(f"   ⚠️ Erro no scraper {scraper.name}: {e}")
        
        if not all_results:
            print("   ❌ Nenhum resultado encontrado.")

        self.cache.set(cache_key, all_results)
        
        return all_results

    def get_complete_series_chapters(self, series_title: str, source_name: str = "mangadex", media_type: str = "manga",
                                     language: str = "pt-br") -> List[float]:
        """
        Consulta a API para obter TODOS os capítulos disponíveis de uma série.
        Retorna lista ordenada de números de capítulos.
        """
        print(f"\n📋 Verificando capítulos disponíveis para '{series_title}'...")
        cache_key = f"chapters::{series_title.strip().lower()}::{source_name.strip().lower()}::{language}"
        cached_chapters = self.cache.get(cache_key, max_age_seconds=6 * 3600)
        if cached_chapters is not None:
            print("   💾 Capítulos recuperados do cache.")
            return cached_chapters

        # Seleciona scraper apropriado
        scraper = self._resolve_scraper(source_name)
        if not scraper:
            print(f"   ⚠️ Scraper '{source_name}' não encontrado.")
            return []

        series_reference = self._resolve_series_reference(scraper, series_title, media_type)

        # Busca metadados da série completa
        try:
            chapters = scraper.get_all_chapters(series_reference, language=language)
            chapter_numbers = sorted(set(chapters))
            if chapter_numbers:
                print(f"   ✅ Encontrados {len(chapter_numbers)} capítulos disponíveis (do {min(chapter_numbers)} ao {max(chapter_numbers)})")
            else:
                print("   ⚠️ Nenhum capítulo foi resolvido para esta fonte.")

            self.cache.set(cache_key, chapter_numbers)
            return chapter_numbers
        except Exception as e:
            print(f"   ❌ Erro ao buscar capítulos: {e}")
            return []

    def _attempt_chapter(self, scraper, series, series_reference: str, series_title: str,
                         chapter_num: float, source_name: str, language: str,
                         progress_callback: Optional[Any], should_cancel: Optional[Any]) -> str:
        """Tenta baixar e registrar um único capítulo.

        Retorna um status: "ok" (sucesso), "fail" (falha genuína, pode ser
        re-tentada) ou "cancelled" (interrompido pelo usuário - não deve
        contar como falha nem ser re-tentado).
        """
        chapter_label = self._format_chapter_label(chapter_num)
        print(f"\n   ⬇️  Baixando Capítulo {chapter_label} ({language})...")

        try:
            # Busca URL específica deste capítulo
            chapter_data = scraper.get_chapter_url(series_reference, chapter_num, language=language)

            if not chapter_data or 'download_url' not in chapter_data:
                if chapter_data and chapter_data.get('download_type') == 'mangadex_cbz':
                    result = self._download_mangadex_chapter(
                        scraper,
                        chapter_data,
                        series_title,
                        chapter_num,
                        progress_callback=progress_callback,
                        should_cancel=should_cancel,
                    )
                else:
                    print(f"      ⚠️ URL não encontrada para cap. {chapter_label}")
                    return "fail"
            else:
                # Executa download real
                result = self.downloader.download(
                    url=chapter_data['download_url'],
                    filename=f"{self._sanitize_filename(series_title)}_cap_{chapter_label}.{chapter_data.get('format', 'cbz')}",
                    metadata={
                        'series': series_title,
                        'chapter': chapter_num,
                        'source': source_name
                    }
                )

            if result['success']:
                metadata = result.get('metadata', {})
                try:
                    # Registra no DB
                    chap_record = self.library.add_chapter(
                        series=series,
                        volume_num=chapter_data.get('volume', 1),
                        chapter_num=chapter_num,
                        title=chapter_data.get('title', f"Capítulo {chapter_label}")
                    )

                    self.library.register_download(
                        chapter=chap_record,
                        file_path=result.get('file_path') or result.get('filepath'),
                        file_format=metadata.get('format', 'unknown'),
                        file_size=metadata.get('size', 0),
                        sha256_hash=metadata.get('sha256', '')
                    )
                except IntegrityError:
                    # O commit falhou (ex.: sha256_hash duplicado). Só tratamos
                    # como sucesso idempotente se o conteúdo já estiver
                    # genuinamente registrado como concluído no banco - caso
                    # contrário é uma falha real (ex.: conflito espúrio) e deve
                    # ser re-tentada.
                    self.library.session.rollback()
                    existing = self.library.session.query(MediaFile).filter(
                        MediaFile.sha256_hash == metadata.get('sha256', ''),
                        MediaFile.download_status == 'completed'
                    ).first()
                    if existing:
                        print(f"      ♻️  Conteúdo já registrado (hash duplicado); considerado concluído.")
                        return "ok"
                    print(f"      ❌ Falha ao registrar capítulo (conflito de integridade no banco).")
                    return "fail"

                print(f"      ✅ Sucesso! ({metadata.get('size', 0) / 1024 / 1024:.2f} MB)")
                return "ok"
            else:
                print(f"      ❌ Falha no download: {result.get('error', 'Erro desconhecido')}")
                if result.get('cancelled'):
                    return "cancelled"
                return "fail"

        except Exception as e:
            print(f"      ❌ Erro inesperado: {e}")
            try:
                # Garante que a sessão volte a um estado utilizável após uma
                # falha de commit (ex.: IntegrityError), para não travar
                # as rodadas de re-tentativa seguintes.
                self.library.session.rollback()
            except Exception:
                pass
            return "fail"

    def download_complete_series(self, series_title: str, media_type: str = "manga",
                                 source_name: str = "mangadex", skip_existing: bool = True,
                                 progress_callback: Optional[Any] = None,
                                 should_cancel: Optional[Any] = None,
                                 chapters: Optional[List[float]] = None,
                                 language: str = "pt-br", fallback_language: Optional[str] = None):
        """
        FLUXO PRINCIPAL: Baixa série completa do capítulo 1 ao último.
        1. Busca série
        2. Registra no DB
        3. Lista capítulos disponíveis online
        4. Identifica faltantes locais
        5. Baixa apenas faltantes (com re-tentativas e fallback de idioma)
        6. Atualiza DB
        """
        print(f"\n{'='*60}")
        print(f"🚀 INICIANDO DOWNLOAD DA SÉRIE: {series_title}")
        print(f"{'='*60}")

        # Passo 1: Registrar/Obter série no DB
        series = self.library.get_or_create_series(series_title, source_name)

        scraper = self._resolve_scraper(source_name)
        if not scraper:
            print(f"   ❌ Scraper '{source_name}' não encontrado.")
            return {
                'total': 0,
                'downloaded': 0,
                'failed': 0,
                'cancelled': False,
                'failed_chapters': [],
            }

        # Passo 2: Obter todos os capítulos disponíveis na fonte (idioma primário)
        series_reference = self._resolve_series_reference(scraper, series_title, media_type)
        available_chapters = self.get_complete_series_chapters(series_reference, source_name, media_type,
                                                                language=language)

        if not available_chapters:
            print("   ❌ Nenhum capítulo disponível para download.")
            return {
                'total': 0,
                'downloaded': 0,
                'failed': 0,
                'cancelled': False,
                'failed_chapters': [],
            }

        # Passo 3: Identificar o que já temos baixado / o que foi selecionado
        if chapters:
            requested = sorted(set(float(c) for c in chapters) & set(available_chapters))
            missing_chapters = self.library.find_missing_chapters(series, requested) if skip_existing else requested
        else:
            missing_chapters = self.library.find_missing_chapters(series, available_chapters)

        if not missing_chapters:
            print(f"   🎉 Série completa! Todos os {len(available_chapters)} capítulos já estão baixados.")
            return {
                'total': 0,
                'downloaded': 0,
                'failed': 0,
                'cancelled': False,
                'failed_chapters': [],
            }

        print(f"   📥 Faltam baixar {len(missing_chapters)} de {len(available_chapters)} capítulos.")
        previous_progress_callback = self.downloader.progress_callback
        self.downloader.progress_callback = progress_callback
        try:
            # Passo 4: Baixar capítulos faltantes, com até 3 rodadas (1 principal + 2 re-tentativas)
            downloaded_count = 0
            cancelled = False

            pending = list(missing_chapters)
            for round_index in range(3):  # 1 principal + 2 re-tentativas
                still_failed = []
                for chapter_num in pending:
                    if should_cancel is not None and should_cancel():
                        print("   ⏹️  Download cancelado pelo usuário.")
                        cancelled = True
                        break
                    status = self._attempt_chapter(scraper, series, series_reference, series_title,
                                                   chapter_num, source_name, language,
                                                   progress_callback, should_cancel)
                    if status == "ok":
                        downloaded_count += 1
                    elif status == "cancelled":
                        print("   ⏹️  Download cancelado pelo usuário.")
                        cancelled = True
                        break
                    else:
                        still_failed.append(chapter_num)
                    # Pausa curta e cancel-responsiva entre capítulos (evita 429s).
                    for _ in range(5):
                        if should_cancel is not None and should_cancel():
                            break
                        time.sleep(0.2)
                if cancelled or not still_failed:
                    pending = still_failed
                    break
                print(f"   🔁 Re-tentando {len(still_failed)} capítulo(s) (rodada {round_index + 2})...")
                pending = still_failed

            # Fallback de idioma, por capítulo, só após esgotar o primário
            if pending and fallback_language and not cancelled:
                print(f"   🌐 Tentando fallback de idioma ({fallback_language}) em {len(pending)} capítulo(s)...")
                still_failed = []
                for chapter_num in pending:
                    if should_cancel is not None and should_cancel():
                        print("   ⏹️  Download cancelado pelo usuário.")
                        cancelled = True
                        break
                    status = self._attempt_chapter(scraper, series, series_reference, series_title,
                                                   chapter_num, source_name, fallback_language,
                                                   progress_callback, should_cancel)
                    if status == "ok":
                        downloaded_count += 1
                    elif status == "cancelled":
                        print("   ⏹️  Download cancelado pelo usuário.")
                        cancelled = True
                        break
                    else:
                        still_failed.append(chapter_num)
                pending = still_failed

            failed_chapters = pending
            failed_count = len(failed_chapters)

            # Resumo final
            print(f"\n{'='*60}")
            print(f"📊 RESUMO DO DOWNLOAD")
            print(f"{'='*60}")
            print(f"   Total faltante: {len(missing_chapters)}")
            print(f"   Baixados com sucesso: {downloaded_count}")
            print(f"   Falhas: {failed_count}")

            # Mostra progresso atualizado
            progress = self.library.get_series_progress(series)
            print(f"   Progresso total: {progress['completion_percentage']:.1f}%")

            if progress['is_complete']:
                print(f"\n🎉 PARABÉNS! Série '{series_title}' COMPLETA!")

            return {
                'total': len(missing_chapters),
                'downloaded': downloaded_count,
                'failed': failed_count,
                'cancelled': cancelled,
                'failed_chapters': failed_chapters,
            }
        finally:
            self.downloader.progress_callback = previous_progress_callback

    def list_series_chapters(self, series_title: str, media_type: str = "manga", source_name: str = "mangadex",
                             language: str = "pt-br", fallback_language: Optional[str] = None) -> Dict[str, Any]:
        """Lista capítulos disponíveis (idioma primário + fallback opcional) vs. baixados localmente."""
        series = self.library.get_or_create_series(series_title, source_name)
        primary = self.get_complete_series_chapters(series_title, source_name, media_type, language=language)
        by_language = {c: [language] for c in primary}
        available = set(primary)
        if fallback_language:
            try:
                scraper = self._resolve_scraper(source_name)
                ref = self._resolve_series_reference(scraper, series_title, media_type)
                fb = sorted(set(scraper.get_all_chapters(ref, language=fallback_language)))
            except Exception:
                fb = []
            for c in fb:
                available.add(c)
                by_language.setdefault(c, [])
                if fallback_language not in by_language[c]:
                    by_language[c].append(fallback_language)
        available = sorted(available)
        missing_online = self.library.find_missing_chapters(series, available)
        downloaded = sorted(set(available) - set(missing_online))
        missing = sorted(set(available) - set(downloaded))
        return {'title': series.title, 'source': source_name, 'available': available,
                'downloaded': downloaded, 'missing': missing, 'by_language': by_language}

    def check_collection_status(self, series_title: str):
        """Exibe status detalhado de uma coleção."""
        series = self.library.get_or_create_series(series_title)
        progress = self.library.get_series_progress(series)
        
        print(f"\n{'='*60}")
        print(f"📚 STATUS: {progress['title']}")
        print(f"{'='*60}")
        print(f"   Status: {progress['status']}")
        print(f"   Volumes registrados: {progress['total_volumes_registered']}")
        print(f"   Capítulos registrados: {progress['total_chapters_registered']}")
        print(f"   Capítulos baixados: {progress['chapters_downloaded']}")
        print(f"   Conclusão: {progress['completion_percentage']:.1f}%")
        
        if progress['missing_chapters']:
            print(f"   Faltando: {progress['missing_chapters']}")
        else:
            print(f"   ✅ Coleção completa!")

    def list_library(self):
        """Lista todas as séries na biblioteca local."""
        series_list = self.library.list_all_series()
        
        if not series_list:
            print("\n📭 Biblioteca vazia. Nenhuma série baixada ainda.")
            return
        
        print(f"\n{'='*60}")
        print(f"📚 MINHA BIBLIOTECA ({len(series_list)} série(s))")
        print(f"{'='*60}")
        
        for series in series_list:
            progress = self.library.get_series_progress(series)
            status_icon = "✅" if progress['is_complete'] else "⏳"
            print(f"   {status_icon} {series.title}")
            print(f"      └─ {progress['completion_percentage']:.1f}% completo ({progress['chapters_downloaded']}/{progress['total_chapters_registered']} caps)")

    def get_library_data(self) -> List[Dict[str, Any]]:
        """Retorna dados estruturados de todas as séries (para a UI)."""
        data = []
        for series in self.library.list_all_series():
            progress = self.library.get_series_progress(series)
            data.append({
                'title': progress['title'],
                'status': progress['status'],
                'completion_percentage': progress['completion_percentage'],
                'chapters_downloaded': progress['chapters_downloaded'],
                'total_chapters_registered': progress['total_chapters_registered'],
                'is_complete': progress['is_complete'],
                'source_name': series.source_name,
            })
        return data

    def get_series_status_data(self, series_title: str) -> Dict[str, Any]:
        """Retorna o progresso de uma coleção como dict (para a UI)."""
        series = self.library.get_or_create_series(series_title)
        return self.library.get_series_progress(series)

    def dashboard_stats(self) -> Dict[str, Any]:
        """Agrega estatísticas da biblioteca para o dashboard."""
        from collections import defaultdict
        from database import MediaFile

        series_list = self.library.list_all_series()
        total_downloaded = 0
        complete = 0
        missing_total = 0
        by_source: Dict[str, int] = defaultdict(int)

        for series in series_list:
            progress = self.library.get_series_progress(series)
            total_downloaded += progress['chapters_downloaded']
            missing_total += len(progress['missing_chapters'])
            if progress['is_complete']:
                complete += 1
            by_source[series.source_name or 'desconhecido'] += 1

        by_format: Dict[str, int] = defaultdict(int)
        session = self.library.session
        for media_file in session.query(MediaFile).all():
            by_format[media_file.file_format or 'desconhecido'] += 1

        return {
            'total_series': len(series_list),
            'total_downloaded': total_downloaded,
            'complete_collections': complete,
            'missing_total': missing_total,
            'by_format': dict(by_format),
            'by_source': dict(by_source),
        }

    def cleanup(self):
        """Limpeza final."""
        self.library.cleanup()
        db_manager.close()

    def clear_cache(self) -> int:
        """Remove cache local de consultas e capítulos."""
        return self.cache.clear()

    def print_graph_status(self):
        """Mostra um resumo simples do grafo gerado pelo graphify, se existir."""
        graph_dir = Path(__file__).parent / "graphify-out"
        graph_path = graph_dir / "graph.json"
        report_path = graph_dir / "GRAPH_REPORT.md"

        print(f"\n{'='*60}")
        print("🕸️ STATUS DO GRAFO")
        print(f"{'='*60}")

        if not graph_path.exists():
            print("   Nenhum graph.json encontrado em graphify-out/.")
            return

        try:
            graph_data = json.loads(graph_path.read_text(encoding='utf-8'))
            nodes = graph_data.get('nodes', [])
            edges = graph_data.get('edges', [])
            communities = graph_data.get('communities', [])

            print(f"   Nós: {len(nodes)}")
            print(f"   Arestas: {len(edges)}")
            print(f"   Comunidades: {len(communities)}")
            print(f"   Relatório: {report_path}")
        except Exception as exc:
            print(f"   Falha ao ler graph.json: {exc}")


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Media Bot PT-BR - pesquisa, download e organização de mídia"
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    search_parser = subparsers.add_parser("search", help="Buscar séries em todas as fontes")
    search_parser.add_argument("query", help="Título ou termo de busca")
    search_parser.add_argument("--media-type", default="manga", help="Tipo de mídia: manga, livro, hq, manhwa, artigo")

    download_parser = subparsers.add_parser("download", help="Baixar uma série completa")
    download_parser.add_argument("series", help="Nome da série")
    download_parser.add_argument("--media-type", default="manga", help="Tipo de mídia")
    download_parser.add_argument("--source", default="mangadex", help="Fonte: mangadex, archive, gutenberg")

    status_parser = subparsers.add_parser("status", help="Ver status de uma coleção")
    status_parser.add_argument("series", help="Nome da série")

    library_parser = subparsers.add_parser("library", help="Listar biblioteca local")

    cache_clear_parser = subparsers.add_parser("cache-clear", help="Limpar cache local")

    subparsers.add_parser("graph-status", help="Mostrar resumo do grafo graphify")

    return parser


def run_cli() -> int:
    parser = build_cli_parser()
    args = parser.parse_args()

    bot = MediaBot()
    try:
        if args.command == "search":
            results = bot.search_series(args.query, media_type=args.media_type)
            if not results:
                return 0

            print(f"\nResultados: {len(results)}")
            for index, result in enumerate(results, 1):
                title = result.get('title') or result.get('series_name') or 'Sem título'
                source = result.get('source', 'unknown')
                format_type = result.get('format_type') or result.get('format') or 'unknown'
                url = result.get('url') or result.get('download_url') or '-'
                print(f"{index:02d}. {title} [{source}] ({format_type})")
                print(f"    {url}")
            return 0

        if args.command == "download":
            bot.download_complete_series(args.series, media_type=args.media_type, source_name=args.source)
            return 0

        if args.command == "status":
            bot.check_collection_status(args.series)
            return 0

        if args.command == "library":
            bot.list_library()
            return 0

        if args.command == "cache-clear":
            removed = bot.clear_cache()
            print(f"Cache removido: {removed} arquivo(s)")
            return 0

        if args.command == "graph-status":
            bot.print_graph_status()
            return 0

        parser.print_help()
        return 0
    finally:
        bot.cleanup()


# Exemplo de uso direto
if __name__ == "__main__":
    raise SystemExit(run_cli())
