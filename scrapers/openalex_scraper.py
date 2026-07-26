#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para OpenAlex (api.openalex.org)
API aberta, sem chave.

Catálogo acadêmico com mais de 500 mil trabalhos de acesso aberto. Boa parte do
que ele indexa em português vem do SciELO — que não tem API própria utilizável
(a auditoria reprovou o OPDS deles). Aqui esse acervo chega pela porta dos fundos,
com PDF direto.
"""

import logging
import unicodedata
from typing import List, Dict, Optional

from .base_scraper import (BaseScraper, ScrapedResult, SourceCapabilities,
                           ARTICLE_MEDIA)

logger = logging.getLogger(__name__)


class OpenAlexScraper(BaseScraper):
    """Artigos de acesso aberto, só os que têm PDF acessível."""

    capabilities = SourceCapabilities(media_types=ARTICLE_MEDIA)

    def __init__(self):
        super().__init__(
            name="OpenAlex",
            base_url="https://api.openalex.org",
            language="en"
        )
        self.search_api = "https://api.openalex.org/works"
        self.rows = 25
        self.use_api_headers()

    @staticmethod
    def _pdf_url(work: Dict) -> Optional[str]:
        """
        Um trabalho pode ser 'aberto' e ainda assim só ter a página de destino,
        sem arquivo. Sem `pdf_url` não há o que baixar.
        """
        return ((work.get('best_oa_location') or {}).get('pdf_url')
                or (work.get('primary_location') or {}).get('pdf_url'))

    @staticmethod
    def _fold(text: str) -> str:
        """Minúsculas sem acento: 'Antonio Candido' precisa casar com 'Antônio Cândido'."""
        folded = unicodedata.normalize('NFKD', str(text or '').lower())
        return ''.join(c for c in folded if not unicodedata.combining(c))

    def _author_ids(self, name: str, limit: int = 5) -> List[str]:
        """
        Resolve nome de autor para IDs.

        O filtro `raw_author_name.search` casa palavra a palavra: buscar
        "Machado de Assis" devolvia 1854 trabalhos de psiquiatria assinados por
        gente com "Machado" *ou* "Assis" no nome. Resolver o autor primeiro e
        filtrar por `author.id` corrige isso — o mesmo caminho de dois passos
        usado no MangaDex.
        """
        response = self.make_request(f"{self.base_url}/authors",
                                     params={'search': name, 'per-page': limit})
        if not response:
            return []

        # O /authors também casa frouxo: "Antonio Candido" trazia "Andrés Catena".
        # Só ficam os autores cujo nome contém todas as palavras buscadas.
        termos = [self._fold(t) for t in name.split() if len(t) > 2]
        ids = []
        for autor in response.json().get('results', []):
            nome = self._fold(autor.get('display_name'))
            if termos and not all(t in nome for t in termos):
                continue
            identificador = (autor.get('id') or '').rsplit('/', 1)[-1]
            if identificador:
                ids.append(identificador)
        return ids

    @staticmethod
    def _authors(work: Dict) -> str:
        nomes = [(a.get('author') or {}).get('display_name')
                 for a in (work.get('authorships') or [])]
        return ', '.join(n for n in nomes if n)

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Busca trabalhos de acesso aberto.

        A API tem filtros por campo: 'titulo' usa `title.search`, 'autor' usa
        `raw_author_name.search`, 'tudo' usa a busca livre `search`.
        """
        results: List[ScrapedResult] = []
        term = (query or '').strip()
        if not term:
            return results

        mode = self.normalize_search_by(search_by)
        # Só material com arquivo aberto: o resto não é baixável.
        filtros = ['open_access.is_oa:true']
        params: Dict[str, object] = {'per-page': self.rows}

        if mode == 'autor':
            ids = self._author_ids(term)
            if not ids:
                logger.info(f"OpenAlex: nenhum autor encontrado para '{term}'")
                return results
            filtros.append(f'author.id:{"|".join(ids)}')   # "|" é OU no OpenAlex
        elif mode == 'tudo':
            params['search'] = term
        else:
            filtros.append(f'title.search:{term}')

        params['filter'] = ','.join(filtros)

        try:
            response = self.make_request(self.search_api, params=params)
            if not response:
                return results

            for work in response.json().get('results', []):
                pdf = self._pdf_url(work)
                if not pdf:
                    continue

                titulo = work.get('title') or work.get('display_name') or 'Sem título'
                results.append(ScrapedResult(
                    title=titulo,
                    url=work.get('id') or pdf,
                    source=self.name,
                    format_type='pdf',
                    series_name=titulo,
                    language=work.get('language') or 'desconhecido',
                    download_url=pdf,
                    metadata={
                        'identifier': (work.get('id') or '').rsplit('/', 1)[-1],
                        'creator': self._authors(work),
                        'year': work.get('publication_year'),
                        'doi': work.get('doi'),
                        'pdf_url': pdf,
                    }
                ))

            logger.info(f"OpenAlex: {len(results)} resultados para '{query}'")

        except Exception as e:
            logger.error(f"Erro ao pesquisar no OpenAlex: {e}")

        return results

    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """Relê o trabalho pelo id do OpenAlex."""
        try:
            work_id = (series_url or '').rstrip('/').rsplit('/', 1)[-1]
            response = self.make_request(f"{self.search_api}/{work_id}")
            if not response:
                return {}

            work = response.json()
            pdf = self._pdf_url(work)
            titulo = work.get('title') or 'Sem título'
            arquivos = [{'name': f"{work_id}.pdf", 'size': 0,
                         'format': 'pdf', 'url': pdf}] if pdf else []

            return {
                'identifier': work_id,
                'title': titulo,
                'creator': self._authors(work),
                'description': '',
                'year': work.get('publication_year'),
                'language': work.get('language') or '',
                'volume': None,
                'chapter': None,
                'total_files': len(arquivos),
                'download_url': pdf,
                'format': 'pdf' if pdf else 'unknown',
                'available_chapters': [{
                    'chapter': 1, 'volume': 1, 'title': titulo,
                    'download_url': pdf, 'format': 'pdf',
                }] if pdf else [],
                'downloadable_files': arquivos,
                'url': series_url,
            }
        except Exception as e:
            logger.error(f"Erro ao obter trabalho do OpenAlex: {e}")
            return {}
