#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para OAPEN Library (library.oapen.org)
API: DSpace REST — /rest/search, sem chave

Livros acadêmicos de acesso aberto, com PDF completo liberado pela editora.
Cobertura relevante em ciências humanas e sociais, incluindo títulos sobre o
Brasil e em português.
"""

import logging
from typing import List, Dict, Optional

from .base_scraper import BaseScraper, ScrapedResult, SourceCapabilities, BOOK_MEDIA

logger = logging.getLogger(__name__)


class OapenScraper(BaseScraper):
    """Busca no OAPEN e entrega o PDF completo do livro."""

    capabilities = SourceCapabilities(media_types=BOOK_MEDIA)

    #: Formatos que interessam; o resto dos bitstreams é licença, capa, etc.
    WANTED_MIME = {
        'application/pdf': 'pdf',
        'application/epub+zip': 'epub',
    }

    def __init__(self):
        super().__init__(
            name="OAPEN",
            base_url="https://library.oapen.org",
            language="en"
        )
        self.search_api = "https://library.oapen.org/rest/search"
        # `expand=metadata,bitstreams` traz todos os arquivos de cada item: a
        # fonte mais lenta do app (11 s com 15 itens, contra menos de 3,5 s de
        # todas as outras). Menos itens é o que a deixa dentro do orçamento.
        self.rows = 10
        self.use_api_headers()

    @staticmethod
    def _metadata_map(item: Dict) -> Dict[str, str]:
        """Achata a lista `[{key, value}]` do DSpace num dicionário."""
        return {m.get('key'): m.get('value')
                for m in (item.get('metadata') or []) if m.get('key')}

    def _files_from(self, item: Dict) -> List[Dict]:
        """Só os bitstreams que são o livro, já com URL absoluta."""
        arquivos = []
        for bitstream in (item.get('bitstreams') or []):
            extensao = self.WANTED_MIME.get(bitstream.get('mimeType'))
            link = bitstream.get('retrieveLink')
            if not extensao or not link:
                continue
            arquivos.append({
                'name': bitstream.get('name') or f"livro.{extensao}",
                'size': bitstream.get('sizeBytes', 0),
                'format': extensao,
                'url': f"{self.base_url}{link}" if link.startswith('/') else link,
            })
        # PDF primeiro; é o que o OAPEN sempre tem.
        arquivos.sort(key=lambda f: 0 if f['format'] == 'pdf' else 1)
        return arquivos

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Busca livros no OAPEN.

        O `query` do DSpace é busca livre sobre todos os campos, então os três
        modos usam a mesma consulta; em 'autor' o nome buscado aparece nos
        metadados de autoria e o resultado é filtrado por isso.
        """
        results: List[ScrapedResult] = []
        term = (query or '').strip()
        if not term:
            return results

        mode = self.normalize_search_by(search_by)

        try:
            response = self.make_request(self.search_api, params={
                'query': term,
                'expand': 'metadata,bitstreams',
                'limit': self.rows,
            })
            if not response:
                return results

            for item in response.json():
                arquivos = self._files_from(item)
                if not arquivos:
                    continue          # sem PDF/EPUB não há o que baixar

                metadata = self._metadata_map(item)
                autor = metadata.get('dc.contributor.author') or ''
                titulo = item.get('name') or metadata.get('dc.title') or 'Sem título'

                if mode == 'autor' and not self._matches_author(autor, term):
                    continue

                handle = item.get('handle') or ''
                results.append(ScrapedResult(
                    title=titulo,
                    url=f"{self.base_url}/handle/{handle}",
                    source=self.name,
                    format_type=arquivos[0]['format'],
                    series_name=titulo,
                    language=metadata.get('dc.language') or 'desconhecido',
                    download_url=arquivos[0]['url'],
                    metadata={
                        'identifier': item.get('uuid'),
                        'creator': autor,
                        'year': metadata.get('dc.date.issued'),
                        'handle': handle,
                        'files': arquivos,
                    }
                ))

            logger.info(f"OAPEN: {len(results)} resultados para '{query}'")

        except Exception as e:
            logger.error(f"Erro ao pesquisar no OAPEN: {e}")

        return results

    @staticmethod
    def _matches_author(autor: str, query: str) -> bool:
        alvo = (autor or '').lower()
        termos = [t for t in query.lower().split() if len(t) > 2]
        return bool(termos) and all(t in alvo for t in termos)

    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """Relê o item pelo handle para montar a lista de arquivos."""
        try:
            handle = series_url.split('/handle/')[-1]
            response = self.make_request(f"{self.base_url}/rest/handle/{handle}",
                                         params={'expand': 'metadata,bitstreams'})
            if not response:
                return {}

            item = response.json()
            arquivos = self._files_from(item)
            metadata = self._metadata_map(item)
            titulo = item.get('name') or 'Sem título'

            return {
                'identifier': item.get('uuid'),
                'title': titulo,
                'creator': metadata.get('dc.contributor.author') or '',
                'description': metadata.get('dc.description.abstract') or '',
                'year': metadata.get('dc.date.issued'),
                'language': metadata.get('dc.language') or '',
                'volume': None,
                'chapter': None,
                'total_files': len(arquivos),
                'download_url': arquivos[0]['url'] if arquivos else None,
                'format': arquivos[0]['format'] if arquivos else 'unknown',
                'available_chapters': [{
                    'chapter': 1,
                    'volume': 1,
                    'title': titulo,
                    'download_url': arquivos[0]['url'],
                    'format': arquivos[0]['format'],
                }] if arquivos else [],
                'downloadable_files': arquivos,
                'url': series_url,
            }
        except Exception as e:
            logger.error(f"Erro ao obter item do OAPEN: {e}")
            return {}
