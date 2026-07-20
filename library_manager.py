"""
Módulo 3.3: Library Manager
Orquestra a lógica de negócio: busca no DB, identifica faltantes, 
registra novos downloads e gera relatórios de coleção.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import and_
from database import db_manager, Series, Volume, Chapter, MediaFile
from normalizer import ContentNormalizer
from datetime import datetime

class LibraryManager:
    """Gerenciador de biblioteca local e detecção de itens faltantes."""

    def __init__(self):
        self.session = db_manager.get_session()
        self.normalizer = ContentNormalizer()

    # --- CRUD: SÉRIES ---
    def get_or_create_series(self, title: str, source_name: str = 'unknown', 
                             source_id: Optional[str] = None) -> Series:
        """Obtém série existente ou cria nova se não existir."""
        normalized_title = self.normalizer.normalize_title(title)
        
        # Busca por título normalizado
        series = self.session.query(Series).filter(
            Series.title.ilike(f'%{normalized_title}%')
        ).first()

        if not series:
            series = Series(
                title=title,
                source_name=source_name,
                source_id=source_id,
                language='pt-br',
                status='unknown'
            )
            self.session.add(series)
            self.session.commit()
            self.session.refresh(series)
        
        return series

    def update_series_info(self, series: Series, **kwargs):
        """Atualiza metadados da série."""
        for key, value in kwargs.items():
            if hasattr(series, key) and value is not None:
                setattr(series, key, value)
        series.updated_at = datetime.utcnow()
        self.session.commit()

    # --- CRUD: VOLUMES & CAPÍTULOS ---
    def add_chapter(self, series: Series, volume_num: float, chapter_num: float,
                    title: Optional[str] = None, external_id: Optional[str] = None) -> Chapter:
        """Adiciona um capítulo à biblioteca (registro lógico)."""
        
        # Busca ou cria volume
        volume = self.session.query(Volume).filter(
            and_(Volume.series_id == series.id, Volume.volume_number == volume_num)
        ).first()

        if not volume:
            volume = Volume(
                series_id=series.id,
                volume_number=volume_num,
                title=f"Volume {volume_num}"
            )
            self.session.add(volume)
            self.session.commit()
            self.session.refresh(volume)

        # Busca se capítulo já existe
        chapter = self.session.query(Chapter).filter(
            and_(Chapter.volume_id == volume.id, Chapter.chapter_number == chapter_num)
        ).first()

        if not chapter:
            chapter = Chapter(
                volume_id=volume.id,
                chapter_number=chapter_num,
                title=title,
                external_id=external_id
            )
            self.session.add(chapter)
            self.session.commit()
            self.session.refresh(chapter)

        return chapter

    def register_download(self, chapter: Chapter, file_path: str, 
                          file_format: str, file_size: int, 
                          sha256_hash: str) -> MediaFile:
        """Registra um arquivo baixado com sucesso no banco."""
        
        media_file = MediaFile(
            chapter_id=chapter.id,
            file_path=file_path,
            file_format=file_format,
            file_size=file_size,
            sha256_hash=sha256_hash,
            download_status='completed',
            downloaded_at=datetime.utcnow()
        )
        self.session.add(media_file)
        self.session.commit()
        return media_file

    # --- CONSULTAS E RELATÓRIOS ---
    def get_series_progress(self, series: Series) -> Dict[str, Any]:
        """Retorna estatísticas de progresso da série."""
        volumes = self.session.query(Volume).filter(Volume.series_id == series.id).all()
        
        total_chapters_db = 0
        downloaded_chapters = 0
        chapter_numbers = []

        for vol in volumes:
            chapters = self.session.query(Chapter).filter(Chapter.volume_id == vol.id).all()
            for chap in chapters:
                total_chapters_db += 1
                chapter_numbers.append(chap.chapter_number)
                
                files = self.session.query(MediaFile).filter(
                    MediaFile.chapter_id == chap.id,
                    MediaFile.download_status == 'completed'
                ).all()
                if files:
                    downloaded_chapters += 1

        missing = []
        if chapter_numbers:
            missing = self.normalizer.find_missing_sequence(chapter_numbers)

        return {
            'title': series.title,
            'status': series.status,
            'total_volumes_registered': len(volumes),
            'total_chapters_registered': total_chapters_db,
            'chapters_downloaded': downloaded_chapters,
            'completion_percentage': (downloaded_chapters / total_chapters_db * 100) if total_chapters_db > 0 else 0,
            'missing_chapters': missing,
            'is_complete': len(missing) == 0 and total_chapters_db > 0
        }

    def find_missing_chapters(self, series: Series, available_online: List[float]) -> List[float]:
        """Compara capítulos disponíveis online com os baixados localmente."""
        # Obtém capítulos já baixados
        volumes = self.session.query(Volume).filter(Volume.series_id == series.id).all()
        downloaded_chapters = set()

        for vol in volumes:
            chapters = self.session.query(Chapter).filter(Chapter.volume_id == vol.id).all()
            for chap in chapters:
                files = self.session.query(MediaFile).filter(
                    MediaFile.chapter_id == chap.id,
                    MediaFile.download_status == 'completed'
                ).all()
                if files:
                    downloaded_chapters.add(chap.chapter_number)

        # Retorna o que está disponível online mas não foi baixado
        missing = [chap for chap in available_online if chap not in downloaded_chapters]
        return sorted(missing)

    def list_all_series(self) -> List[Series]:
        """Lista todas as séries na biblioteca."""
        return self.session.query(Series).order_by(Series.title).all()

    def cleanup(self):
        """Fecha sessão do banco."""
        self.session.close()
