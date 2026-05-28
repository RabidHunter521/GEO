import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scan import Scan
from app.schemas.scan import TriggerScanRequest, ScanResponse

router = APIRouter(prefix="/scans", tags=["scans"])


@router.post("/", response_model=ScanResponse, status_code=202)
def trigger_scan(payload: TriggerScanRequest, db: Session = Depends(get_db)):
    from workers.tasks.scan_tasks import execute_scan

    scan = Scan(client_id=payload.client_id)
    db.add(scan)
    db.commit()
    db.refresh(scan)

    execute_scan.delay(str(scan.id))
    return scan


@router.get("/{scan_id}", response_model=ScanResponse)
def get_scan(scan_id: uuid.UUID, db: Session = Depends(get_db)):
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan
