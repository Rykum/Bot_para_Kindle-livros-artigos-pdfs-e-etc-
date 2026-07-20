# 📋 BRAINSTORM: MELHORIAS PARA O MEDIA BOT PT-BR

## Baseado na auditoria e pesquisa realizada

---

## 🎯 MELHORIAS CRÍTICAS (Implementar Imediatamente)

### 1. Corrigir Loop Infinito de Pesquisa
**Problema:** Bot atual executa pesquisas infinitas sem critério de parada
**Solução:**
```python
# Adicionar limite máximo de iterações
MAX_SEARCH_ITERATIONS = 50
current_iteration = 0

while current_iteration < MAX_SEARCH_ITERATIONS:
    # lógica de busca
    current_iteration += 1
    
    # Critério de parada: encontrou todos os volumes até o último conhecido
    if found_last_volume or no_new_results:
        break
```

### 2. Implementar Scrapers Reais (Prioridade Máxima)
**Arquitetura sugerida:**
```
scrapers/
├── __init__.py
├── base_scraper.py      # Classe abstrata base
├── mangas_online.py     # Scraper específico
├── le_manga.py          # Outro site
└── generic_search.py    # Busca genérica fallback
```

**Interface base:**
```python
from abc import ABC, abstractmethod

class BaseScraper(ABC):
    @abstractmethod
    def search(self, query: str) -> List[SearchResult]:
        pass
    
    @abstractmethod
    def get_chapters(self, series_url: str) -> List[Chapter]:
        pass
    
    @abstractmethod
    def download_chapter(self, chapter_url: str) -> bytes:
        pass
    
    @property
    @abstractmethod
    def site_name(self) -> str:
        pass
```

### 3. Sistema de Rate Limiting Inteligente
```python
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self):
        self.last_request = defaultdict(float)
        self.min_delay = {
            'default': 2.0,
            'mangas-online.com': 3.0,
            'leitura.xyz': 5.0,
        }
    
    def wait_if_needed(self, domain: str):
        now = time.time()
        delay = self.min_delay.get(domain, self.min_delay['default'])
        elapsed = now - self.last_request[domain]
        
        if elapsed < delay:
            time.sleep(delay - elapsed)
        
        self.last_request[domain] = time.time()
```

### 4. Downloads Funcionais com Retry
```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session_with_retry():
    session = requests.Session()
    
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

def download_file(url: str, dest_path: str, chunk_size=8192):
    session = create_session_with_retry()
    
    with session.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        
        total_size = int(r.headers.get('content-length', 0))
        
        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)
    
    # Verificar integridade
    if os.path.getsize(dest_path) == 0:
        raise Exception("Download resulted in empty file")
```

---

## 💡 MELHORIAS DE ARQUITETURA

### 5. Sistema de Plugins/Connectors
**Inspirado no Tachiyomi/HakuNeko:**

```python
# connectors/connector_registry.py
class ConnectorRegistry:
    def __init__(self):
        self.connectors = {}
    
    def register(self, connector_class):
        self.connectors[connector_class.site_name] = connector_class()
    
    def get_connector(self, site_name: str):
        return self.connectors.get(site_name)
    
    def search_all(self, query: str) -> List[SearchResult]:
        results = []
        for connector in self.connectors.values():
            try:
                results.extend(connector.search(query))
            except Exception as e:
                logger.error(f"Error searching {connector.site_name}: {e}")
        return results

# Uso:
registry = ConnectorRegistry()
registry.register(MangasOnlineConnector())
registry.register(LeMangaConnector())

results = registry.search_all("Dandadan")
```

### 6. Cache de Resultados
```python
import hashlib
import json
from pathlib import Path

class SearchCache:
    def __init__(self, cache_dir="./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_cache_key(self, query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()
    
    def get(self, query: str, max_age_hours=24):
        key = self._get_cache_key(query)
        cache_file = self.cache_dir / f"{key}.json"
        
        if not cache_file.exists():
            return None
        
        # Verificar idade do cache
        age = time.time() - cache_file.stat().st_mtime
        if age > max_age_hours * 3600:
            return None
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def set(self, query: str, data: dict):
        key = self._get_cache_key(query)
        cache_file = self.cache_dir / f"{key}.json"
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
```

