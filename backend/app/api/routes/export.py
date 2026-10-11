"""Portable Export API。

权限矩阵：export / backup 仅 Owner（zhan_mcp ❌，防批量外泄）。
导出包里不含 token、不含 DSN；日志与审计只记计数，不记正文。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import require_owner
from app.db.session import get_db
from app.models import ApiToken
from app.services import export_service

router = APIRouter(prefix="/api/export", tags=["export"])
logger = logging.getLogger("rianvault")


class ExportResponse(BaseModel):
    export_id: str
    sha256: str
    size_bytes: int
    counts: dict


@router.post("", response_model=ExportResponse)
def create_export(
    db: Session = Depends(get_db),
    actor: ApiToken = Depends(require_owner),
) -> ExportResponse:
    report = export_service.build_export(db, actor=actor.role, actor_model=None)
    logger.info("export created files=%s", report.files)
    return ExportResponse(
        export_id=report.export_id,
        sha256=report.sha256,
        size_bytes=report.zip_path.stat().st_size,
        counts=report.counts,
    )


@router.get("")
def list_exports(actor: ApiToken = Depends(require_owner)) -> list[dict]:
    return export_service.list_exports()


@router.get("/{export_id}/download")
def download_export(
    export_id: str,
    actor: ApiToken = Depends(require_owner),
) -> FileResponse:
    try:
        path = export_service.resolve_export_path(export_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="导出文件不存在") from e
    return FileResponse(
        path=path,
        media_type="application/zip",
        filename=path.name,
    )


@router.get("/status")
def export_status(actor: ApiToken = Depends(require_owner)) -> dict:
    return {"export_dir": str(get_settings().export_dir)}
