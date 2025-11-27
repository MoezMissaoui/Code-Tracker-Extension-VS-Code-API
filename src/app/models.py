from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.mysql import LONGTEXT

from app.database import Base


class TrackedFile(Base):
    __tablename__ = "tracked_files"

    id = Column(Integer, primary_key=True, index=True)
    fileName = Column("file_name", String(255), nullable=False)
    filePath = Column("file_path", String(1024), nullable=False)
    key = Column("key", String(255), nullable=False)
    fullContent = Column("content", LONGTEXT, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


