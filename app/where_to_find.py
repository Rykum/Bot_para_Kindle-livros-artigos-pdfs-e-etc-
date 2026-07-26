#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"Onde encontrar" — o que fazer quando nenhuma fonte tem o arquivo.

A auditoria de fontes (docs/AUDITORIA_FONTES.md) concluiu que o gargalo da
biblioteca não é falta de fonte, é direito autoral: nenhum acervo aberto
distribui lançamento recente. Então, em vez de devolver lista vazia, o app
aponta onde a obra pode estar legalmente — emprestada, lida online ou comprada.

É o mesmo padrão que o app já usa para capítulo externo do MangaDex: quando não
dá para baixar, entrega o link em vez de falhar calado.

Este módulo não faz rede: monta endereços de busca determinísticos, que abrem no
navegador do usuário. Assim ele nunca é motivo de lentidão nem de erro.
"""

from typing import List, Dict, Optional
from urllib.parse import quote_plus


#: Destinos fixos. `tipo` serve para a interface agrupar/ícone.
def _destinos(termo_url: str, idioma: Optional[str]) -> List[Dict[str, str]]:
    destinos = [
        {
            'nome': 'Open Library',
            'tipo': 'emprestimo',
            'descricao': 'Empréstimo digital gratuito, se houver exemplar disponível.',
            'url': f'https://openlibrary.org/search?q={termo_url}',
        },
        {
            'nome': 'Internet Archive',
            'tipo': 'emprestimo',
            'descricao': 'Empréstimo por 1 hora ou 14 dias, com conta gratuita.',
            'url': f'https://archive.org/search?query={termo_url}',
        },
        {
            'nome': 'HathiTrust',
            'tipo': 'leitura',
            'descricao': 'Leitura completa quando a obra é de domínio público.',
            'url': f'https://catalog.hathitrust.org/Search/Home?lookfor={termo_url}&type=all',
        },
        {
            'nome': 'Google Livros',
            'tipo': 'leitura',
            'descricao': 'Prévia de trechos e indicação de onde comprar.',
            'url': f'https://www.google.com/search?tbm=bks&q={termo_url}',
        },
        {
            'nome': 'WorldCat',
            'tipo': 'catalogo',
            'descricao': 'Bibliotecas físicas perto de você que têm o exemplar.',
            'url': f'https://search.worldcat.org/search?q={termo_url}',
        },
    ]

    # Destinos brasileiros só fazem sentido para busca em português.
    if (idioma or '').lower() in ('', 'pt', 'pt-br'):
        destinos.append({
            'nome': 'Estante Virtual',
            'tipo': 'compra',
            'descricao': 'Sebos brasileiros — costuma ter esgotado e usado.',
            'url': f'https://www.estantevirtual.com.br/busca?q={termo_url}',
        })

    return destinos


def onde_encontrar(titulo: str, autor: Optional[str] = None,
                   idioma: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Monta a lista de lugares onde procurar uma obra que não está disponível
    para download em nenhuma fonte.

    Args:
        titulo: o que o usuário procurou
        autor: acrescentado à busca quando conhecido, para desambiguar
        idioma: 'pt'/'pt-br' habilita destinos brasileiros

    Returns:
        Lista de dicts {nome, tipo, descricao, url}; vazia se não houver termo.
    """
    termo = ' '.join(p for p in [(titulo or '').strip(), (autor or '').strip()] if p)
    if not termo:
        return []
    return _destinos(quote_plus(termo), idioma)
