#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para MangaDex - API Oficial
https://api.mangadex.org/
Documentação: https://api.mangadex.org/docs.html
"""

import logging
import requests
from typing import List, Dict, Optional
from .base_scraper import BaseScraper, ScrapedResult

logger = logging.getLogger(__name__)


class MangaDexScraper(BaseScraper):
    """
    Scraper oficial da API MangaDex
    Suporta pesquisa por título em português do Brasil
    Retorna informações de mangás, capítulos e volumes
    """
    
    def __init__(self):
        super().__init__(
            name="MangaDex",
            base_url="https://api.mangadex.org",
            language="pt-br"
        )
        self.api_version = "2"
        # Configurar headers específicos para API
        self.session.headers.update({
            'Accept': 'application/json',
        })
    
    def search(self, query: str, formats: List[str] = None) -> List[ScrapedResult]:
        """
        Pesquisa mangás na API MangaDex
        Foca em conteúdo em português brasileiro
        
        Args:
            query: Título ou termo de pesquisa
            formats: Lista de formatos desejados (não aplicável para MangaDex, mas mantido por compatibilidade)
        
        Returns:
            Lista de ScrapedResult com mangás encontrados
        """
        results = []
        
        try:
            # Endpoint de pesquisa de mangás
            search_url = f"{self.base_url}/manga"
            params = {
                'title': query,
                'includes[]': ['cover_art'],  # Incluir arte da capa
                'limit': 20,
                'offset': 0
            }
            
            response = self.make_request(search_url, params=params)
            if not response:
                return results
            
            data = response.json()
            
            for manga in data.get('data', []):
                attributes = manga.get('attributes', {})
                title_data = attributes.get('title', {})
                
                # Tentar obter título em português, senão usar inglês
                title = title_data.get('pt-br') or title_data.get('en') or list(title_data.values())[0]
                
                # Obter ID do mangá para buscar capítulos
                manga_id = manga.get('id')
                manga_url = f"https://mangadex.org/title/{manga_id}"
                
                result = ScrapedResult(
                    title=title,
                    url=manga_url,
                    source=self.name,
                    format_type='cbz',  # MangaDex geralmente fornece CBZ
                    series_name=title,
                    language='pt-br',
                    metadata={
                        'manga_id': manga_id,
                        'status': attributes.get('status'),
                        'year': attributes.get('year'),
                        'description': attributes.get('description', {}).get('pt-br', ''),
                    }
                )
                results.append(result)
                
            logger.info(f"MangaDex: {len(results)} resultados para '{query}'")
            
        except Exception as e:
            logger.error(f"Erro ao pesquisar no MangaDex: {e}")
        
        return results
    
    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """
        Obtém informações detalhadas da série
        Inclui lista de capítulos, volumes e último lançamento

        Args:
            series_url: URL da série no formato https://mangadex.org/title/{id}
            language: idioma traduzido desejado para o feed de capítulos

        Returns:
            Dict com informações da série
        """
        try:
            # Extrair ID da URL
            manga_id = series_url.rstrip('/').split('/')[-1]
            
            # Obter detalhes do mangá
            manga_url = f"{self.base_url}/manga/{manga_id}"
            params = {'includes[]': ['cover_art']}
            
            response = self.make_request(manga_url, params=params)
            if not response:
                return {}
            
            manga_data = response.json().get('data', {})
            attributes = manga_data.get('attributes', {})
            
            # Obter TODOS os capítulos (paginado — feed limita a 500 por página).
            chapters_url = f"{self.base_url}/manga/{manga_id}/feed"
            chapters_data = []
            offset = 0
            page_size = 500
            while True:
                params = {
                    'translatedLanguage[]': [language],
                    'order[volume]': 'asc',
                    'order[chapter]': 'asc',
                    'limit': page_size,
                    'offset': offset,
                    'includes[]': ['scanlation_group'],
                }
                chapters_response = self.make_request(chapters_url, params=params)
                if not chapters_response:
                    break
                chapters_json = chapters_response.json()
                batch = chapters_json.get('data', [])
                chapters_data.extend(batch)
                total = chapters_json.get('total', 0)
                offset += len(batch)
                # Para quando não veio página cheia ou já cobriu o total.
                if len(batch) < page_size or (total and offset >= total):
                    break

            # Processar capítulos para encontrar volumes/capítulos disponíveis
            available_chapters = []
            volumes = set()
            
            for chapter in chapters_data:
                chap_attrs = chapter.get('attributes', {})
                chapter_num = chap_attrs.get('chapter')
                volume_num = chap_attrs.get('volume')
                
                if volume_num:
                    volumes.add(int(float(volume_num)))
                
                available_chapters.append({
                    'chapter': float(chapter_num) if chapter_num else None,
                    'volume': float(volume_num) if volume_num else None,
                    'title': chap_attrs.get('title'),
                    'chapter_id': chapter.get('id'),
                })
            
            # Determinar primeiro e último volume/capítulo
            first_volume = min(volumes) if volumes else None
            last_volume = max(volumes) if volumes else None
            
            total_chapters = len([c for c in available_chapters if c['chapter']])
            
            return {
                'manga_id': manga_id,
                'title': attributes.get('title', {}).get('pt-br') or attributes.get('title', {}).get('en'),
                'status': attributes.get('status'),
                'year': attributes.get('year'),
                'first_volume': first_volume,
                'last_volume': last_volume,
                'total_volumes': len(volumes),
                'total_chapters': total_chapters,
                'available_chapters': available_chapters,
                'language': language,
                'url': series_url
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter informações da série: {e}")
            return {}
    
    def get_chapter_download_url(self, chapter_id: str) -> Optional[str]:
        """
        Obtém URL de download para um capítulo específico
        Usa o endpoint at-home server do MangaDex
        
        Args:
            chapter_id: ID do capítulo
        
        Returns:
            URL base para download das páginas
        """
        try:
            url = f"{self.base_url}/at-home/server/{chapter_id}"
            response = self.make_request(url)
            
            if response:
                data = response.json()
                if data.get('result') == 'ok':
                    base_url = data['baseUrl']
                    chapter_hash = data['chapter']['hash']
                    pages = data['chapter']['data']
                    
                    return {
                        'base_url': base_url,
                        'hash': chapter_hash,
                        'pages': pages,
                        'force_port_443': data.get('forcePort443', False)
                    }
        except Exception as e:
            logger.error(f"Erro ao obter URL de download do capítulo: {e}")
        
        return None
    
    def build_page_urls(self, chapter_info: Dict) -> List[str]:
        """
        Constrói URLs completas para todas as páginas de um capítulo
        
        Args:
            chapter_info: Dict retornado por get_chapter_download_url
        
        Returns:
            Lista de URLs das páginas
        """
        if not chapter_info:
            return []
        
        base_url = chapter_info['base_url']
        chapter_hash = chapter_info['hash']
        pages = chapter_info['pages']
        
        page_urls = []
        for page in pages:
            page_url = f"{base_url}/data/{chapter_hash}/{page}"
            page_urls.append(page_url)
        
        return page_urls

    def get_chapter_url(self, series_identifier: str, chapter_number: float, language: str = "pt-br") -> Optional[Dict]:
        """Resolves a chapter into page URLs that can be packed into a CBZ."""
        series_info = self.get_series_info(series_identifier, language=language)
        if not series_info:
            return None

        matched_chapter = None
        for item in series_info.get('available_chapters', []):
            try:
                item_chapter = item.get('chapter')
                if item_chapter is not None and float(item_chapter) == float(chapter_number):
                    matched_chapter = item
                    break
            except (TypeError, ValueError):
                continue

        if not matched_chapter:
            return None

        chapter_id = matched_chapter.get('chapter_id')
        if not chapter_id:
            return None

        chapter_info = self.get_chapter_download_url(chapter_id)
        if not chapter_info:
            return None

        page_urls = self.build_page_urls(chapter_info)
        if not page_urls:
            return None

        return {
            'chapter_id': chapter_id,
            'title': matched_chapter.get('title') or f'Capítulo {chapter_number}',
            'volume': matched_chapter.get('volume') or 1,
            'chapter': float(chapter_number),
            'format': 'cbz',
            'download_type': 'mangadex_cbz',
            'page_urls': page_urls,
            'page_count': len(page_urls),
        }

    def fetch_page(self, page_url: str, should_cancel=None, max_attempts: int = 3):
        """Baixa uma página com retry local. Retorna bytes ou levanta a última exceção."""
        import time
        last_error = None
        for attempt in range(max_attempts):
            if should_cancel is not None and should_cancel():
                raise RuntimeError("cancelled")
            try:
                self.rate_limiter.wait(page_url)
                response = self.session.get(page_url, timeout=60)
                if response.status_code == 429:
                    retry_after = response.headers.get('Retry-After')
                    try:
                        wait_time = float(retry_after) if retry_after is not None else 1.5 ** attempt
                    except (TypeError, ValueError):
                        wait_time = 1.5 ** attempt
                    time.sleep(wait_time)
                    continue
                response.raise_for_status()
                return response.content
            except requests.exceptions.HTTPError as exc:
                last_error = exc
                # URLs expiradas não adiantam re-tentar: propaga para re-resolução
                status = getattr(exc.response, 'status_code', None)
                if status in (403, 404, 410):
                    raise
                time.sleep(1.5 ** attempt)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(1.5 ** attempt)
        raise last_error if last_error else RuntimeError("falha ao baixar página")

    def reresolve_pages(self, chapter_id: str):
        try:
            info = self.get_chapter_download_url(chapter_id)
            return self.build_page_urls(info) if info else []
        except Exception:
            return []
