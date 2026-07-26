#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para Open Library (openlibrary.org)
API: https://openlibrary.org/search.json — sem chave

Não é uma fonte de arquivos: é a camada de **precisão**. O Open Library conhece a
obra (título canônico, autor, ano, ISBN) e sabe quais exemplares existem no
Internet Archive, no campo `ia`. Isso resolve o caso que a busca por texto no
Archive.org erra: procurar "Dune" lá devolvia "Dune Buggy Rental"; aqui devolve
Frank Herbert, com o identificador do exemplar para baixar.
"""

import logging
from typing import List, Dict, Optional
from .base_scraper import BaseScraper, ScrapedResult, SourceCapabilities, BOOK_MEDIA
from .archive_scraper import ArchiveOrgScraper

logger = logging.getLogger(__name__)


class OpenLibraryScraper(BaseScraper):
    """
    Resolve título/autor para a obra certa e devolve o exemplar correspondente
    no Archive.org, já pronto para download.
    """

    capabilities = SourceCapabilities(media_types=BOOK_MEDIA)

    #: Campos pedidos à API (menos tráfego e resposta mais rápida).
    FIELDS = 'key,title,author_name,first_publish_year,ia,isbn,language,edition_count'

    #: O Open Library usa ISO 639-2 (3 letras), não os códigos curtos do app.
    LANGUAGE_CODES = {'pt': 'por', 'pt-br': 'por', 'en': 'eng', 'es': 'spa'}

    def __init__(self):
        super().__init__(
            name="Open Library",
            base_url="https://openlibrary.org",
            language="pt-br"
        )
        self.search_api = "https://openlibrary.org/search.json"
        self.rows = 40
        # Os exemplares vivem no Archive.org; a leitura de arquivos e a escolha
        # de formato já estão resolvidas lá — não vale reimplementar.
        self._archive = ArchiveOrgScraper()
        self.use_api_headers()

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Busca obras e devolve só as que têm exemplar baixável no Archive.org.

        Args:
            query: Título ou nome de autor
            formats: mantido por compatibilidade; o formato real sai do exemplar
            language: pt/en/es — convertido para o código de 3 letras
            search_by: 'titulo' (padrão), 'autor' ou 'tudo'

        Returns:
            Lista de ScrapedResult apontando para o item no Archive.org
        """
        results: List[ScrapedResult] = []
        mode = self.normalize_search_by(search_by)
        term = (query or '').strip()
        if not term:
            return results

        params = {'fields': self.FIELDS, 'limit': self.rows}
        if mode == 'autor':
            params['author'] = term
        elif mode == 'tudo':
            params['q'] = term
        else:
            params['title'] = term

        lang_code = self.LANGUAGE_CODES.get((language or '').lower())
        if lang_code:
            params['language'] = lang_code

        try:
            response = self.make_request(self.search_api, params=params)
            if not response:
                return results

            for doc in response.json().get('docs', []):
                # Sem exemplar no Archive.org não há o que baixar. A obra existe
                # e é conhecida — esse é justamente o caso do "onde encontrar",
                # tratado separadamente.
                copies = doc.get('ia') or []
                if not copies:
                    continue

                authors = doc.get('author_name') or []
                isbns = doc.get('isbn') or []
                title = doc.get('title') or 'Sem título'

                results.append(ScrapedResult(
                    title=title,
                    url=f"https://archive.org/details/{copies[0]}",
                    source=self.name,
                    format_type='pdf',   # o real é decidido em get_series_info
                    series_name=title,
                    language=(doc.get('language') or [None])[0] or 'desconhecido',
                    metadata={
                        'identifier': copies[0],
                        'creator': ', '.join(authors),
                        'year': doc.get('first_publish_year'),
                        'isbn': isbns[0] if isbns else None,
                        'openlibrary_key': doc.get('key'),
                        'copies': copies[:10],
                        'edition_count': doc.get('edition_count'),
                    }
                ))

            logger.info(f"Open Library: {len(results)} resultados para '{query}'")

        except Exception as e:
            logger.error(f"Erro ao pesquisar no Open Library: {e}")

        return results

    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """Os exemplares são itens do Archive.org — delega para lá."""
        return self._archive.get_series_info(series_url, language=language)
