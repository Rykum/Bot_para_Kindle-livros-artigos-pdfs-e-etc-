"""Taxonomia de gêneros por tipo de mídia.

Curada de propósito: os nomes ficam em português, a hierarquia é estável e o
módulo não faz rede — dá para testar sem API. Os UUIDs das tags do MangaDex
NÃO ficam aqui; são resolvidos em execução (ver mangadex_scraper._tag_ids).

O vocabulário de assunto das fontes de livro é inglês: medido, `science fiction`
devolve 90.804 obras e `ficção científica` devolve 14.
"""

import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Genero:
    nome: str
    subgeneros: Tuple[str, ...] = ()
    mangadex_tag: Optional[str] = None
    openlibrary: Optional[str] = None
    gutendex: Optional[str] = None
    archive: Optional[str] = None


_MANGA = (
    Genero("Ação", ("Artes marciais", "Samurais", "Militar"), mangadex_tag="Action"),
    Genero("Aventura", ("Sobrevivência", "Viagem no tempo"), mangadex_tag="Adventure"),
    Genero("Comédia", ("Paródia", "Fatia de vida"), mangadex_tag="Comedy"),
    Genero("Drama", ("Tragédia", "Psicológico"), mangadex_tag="Drama"),
    Genero("Fantasia", ("Isekai", "Magia", "Demônios"), mangadex_tag="Fantasy"),
    Genero("Terror", ("Fantasmas", "Monstros", "Psicológico"), mangadex_tag="Horror"),
    Genero("Mistério", ("Detetive", "Crime"), mangadex_tag="Mystery"),
    Genero("Romance", ("Harém", "Escolar"), mangadex_tag="Romance"),
    Genero("Ficção científica", ("Mechas", "Realidade virtual", "Aliens"), mangadex_tag="Sci-Fi"),
    Genero("Esportes", ("Artes marciais",), mangadex_tag="Sports"),
    Genero("Histórico", ("Samurais", "Militar"), mangadex_tag="Historical"),
    Genero("Sobrenatural", ("Demônios", "Fantasmas", "Magia"), mangadex_tag="Supernatural"),
)

_LIVRO = (
    Genero("Ficção científica", ("Distopia", "Space opera", "Cyberpunk"),
           openlibrary="science fiction", gutendex="science fiction"),
    Genero("Terror", ("Gótico", "Sobrenatural"),
           openlibrary="horror", gutendex="horror"),
    Genero("Romance", ("Histórico", "Contemporâneo"),
           openlibrary="romance", gutendex="love stories"),
    Genero("Mistério", ("Policial", "Suspense"),
           openlibrary="detective and mystery stories", gutendex="detective"),
    Genero("Fantasia", ("Épica", "Contos de fadas"),
           openlibrary="fantasy", gutendex="fantasy"),
    Genero("Poesia", ("Épica", "Lírica"),
           openlibrary="poetry", gutendex="poetry"),
    Genero("Filosofia", ("Ética", "Metafísica"),
           openlibrary="philosophy", gutendex="philosophy"),
    Genero("História", ("Brasil", "Antiguidade"),
           openlibrary="history", gutendex="history"),
    Genero("Biografia", ("Memórias",),
           openlibrary="biography", gutendex="biography"),
    Genero("Aventura", ("Viagem", "Náutica"),
           openlibrary="adventure stories", gutendex="adventure"),
)

# Grade pequena de propósito. Medido em collection:comics: `superhero` trouxe
# X-Men e Spider-Man; `horror` trouxe Berserk (mangá) e `romance` derivou.
# Acrescentar gênero aqui EXIGE medir antes — ver §5.3 da spec.
_HQ = (
    Genero("Super-heróis", (), archive="superhero"),
)

GENEROS_POR_MIDIA: Dict[str, Tuple[Genero, ...]] = {
    "manga": _MANGA,
    "manhwa": _MANGA,      # mesma taxonomia; muda só o idioma de origem
    "livro": _LIVRO,
    "hq": _HQ,
}


def _dobra(texto: str) -> str:
    """Minúsculas sem acento, para casar 'FICCAO' com 'Ficção'."""
    plano = unicodedata.normalize("NFKD", str(texto or "").lower())
    return "".join(c for c in plano if not unicodedata.combining(c)).strip()


def generos_de(media_type: str) -> Tuple[Genero, ...]:
    return GENEROS_POR_MIDIA.get((media_type or "").strip().lower(), ())


def genero_por_nome(media_type: str, nome: str) -> Optional[Genero]:
    alvo = _dobra(nome)
    for g in generos_de(media_type):
        if _dobra(g.nome) == alvo:
            return g
    return None
