import uuid
from fastapi import APIRouter, Depends
from app.core.auth import require_api_key

router = APIRouter(prefix="/digest", tags=["digest"])


@router.post(
    "/trigger/{client_id}",
    dependencies=[Depends(require_api_key)],
)
def trigger_digest(client_id: uuid.UUID) -> dict:
    from workers.tasks.digest_tasks import send_single_client_digest

    task = send_single_client_digest.delay(str(client_id))
    return {"task_id": task.id, "client_id": str(client_id)}
