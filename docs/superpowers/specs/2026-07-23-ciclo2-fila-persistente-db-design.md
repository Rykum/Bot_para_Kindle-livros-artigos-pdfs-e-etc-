# Ciclo 2 — Refactor do DB + Fila de downloads persistente + UI

**Data:** 2026-07-23
**Status:** Aprovado para implementação
**Base:** branch `feat/desktop-ip` (PR #2). Decorre do [BRAINSTORM_MELHORIAS_V2.md](../../../BRAINSTORM_MELHORIAS_V2.md) (A2 + C1 + B3).
**Escopo confirmado:** inclui o refactor do singleton do DB.

## 1. Objetivo

Transformar a aba Downloads num **gerenciador de fila** de verdade, com controle por item e persistência entre sessões, e limpar a dívida técnica do DB que a sustenta:
1. **B3 — DB sem singleton global compartilhado:** introduzir `session_scope()` (context manager) e dar ao `LibraryManager` **sessão própria por instância** (fim da `Session` global mutável compartilhada). O código novo (fila) usa `session_scope()` por operação.
2. **A2 — Fila persistente:** tabela `download_jobs`; enfileirar uma série expande em **1 linha por capítulo**; retomável entre sessões.
3. **C1 — UI de gerenciador:** a aba Downloads mostra a fila com estado por item e ações (cancelar/re-tentar/remover), pausar fila e limpar concluídos.

Não-objetivos: migração total do `LibraryManager` para session-per-operation (risco de objetos ORM detached — fica para depois); downloads concorrentes (Ciclo 3); favoritos/auto-update (Ciclo 3).

## 2. Contexto (código atual)

- `database.py`: `DatabaseManager` cria `self.session` **única** e há um singleton global `db_manager`. `reset_db()` existe.
- `library_manager.py`: `LibraryManager.__init__` faz `self.session = db_manager.get_session()` (a global). Métodos retornam objetos ORM (Series/Chapter).
- `media_bot.py`: `from database import db_manager, Series`; `cleanup()` chama `db_manager.close()`. `download_complete_series` tem rodadas de retry + fallback por capítulo (via `_attempt_chapter`).
- `app/bot_service.py`: worker serial (`submit`/`run_sync`), `is_cancelled(job_id)`.
- `app/api.py`: `download_series` submete UM job que baixa tudo sequencialmente.
- `frontend/`: aba Downloads = barra de progresso + log + botão cancelar (1 download por vez).

## 3. Design

### 3.1 B3 — DB: `session_scope()` + sessão própria

`database.py`:
- Manter `engine` global (thread-safe) e `SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)`.
- Adicionar `@contextmanager session_scope()`: cria `SessionLocal()`, `yield`, `commit` no sucesso, `rollback` na exceção, `close` no fim.
- `DatabaseManager` deixa de expor uma `self.session` compartilhada; `get_session()` passa a retornar `SessionLocal()` (uma nova). `reset_db()` continua (drop/create no engine).
- Manter o objeto `db_manager` para compatibilidade de import, mas sem sessão global mutável.

`library_manager.py`:
- `__init__`: `self.session = db_manager.get_session()` agora dá uma sessão **própria**; `cleanup()`: `self.session.close()`. (Objetos ORM continuam ligados a essa sessão — padrão de retorno inalterado.)
- `expire_on_commit=False` evita que os objetos retornados fiquem "expirados" após commit.

`media_bot.py`:
- `cleanup()`: só `self.library.cleanup()` (remover `db_manager.close()`).

`tests/conftest.py`: `reset_db()` continua isolando; poderá ser simplificado, mas mantém o comportamento.

### 3.2 Modelo `DownloadJob` (`database.py`)

```python
class DownloadJob(Base):
    __tablename__ = 'download_jobs'
    id = Column(Integer, primary_key=True)
    series = Column(String, nullable=False)
    source = Column(String, default='mangadex')
    media_type = Column(String, default='manga')
    chapter_number = Column(Float, nullable=True)  # None = série inteira (faltantes)
    language = Column(String, default='pt-br')
    fallback_language = Column(String, nullable=True)
    status = Column(String, default='queued')  # queued/downloading/done/failed/cancelled
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 3.3 `download_queue.py` — `DownloadQueue`

Usa `session_scope()` por operação (retorna **dicts**, não objetos ORM):
- `enqueue(series, chapters, source, media_type, language, fallback) -> List[int]` — 1 linha por capítulo (ou 1 linha `chapter_number=None` se `chapters` for None = "todos os faltantes").
- `list_items(limit=500) -> List[dict]` — todos os itens, mais recentes/estado.
- `next_queued() -> Optional[dict]` — próximo `queued` (FIFO por id).
- `mark(job_id, status, error=None) -> None`.
- `cancel_item(job_id)`, `retry_item(job_id)` (volta a `queued`), `remove_item(job_id)`, `clear_finished()` (remove done/cancelled).

### 3.4 Runner da fila (`app/api.py` + `media_bot.py`)

- `MediaBot.download_single_chapter(series, chapter_num, source, media_type, language, fallback_language, should_cancel, progress_callback, series_meta) -> bool` — reaproveita a lógica de rodadas de retry + fallback + ComicInfo para **um** capítulo (extrair `_download_one_chapter_with_retries` de `download_complete_series`; ambos passam a usá-lo).
- **Api.enqueue(...)**: grava na fila via `DownloadQueue.enqueue`, emite `queue_update`, e **submete um "drain job"** ao `BotService` se nenhum estiver ativo.
- **Drain job** (roda no worker serial): laço `while not paused: item = queue.next_queued(); if not item: break; mark downloading + emit; ok = baixar item (single chapter, honrando should_cancel do item); mark done/failed + emit`. Um item `chapter_number=None` chama `download_complete_series` (comportamento atual) para aquela série.
- **Cancelamento por item**: `cancel_item(id)` marca `cancelled` (se `queued`, o runner pula; se `downloading`, o `should_cancel` do item para o download). **Pausa global**: flag no `BotService`/Api; o runner encerra após o item atual e re-inicia no `resume`.

### 3.5 Api de fila

`enqueue`, `queue_list` (sync), `cancel_item(id)`, `retry_item(id)`, `remove_item(id)`, `clear_finished()`, `pause_queue()`, `resume_queue()`. Eventos: `queue_update` (empurrado a cada mudança de item).

### 3.6 UI — aba Downloads como gerenciador

- Lista da fila: cada item com série + capítulo, **badge de estado** (fila/baixando/ok/falhou/cancelado), barra do item em download, e ações por item (**cancelar** / **re-tentar** / **remover**).
- Barra de topo: **Pausar/Retomar fila**, **Limpar concluídos**, contador (`N na fila · M concluídos · K falharam`).
- O botão "Baixar" do seletor de capítulos passa a **enfileirar** (`enqueue`) em vez de disparar um download único; a UI vai para a aba Downloads mostrando a fila.
- Mantém o log ao vivo. Aplica Nielsen: visibilidade de estado (#1), controle/liberdade (#3), recuperação de erro (#9 — item falho tem "re-tentar").

## 4. Testes

- **B3**: `session_scope()` commita no sucesso e faz rollback na exceção (com um modelo de teste); dois `LibraryManager` têm sessões independentes; `MediaBot.cleanup()` não fecha uma sessão global compartilhada.
- **DownloadQueue**: `enqueue` cria N linhas (1/capítulo); `next_queued` FIFO; `mark`/`cancel`/`retry`/`remove`/`clear_finished` corretos; `enqueue(chapters=None)` cria 1 linha `chapter_number=None`.
- **Runner**: com um `MediaBot` fake, o drain processa a fila em ordem, marca done/failed, respeita pausa e cancel por item; item `None` chama a série inteira.
- **download_single_chapter**: baixa 1 capítulo com retry (fake) e retorna sucesso; falha após rodadas retorna False.
- **Api**: `enqueue` grava + emite `queue_update` + inicia drain; `queue_list` retorna os itens; `cancel_item`/`retry_item`/`remove_item`/`clear_finished`/`pause`/`resume`.
- **Frontend**: asserções estáticas (view de fila, botões, `queue_update`, enqueue no seletor); `node --check`.

## 5. Arquivos tocados

`database.py` (session_scope + DownloadJob), `library_manager.py` (sessão própria), `media_bot.py` (cleanup + single-chapter), novo `download_queue.py`, `app/api.py` (fila + drain), `app/bot_service.py` (flag de pausa, se necessário), `frontend/index.html`+`app.js`+`styles.css` (UI de fila), testes em `tests/`.

## 6. Riscos

| Risco | Mitigação |
|-------|-----------|
| Refactor do DB quebrar objetos ORM retornados | `expire_on_commit=False` + sessão própria por instância (não migrar LibraryManager p/ session-per-op agora) |
| Drain job concorrente duplicado | Api garante 1 drain ativo (flag); enqueue só inicia se não houver |
| Item `downloading` órfão após crash | No start, itens `downloading` remanescentes voltam a `queued` (auto-recuperação) |
| Fila e download_complete_series divergirem | Ambos usam o mesmo `_download_one_chapter_with_retries` |
| UI de fila pesada com muitos itens | `list_items(limit=500)`; render simples; `clear_finished` |