### 7. Processamento Assíncrono
```python
import asyncio
import aiohttp

async def download_chapters_async(chapters: List[Chapter], max_concurrent=5):
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async with aiohttp.ClientSession() as session:
        tasks = [
            download_single_chapter(session, chapter, semaphore)
            for chapter in chapters
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
    return results

async def download_single_chapter(session, chapter, semaphore):
    async with semaphore:
        try:
            # Download logic here
            await asyncio.sleep(0)  # Yield control
            return {"chapter": chapter, "success": True}
        except Exception as e:
            return {"chapter": chapter, "success": False, "error": str(e)}
```

---

## 🎨 MELHORIAS DE UX/UI

### 8. CLI Melhorada com Rich
```python
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.table import Table

console = Console()

def show_collection_table(collection: SeriesCollection):
    table = Table(title=f"Coleção: {collection.series_name}")
    
    table.add_column("Tipo", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Completo", justify="center")
    table.add_column("Faltantes", justify="right")
    
    status_style = "green" if collection.complete else "yellow"
    
    table.add_row(
        collection.media_type,
        str(collection.total_items),
        "[green]SIM[/green]" if collection.complete else "[yellow]NÃO[/yellow]",
        f"[red]{len(collection.missing_items)}[/red]",
        style=status_style
    )
    
    console.print(table)

def download_progress():
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        task = progress.add_task("Baixando...", total=100)
        
        # Update progress during download
        for i in range(0, 101, 10):
            progress.update(task, completed=i)
```

### 9. Logs Estruturados (JSON)
```python
import logging
import json
from pythonjsonlogger import jsonlogger

def setup_json_logging():
    logger = logging.getLogger()
    logHandler = logging.FileHandler("media_bot.json.log")
    
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(filename)s %(lineno)d",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)

# Uso:
logger.info("Download iniciado", extra={
    "series": "Dandadan",
    "chapter": 15,
    "format": "cbz",
    "source": "mangas-online"
})
```

### 10. Menu Interativo
```python
from InquirerPy import inquirer

def interactive_menu():
    while True:
        action = inquirer.select(
            message="O que deseja fazer?",
            choices=[
                "Buscar série completa",
                "Buscar intervalo específico",
                "Ver coleções salvas",
                "Verificar itens faltantes",
                "Configurações",
                "Sair"
            ]
        ).execute()
        
        if action == "Sair":
            break
        elif action == "Buscar série completa":
            series = inquirer.text(message="Nome da série:").execute()
            media_type = inquirer.select(
                message="Tipo:",
                choices=["manga", "hq", "manhwa", "livro"]
            ).execute()
            
            bot.search_complete_series(series, media_type)
```

---

## 🔧 FEATURES AVANÇADAS

### 11. Monitoramento de Novos Capítulos
```python
class SeriesMonitor:
    def __init__(self, db_path="monitored_series.json"):
        self.db_path = Path(db_path)
        self.monitored = self.load_monitored()
    
    def add_series(self, series_name: str, last_chapter: int):
        self.monitored[series_name] = {
            "last_chapter": last_chapter,
            "last_check": datetime.now().isoformat(),
            "notify": True
        }
        self.save()
    
    def check_updates(self) -> Dict[str, List[int]]:
        updates = {}
        
        for series_name, info in self.monitored.items():
            # Buscar últimos capítulos
            latest = bot.get_latest_chapters(series_name)
            
            new_chapters = [
                ch for ch in latest 
                if ch.number > info["last_chapter"]
            ]
            
            if new_chapters:
                updates[series_name] = new_chapters
                info["last_chapter"] = max(ch.number for ch in new_chapters)
        
        self.save()
        return updates
    
    def send_notifications(self, updates: Dict[str, List[int]]):
        # Integrar com Telegram/Discord webhook
        for series, chapters in updates.items():
            message = f"📢 Novos capítulos de {series}: {chapters}"
            send_telegram_message(message)
```

