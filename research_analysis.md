# 🔬 PESQUISA PROFUNDA: BOTS DE MANGÁ/HQ E PROJETOS SIMILARES

## 1. ANÁLISE DE PROJETOS NO GITHUB

### Projetos Populares de Download/Organização de Mangás

#### 1.1 Manga-DL (e variantes)
- **Repositórios similares:** `manga-dl`, `mangadex-dl`, `comic-dl`
- **Funcionalidades comuns:**
  - Scraping de sites de mangá
  - Download em CBZ/PDF
  - Organização por volume/capítulo
  - Suporte a múltiplas fontes
- **Pontos fortes observados:**
  - Arquitetura modular com plugins por site
  - Cache inteligente para evitar re-download
  - CLI bem documentada
- **Lições aplicáveis:**
  - Implementar sistema de plugins para novos sources
  - Adicionar cache baseado em hash de conteúdo
  - Criar CLI intuitiva com auto-complete

#### 1.2 Komga/Kavita (Servidores de Mídia)
- **Tipo:** Servidores self-hosted para leitura
- **Funcionalidades:**
  - Organização automática de bibliotecas
  - Metadados via APIs (ComicVine, MyAnimeList)
  - Leitor web integrado
  - Multi-usuário com progresso de leitura
- **Lições aplicáveis:**
  - Integrar com APIs de metadados
  - Estruturar pastas no padrão compatível
  - Considerar exportação para estes formatos

#### 1.3 HakuNeko / Hakuneko
- **Tipo:** Aplicativo desktop (Electron + Node.js)
- **Diferenciais:**
  - +400 fontes suportadas
  - Sistema de plugins extensível
  - Downloads paralelos
  - Filtros avançados de busca
- **Arquitetura interessante:**
  ```
  Core -> Connector (site-specific) -> Scraper -> Downloader
  ```
- **Lições aplicáveis:**
  - Separar lógica genérica de scrapers específicos
  - Implementar sistema de conectores plugináveis
  - Adicionar downloads paralelos com controle de concorrência

#### 1.4 Paperback (iOS) e Tachiyomi (Android)
- **Tipo:** Apps móveis de leitura
- **Modelo:** Extensões/comunidade
  - Core app mínimo
  - Extensões feitas pela comunidade para cada fonte
  - Atualizações automáticas de capítulos
- **Lições aplicáveis:**
  - Criar API clara para extensões de terceiros
  - Permitir que usuários compartilhem scrapers
  - Sistema de update automático de séries monitoradas

---

## 2. PADRÕES ARQUITETURAIS IDENTIFICADOS

### 2.1 Arquitetura Modular (Mais Comum)
```
┌─────────────────────────────────────────┐
│           Core Engine                   │
│  - Gerenciamento de filas               │
│  - Persistência                         │
│  - Rate limiting                        │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│Source │ │Source │ │Source │
│ A     │ │ B     │ │ C     │
└───────┘ └───────┘ └───────┘
```

### 2.2 Pipeline de Processamento
```
Busca → Parser → Filtro → Download → Verificação → Organização
```

### 2.3 Padrões de Design Comuns
- **Strategy Pattern:** Para diferentes fontes de scraping
- **Observer Pattern:** Para notificações de novos capítulos
- **Factory Pattern:** Para criação de scrapers dinâmicos
- **Repository Pattern:** Para abstração de persistência

---

## 3. TÉCNICAS DE SCRAPING EFICIENTES

### 3.1 Evitando Bloqueios
- **User-Agent Rotation:** Mudar UA a cada N requests
- **Delay Exponencial:** Aumentar delay após falhas
- **Proxy Rotation:** Usar pools de proxies residenciais
- **Session Management:** Manter cookies/sessões quando necessário
- **Headless Browsers:** Para sites com JavaScript pesado

### 3.2 Padrões de URL Comuns (Sites PT-BR)
```
Site A: site.com/manga/{nome}/capitulo-{num}
Site B: site.com/ler/{nome}-{volume}-{capitulo}
Site C: site.com/mangas/{slug}/{cap}/{pagina}
```

### 3.3 Seletores CSS/XPath Frequentes
```css
/* Imagens das páginas */
img.chapter-page, .page-image, #current-img

/* Lista de capítulos */
ul.chapters li, .chapter-list a, #episode-list

/* Next/Prev */
a.next-chapter, .nav-next, button[rel="next"]

/* Título */
h1.manga-title, .series-name, h2.chapter-title
```

---

## 4. COMUNIDADES E FÓRUNS ATIVOS

### 4.1 Reddit
- r/mangapiracy - Discussões sobre ferramentas
- r/selfhosted - Servidores como Komga/Kavita
- r/opendirectories - Fontes de conteúdo

### 4.2 Discord
- Servidores de leitores de mangá
- Comunidades de desenvolvimento de bots
- Grupos de compartilhamento de ferramentas

### 4.3 Fóruns Especializados
- Anime-Planet Forums
- MyAnimeList Clubs
- Fóruns brasileiros (Adoro Cinema, Jovem Nerd)

### 4.4 GitHub Topics
- `#manga-downloader`
- `#comic-scraper`
- `#ebook-management`

---

## 5. APIs ÚTEIS PARA INTEGRAÇÃO

