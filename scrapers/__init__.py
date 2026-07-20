"""
Sistema de Scrapers Modulares para Media Bot PT-BR
Inspirado na arquitetura do Tachiyomi - plugins carregáveis dinamicamente
"""

from .base_scraper import BaseScraper
from .mangadex_scraper import MangaDexScraper
from .archive_scraper import ArchiveOrgScraper
from .gutenberg_scraper import ProjectGutenbergScraper

__all__ = [
    'BaseScraper',
    'MangaDexScraper',
    'ArchiveOrgScraper',
    'ProjectGutenbergScraper'
]
