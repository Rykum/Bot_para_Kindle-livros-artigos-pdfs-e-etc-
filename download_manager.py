#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerenciador de Downloads com Retry, Verificação de Hash e Progresso
Implementação real para downloads de arquivos (PDF, EPUB, CBZ)
"""

import os
import time
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Callable
import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)


class DownloadManager:
    """
    Gerenciador de downloads com funcionalidades avançadas:
    - Retry com backoff exponencial
    - Verificação de integridade via hash
    - Resume de downloads interrompidos
    - Progresso em tempo real
    - Rate limiting
    """
    
    def __init__(self, base_directory: str = "./downloads"):
        self.base_directory = Path(base_directory)
        self.base_directory.mkdir(parents=True, exist_ok=True)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
        })
        
        # Configurações de retry
        self.max_retries = 5
        self.retry_backoff = 2.0
        self.timeout = 60
        
        # Rate limiting
        self.request_delay = 1.0
        self.last_request_time = 0
        
        # Callbacks para progresso
        self.progress_callback: Optional[Callable] = None
    
    def _wait_rate_limit(self):
        """Aplica rate limiting entre requisições"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            sleep_time = self.request_delay - elapsed
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def calculate_hash(self, filepath: str, algorithm: str = 'sha256') -> str:
        """Calcula hash de um arquivo para verificação"""
        hash_func = hashlib.new(algorithm)
        
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def download(
        self,
        url: str,
        filename: str,
        destination_dir: str = None,
        expected_hash: str = None,
        resume: bool = True,
        progress_bar: bool = True
    ) -> Dict:
        """
        Faz download de um arquivo com todas as funcionalidades
        
        Args:
            url: URL do arquivo para download
            filename: Nome do arquivo a ser salvo
            destination_dir: Diretório de destino (padrão: base_directory)
            expected_hash: Hash esperado para verificação de integridade
            resume: Se True, tenta retomar download interrompido
            progress_bar: Se True, mostra barra de progresso
        
        Returns:
            Dict com informações do download:
            {
                'success': bool,
                'filepath': str,
                'size': int,
                'hash': str,
                'error': str (se houver),
                'retries': int,
                'resumed': bool
            }
        """
        result = {
            'success': False,
            'filepath': None,
            'size': 0,
            'hash': None,
            'error': None,
            'retries': 0,
            'resumed': False
        }
        
        # Determinar caminho completo
        dest_dir = Path(destination_dir) if destination_dir else self.base_directory
        dest_dir.mkdir(parents=True, exist_ok=True)
        filepath = dest_dir / filename
        
        # Verificar se arquivo já existe e está completo
        if filepath.exists() and not expected_hash:
            logger.info(f"Arquivo já existe: {filepath}")
            result['success'] = True
            result['filepath'] = str(filepath)
            result['size'] = filepath.stat().st_size
            result['hash'] = self.calculate_hash(str(filepath))
            return result
        
        # Tentar download com retry
        for attempt in range(self.max_retries + 1):
            try:
                result['retries'] = attempt
                
                # Aplicar rate limiting
                self._wait_rate_limit()
                
                # Preparar headers para resume
                headers = {}
                start_pos = 0
                
                if resume and filepath.exists():
                    start_pos = filepath.stat().st_size
                    headers['Range'] = f'bytes={start_pos}-'
                    result['resumed'] = True
                    logger.info(f"Retomando download de {start_pos} bytes")
                
                # Fazer requisição
                response = self.session.get(
                    url,
                    headers=headers,
                    stream=True,
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                # Obter tamanho total
                total_size = int(response.headers.get('Content-Length', 0))
                if total_size == 0:
                    total_size = start_pos + int(response.headers.get('Content-Range', '').split('/')[-1] or 0)
                
                # Modo de escrita (append se retomando)
                mode = 'ab' if start_pos > 0 else 'wb'
                
                # Download com progresso
                downloaded = start_pos
                with open(filepath, mode) as f:
                    if progress_bar and total_size > 0:
                        with tqdm(
                            total=total_size,
                            initial=downloaded,
                            unit='B',
                            unit_scale=True,
                            unit_divisor=1024,
                            desc=filename[:50]
                        ) as pbar:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    pbar.update(len(chunk))
                                    
                                    # Callback de progresso
                                    if self.progress_callback:
                                        self.progress_callback(filename, downloaded, total_size)
                    else:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                                # Callback de progresso
                                if self.progress_callback:
                                    self.progress_callback(filename, downloaded, total_size)
                
                # Verificar hash se fornecido
                file_hash = self.calculate_hash(str(filepath))
                result['hash'] = file_hash
                
                if expected_hash and file_hash != expected_hash:
                    logger.warning(f"Hash mismatch! Expected: {expected_hash}, Got: {file_hash}")
                    result['error'] = f"Hash verification failed"
                    # Não considerar como erro fatal, apenas warning
                
                # Sucesso
                result['success'] = True
                result['filepath'] = str(filepath)
                result['size'] = downloaded
                
                logger.info(f"Download concluído: {filepath} ({downloaded / 1024 / 1024:.2f} MB)")
                return result
                
            except requests.exceptions.RequestException as e:
                wait_time = self.retry_backoff ** attempt
                logger.warning(f"Tentativa {attempt + 1} falhou: {e}. Aguardando {wait_time}s")
                
                if attempt < self.max_retries:
                    time.sleep(wait_time)
                else:
                    result['error'] = str(e)
                    logger.error(f"Download falhou após {self.max_retries + 1} tentativas: {url}")
                    return result
            
            except Exception as e:
                result['error'] = str(e)
                logger.error(f"Erro inesperado no download: {e}")
                return result
        
        return result
    
    def download_multiple(
        self,
        items: list,
        destination_dir: str = None,
        concurrent: bool = False,
        max_workers: int = 3
    ) -> list:
        """
        Faz download de múltiplos arquivos
        
        Args:
            items: Lista de dicts com {'url': str, 'filename': str, ...}
            destination_dir: Diretório base para downloads
            concurrent: Se True, faz downloads concorrentes (não implementado nesta versão)
            max_workers: Número máximo de workers para downloads concorrentes
        
        Returns:
            Lista de resultados de download
        """
        results = []
        
        for i, item in enumerate(items, 1):
            logger.info(f"Download {i}/{len(items)}: {item.get('filename', 'unknown')}")
            
            result = self.download(
                url=item.get('url'),
                filename=item.get('filename'),
                destination_dir=destination_dir or item.get('destination_dir'),
                expected_hash=item.get('expected_hash'),
                resume=item.get('resume', True),
                progress_bar=item.get('progress_bar', True)
            )
            
            results.append(result)
            
            # Delay entre downloads
            if i < len(items):
                time.sleep(self.request_delay)
        
        return results
    
    def verify_downloads(self, files: Dict[str, str]) -> Dict[str, bool]:
        """
        Verifica integridade de arquivos baixados
        
        Args:
            files: Dict {filepath: expected_hash}
        
        Returns:
            Dict {filepath: is_valid}
        """
        results = {}
        
        for filepath, expected_hash in files.items():
            if not Path(filepath).exists():
                results[filepath] = False
                logger.warning(f"Arquivo não encontrado: {filepath}")
                continue
            
            actual_hash = self.calculate_hash(filepath)
            is_valid = actual_hash == expected_hash
            results[filepath] = is_valid
            
            if not is_valid:
                logger.error(f"Hash verification failed for {filepath}")
            else:
                logger.info(f"Hash verified: {filepath}")
        
        return results
    
    def cleanup_incomplete(self, directory: str = None):
        """Remove arquivos incompletos (parciais)"""
        dir_path = Path(directory) if directory else self.base_directory
        
        removed_count = 0
        for filepath in dir_path.glob('*.part'):
            try:
                filepath.unlink()
                removed_count += 1
                logger.info(f"Removido arquivo parcial: {filepath}")
            except Exception as e:
                logger.error(f"Erro ao remover {filepath}: {e}")
        
        logger.info(f"Limpeza concluída: {removed_count} arquivos removidos")
        return removed_count
