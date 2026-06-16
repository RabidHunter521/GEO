from fastapi import APIRouter
from app.api.v1 import scans, clients, competitors, toolkit, activity, digest, reports, content_gaps, content_roadmap, action_center, traffic, client_view, costs

router = APIRouter(prefix="/api/v1")
router.include_router(scans.router)
router.include_router(clients.router)
router.include_router(competitors.router)
router.include_router(toolkit.router)
router.include_router(activity.router)
router.include_router(digest.router)
router.include_router(reports.router)
router.include_router(content_gaps.router)
router.include_router(content_roadmap.router)
router.include_router(action_center.router)
router.include_router(traffic.router)
router.include_router(client_view.router)
router.include_router(costs.router)
