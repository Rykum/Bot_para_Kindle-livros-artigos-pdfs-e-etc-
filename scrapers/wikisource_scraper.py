#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para Wikisource (pt/en/es)
API de busca: MediaWiki `action=query&list=search`
Geração de arquivo: ws-export (https://ws-export.wmcloud.org/)

Diferencial: o Wikisource guarda o texto **transcrito**, não a imagem escaneada.
O EPUB gerado é texto de verdade — pesquisável, reflowable e leve — em vez de um
PDF de digitalização. Para literatura brasileira de domínio público é o melhor
formato disponível de graça.
"""

import logging
from typing import List, Dict, Optional
from urllib.parse import quote

from .base_scraper import BaseScraper, ScrapedResult, SourceCapabilities, BOOK_MEDIA

logger = logging.getLogger(__name__)


class WikisourceScraper(BaseScraper):
    """Busca obras no Wikisource e entrega EPUB gerado pelo ws-export."""

    capabilities = SourceCapabilities(media_types=BOOK_MEDIA)

    #: Cada idioma é um site separado. Sem idioma escolhido, assume português.
    LANGUAGE_HOSTS = {
        'pt': 'pt.wikisource.org',
        'pt-br': 'pt.wikisource.org',
        'en': 'en.wikisource.org',
        'es': 'es.wikisource.org',
    }
    DEFAULT_HOST = 'pt.wikisource.org'

    #: Serviço oficial da Wikimedia que monta o livro a partir das páginas.
    EXPORT_URL = 'https://ws-export.wmcloud.org/'
    #: Só EPUB: o ws-export responde 503 para PDF de forma consistente.
    EXPORT_FORMAT = 'epub'

    def __init__(self):
        super().__init__(
            name="Wikisource",
            base_url="https://pt.wikisource.org",
            language="pt-br"
        )
        self.rows = 30
        self.use_api_headers()

    def _host_for(self, language: str = None) -> str:
        return self.LANGUAGE_HOSTS.get((language or '').lower(), self.DEFAULT_HOST)

    @staticmethod
    def _is_work_page(title: str) -> bool:
        """
        Descarta subpágina de capítulo. Uma obra vive em "Dom Casmurro"; cada
        capítulo em "Dom Casmurro/I", "Dom Casmurro/II"... Sem esse filtro a
        busca devolveria 139 "resultados" que são o mesmo livro fatiado.
        """
        return '/' not in (title or '')

    def _export_url(self, host: str, page_title: str) -> str:
        return (f"{self.EXPORT_URL}?format={self.EXPORT_FORMAT}"
                f"&lang={host.split('.')[0]}&page={quote(page_title)}")

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Busca obras no Wikisource do idioma escolhido.

        A busca do MediaWiki é de texto completo e cobre título e conteúdo, então
        'titulo', 'autor' e 'tudo' usam a mesma consulta — buscar por autor
        funciona porque o nome dele aparece na página da obra.
        """
        results: List[ScrapedResult] = []
        term = (query or '').strip()
        if not term:
            return results

        host = self._host_for(language)
        lang_code = host.split('.')[0]

        try:
            response = self.make_request(f"https://{host}/w/api.php", params={
                'action': 'query',
                'list': 'search',
                'srsearch': term,
                'srnamespace': 0,          # só o espaço principal (obras)
                'srlimit': self.rows,
                'format': 'json',
            })
            if not response:
                return results

            for hit in response.json().get('query', {}).get('search', []):
                page_title = hit.get('title') or ''
                if not self._is_work_page(page_title):
                    continue

                results.append(ScrapedResult(
                    title=page_title,
                    url=f"https://{host}/wiki/{quote(page_title.replace(' ', '_'))}",
                    source=self.name,
                    format_type=self.EXPORT_FORMAT,
                    series_name=page_title,
                    language=lang_code,
                    download_url=self._export_url(host, page_title),
                    metadata={
                        'identifier': page_title,
                        'creator': '',      # o Wikisource não expõe autor na busca
                        'host': host,
                        'wordcount': hit.get('wordcount'),
                    }
                ))

            logger.info(f"Wikisource: {len(results)} resultados para '{query}'")

        except Exception as e:
            logger.error(f"Erro ao pesquisar no Wikisource: {e}")

        return results

    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """Monta o link do ws-export a partir da URL da obra."""
        try:
            host = series_url.split('/wiki/')[0].replace('https://', '')
            page_title = series_url.split('/wiki/')[-1].replace('_', ' ')
            from urllib.parse import unquote
            page_title = unquote(page_title)

            download_url = self._export_url(host, page_title)
            files = [{
                'name': f"{page_title}.{self.EXPORT_FORMAT}",
                'size': 0,
                'format': self.EXPORT_FORMAT,
                'url': download_url,
            }]

            return {
                'identifier': page_title,
                'title': page_title,
                'creator': '',
                'description': '',
                'year': None,
                'language': host.split('.')[0],
                'volume': None,
                'chapter': None,
                'total_files': len(files),
                'download_url': download_url,
                'format': self.EXPORT_FORMAT,
                'available_chapters': [{
                    'chapter': 1,
                    'volume': 1,
                    'title': page_title,
                    'download_url': download_url,
                    'format': self.EXPORT_FORMAT,
                }],
                'downloadable_files': files,
                'url': series_url,
            }
        except Exception as e:
            logger.error(f"Erro ao montar informações do Wikisource: {e}")
            return {}
