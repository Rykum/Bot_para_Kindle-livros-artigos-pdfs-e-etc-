#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper para Archive.org (Internet Archive)
https://archive.org/
API: https://archive.org/help/about_search_api.php
Foco: Livros, mangás e HQs de domínio público ou Creative Commons
"""

import logging
from typing import List, Dict, Optional
from .base_scraper import BaseScraper, ScrapedResult

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
    
    def search(self, query: str, formats: List[str] = None) -> List[ScrapedResult]:
        """
        Pesquisa no Internet Archive usando Advanced Search API
        
        Args:
            query: Título ou termo de pesquisa
            formats: Lista de formatos desejados ['pdf', 'epub', 'cbz', etc]
        
        Returns:
            Lista de ScrapedResult com itens encontrados
        """
        if formats is None:
            formats = ['pdf', 'epub', 'djvu']
        
        results = []
        
        try:
            # Construir query para API
            # Focar em conteúdo em português e formatos específicos
            format_query = ' OR '.join([f'mediatype:{fmt}' for fmt in formats])
            
            # Query principal com filtros
            search_query = f'({query}) AND language:(por OR portuguese OR "português")'
            
            params = {
                'q': search_query,
                'fl[]': ['identifier', 'title', 'creator', 'year', 'language', 'mediatype'],
                'sort[]': ['downloads desc'],
                'rows': 50,
                'page': 1,
                'output': 'json',
                'save': 'yes',
                'fields': 'identifier,title,creator,year,language,mediatype,downloads'
            }
            
            response = self.make_request(self.search_api, params=params)
            if not response:
                return results
            
            data = response.json()
            docs = data.get('response', {}).get('docs', [])
            
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
                
                result = ScrapedResult(
                    title=title,
                    url=item_url,
                    source=self.name,
                    format_type=format_type,
                    volume=metadata_parsed.get('volume'),
                    chapter=metadata_parsed.get('chapter'),
                    number=metadata_parsed.get('number'),
                    series_name=query,
                    language='pt-br',
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
            
            # Filtrar arquivos baixáveis (PDF, EPUB, etc)
            downloadable_files = []
            for file in files:
                name = file.get('name', '')
                source = file.get('source', '')
                
                # Apenas arquivos originais ou derivados principais
                if source == 'original' or any(name.endswith(ext) for ext in ['.pdf', '.epub', '.djvu', '.cbz']):
                    downloadable_files.append({
                        'name': name,
                        'size': file.get('size', 0),
                        'format': name.split('.')[-1].lower() if '.' in name else 'unknown',
                        'url': f"{self.base_url}/download/{identifier}/{name}"
                    })
            
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
