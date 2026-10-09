import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import require_owner
from app.db.session import get_db
from app.models import Import, ImportQuarantine
from app.schemas.import_ import ImportOut, ImportReport, QuarantineOut
from app.services.importers.pipeline import ImportRejected, run_import

router = APIRouter(
    prefix="/api/imports",
    tags=["imports"],
    dependencies=[Depends(require_owner)],  # import 仅 owner（权限矩阵）
)


@router.post("", response_model=ImportReport)
def create_import(
    file: UploadFile = File(...),
    source_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ImportReport:
    data = file.file.read()
    settings = get_settings()
    try:
        outcome = run_import(
            db,
            data,
            filename=file.filename or "unknown",
            source_type=source_type,
            max_file_mb=settings.import_max_file_mb,
        )
    except ImportRejected as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    quarantine = []
    if outcome.import_.status != "running":
        quarantine = list(
            db.scalars(
                select(ImportQuarantine).where(ImportQuarantine.import_id == outcome.import_.id)
            )
        )
    return ImportReport(
        already_imported=outcome.already_imported,
        import_=ImportOut.model_validate(outcome.import_),
        quarantine=[QuarantineOut.model_validate(q) for q in quarantine],
    )


@router.get("", response_model=list[ImportOut])
def list_imports(db: Session = Depends(get_db)) -> list[ImportOut]:
    rows = db.scalars(select(Import).order_by(Import.created_at.desc())).all()
    return [ImportOut.model_validate(r) for r in rows]


@router.get("/{import_id}", response_model=ImportReport)
def get_import(import_id: uuid.UUID, db: Session = Depends(get_db)) -> ImportReport:
    imp = db.get(Import, import_id)
    if imp is None:
        raise HTTPException(status_code=404, detail="import not found")
    quarantine = list(
        db.scalars(select(ImportQuarantine).where(ImportQuarantine.import_id == imp.id))
    )
    return ImportReport(
        already_imported=False,
        import_=ImportOut.model_validate(imp),
        quarantine=[QuarantineOut.model_validate(q) for q in quarantine],
    )
