#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para Project Gutenberg
https://www.gutenberg.org/
API: https://www.gutenberg.org/ebooks/
Foco: Livros de domínio público em português
"""

import logging
from typing import List, Dict, Optional
from .base_scraper import BaseScraper, ScrapedResult, SourceCapabilities, BOOK_MEDIA

logger = logging.getLogger(__name__)


class ProjectGutenbergScraper(BaseScraper):
    """
    Scraper para Project Gutenberg
    Pesquisa livros clássicos e obras de domínio público em português
    """
    
    def __init__(self):
        super().__init__(
            name="Project Gutenberg",
            base_url="https://www.gutenberg.org",
            language="pt-br"
        )
        self.search_url = "https://gutendex.com/books"
    
    capabilities = SourceCapabilities(media_types=BOOK_MEDIA, explora_genero=True)

    @staticmethod
    def _matches_author(book: Dict, query: str) -> bool:
        """Confere se algum autor do livro bate com os termos buscados."""
        names = ' '.join(a.get('name', '') for a in book.get('authors', [])).lower()
        terms = [t for t in query.lower().split() if len(t) > 2]
        return bool(terms) and all(t in names for t in terms)

    @staticmethod
    def _cover_url(formats):
        """A capa vem no próprio dicionário de formatos, sob uma chave image/*."""
        for mime, url in (formats or {}).items():
            if mime.startswith('image/'):
                return url
        return None

    def _resultados_de(self, params, rotulo_genero=None):
        """Executa a consulta e monta os ScrapedResult. Usado por search e explorar."""
        resultados = []
        try:
            resposta = self.make_request(self.search_url, params=params)
            if not resposta:
                return resultados
            for livro in resposta.json().get('results', []):
                formatos = livro.get('formats', {}) or {}
                download = (formatos.get('application/epub+zip')
                            or formatos.get('application/pdf'))
                if not download:
                    continue
                autores = ', '.join(a.get('name', '') for a in livro.get('authors', []))
                titulo = livro.get('title', 'Sem título')
                resultados.append(ScrapedResult(
                    title=titulo,
                    url=f"{self.base_url}/ebooks/{livro.get('id')}",
                    source=self.name,
                    format_type='epub' if 'epub' in str(download) else 'pdf',
                    series_name=titulo,
                    language=(livro.get('languages') or ['desconhecido'])[0],
                    download_url=download,
                    metadata={
                        'identifier': str(livro.get('id')),
                        'creator': autores,
                        'cover_url': self._cover_url(formatos),
                        'genero': rotulo_genero,
                    },
                ))
        except Exception as e:
            logger.error(f"Erro no Project Gutenberg: {e}")
        return resultados

    def search(self, query: str, formats: List[str] = None, language: str = None,
               search_by: str = "titulo") -> List[ScrapedResult]:
        """
        Pesquisa livros no Project Gutenberg via Gutendex API

        O parâmetro `search` da Gutendex já cobre título E autor, então os três
        modos usam a mesma consulta; em 'autor' os resultados são filtrados
        para manter só os que realmente batem com o nome buscado.

        Args:
            query: Título, autor ou termo de pesquisa
            formats: Lista de formatos desejados ['pdf', 'epub', etc]
            language: Filtra por idioma (pt/en/es); vazio busca em pt,en,es
            search_by: 'titulo' (padrão), 'autor' ou 'tudo'

        Returns:
            Lista de ScrapedResult com livros encontrados
        """
        if formats is None:
            formats = ['epub', 'pdf']

        results = []
        mode = self.normalize_search_by(search_by)

        try:
            # Gutendex API. Idioma escolhido pelo usuário (pt/en/es); sem
            # escolha, busca amplo (pt,en,es) em vez de travar só em português.
            lang = (language or '').lower().replace('pt-br', 'pt')
            params = {
                'search': query,
                'languages': lang if lang in ('pt', 'en', 'es') else 'pt,en,es',
                'sort_by': 'downloads',
            }

            response = self.make_request(self.search_url, params=params)
            if not response:
                return results

            data = response.json()
            books = data.get('results', [])

            for book in books:
                # Em 'autor', descarta o que veio por casar só com o título.
                if mode == 'autor' and not self._matches_author(book, query):
                    continue

                title = book.get('title', 'Sem título')
                book_id = book.get('id')
                authors = book.get('authors', [])
                author_names = ', '.join([a.get('name', '') for a in authors])

                # URLs dos formatos disponíveis
                formats_dict = book.get('formats', {})

                # Verificar formatos disponíveis
                available_formats = []
                download_url = None

                for fmt in formats:
                    if fmt == 'epub':
                        epub_url = formats_dict.get('application/epub+zip')
                        if epub_url:
                            available_formats.append('epub')
                            download_url = epub_url
                    elif fmt == 'pdf':
                        pdf_url = formats_dict.get('application/pdf')
                        if pdf_url:
                            available_formats.append('pdf')
                            if not download_url:
                                download_url = pdf_url

                if not download_url:
                    # Tentar outros formatos se nenhum dos desejados estiver disponível
                    for mime_type, url in formats_dict.items():
                        if 'text' in mime_type or 'ebook' in mime_type:
                            download_url = url
                            break

                if not download_url:
                    continue  # Pular se não houver formato baixável

                book_url = f"{self.base_url}/ebooks/{book_id}"

                # Extrair metadados de volume/capítulo (raro em Gutenberg, mas possível)
                metadata_parsed = self.parse_volume_chapter(title)

                result = ScrapedResult(
                    title=title,
                    url=book_url,
                    source=self.name,
                    format_type=available_formats[0] if available_formats else 'unknown',
                    volume=metadata_parsed.get('volume'),
                    chapter=metadata_parsed.get('chapter'),
                    number=metadata_parsed.get('number'),
                    series_name=query,
                    language='pt-br',
                    file_size=None,  # Gutenberg não fornece size diretamente
                    download_url=download_url,
                    metadata={
                        'book_id': book_id,
                        'authors': author_names,
                        'subjects': book.get('subjects', []),
                        'download_count': book.get('download_count', 0),
                        'available_formats': available_formats,
                    }
                )
                results.append(result)

            logger.info(f"Gutenberg: {len(results)} resultados para '{query}'")

        except Exception as e:
            logger.error(f"Erro ao pesquisar no Project Gutenberg: {e}")

        return results

    def explorar(self, genero, subgenero=None, ordenacao="relevancia"):
        """Lista livros de domínio público de um gênero."""
        if genero is None or not genero.gutendex:
            return []
        return self._resultados_de({
            "topic": genero.gutendex,
            "sort": "popular",
        }, rotulo_genero=genero.nome)

    def get_series_info(self, series_url: str, language: str = "pt-br") -> Dict:
        """
        Obtém informações detalhadas de um livro
        Para Gutenberg, cada livro é geralmente uma obra única

        Args:
            series_url: URL do livro no formato https://www.gutenberg.org/ebooks/{id}
            language: não aplicável ao Gutenberg, mantido por compatibilidade de assinatura

        Returns:
            Dict com informações do livro
        """
        try:
            # Extrair ID da URL
            book_id = series_url.rstrip('/').split('/')[-1]
            
            # Obter detalhes via Gutendex
            book_url = f"https://gutendex.com/books/{book_id}"
            response = self.make_request(book_url)
            
            if not response:
                return {}
            
            book = response.json()
            
            authors = book.get('authors', [])
            author_names = ', '.join([a.get('name', '') for a in authors])
            
            formats_dict = book.get('formats', {})
            available_formats = []
            download_url = None
            
            # Mapear MIME types para formatos
            mime_to_format = {
                'application/epub+zip': 'epub',
                'application/pdf': 'pdf',
                'text/html': 'html',
                'text/plain': 'txt',
            }
            
            for mime_type, url in formats_dict.items():
                if mime_type in mime_to_format:
                    fmt = mime_to_format[mime_type]
                    available_formats.append(fmt)
                    if not download_url:
                        download_url = url
            
            title = book.get('title', '')
            metadata_parsed = self.parse_volume_chapter(title)
            
            return {
                'book_id': book.get('id'),
                'title': title,
                'authors': author_names,
                'language': book.get('languages', []),
                'subjects': book.get('subjects', []),
                'download_count': book.get('download_count', 0),
                'volume': metadata_parsed.get('volume'),
                'chapter': metadata_parsed.get('chapter'),
                'available_formats': available_formats,
                'download_url': download_url,
                'format': available_formats[0] if available_formats else 'unknown',
                'available_chapters': [{
                    'chapter': metadata_parsed.get('chapter') or 1,
                    'volume': metadata_parsed.get('volume') or 1,
                    'title': title,
                    'download_url': download_url,
                    'format': available_formats[0] if available_formats else 'unknown',
                }] if download_url else [],
                'url': series_url
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter informações do livro: {e}")
            return {}
    
    def get_download_url(self, book_id: str, format_type: str = 'epub') -> Optional[str]:
        """
        Constrói URL direta para download de um livro
        
        Args:
            book_id: ID do livro no Gutenberg
            format_type: Formato desejado (epub, pdf, etc)
        
        Returns:
            URL direta para download ou None
        """
        try:
            # Obter informações do livro para encontrar URL correta
            book_url = f"https://gutendex.com/books/{book_id}"
            response = self.make_request(book_url)
            
            if not response:
                return None
            
            book = response.json()
            formats_dict = book.get('formats', {})
            
            # Mapear formato solicitado para MIME type
            format_to_mime = {
                'epub': 'application/epub+zip',
                'pdf': 'application/pdf',
                'html': 'text/html',
                'txt': 'text/plain',
            }
            
            mime_type = format_to_mime.get(format_type)
            if mime_type and mime_type in formats_dict:
                return formats_dict[mime_type]
            
            # Retornar primeiro formato disponível se o solicitado não existir
            for mime, url in formats_dict.items():
                if 'epub' in mime or 'pdf' in mime:
                    return url
            
        except Exception as e:
            logger.error(f"Erro ao obter URL de download: {e}")
        
        return None
