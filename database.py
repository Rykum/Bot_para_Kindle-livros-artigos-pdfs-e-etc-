"""
Módulo 3.1: Database Layer
Gerencia persistência de dados com SQLite e SQLAlchemy.
Modela Séries, Volumes, Capítulos e Arquivos baixados.
"""

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, UniqueConstraint, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "media_bot.db"

Base = declarative_base()

class Series(Base):
    """Tabela mestre de séries/mangás/livros."""
    __tablename__ = 'series'

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, index=True)
    alternative_titles = Column(String) # JSON string ou separado por pipe
    source_id = Column(String) # ID externo (ex: MangaDex UUID)
    source_name = Column(String) # ex: 'mangadex', 'archive'
    language = Column(String, default='pt-br')
    status = Column(String) # 'ongoing', 'completed', 'unknown'
    total_volumes = Column(Integer, nullable=True)
    total_chapters = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    volumes = relationship("Volume", back_populates="series", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Series(title='{self.title}', status='{self.status}')>"

class Volume(Base):
    """Agrupamento lógico de capítulos (Tankobon)."""
    __tablename__ = 'volumes'
    __table_args__ = (UniqueConstraint('series_id', 'volume_number'),)

    id = Column(Integer, primary_key=True)
    series_id = Column(Integer, ForeignKey('series.id'), nullable=False)
    volume_number = Column(Float, nullable=False) # Float permite vols como 1.5 (comum em algumas edições)
    title = Column(String, nullable=True)
    
    series = relationship("Series", back_populates="volumes")
    chapters = relationship("Chapter", back_populates="volume", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Volume(series_id={self.series_id}, vol={self.volume_number})>"

class Chapter(Base):
    """Unidade individual de leitura (capítulo, one-shot, artigo)."""
    __tablename__ = 'chapters'
    __table_args__ = (UniqueConstraint('volume_id', 'chapter_number'),)

    id = Column(Integer, primary_key=True)
    volume_id = Column(Integer, ForeignKey('volumes.id'), nullable=False)
    chapter_number = Column(Float, nullable=False) # Float permite caps como 10.5
    title = Column(String, nullable=True)
    external_id = Column(String, unique=True, nullable=True) # ID na fonte
    
    volume = relationship("Volume", back_populates="chapters")
    files = relationship("MediaFile", back_populates="chapter", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Chapter(vol={self.volume_id}, chap={self.chapter_number})>"

class MediaFile(Base):
    """Arquivo físico baixado no disco."""
    __tablename__ = 'media_files'

    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey('chapters.id'), nullable=False)
    file_path = Column(String, unique=True, nullable=False)
    file_format = Column(String) # pdf, epub, cbz, cbr
    file_size = Column(Integer) # bytes
    sha256_hash = Column(String, unique=True) # Para deduplicação
    download_status = Column(String, default='pending') # pending, downloading, completed, corrupted
    downloaded_at = Column(DateTime, nullable=True)

    chapter = relationship("Chapter", back_populates="files")

    def __repr__(self):
        return f"<MediaFile(path='{self.file_path}', status='{self.download_status}')>"

class DownloadJob(Base):
    """Item da fila de downloads (persistente)."""
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

    def __repr__(self):
        return f"<DownloadJob(series='{self.series}', chapter={self.chapter_number}, status='{self.status}')>"


class DatabaseManager:
    """Gerenciador de engine e sessões. Sem sessão global compartilhada."""

    def __init__(self, db_path: str = str(DB_PATH)):
        # check_same_thread=False: a fila é mutada pela thread do JS-API enquanto o
        # worker serial drena — cada session_scope abre sua própria conexão.
        self.engine = create_engine(
            f'sqlite:///{db_path}', echo=False,
            connect_args={"check_same_thread": False},
        )

        # WAL + busy_timeout reduzem "database is locked" sob acesso concorrente.
        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def get_session(self):
        """Retorna uma NOVA sessão (o chamador é responsável por fechá-la)."""
        return self.SessionLocal()

    @contextmanager
    def session_scope(self):
        """Sessão com commit/rollback/close automáticos."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def reset_db(self):
        """CUIDADO: Apaga todo o banco."""
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)


db_manager = DatabaseManager()
