# 🗺️ ROADMAP DE IMPLEMENTAÇÃO - MEDIA BOT PT-BR

## Visão Geral
Implementação real e funcional substituindo mockups por scrapers verdadeiros, downloads reais e integração com fontes pt-br.

---

## 📦 MÓDULOS PRINCIPAIS

### Módulo 1: Sistema de Scrapers (SEMANA 1)
- [x] 1.1 Criar classe base `BaseScraper`
- [ ] 1.2 Implementar scraper para sites pt-br
  - [ ] MangaDex (API oficial)
  - [ ] Nyaa.si (torrents)
  - [ ] Archive.org (domínio público)
  - [ ] Project Gutenberg (livros)
  - [ ] Sci-Hub (artigos científicos)
- [ ] 1.3 Sistema de plugins carregáveis dinamicamente
- [ ] 1.4 Rate limiting inteligente por domínio
- [ ] 1.5 Retry com backoff exponencial

### Módulo 2: Downloads Reais (SEMANA 1-2)
- [ ] 2.1 Download manager com retry
- [ ] 2.2 Verificação de integridade (hash)
- [ ] 2.3 Resume de downloads interrompidos
- [ ] 2.4 Download concorrente (asyncio)
- [ ] 2.5 Progresso em tempo real (tqdm)

### Módulo 3: Detecção de Último Volume (SEMANA 2)
- [ ] 3.1 Integração com APIs de metadados
  - [ ] Jikan API (MyAnimeList)
  - [ ] AniList API
  - [ ] ComicVine API
- [ ] 3.2 Web scraping de páginas oficiais
- [ ] 3.3 Cache de metadados
- [ ] 3.4 Detecção de lançamentos novos

### Módulo 4: Organização Avançada (SEMANA 2-3)
- [ ] 4.1 Estrutura de diretórios inteligente
- [ ] 4.2 Renomeação automática de arquivos
- [ ] 4.3 Extração de metadados de PDF/EPUB
- [ ] 4.4 Geração de thumbnails
- [ ] 4.5 Exportação para Komga/Kavita

### Módulo 5: Monitoramento (SEMANA 3)
- [ ] 5.1 Watchlist de séries
- [ ] 5.2 Notificações de novos capítulos
- [ ] 5.3 Polling automático (configurável)
- [ ] 5.4 Webhook para Discord/Telegram

### Módulo 6: Interface e CLI (SEMANA 3-4)
- [ ] 6.1 CLI avançada com Rich
- [ ] 6.2 Configuração via YAML/JSON
- [ ] 6.3 Logs estruturados
- [ ] 6.4 Dashboard web opcional (FastAPI)

---

## 🎯 PRIORIDADE ATUAL (MVP - 2 SEMANAS)

1. **Scrapers funcionais** (MangaDex + Archive.org)
2. **Downloads reais** com retry e verificação
3. **Detecção automática** do último volume
4. **Rate limiting** para evitar bloqueios

---

## 📝 CRITÉRIOS DE ACEITAÇÃO

- [ ] Scrapers retornam dados reais (não mockups)
- [ ] Downloads são salvos em disco corretamente
- [ ] Hash verification funciona
- [ ] Rate limiting respeita limites dos sites
- [ ] Detecta automaticamente último volume
- [ ] Organiza coleção sem intervenção manual
- [ ] Relatório mostra status real da coleção

---

## ⚠️ CONSIDERAÇÕES LEGAIS

- Respeitar robots.txt de cada site
- Implementar delays entre requisições
- Não contornar paywalls ou proteções
- Focar em conteúdo de domínio público ou APIs oficiais
- Adicionar disclaimer de responsabilidade ao usuário

---

**Status:** Em implementação
**Última atualização:** 2025
