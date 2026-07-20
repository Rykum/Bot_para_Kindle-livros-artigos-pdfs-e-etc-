#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo 4: Media Bot Principal (Refatorado)
Integra Scrapers, Database, Normalizer e DownloadManager em um fluxo coeso.
Substitui todos os mockups por implementação real.

Fluxo: Search -> Filter -> DB Check -> Download -> Register
"""

import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Imports dos módulos reais
from scrapers.mangadex_scraper import MangaDexScraper
from scrapers.archive_scraper import ArchiveOrgScraper
from scrapers.gutenberg_scraper import ProjectGutenbergScraper
from download_manager import DownloadManager
from database import db_manager, Series
from library_manager import LibraryManager
from normalizer import ContentNormalizer


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
        self.normalizer = ContentNormalizer()
        
        # Inicializa scrapers disponíveis
        self.scrapers = [
            MangaDexScraper(),
            ArchiveOrgScraper(),
            ProjectGutenbergScraper()
        ]
        
        print(f"✅ Media Bot inicializado. Downloads em: {self.base_dir.absolute()}")

    def search_series(self, query: str, media_type: str = "manga") -> List[Dict[str, Any]]:
        """
        Busca série em todos os scrapers disponíveis.
        Retorna lista unificada de resultados.
        """
        print(f"\n🔍 Buscando por: '{query}' ({media_type})...")
        all_results = []
        
        for scraper in self.scrapers:
            try:
                results = scraper.search(query, media_type)
                if results:
                    print(f"   📚 {scraper.name}: {len(results)} resultado(s)")
                    all_results.extend(results)
            except Exception as e:
                print(f"   ⚠️ Erro no scraper {scraper.name}: {e}")
        
        if not all_results:
            print("   ❌ Nenhum resultado encontrado.")
        
        return all_results

    def get_complete_series_chapters(self, series_title: str, source_name: str = "mangadex") -> List[float]:
        """
        Consulta a API para obter TODOS os capítulos disponíveis de uma série.
        Retorna lista ordenada de números de capítulos.
        """
        print(f"\n📋 Verificando capítulos disponíveis para '{series_title}'...")
        
        # Seleciona scraper apropriado
        scraper = next((s for s in self.scrapers if s.name.lower() == source_name.lower()), None)
        if not scraper:
            print(f"   ⚠️ Scraper '{source_name}' não encontrado.")
            return []
        
        # Busca metadados da série completa
        try:
            chapters = scraper.get_all_chapters(series_title)
            chapter_numbers = sorted(set(chapters))
            print(f"   ✅ Encontrados {len(chapter_numbers)} capítulos disponíveis (do {min(chapter_numbers)} ao {max(chapter_numbers)})")
            return chapter_numbers
        except Exception as e:
            print(f"   ❌ Erro ao buscar capítulos: {e}")
            return []

    def download_complete_series(self, series_title: str, media_type: str = "manga",
                                 source_name: str = "mangadex", skip_existing: bool = True):
        """
        FLUXO PRINCIPAL: Baixa série completa do capítulo 1 ao último.
        1. Busca série
        2. Registra no DB
        3. Lista capítulos disponíveis online
        4. Identifica faltantes locais
        5. Baixa apenas faltantes
        6. Atualiza DB
        """
        print(f"\n{'='*60}")
        print(f"🚀 INICIANDO DOWNLOAD DA SÉRIE: {series_title}")
        print(f"{'='*60}")
        
        # Passo 1: Registrar/Obter série no DB
        series = self.library.get_or_create_series(series_title, source_name)
        
        # Passo 2: Obter todos os capítulos disponíveis na fonte
        available_chapters = self.get_complete_series_chapters(series_title, source_name)
        
        if not available_chapters:
            print("   ❌ Nenhum capítulo disponível para download.")
            return
        
        # Passo 3: Identificar o que já temos baixado
        missing_chapters = self.library.find_missing_chapters(series, available_chapters)
        
        if not missing_chapters:
            print(f"   🎉 Série completa! Todos os {len(available_chapters)} capítulos já estão baixados.")
            return
        
        print(f"   📥 Faltam baixar {len(missing_chapters)} de {len(available_chapters)} capítulos.")
        
        # Passo 4: Baixar capítulos faltantes
        downloaded_count = 0
        failed_count = 0
        
        # Re-obtém o scraper para usar no loop
        scraper = next((s for s in self.scrapers if s.name.lower() == source_name.lower()), None)
        
        for chapter_num in missing_chapters:
            print(f"\n   ⬇️  Baixando Capítulo {chapter_num}...")
            
            try:
                # Busca URL específica deste capítulo
                chapter_data = scraper.get_chapter_url(series_title, chapter_num)
                
                if not chapter_data or 'download_url' not in chapter_data:
                    print(f"      ⚠️ URL não encontrada para cap. {chapter_num}")
                    failed_count += 1
                    continue
                
                # Executa download real
                result = self.downloader.download(
                    url=chapter_data['download_url'],
                    filename=f"{series_title}_cap_{chapter_num:04d}.{chapter_data.get('format', 'cbz')}",
                    metadata={
                        'series': series_title,
                        'chapter': chapter_num,
                        'source': source_name
                    }
                )
                
                if result['success']:
                    # Registra no DB
                    chap_record = self.library.add_chapter(
                        series=series,
                        volume_num=chapter_data.get('volume', 1),
                        chapter_num=chapter_num,
                        title=chapter_data.get('title', f"Capítulo {chapter_num}")
                    )
                    
                    self.library.register_download(
                        chapter=chap_record,
                        file_path=result['file_path'],
                        file_format=result['metadata'].get('format', 'unknown'),
                        file_size=result['metadata'].get('size', 0),
                        sha256_hash=result['metadata'].get('sha256', '')
                    )
                    
                    downloaded_count += 1
                    print(f"      ✅ Sucesso! ({result['metadata'].get('size', 0) / 1024 / 1024:.2f} MB)")
                else:
                    failed_count += 1
                    print(f"      ❌ Falha no download: {result.get('error', 'Erro desconhecido')}")
                    
            except Exception as e:
                failed_count += 1
                print(f"      ❌ Erro inesperado: {e}")
            
            # Rate limiting entre capítulos
            time.sleep(2)
        
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

    def cleanup(self):
        """Limpeza final."""
        self.library.cleanup()
        db_manager.close()


# Exemplo de uso direto
if __name__ == "__main__":
    bot = MediaBot()
    
    # Exemplo: Buscar e baixar Dandadan completo
    # bot.download_complete_series("Dandadan", media_type="manga", source_name="mangadex")
    
    # Exemplo: Ver status da biblioteca
    bot.list_library()
    
    bot.cleanup()
