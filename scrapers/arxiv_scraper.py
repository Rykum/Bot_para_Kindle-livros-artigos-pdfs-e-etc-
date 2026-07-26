#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para arXiv (export.arxiv.org)
API Atom, sem chave.

Pré-publicações de exatas, computação, física e áreas correlatas. Tudo com PDF
aberto — é a única fonte do app onde o download nunca esbarra em direito autoral.
"""

import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional

from .base_scraper import (BaseScraper, ScrapedResult, SourceCapabilities,
                           ARTICLE_MEDIA)

logger = logging.getLogger(__name__)


class ArxivScraper(BaseScraper):
    """Busca no arXiv e entrega o PDF da pré-publicação."""

    capabilities = SourceCapabilities(media_types=ARTICLE_MEDIA)

    #: A resposta é Atom, não JSON — daí os namespaces.
    NS = {'a': 'http://www.w3.org/2005/Atom'}

    #: Prefixos de campo da própria linguagem de consulta do arXiv.
    CAMPOS = {'titulo': 'ti', 'autor': 'au', 'tudo': 'all'}

    def __init__(self):
        super().__init__(
            name="arXiv",
            base_url="https://export.arxiv.org",
            language="en"
        )
        # HTTPS direto: em http o arXiv redireciona, e cada re-tentativa da
        # cadeia de redirecionamento contava como chamada nova — resultado 429.
        self.search_api = "https://export.arxiv.org/api/query"
        self.rows = 25
        # A política do arXiv pede ~3 s entre chamadas; o padrão de 1 s tomava 429.
        self.rate_limiter.delays['export.arxiv.org'] = 3.0
        # Atom, não JSON: pede XML e se identifica honestamente.
        self.session.headers.update({
            'User-Agent': self.API_USER_AGENT,
            'Accept': 'application/atom+xml',
        })

    @staticmethod
    def _pdf_link(entry: ET.Element) -> Optional[str]:
        for link in entry.findall('a:link', ArxivScraper.NS):
            if link.get('title') == 'pdf':
                return link.get('href')
        return None

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Busca no arXiv usando a linguagem de consulta dele: `ti:` para título,
        `au:` para autor e `all:` para qualquer campo.
        """
        results: List[ScrapedResult] = []
        term = (query or '').strip()
        if not term:
            return results

        campo = self.CAMPOS[self.normalize_search_by(search_by)]

        try:
            response = self.make_request(self.search_api, params={
                'search_query': f'{campo}:"{term}"',
                'max_results': self.rows,
                'sortBy': 'relevance',
            })
            if not response:
                return results

            # `response.text` já vem decodificado; ET aceita str sem declaração.
            root = ET.fromstring(response.text)

            for entry in root.findall('a:entry', self.NS):
                pdf = self._pdf_link(entry)
                if not pdf:
                    continue

                titulo_el = entry.find('a:title', self.NS)
                titulo = (titulo_el.text or '').strip() if titulo_el is not None else 'Sem título'
                # O arXiv quebra o título em várias linhas no Atom.
                titulo = ' '.join(titulo.split())

                autores = [n.text for n in entry.findall('a:author/a:name', self.NS) if n.text]
                id_el = entry.find('a:id', self.NS)
                arxiv_id = (id_el.text or '').rsplit('/', 1)[-1] if id_el is not None else ''
                publicado = entry.find('a:published', self.NS)

                results.append(ScrapedResult(
                    title=titulo,
                    url=id_el.text if id_el is not None else pdf,
                    source=self.name,
                    format_type='pdf',
                    series_name=titulo,
                    language='en',
                    download_url=pdf,
                    metadata={
                        'identifier': arxiv_id,
                        'creator': ', '.join(autores),
                        'year': (publicado.text or '')[:4] if publicado is not None else None,
                        'pdf_url': pdf,
                    }
                ))

            logger.info(f"arXiv: {len(results)} resultados para '{query}'")

        except ET.ParseError as e:
            logger.error(f"Resposta do arXiv não é XML válido: {e}")
        except Exception as e:
            logger.error(f"Erro ao pesquisar no arXiv: {e}")

        return results

    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """O PDF do arXiv é derivável do id — não precisa de nova consulta."""
        try:
            arxiv_id = (series_url or '').rstrip('/').rsplit('/', 1)[-1]
            if not arxiv_id:
                return {}
            pdf = f"https://arxiv.org/pdf/{arxiv_id}"
            arquivos = [{'name': f"{arxiv_id}.pdf", 'size': 0,
                         'format': 'pdf', 'url': pdf}]
            return {
                'identifier': arxiv_id,
                'title': arxiv_id,
                'creator': '',
                'description': '',
                'year': None,
                'language': 'en',
                'volume': None,
                'chapter': None,
                'total_files': 1,
                'download_url': pdf,
                'format': 'pdf',
                'available_chapters': [{
                    'chapter': 1, 'volume': 1, 'title': arxiv_id,
                    'download_url': pdf, 'format': 'pdf',
                }],
                'downloadable_files': arquivos,
                'url': series_url,
            }
        except Exception as e:
            logger.error(f"Erro ao montar informações do arXiv: {e}")
            return {}
