"""
Módulo 3.2: Normalizer & Parser
Responsável por extrair e padronizar números de volumes/capítulos de strings brutas.
Lida com variações como "Vol. 01", "Volume 1", "v.1", "Capítulo 15", "Ch.10.5".
"""

import re
from typing import Optional, Tuple, List
from dataclasses import dataclass

@dataclass
class ParsedMetadata:
    volume_number: Optional[float]
    chapter_number: Optional[float]
    title: Optional[str]
    format_detected: Optional[str]

class ContentNormalizer:
    """Classe estática para normalização de metadados de conteúdo."""

    # Regex patterns robustos
    PATTERNS_VOLUME = [
        r'volume\s*#?\s*(\d+(?:\.\d+)?)',
        r'vol\.?\s*(\d+(?:\.\d+)?)',
        r'v\.?\s*(\d+(?:\.\d+)?)',
        r'tomo\s*#?\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*º?\s*volume',
    ]

    PATTERNS_CHAPTER = [
        r'cap(?:[íi]tulo)?\s*#?\s*(\d+(?:\.\d+)?)',
        r'cap\.?\s*(\d+(?:\.\d+)?)',
        r'ch\.?\s*(\d+(?:\.\d+)?)',
        r'episode\s*#?\s*(\d+(?:\.\d+)?)',
        r'ep\.?\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*º?\s*cap(?:[íi]tulo)?',
        r'^(\d+(?:\.\d+)?)', # Fallback: número no início da string
    ]

    FORMAT_MAP = {
        '.pdf': 'pdf',
        '.epub': 'epub',
        '.cbz': 'cbz',
        '.cbr': 'cbr',
        '.zip': 'cbz', # Assume CBZ se for zip de imagens
    }

    @classmethod
    def extract_volume(cls, text: str) -> Optional[float]:
        """Extrai número do volume de uma string."""
        if not text:
            return None
        
        text_lower = text.lower()
        for pattern in cls.PATTERNS_VOLUME:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    @classmethod
    def extract_chapter(cls, text: str) -> Optional[float]:
        """Extrai número do capítulo de uma string."""
        if not text:
            return None
        
        text_lower = text.lower()
        for pattern in cls.PATTERNS_CHAPTER:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    @classmethod
    def detect_format(cls, filename: str) -> Optional[str]:
        """Detecta formato do arquivo pela extensão."""
        if not filename:
            return None
        
        ext = '.' + filename.split('.')[-1].lower()
        return cls.FORMAT_MAP.get(ext)

    @classmethod
    def parse_filename(cls, filename: str) -> ParsedMetadata:
        """Analisa um nome de arquivo e extrai todos os metadados possíveis."""
        vol = cls.extract_volume(filename)
        chap = cls.extract_chapter(filename)
        fmt = cls.detect_format(filename)
        
        # Tenta limpar o título removendo números e extensões
        title = filename
        if fmt:
            title = title.replace('.' + filename.split('.')[-1], '')
        
        return ParsedMetadata(
            volume_number=vol,
            chapter_number=chap,
            title=title.strip(),
            format_detected=fmt
        )

    @classmethod
    def normalize_title(cls, title: str) -> str:
        """Padroniza títulos para busca (minúsculas, sem acentos, espaços extras)."""
        import unicodedata
        if not title:
            return ""
        
        # Remove acentos
        normalized = unicodedata.normalize('NFD', title)
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        
        # Lowercase e limpa espaços
        return re.sub(r'\s+', ' ', normalized.lower()).strip()

    @classmethod
    def find_missing_sequence(cls, existing_numbers: List[float]) -> List[float]:
        """Dada uma lista de números existentes, retorna quais estão faltando na sequência."""
        if not existing_numbers:
            return []
        
        sorted_nums = sorted(set(existing_numbers))
        if not sorted_nums:
            return []
            
        start = sorted_nums[0]
        end = sorted_nums[-1]
        
        # Gera sequência completa esperada
        full_sequence = []
        current = start
        while current <= end:
            full_sequence.append(current)
            current += 1.0 if current.is_integer() else 0.5 # Lida com meio-capítulos
            
        # Encontra diferença
        missing = [x for x in full_sequence if x not in sorted_nums]
        return missing