### 12. Comparador de Qualidade de Scans
```python
from PIL import Image
import io

class ScanQualityAnalyzer:
    def analyze(self, image_bytes: bytes) -> dict:
        img = Image.open(io.BytesIO(image_bytes))
        
        return {
            "resolution": img.size,
            "aspect_ratio": img.size[0] / img.size[1],
            "avg_brightness": self.calculate_brightness(img),
            "is_color": self.is_color_image(img),
            "estimated_quality": self.estimate_quality(img)
        }
    
    def estimate_quality(self, img) -> str:
        width, height = img.size
        
        if width >= 1600:
            return "Alta"
        elif width >= 1000:
            return "Média"
        else:
            return "Baixa"
    
    def compare_sources(self, chapter_urls: List[str]) -> str:
        qualities = []
        
        for url in chapter_urls:
            img_data = download_first_page(url)
            quality = self.analyze(img_data)
            qualities.append({
                "source": url,
                "quality": quality
            })
        
        # Retornar melhor qualidade
        best = max(qualities, key=lambda x: x["quality"]["resolution"][0])
        return best["source"]
```

### 13. Integração com APIs de Metadados
```python
class MetadataEnricher:
    def __init__(self):
        self.jikan_url = "https://api.jikan.moe/v4"
        self.anilist_url = "https://graphql.anilist.co"
    
    def get_manga_info(self, title: str) -> dict:
        # Buscar no Jikan (MyAnimeList)
        search_url = f"{self.jikan_url}/manga?q={quote(title)}"
        
        response = requests.get(search_url)
        data = response.json()
        
        if data.get('data'):
            manga = data['data'][0]
            return {
                "title": manga.get('title'),
                "alternative_titles": manga.get('titles', []),
                "status": manga.get('status'),
                "chapters": manga.get('chapters'),
                "volumes": manga.get('volumes'),
                "score": manga.get('score'),
                "synopsis": manga.get('synopsis'),
                "cover_image": manga.get('images', {}).get('jpg', {}).get('large_image_url')
            }
        
        return None
    
    def enrich_collection(self, collection: SeriesCollection):
        info = self.get_manga_info(collection.series_name)
        
        if info:
            print(f"\n📊 Informações da série:")
            print(f"   Status: {info['status']}")
            print(f"   Capítulos totais: {info['chapters'] or 'Desconhecido'}")
            print(f"   Volumes: {info['volumes'] or 'Desconhecido'}")
            print(f"   Score MAL: {info['score'] or 'N/A'}")
            
            # Atualizar coleção com info
            if info['chapters']:
                expected_chapters = set(range(1, info['chapters'] + 1))
                current_chapters = {item.chapter for item in collection.items if item.chapter}
                
                missing = expected_chapters - current_chapters
                print(f"   Faltam {len(missing)} capítulos para completar")
```

### 14. Exportação para Servidores de Mídia
```python
class MediaServerExporter:
    def export_to_komga_format(self, collection: SeriesCollection):
        """Organiza no padrão esperado pelo Komga"""
        base_path = Path("./exports/komga") / collection.series_name
        
        for item in collection.items:
            if item.volume:
                dir_name = f"Volume {item.volume:03d}"
            elif item.chapter:
                dir_name = f"Chapter {item.chapter:03d}"
            else:
                continue
            
            target_dir = base_path / dir_name
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Copiar/mover arquivo
            if item.download_path:
                src = Path(item.download_path)
                dst = target_dir / src.name
                
                if src.exists():
                    shutil.copy(src, dst)
        
        print(f"✅ Coleção exportada para {base_path}")
        print(f"   Pronto para importar no Komga/Kavita")
```

---

## 📊 MONITORAMENTO E MÉTRICAS

