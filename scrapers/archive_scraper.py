#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para Archive.org (Internet Archive)
https://archive.org/
API: https://archive.org/help/about_search_api.php
Foco: Livros, mangás e HQs de domínio público ou Creative Commons
"""

import logging
import unicodedata
from typing import List, Dict, Optional
from .base_scraper import BaseScraper, ScrapedResult, SourceCapabilities, SERIAL_MEDIA, BOOK_MEDIA

logger = logging.getLogger(__name__)


class ArchiveOrgScraper(BaseScraper):
    """
    Scraper para Internet Archive
    Pesquisa livros, mangás e HQs em português disponíveis gratuitamente
    """
    
    def __init__(self):
        super().__init__(
            name="Archive.org",
            base_url="https://archive.org",
            language="pt-br"
        )
        self.search_api = "https://archive.org/advancedsearch.php"
        #: Quantos itens pedir por consulta.
        self.rows = 75
        #: Abaixo disso, a busca por título é complementada pela busca ampla.
        self.broaden_threshold = 25
        #: Abaixo disso, vale o último recurso: termos soltos com AND.
        self.last_resort_threshold = 3

    capabilities = SourceCapabilities(media_types=SERIAL_MEDIA | BOOK_MEDIA)

    #: Termos de idioma por código, usados no filtro `language:`.
    _LANG_TERMS = {
        'pt': '(portuguese OR por OR pt OR "pt-br" OR "português")',
        'pt-br': '(portuguese OR por OR pt OR "pt-br" OR "português")',
        'en': '(english OR eng OR en)',
        'es': '(spanish OR spa OR es OR "español")',
    }

    @staticmethod
    def _phrase(term: str) -> str:
        """
        Aspas viram frase exata. Sem elas o Archive.org trata cada palavra como
        alternativa: `creator:(John Douglas)` devolve 1331 itens — com Krakatoa
        e Douglas Haig no topo — contra 359 de `creator:("John Douglas")`.
        """
        return '"{}"'.format((term or '').strip().replace('"', ' ').strip())

    @classmethod
    def _author_variants(cls, name: str) -> str:
        """
        Bibliotecas catalogam autor invertido: o Mindhunter está como
        "Douglas, John E", que nunca casaria com "John Douglas". Procuramos
        as duas ordens.
        """
        term = (name or '').strip().replace('"', ' ').strip()
        variants = [cls._phrase(term)]
        parts = term.split()
        if len(parts) >= 2:
            variants.append(cls._phrase(f'{parts[-1]}, {" ".join(parts[:-1])}'))
        return ' OR '.join(variants)

    @staticmethod
    def _fold(text) -> str:
        """Minúsculas sem acento, para comparar título com o que foi digitado."""
        if isinstance(text, list):
            text = ' '.join(str(t) for t in text)
        folded = unicodedata.normalize('NFKD', str(text).lower())
        return ''.join(c for c in folded if not unicodedata.combining(c))

    @staticmethod
    def _terms(query: str) -> List[str]:
        """Palavras significativas do que foi digitado (ignora 'de', 'do', 'a')."""
        return [t for t in (query or '').split() if len(t) > 2]

    def _rank_by_term_coverage(self, docs: List[Dict], query: str) -> List[Dict]:
        """
        Ordena por quantas palavras da busca aparecem no título. Usado só no
        último recurso, onde a consulta é frouxa: sem isso, "Clean Code Robert
        Martin" devolve arquivos da CIA antes do livro.
        """
        terms = [self._fold(t) for t in self._terms(query)]
        if not terms:
            return docs
        return sorted(docs, key=lambda d: -sum(
            1 for t in terms if t in self._fold(d.get('title', ''))))

    def build_query(self, query: str, search_by: str = "titulo", language: str = None) -> str:
        """
        Monta a consulta do Advanced Search conforme o campo escolhido.

        - 'titulo': frase exata no campo title
        - 'autor':  frase exata em creator, nas duas ordens do nome
        - 'tudo':   frase exata em qualquer campo (mais alcance, sem perder
                    precisão — buscar termos soltos traz lixo sem relação)
        - 'termos': interno, só como último recurso (ver search)
        """
        term = (query or '').strip()
        # 'termos' é um degrau interno da escada, não uma opção da interface.
        mode = 'termos' if search_by == 'termos' else self.normalize_search_by(search_by)

        if mode == 'autor':
            search_query = f'creator:({self._author_variants(term)}) AND mediatype:texts'
        elif mode == 'termos':
            # Último recurso: as palavras em qualquer lugar, em qualquer ordem.
            # Resgata buscas que misturam título e autor ("Sapiens Harari"),
            # que como frase exata não existem em lugar nenhum.
            search_query = f'({" AND ".join(self._terms(term))}) AND mediatype:texts'
        elif mode == 'tudo':
            search_query = f'({self._phrase(term)}) AND mediatype:texts'
        else:
            search_query = f'title:({self._phrase(term)}) AND mediatype:texts'

        # O idioma é opcional: sem idioma traz tudo; com idioma, filtra.
        lang_terms = self._LANG_TERMS.get((language or '').lower())
        if lang_terms:
            search_query += f' AND language:{lang_terms}'
        return search_query

    @staticmethod
    def _append_new(docs: List[Dict], extra: List[Dict]) -> List[Dict]:
        """Anexa o que ainda não apareceu, preservando a ordem já estabelecida."""
        seen = {d.get('identifier') for d in docs}
        for doc in extra:
            if doc.get('identifier') not in seen:
                seen.add(doc.get('identifier'))
                docs.append(doc)
        return docs

    def _fetch_docs(self, search_query: str) -> List[Dict]:
        """Executa uma consulta e devolve os documentos crus."""
        # Sem `sort[]` o Archive.org ordena por relevância. Ordenar por
        # downloads enterrava o item certo: buscando "John Douglas" o
        # Mindhunter ficava atrás de qualquer best-seller sem relação.
        params = {
            'q': search_query,
            'fl[]': ['identifier', 'title', 'creator', 'year', 'language', 'mediatype', 'downloads'],
            'rows': self.rows,
            'output': 'json',
        }
        response = self.make_request(self.search_api, params=params)
        if not response:
            return []
        return response.json().get('response', {}).get('docs', [])

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Pesquisa no Internet Archive usando Advanced Search API

        Args:
            query: Título, autor ou termo de pesquisa
            formats: Lista de formatos desejados ['pdf', 'epub', 'cbz', etc]
            language: Filtra por idioma (pt/en/es); vazio traz qualquer um
            search_by: 'titulo' (padrão), 'autor' ou 'tudo'

        Returns:
            Lista de ScrapedResult com itens encontrados
        """
        if formats is None:
            formats = ['pdf', 'epub', 'djvu']

        results = []
        mode = self.normalize_search_by(search_by)

        try:
            docs = self._fetch_docs(self.build_query(query, mode, language))

            # Buscar só no campo `title` descarta itens catalogados pelo nome da
            # coleção ou com o autor no título. Quando a busca por título rende
            # pouco, completamos com a mesma frase em qualquer campo — os
            # acertos de título continuam na frente, e o resto entra depois.
            if mode == 'titulo' and len(docs) < self.broaden_threshold:
                docs = self._append_new(
                    docs, self._fetch_docs(self.build_query(query, 'tudo', language)))

            # Último recurso, só quando quase nada apareceu: as palavras soltas
            # em qualquer campo. É o que resgata "Sapiens Harari" — que não
            # existe como frase em título nenhum — e buscas com o autor junto.
            # Como a consulta é frouxa, o lote entra reordenado por quantas
            # palavras batem, e sempre depois do que já tinha sido achado.
            if (mode in ('titulo', 'tudo') and len(docs) < self.last_resort_threshold
                    and len(self._terms(query)) > 1):
                extra = self._fetch_docs(self.build_query(query, 'termos', language))
                docs = self._append_new(docs, self._rank_by_term_coverage(extra, query))

            # Existem muitos "John Douglas". Quem bate com o nome inteiro no
            # campo creator vem primeiro; o resto (casou por um sobrenome só)
            # desce. sorted() é estável, então a relevância do Archive.org
            # continua valendo como desempate.
            if mode == 'autor':
                terms = [t for t in query.lower().split() if len(t) > 2]

                def _creator_text(doc: Dict) -> str:
                    creator = doc.get('creator') or ''
                    if isinstance(creator, list):
                        creator = ' '.join(str(c) for c in creator)
                    return str(creator).lower()

                docs = sorted(docs, key=lambda d: 0 if terms and all(
                    t in _creator_text(d) for t in terms) else 1)

            for doc in docs:
                identifier = doc.get('identifier')
                title = doc.get('title', '')
                
                # Se title for lista, pegar primeiro elemento
                if isinstance(title, list):
                    title = title[0] if title else 'Sem título'
                
                item_url = f"{self.base_url}/details/{identifier}"
                
                # Detectar formato baseado no mediatype ou tentar obter detalhes
                format_type = self._detect_archive_format(doc)
                
                # Extrair metadados de volume/capítulo do título
                metadata_parsed = self.parse_volume_chapter(title)

                # Idioma real do item (pode vir como lista).
                doc_lang = doc.get('language')
                if isinstance(doc_lang, list):
                    doc_lang = doc_lang[0] if doc_lang else None

                result = ScrapedResult(
                    title=title,
                    url=item_url,
                    source=self.name,
                    format_type=format_type,
                    volume=metadata_parsed.get('volume'),
                    chapter=metadata_parsed.get('chapter'),
                    number=metadata_parsed.get('number'),
                    series_name=query,
                    language=doc_lang or 'desconhecido',
                    metadata={
                        'identifier': identifier,
                        'creator': doc.get('creator', ''),
                        'year': doc.get('year'),
                        'downloads': doc.get('downloads', 0),
                    }
                )
                results.append(result)
            
            logger.info(f"Archive.org: {len(results)} resultados para '{query}'")
            
        except Exception as e:
            logger.error(f"Erro ao pesquisar no Archive.org: {e}")
        
        return results
    
    def _detect_archive_format(self, doc: Dict) -> str:
        """Detecta formato do item no Archive.org"""
        mediatype = doc.get('mediatype', '').lower()
        
        if mediatype == 'texts':
            # Pode ser PDF, EPUB ou DJVU
            # Tentar inferir pelo título
            title = str(doc.get('title', '')).lower()
            if '.pdf' in title:
                return 'pdf'
            elif '.epub' in title:
                return 'epub'
            elif '.djvu' in title:
                return 'djvu'
            return 'pdf'  # Padrão para textos
        elif 'image' in mediatype:
            return 'cbz'
        
        return 'unknown'
    
    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """
        Obtém informações detalhadas de um item
        Inclui lista de arquivos disponíveis para download

        Args:
            series_url: URL do item no formato https://archive.org/details/{identifier}
            language: não aplicável ao Archive.org, mantido por compatibilidade de assinatura

        Returns:
            Dict com informações do item e arquivos disponíveis
        """
        try:
            # Extrair identifier da URL
            identifier = series_url.rstrip('/').split('/')[-1]
            
            # Obter metadados via API
            metadata_url = f"{self.base_url}/metadata/{identifier}"
            response = self.make_request(metadata_url)
            
            if not response:
                return {}
            
            data = response.json()
            metadata = data.get('metadata', {})
            files = data.get('files', [])
            
            # Só arquivos de livro/quadrinho de verdade (evita .jpg/.xml/etc.).
            book_exts = ('.pdf', '.epub', '.djvu', '.cbz', '.cbr', '.mobi', '.txt')
            downloadable_files = []
            for file in files:
                name = file.get('name', '')
                if name.lower().endswith(book_exts):
                    downloadable_files.append({
                        'name': name,
                        'size': file.get('size', 0),
                        'format': name.rsplit('.', 1)[-1].lower(),
                        'url': f"{self.base_url}/download/{identifier}/{name}"
                    })
            # Prefere PDF, depois EPUB, depois o resto.
            _priority = {'pdf': 0, 'epub': 1, 'djvu': 2, 'cbz': 3, 'cbr': 4, 'mobi': 5, 'txt': 6}
            downloadable_files.sort(key=lambda f: _priority.get(f['format'], 9))
            
            # Extrair informações de volume/capítulo
            title = metadata.get('title', '')
            if isinstance(title, list):
                title = title[0]
            
            metadata_parsed = self.parse_volume_chapter(title)
            
            return {
                'identifier': identifier,
                'title': title,
                'creator': metadata.get('creator', ''),
                'description': metadata.get('description', ''),
                'year': metadata.get('year'),
                'language': metadata.get('language', ''),
                'volume': metadata_parsed.get('volume'),
                'chapter': metadata_parsed.get('chapter'),
                'total_files': len(downloadable_files),
                'download_url': downloadable_files[0]['url'] if downloadable_files else None,
                'format': downloadable_files[0]['format'] if downloadable_files else 'unknown',
                'available_chapters': [{
                    'chapter': metadata_parsed.get('chapter') or 1,
                    'volume': metadata_parsed.get('volume') or 1,
                    'title': title,
                    'download_url': downloadable_files[0]['url'] if downloadable_files else None,
                    'format': downloadable_files[0]['format'] if downloadable_files else 'unknown',
                }] if downloadable_files else [],
                'downloadable_files': downloadable_files,
                'url': series_url
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter informações do item: {e}")
            return {}
    
    def get_download_url(self, identifier: str, filename: str) -> str:
        """
        Constrói URL direta para download de um arquivo
        
        Args:
            identifier: ID do item no Archive.org
            filename: Nome do arquivo
        
        Returns:
            URL direta para download
        """
        return f"{self.base_url}/download/{identifier}/{filename}"
