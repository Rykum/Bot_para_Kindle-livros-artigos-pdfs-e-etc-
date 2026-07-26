#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para Zenodo (zenodo.org)
API: https://zenodo.org/api/records — sem chave

Repositório aberto do CERN. Guarda livros, teses, relatórios e artigos, com
arquivo liberado. Tem bastante material acadêmico brasileiro em português que
não aparece em nenhuma das outras fontes.
"""

import logging
from typing import List, Dict, Optional

from .base_scraper import BaseScraper, ScrapedResult, SourceCapabilities, BOOK_MEDIA

logger = logging.getLogger(__name__)


class ZenodoScraper(BaseScraper):
    """Busca no Zenodo e entrega o arquivo depositado."""

    capabilities = SourceCapabilities(media_types=BOOK_MEDIA)

    #: Extensões que o app sabe tratar.
    WANTED_EXT = ('.pdf', '.epub', '.djvu')

    def __init__(self):
        super().__init__(
            name="Zenodo",
            base_url="https://zenodo.org",
            language="en"
        )
        self.search_api = "https://zenodo.org/api/records"
        self.rows = 25
        self.use_api_headers()

    def _files_from(self, record: Dict) -> List[Dict]:
        """Só os arquivos de livro; o resto é dado bruto, planilha, código."""
        arquivos = []
        for arquivo in (record.get('files') or []):
            nome = arquivo.get('key') or ''
            if not nome.lower().endswith(self.WANTED_EXT):
                continue
            url = (arquivo.get('links') or {}).get('self')
            if not url:
                continue
            arquivos.append({
                'name': nome,
                'size': arquivo.get('size', 0),
                'format': nome.rsplit('.', 1)[-1].lower(),
                'url': url,
            })
        arquivos.sort(key=lambda f: {'pdf': 0, 'epub': 1}.get(f['format'], 2))
        return arquivos

    @staticmethod
    def _authors(record: Dict) -> str:
        criadores = (record.get('metadata') or {}).get('creators') or []
        return ', '.join(c.get('name', '') for c in criadores if c.get('name'))

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Busca registros no Zenodo.

        A API tem sintaxe de campo: 'titulo' consulta `title:`, 'autor' consulta
        `creators.name:` e 'tudo' faz busca livre.
        """
        results: List[ScrapedResult] = []
        term = (query or '').strip()
        if not term:
            return results

        mode = self.normalize_search_by(search_by)
        if mode == 'autor':
            consulta = f'creators.name:"{term}"'
        elif mode == 'tudo':
            consulta = term
        else:
            consulta = f'title:"{term}"'

        try:
            response = self.make_request(self.search_api, params={
                'q': consulta,
                'size': self.rows,
            })
            if not response:
                return results

            for record in response.json().get('hits', {}).get('hits', []):
                arquivos = self._files_from(record)
                if not arquivos:
                    continue

                metadata = record.get('metadata') or {}
                titulo = metadata.get('title') or 'Sem título'

                results.append(ScrapedResult(
                    title=titulo,
                    url=f"{self.base_url}/records/{record.get('id')}",
                    source=self.name,
                    format_type=arquivos[0]['format'],
                    series_name=titulo,
                    language=metadata.get('language') or 'desconhecido',
                    download_url=arquivos[0]['url'],
                    metadata={
                        'identifier': str(record.get('id')),
                        'creator': self._authors(record),
                        'year': (metadata.get('publication_date') or '')[:4] or None,
                        'doi': metadata.get('doi'),
                        'files': arquivos,
                    }
                ))

            logger.info(f"Zenodo: {len(results)} resultados para '{query}'")

        except Exception as e:
            logger.error(f"Erro ao pesquisar no Zenodo: {e}")

        return results

    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """Relê o registro pelo id para montar a lista de arquivos."""
        try:
            record_id = series_url.rstrip('/').split('/')[-1]
            response = self.make_request(f"{self.search_api}/{record_id}")
            if not response:
                return {}

            record = response.json()
            arquivos = self._files_from(record)
            metadata = record.get('metadata') or {}
            titulo = metadata.get('title') or 'Sem título'

            return {
                'identifier': str(record.get('id')),
                'title': titulo,
                'creator': self._authors(record),
                'description': metadata.get('description') or '',
                'year': (metadata.get('publication_date') or '')[:4] or None,
                'language': metadata.get('language') or '',
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
            logger.error(f"Erro ao obter registro do Zenodo: {e}")
            return {}
