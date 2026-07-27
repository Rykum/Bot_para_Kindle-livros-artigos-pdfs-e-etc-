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
import unicodedata
from typing import List, Dict, Optional
from .base_scraper import BaseScraper, ScrapedResult, SourceCapabilities, BOOK_MEDIA
from .archive_scraper import ArchiveOrgScraper

logger = logging.getLogger(__name__)


class OpenLibraryScraper(BaseScraper):
    """
    Resolve título/autor para a obra certa e devolve o exemplar correspondente
    no Archive.org, já pronto para download.
    """

    capabilities = SourceCapabilities(media_types=BOOK_MEDIA, explora_genero=True)

    #: Campos pedidos à API (menos tráfego e resposta mais rápida).
    FIELDS = 'key,title,author_name,first_publish_year,ia,isbn,language,edition_count'

    #: O Open Library usa ISO 639-2 (3 letras), não os códigos curtos do app.
    LANGUAGE_CODES = {'pt': 'por', 'pt-br': 'por', 'en': 'eng', 'es': 'spa'}

    #: Subgênero em português -> termo de assunto em inglês. As chaves ficam
    #: já dobradas (minúsculas, sem acento) porque o lookup em `explorar` usa
    #: `self._fold(subgenero)` — uma chave acentuada aqui nunca seria
    #: encontrada e o subgênero cairia em silêncio para o gênero inteiro.
    SUBGENEROS = {
        "distopia": "dystopias", "space opera": "space opera", "cyberpunk": "cyberpunk",
        "gotico": "gothic fiction", "sobrenatural": "supernatural",
        "historico": "historical fiction", "contemporaneo": "contemporary fiction",
        "policial": "detective and mystery stories", "suspense": "suspense",
        "epica": "epic", "contos de fadas": "fairy tales", "lirica": "lyric poetry",
        "etica": "ethics", "metafisica": "metaphysics",
        "brasil": "brazil", "antiguidade": "antiquities",
        "memorias": "autobiography", "viagem": "voyages and travels",
        "nautica": "seafaring life",
    }

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

    @staticmethod
    def _fold(text) -> str:
        """Minúsculas sem acento, para casar 'Distopia' com a chave em SUBGENEROS."""
        if isinstance(text, list):
            text = ' '.join(str(t) for t in text)
        folded = unicodedata.normalize('NFKD', str(text).lower())
        return ''.join(c for c in folded if not unicodedata.combining(c))

    #: Formas em que o Archive.org grava português no campo `language`.
    IDIOMAS_PT = frozenset({"por", "portuguese", "pt", "pt-br", "português"})

    def _idiomas_dos_exemplares(self, identificadores):
        """
        Idioma real de cada exemplar, numa **única** consulta em lote.

        O campo `language` do Open Library não serve: ele lista *todos* os
        idiomas em que a obra existe — `Misery` traz 15 — e não o idioma do
        arquivo que se vai baixar. Medido: o exemplar que o app escolhia para
        `Misery` estava em chinês, o de `It` em alemão, o de `Pet Sematary` em
        russo. O idioma de verdade mora no item do Archive.org.
        """
        if not identificadores:
            return {}
        idiomas = {}
        # O Advanced Search aceita uma disjunção de identificadores, então todos
        # os exemplares de uma página saem numa chamada só.
        for inicio in range(0, len(identificadores), 50):
            lote = identificadores[inicio:inicio + 50]
            consulta = " OR ".join(f"identifier:{i}" for i in lote)
            resposta = self._archive.make_request(
                self._archive.search_api,
                params={"q": consulta, "fl[]": ["identifier", "language"],
                        "rows": len(lote), "output": "json"})
            if not resposta:
                continue
            for doc in resposta.json().get("response", {}).get("docs", []):
                bruto = doc.get("language")
                if isinstance(bruto, list):
                    bruto = bruto[0] if bruto else None
                if bruto:
                    idiomas[doc["identifier"]] = str(bruto).lower()
        return idiomas

    def _melhor_exemplar(self, copias):
        """
        Escolhe o exemplar a baixar, preferindo português.

        Devolve (identificador, idioma). Sem informação de idioma, mantém o
        primeiro — o comportamento anterior — e reporta 'desconhecido' em vez
        de inventar.
        """
        idiomas = getattr(self, "_idiomas_cache", {})
        for identificador in copias:
            if idiomas.get(identificador) in self.IDIOMAS_PT:
                return identificador, "por"
        return copias[0], idiomas.get(copias[0], "desconhecido")

    def explorar(self, genero, subgenero=None, ordenacao="relevancia"):
        """
        Lista obras de um gênero.

        A ordenação padrão é relevância — ausência de `sort`. Medido: ordenar por
        popularidade traz o livro mais reimpresso do acervo inteiro para dentro de
        qualquer gênero, e `Alice no País das Maravilhas` aparecia tanto em ficção
        científica quanto em filosofia.
        """
        if genero is None or not genero.openlibrary:
            return []

        assunto = genero.openlibrary
        if subgenero:
            traduzido = self.SUBGENEROS.get(self._fold(subgenero))
            if traduzido:
                assunto = f"{assunto} {traduzido}"
            else:
                logger.warning(
                    f"Open Library: subgênero '{subgenero}' sem tradução "
                    f"conhecida; resultado cai para o gênero '{genero.nome}' "
                    f"inteiro, sem esse refinamento")

        params = {
            "subject": assunto,
            "fields": self.FIELDS + ",cover_i",
            "limit": self.rows,
            "has_fulltext": "true",     # só o que dá para baixar
        }
        if ordenacao == "mais_lidos":
            params["sort"] = "readinglog"

        resultados = []
        try:
            resposta = self.make_request(self.search_api, params=params)
            if not resposta:
                return resultados

            documentos = [d for d in resposta.json().get("docs", []) if d.get("ia")]

            # Uma chamada em lote resolve o idioma de todos os exemplares da
            # página. Limitamos a 8 exemplares por obra: passar disso engorda a
            # consulta sem melhorar a chance de achar português.
            candidatos = [i for d in documentos for i in (d.get("ia") or [])[:8]]
            self._idiomas_cache = self._idiomas_dos_exemplares(candidatos)

            for doc in documentos:
                copias = doc.get("ia") or []
                autores = doc.get("author_name") or []
                isbns = doc.get("isbn") or []
                titulo = doc.get("title") or "Sem título"
                capa = doc.get("cover_i")
                escolhido, idioma = self._melhor_exemplar(copias)
                resultados.append(ScrapedResult(
                    title=titulo,
                    url=f"https://archive.org/details/{escolhido}",
                    source=self.name,
                    format_type="pdf",
                    series_name=titulo,
                    language=idioma,
                    metadata={
                        "identifier": escolhido,
                        "creator": ", ".join(autores),
                        "year": doc.get("first_publish_year"),
                        "isbn": isbns[0] if isbns else None,
                        "openlibrary_key": doc.get("key"),
                        "cover_url": (f"https://covers.openlibrary.org/b/id/{capa}-M.jpg"
                                      if capa else None),
                        "genero": genero.nome,
                        "idioma": idioma,
                    },
                ))

            # Português primeiro. É raro — medido, ~1 obra em 12 de terror tem
            # exemplar em português —, então ordenar não esvazia a tela, ao
            # contrário de filtrar (0,3% a 2,7% do acervo sobrevive ao filtro).
            resultados.sort(key=lambda r: 0 if r.language in self.IDIOMAS_PT else 1)
        except Exception as e:
            logger.error(f"Erro ao explorar no Open Library: {e}")
        return resultados