### 15. Dashboard de Estatísticas
```python
def generate_stats_dashboard():
    stats = {
        "total_collections": len(bot.list_all_collections()),
        "total_items": sum(c.total_items for c in bot.list_all_collections()),
        "complete_collections": sum(1 for c in bot.list_all_collections() if c.complete),
        "missing_items_total": sum(len(c.missing_items) for c in bot.list_all_collections()),
        "formats": defaultdict(int),
        "sources": defaultdict(int)
    }
    
    for collection in bot.list_all_collections():
        for item in collection.items:
            stats["formats"][item.format_type] += 1
            stats["sources"][item.source] += 1
    
    # Exibir dashboard
    console.print(Panel(generate_stats_table(stats), title="📊 Estatísticas"))
```

### 16. Health Check de Sources
```python
class SourceHealthChecker:
    def __init__(self):
        self.results = {}
    
    def check_all_sources(self) -> dict:
        sources = [
            "mangas-online.com",
            "le-manga.net",
            # ... outros sources
        ]
        
        for source in sources:
            start_time = time.time()
            
            try:
                # Testar conexão básica
                response = requests.get(f"https://{source}", timeout=10)
                
                self.results[source] = {
                    "status": "online" if response.status_code == 200 else "error",
                    "response_time": time.time() - start_time,
                    "status_code": response.status_code,
                    "last_check": datetime.now().isoformat()
                }
            except Exception as e:
                self.results[source] = {
                    "status": "offline",
                    "error": str(e),
                    "last_check": datetime.now().isoformat()
                }
        
        return self.results
    
    def get_working_sources(self) -> List[str]:
        return [
            source for source, info in self.results.items()
            if info["status"] == "online"
        ]
```

---

## 🚀 ROADMAP DE IMPLEMENTAÇÃO

### Semana 1-2: Fundamentos
- [ ] Implementar sistema de scrapers modulares
- [ ] Criar 3-5 scrapers funcionais para sites pt-br
- [ ] Adicionar downloads com retry
- [ ] Implementar rate limiting
- [ ] Criar cache de buscas

### Semana 3-4: Robustez
- [ ] Adicionar processamento assíncrono
- [ ] Implementar logs estruturados
- [ ] Criar testes automatizados
- [ ] Adicionar health checks
- [ ] Melhorar tratamento de erros

### Semana 5-6: UX
- [ ] Implementar CLI com Rich
- [ ] Criar menu interativo
- [ ] Adicionar barras de progresso
- [ ] Melhorar relatórios visuais
- [ ] Documentação completa

### Semana 7-8: Features Avançadas
- [ ] Monitoramento de novos capítulos
- [ ] Integração com APIs de metadados
- [ ] Exportação para Komga/Kavita
- [ ] Notificações Telegram/Discord
- [ ] Comparador de qualidade

### Semana 9-10: Polimento
- [ ] Otimização de performance
- [ ] Refatoração de código
- [ ] Testes de carga
- [ ] Beta testing com usuários
- [ ] Lançamento versão 1.0

---

## 📝 PRIORIZAÇÃO FINAL

| Prioridade | Feature | Impacto | Esforço |
|------------|---------|---------|---------|
| 🔴 ALTA | Scrapers reais | Crítico | Alto |
| 🔴 ALTA | Downloads funcionais | Crítico | Médio |
| 🔴 ALTA | Rate limiting | Importante | Baixo |
| 🟡 MÉDIA | Cache | Bom | Baixo |
| 🟡 MÉDIA | CLI melhorada | Bom | Médio |
| 🟡 MÉDIA | Processamento async | Ótimo | Alto |
| 🟢 BAIXA | Notificações | Legal | Médio |
| 🟢 BAIXA | Comparador qualidade | Nice-to-have | Alto |

---

**Documento criado:** 2026-07-20  
**Baseado em:** Auditoria de tarefas + Pesquisa de projetos similares  
**Próxima ação:** Implementar scrapers modulares (Task 4)
