# Bot de Pesquisa e Organização de Mídia

Bot em Python para pesquisar e organizar coleções de mangás, livros, artigos, manhwas e HQs em português do Brasil (pt-br).

## Funcionalidades

- ✅ Pesquisa por títulos em múltiplos formatos (PDF, EPUB, CBZ, CBR)
- ✅ Detecção automática de volumes, capítulos e numeração
- ✅ Busca por coleção completa (do volume/capítulo 1 ao último lançado)
- ✅ Organização automática da coleção com verificação de continuidade
- ✅ Identificação de itens faltantes
- ✅ Estrutura de diretórios organizada por tipo e série
- ✅ Banco de dados JSON para persistência das coleções
- ✅ Relatórios detalhados de status da coleção

## Inspiração

Este bot foi inspirado no funcionamento do **MangaFlix**, que centraliza mangás em português do Brasil organizando do capítulo 1 até o mais atual lançado.

## Instalação

```bash
# Instalar dependências
pip install -r requirements.txt
```

## Configuração Opcional (Google Custom Search API)

Para habilitar pesquisas via Google:

1. Crie um arquivo `.env` na raiz do projeto
2. Adicione suas credenciais:

```env
GOOGLE_API_KEY=sua_api_key_aqui
GOOGLE_CX=seu_cx_aqui
```

## Uso Básico

### Exemplo 1: Buscar série completa (estilo MangaFlix)

```python
from media_bot import MediaBot

bot = MediaBot()

# Buscar Dandadan completo (do cap. 1 ao último)
collection = bot.search_complete_series("Dandadan", media_type="manga")
```

### Exemplo 2: Buscar intervalo específico

```python
# Buscar One Piece do volume 1 ao 100
collection = bot.search_and_download(
    series_name="One Piece",
    media_type="manga",
    from_volume=1,
    to_volume=100
)
```

### Exemplo 3: Adicionar item manualmente

```python
# Adicionar um item encontrado manualmente
bot.add_manual_item(
    series_name="Batman",
    media_type="hq",
    title="Batman Volume 1.pdf",
    url="https://exemplo.com/batman-vol-1.pdf",
    volume=1,
    format_type="pdf"
)
```

### Exemplo 4: Verificar status de coleção

```python
# Verificar se há itens faltantes
status = bot.get_collection_status("Dandadan")
if status:
    print(f"Completa: {status.complete}")
    print(f"Itens faltantes: {status.missing_items}")
```

## Estrutura de Diretórios Gerada

```
collections/
├── collection_database.json    # Banco de dados das coleções
├── manga/
│   └── dandadan/
│       ├── volume_001/
│       ├── volume_002/
│       ├── capitulo_015/
│       └── ...
├── hq/
│   └── batman/
│       └── ...
└── manhwa/
    └── solo_leveling/
        └── ...
```

## Formatos Suportados

- 📄 **PDF** - Livros, mangás, artigos
- 📖 **EPUB** - E-books
- 📚 **CBZ/CBR** - Quadrinhos digitais, mangás

## Tipos de Mídia

- `manga` - Mangás japoneses
- `livro` - Livros e romances
- `hq` - Histórias em quadrinhos ocidentais
- `manhwa` - Quadrinhos coreanos
- `artigo` - Artigos e papers acadêmicos

## Métodos Principais

| Método | Descrição |
|--------|-----------|
| `search_complete_series(name, type)` | Busca série completa do 1º ao último item |
| `search_and_download(name, type, from, to)` | Busca intervalo específico |
| `add_manual_item(...)` | Adiciona item manualmente |
| `list_all_collections()` | Lista todas as coleções |
| `get_collection_status(name)` | Obtém status de uma coleção |
| `find_missing_items(name)` | Retorna itens faltantes |

## Recursos Avançados

### Detecção Automática de Metadados

O bot extrai automaticamente informações dos títulos:

- `"Dandadan Volume 1.pdf"` → volume: 1
- `"Dandadan Capítulo 15.cbz"` → chapter: 15
- `"One Piece #100.pdf"` → number: "100"

### Padrões Reconhecidos

**Volumes:**
- `Volume 1`, `Vol. 1`, `V1`, `Tomo 1`

**Capítulos:**
- `Capítulo 15`, `Cap 15`, `Ch. 15`, `C15`, `Episode 15`

**Numeração:**
- `#100`, `#45A`

## Executando o Bot

```bash
python media_bot.py
```

## Interface Gráfica (Desktop)

A interface oficial agora é uma janela desktop moderna (pywebview):

```bash
py -3.13 -m pip install -r requirements.txt
py -3.13 desktop.py
```

Abas disponíveis:
- **Dashboard** — totais da biblioteca (séries, itens, completas, faltantes)
- **Buscar** — pesquisa em todas as fontes com resultados em cards
- **Biblioteca** — cards visuais por série com capa, progresso, status e exportação Komga/Kavita
- **Downloads** — progresso e log em tempo real
- **Ferramentas** — limpar cache e status do grafo

Para gerar o executável clicável (`dist/MediaBot.exe`):

```bash
py -3.13 build.py
```

> A GUI antiga em Tkinter foi preservada em `legacy/gui_app.py`.

## CLI

O bot agora possui uma interface de linha de comando simples:

```bash
# Buscar uma série em todas as fontes
python media_bot.py search "Dandadan" --media-type manga

# Baixar uma série completa
python media_bot.py download "Dandadan" --media-type manga --source mangadex

# Ver status de uma coleção
python media_bot.py status "Dandadan"

# Listar biblioteca local
python media_bot.py library

# Limpar cache local
python media_bot.py cache-clear

# Ver resumo do grafo gerado pelo graphify
python media_bot.py graph-status
```

## Logs

Os logs são salvos em `media_bot.log` e também exibidos no console.

## Personalização

### Ajustar Delay de Pesquisa

```python
bot = MediaBot()
bot.searcher.search_delay = 2.0  # Aumentar delay para 2 segundos
```

### Adicionar Novos Formatos

```python
bot.supported_formats.extend([txt, mobi])
```

## Notas Importantes

⚠️ **Aviso Legal**: Este bot é uma ferramenta de organização e pesquisa. Certifique-se de baixar apenas conteúdo disponível legalmente e respeite os direitos autorais.

⚠️ **Scraping**: A implementação atual é um esqueleto funcional. Para produção, você precisará implementar scrapers específicos para cada site fonte, respeitando seus termos de uso e robots.txt.

## Próximos Passos Sugeridos

1. Implementar scrapers específicos para sites de sua preferência
2. Adicionar suporte a download automático de arquivos
3. Integrar com APIs de serviços legítimos
4. Adicionar interface web ou GUI
5. Implementar busca por OCR em imagens
6. Adicionar suporte a metadados avançados (autor, editora, ano)

## Licença

Use este código de forma responsável e ética.
