import uuid
from datetime import datetime

from pydantic import BaseModel


class QuarantineOut(BaseModel):
    id: uuid.UUID
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportOut(BaseModel):
    id: uuid.UUID
    source_type: str
    original_filename: str | None
    checksum_sha256: str
    file_size_bytes: int
    adapter_version: str
    status: str
    stats: dict
    warnings: list
    error: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ImportReport(BaseModel):
    already_imported: bool
    import_: ImportOut
    quarantine: list[QuarantineOut] = []