### 5.1 Metadados
| API | Uso | Auth | Rate Limit |
|-----|-----|------|------------|
| Jikan (MyAnimeList) | Info de mangás | Não | 3 req/min |
| AniList | Info + tracking | OAuth | 90 req/min |
| ComicVine | HQs ocidentais | API Key | 100 req/day |
| Google Books | Livros | API Key | 1000 req/day |
| OpenLibrary | Livros públicos | Não | Generoso |

### 5.2 Busca
| API | Uso | Custo |
|-----|-----|-------|
| Google Custom Search | Busca geral | Gratis até 100/dia |
| Bing Search API | Alternativa Google | $15/milhão |
| SerpAPI | Google scraping | Pago |

---

## 6. DESAFIOS ESPECÍFICOS PARA PT-BR

### 6.1 Sites Populares no Brasil
- Mangás Online (vários domínios espelho)
- Lê Mangá
- União dos Quadrinhos
- Grupos de Telegram/Facebook
- Fóruns como Babo e afins

### 6.2 Particularidades
- **Traduções informais:** Títulos variam muito
- **Scans diferentes:** Mesma obra em múltiplas scanlators
- **Qualidade inconsistente:** Desde OCR ruim até edições profissionais
- **Hospedagem volátil:** Sites mudam de domínio frequentemente

### 6.3 Estratégias
- Buscar por múltiplos nomes/títulos alternativos
- Priorizar scans conhecidas pela qualidade
- Verificar comentários/feedback da comunidade
- Manter lista atualizada de domínios ativos

---

## 7. FEATURES DIFERENCIADAS SUGERIDAS

### 7.1 Baseado em Análise Competitiva
1. **Comparador de Scans:** Mostrar opções disponíveis por capítulo
2. **Detector de Qualidade:** Analisar resolução, limpeza, tradução
3. **Agregador de Fontes:** Unificar busca em múltiplos sites
4. **Tracker de Lançamentos:** Monitorar sites por novos caps
5. **Backup Automático:** Salvar em múltiplos locais (local + cloud)

### 7.2 Inovações Potenciais
1. **ML para Detecção de Páginas:** Identificar páginas duplas, coloridas, etc.
2. **Tradução Automática:** Integrar DeepL/Google Translate para obras não-traduzidas
3. **OCR Inteligente:** Extrair texto de imagens para busca interna
4. **Recomendação:** Sugerir obras similares baseado na coleção
5. **Social Features:** Compartilhar coleções, listas de desejos

---

## 8. LIÇÕES DE PROJETOS FAILIDOS

### Problemas Comuns Observados
1. **Dependência de single source:** Site sai do ar → projeto morre
2. **Sem manutenção:** Scrapers quebram com mudanças de layout
3. **Performance ruim:** Downloads lentos, sem paralelismo
4. **UX pobre:** CLI confusa, sem feedback visual
5. **Legal issues:** DMCA takedowns frequentes

### Como Evitar
- ✅ Multiplicar fontes (no mínimo 5-10 sites suportados)
- ✅ Criar testes automatizados para scrapers
- ✅ Implementar downloads paralelos inteligentes
- ✅ Investir em UX (logs claros, progresso visível)
- ✅ Focar em conteúdo legal/domínio público quando possível

---

## 9. TECNOLOGIAS RECOMENDADAS

### Stack Moderna
```
Python 3.10+
├── httpx ou aiohttp (async HTTP)
├── BeautifulSoup4 + lxml (parsing)
├── Playwright (sites JS-heavy)
├── SQLite/PostgreSQL (persistência)
├── Redis (cache e filas)
├── Celery/RQ (background jobs)
├── FastAPI (API REST se necessário)
└── Rich (CLI bonita)
```

### Ferramentas Auxiliares
- **yt-dlp:** Referência de código para downloads
- **calibre:** Manipulação de ebooks
- **kindle-send:** Envio para dispositivos
- **pydantic:** Validação de dados

---

## 10. CHECKLIST DE IMPLEMENTAÇÃO BASEADO EM PESQUISA

### Fase Imitação (copiar o que funciona)
- [ ] Sistema de plugins/connectors
- [ ] Downloads paralelos com limite configurável
- [ ] Cache de URLs já processadas
- [ ] Retry exponencial com backoff
- [ ] User-agent rotation
- [ ] Respeito a robots.txt
- [ ] Extração robusta de metadados
- [ ] Organização no padrão Komga/Kavita

### Fase Diferenciação (inovar)
- [ ] Foco específico em pt-br (nichos não atendidos)
- [ ] Comparador de qualidade entre scans
- [ ] Integração com trackers brasileiros
- [ ] Comunidade de compartilhamento de connectors
- [ ] Interface web simplificada
- [ ] Notificações via Telegram/Discord

### Fase Sustentabilidade
- [ ] Documentação completa em português
- [ ] Testes automatizados CI/CD
- [ ] Sistema de report de bugs integrado
- [ ] Canal de comunicação com usuários
- [ ] Modelo de contribuição clara (open source)

---

**Fontes Consultadas:**
- GitHub Trending (manga downloader keywords)
- Awesome-selfhosted (categoria media management)
- Fóruns de desenvolvimento Python
- Documentação de projetos similares
- Comunidades Reddit/Discord

**Data da Pesquisa:** 2026-07-20
**Próxima Atualização:** Após implementação de scrapers reais
