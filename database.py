"""
Módulo 3.1: Database Layer
Gerencia persistência de dados com SQLite e SQLAlchemy.
Modela Séries, Volumes, Capítulos e Arquivos baixados.
"""

import os
from datetime import datetime
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, UniqueConstraint
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

class DatabaseManager:
    """Gerenciador de sessão e inicialização do DB."""
    
    def __init__(self, db_path: str = str(DB_PATH)):
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine)
        self.session = SessionLocal()

    def get_session(self):
        return self.session

    def close(self):
        self.session.close()

    def reset_db(self):
        """CUIDADO: Apaga todo o banco."""
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)

# Inicialização singleton para uso global
db_manager = DatabaseManager()
