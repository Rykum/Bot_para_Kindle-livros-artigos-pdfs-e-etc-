#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Classe Base para Scrapers - Sistema Modular inspirado no Tachiyomi
Define contrato e funcionalidades comuns para todos os scrapers
"""

import logging
import time
import hashlib
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import requests
from urllib.parse import urljoin, urlparse
import json
import re

logger = logging.getLogger(__name__)


@dataclass
class ScrapedResult:
    """Resultado padronizado de scraping"""
    title: str
    url: str
    source: str
    format_type: str  # pdf, epub, cbz, cbr
    volume: Optional[int] = None
    chapter: Optional[int] = None
    number: Optional[str] = None
    series_name: str = ""
    language: str = "pt-br"
    file_size: Optional[int] = None
    download_url: Optional[str] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RateLimiter:
    """Rate limiter inteligente por domínio"""
    
    def __init__(self):
        self.domains = {}  # domain -> last_request_time
        self.delays = {
            'default': 1.0,
            'mangadex.org': 2.0,
            'archive.org': 1.5,
            'gutenberg.org': 2.0,
            'nyaa.si': 3.0,
        }
    
    def wait(self, url: str):
        """Espera o tempo necessário antes de fazer requisição"""
        domain = urlparse(url).netloc
        delay = self.delays.get(domain, self.delays['default'])
        
        if domain in self.domains:
            elapsed = time.time() - self.domains[domain]
            if elapsed < delay:
                sleep_time = delay - elapsed
                logger.debug(f"Rate limit: aguardando {sleep_time:.2f}s para {domain}")
                time.sleep(sleep_time)
        
        self.domains[domain] = time.time()


class BaseScraper(ABC):
    """
    Classe abstrata base para todos os scrapers
    Implementa funcionalidades comuns e define contrato
    """
    
    def __init__(self, name: str, base_url: str, language: str = "pt-br"):
        self.name = name
        self.base_url = base_url
        self.language = language
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': f'{language},pt;q=0.9,en;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
        self.rate_limiter = RateLimiter()
        self.timeout = 30
        self.max_retries = 3
        self.retry_backoff = 2.0  # Backoff exponencial
        
    @abstractmethod
    def search(self, query: str, formats: List[str] = None) -> List[ScrapedResult]:
        """
        Pesquisa por título/serie
        Deve ser implementado por cada scraper específico
        """
        pass
    
    @abstractmethod
    def get_series_info(self, series_url: str) -> Dict:
        """
        Obtém informações da série (último volume, total de capítulos, etc)
        Deve ser implementado por cada scraper específico
        """
        pass
    
    def make_request(self, url: str, params: Dict = None, retries: int = 0) -> Optional[requests.Response]:
        """
        Faz requisição HTTP com retry e rate limiting
        """
        try:
            # Aplicar rate limiting
            self.rate_limiter.wait(url)
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            if retries < self.max_retries:
                wait_time = self.retry_backoff ** retries
                logger.warning(f"Tentativa {retries + 1} falhou para {url}: {e}. Aguardando {wait_time}s")
                time.sleep(wait_time)
                return self.make_request(url, params, retries + 1)
            else:
                logger.error(f"Falha após {self.max_retries} tentativas para {url}: {e}")
                return None
    
    def parse_volume_chapter(self, text: str) -> Dict:
        """
        Extrai volume, capítulo e número de texto
        Padrões comuns em português
        """
        result = {'volume': None, 'chapter': None, 'number': None}
        
        # Volume patterns
        volume_patterns = [
            r'volume\s*(\d+)',
            r'vol\.?\s*(\d+)',
            r'v(\d+)',
            r'tomo\s*(\d+)',
        ]
        
        for pattern in volume_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['volume'] = int(match.group(1))
                break
        
        # Chapter patterns
        chapter_patterns = [
            r'cap(?:ítulo)?\s*(\d+)',
            r'ch\.?\s*(\d+)',
            r'c(\d+)',
            r'episode\s*(\d+)',
        ]
        
        for pattern in chapter_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['chapter'] = int(match.group(1))
                break
        
        # Number pattern (#)
        number_match = re.search(r'#(\d+)', text)
        if number_match:
            result['number'] = number_match.group(1)
        
        return result
    
    def detect_format(self, url: str, title: str = "") -> str:
        """Detecta formato do arquivo baseado na URL ou título"""
        url_lower = url.lower()
        title_lower = title.lower()
        
        for fmt in ['pdf', 'epub', 'cbz', 'cbr']:
            if f'.{fmt}' in url_lower or f'.{fmt}' in title_lower:
                return fmt
        
        # Detectar por caminho na URL
        if '/pdf/' in url_lower:
            return 'pdf'
        elif '/epub/' in url_lower:
            return 'epub'
        elif '/cbz/' in url_lower or '/cbr/' in url_lower:
            return 'cbz'
        
        return 'unknown'
    
    def calculate_hash(self, content: bytes) -> str:
        """Calcula hash SHA256 do conteúdo para verificação"""
        return hashlib.sha256(content).hexdigest()
    
    def get_file_size(self, url: str) -> Optional[int]:
        """Obtém tamanho do arquivo via HEAD request"""
        try:
            self.rate_limiter.wait(url)
            response = self.session.head(url, timeout=10)
            content_length = response.headers.get('Content-Length')
            if content_length:
                return int(content_length)
        except Exception as e:
            logger.debug(f"Não foi possível obter tamanho do arquivo: {e}")
        return None
    
    def to_dict(self) -> Dict:
        """Serializa scraper para dict"""
        return {
            'name': self.name,
            'base_url': self.base_url,
            'language': self.language,
            'type': self.__class__.__name__
        }
