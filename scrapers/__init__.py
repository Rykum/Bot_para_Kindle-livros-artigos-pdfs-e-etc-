"""
Sistema de Scrapers Modulares para Media Bot PT-BR
Inspirado na arquitetura do Tachiyomi - plugins carregáveis dinamicamente
"""

from .base_scraper import BaseScraper
from .mangadex_scraper import MangaDexScraper
from .archive_scraper import ArchiveOrgScraper
from .gutenberg_scraper import ProjectGutenbergScraper
from .openlibrary_scraper import OpenLibraryScraper
from .wikisource_scraper import WikisourceScraper
from .oapen_scraper import OapenScraper
from .zenodo_scraper import ZenodoScraper
from .openalex_scraper import OpenAlexScraper
from .arxiv_scraper import ArxivScraper

__all__ = [
    'BaseScraper',
    'MangaDexScraper',
    'ArchiveOrgScraper',
    'ProjectGutenbergScraper',
    'OpenLibraryScraper',
    'WikisourceScraper',
    'OapenScraper',
    'ZenodoScraper',
    'OpenAlexScraper',
    'ArxivScraper'
]
