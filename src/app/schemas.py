from datetime import datetime

from pydantic import BaseModel, Field


class FileCreate(BaseModel):
    fileName: str = Field(..., description="Name of the file")
    filePath: str = Field(..., description="Absolute path of the file")
    fullContent: str = Field(..., description="Full content of the file")
    timestamp: datetime = Field(
        ..., description="Timestamp associated with this file snapshot"
    )


class FileResponse(BaseModel):
    id: int
    fileName: str
    filePath: str
    fullContent: str
    timestamp: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class FileResponseEnvelope(BaseModel):
    message: str
    data: FileResponse


class FileListResponseEnvelope(BaseModel):
    message: str
    data: list[FileResponse]



