from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import require_store_admin
from ..database import get_db_session
from ..models import Developer
from ..schemas.admin import ReviewActionRequest
from ..services.skills import (
    approve_review,
    get_admin_stats,
    list_reviews,
    reject_review,
    revoke_certificate,
    serialize_review,
    start_review,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_store_admin)])


@router.get("/reviews")
async def list_reviews_route(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    data, total = await list_reviews(session, status_filter=status, page=page, limit=limit)
    return {
        "data": data,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
        },
    }


@router.post("/reviews/{review_id}/start")
async def start_review_route(
    review_id: int,
    current_user: Developer = Depends(require_store_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    review = await start_review(session, review_id, current_user)
    return {"data": serialize_review(review)}


@router.post("/reviews/{review_id}/approve")
async def approve_review_route(
    review_id: int,
    payload: ReviewActionRequest,
    current_user: Developer = Depends(require_store_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    review = await approve_review(session, review_id, current_user, payload.comment)
    return {"data": serialize_review(review)}


@router.post("/reviews/{review_id}/reject")
async def reject_review_route(
    review_id: int,
    payload: ReviewActionRequest,
    current_user: Developer = Depends(require_store_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict]:
    review = await reject_review(session, review_id, current_user, payload.comment)
    return {"data": serialize_review(review)}


@router.post("/certifications/{certificate_serial}/revoke")
async def revoke_certification(
    certificate_serial: str,
    payload: ReviewActionRequest,
    current_user: Developer = Depends(require_store_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, dict[str, str | None]]:
    certification = await revoke_certificate(
        session,
        certificate_serial=certificate_serial,
        reviewer=current_user,
        reason=payload.comment,
    )
    return {
        "data": {
            "certificate_serial": certification.certificate_serial,
            "revoked_at": certification.revoked_at.isoformat() if certification.revoked_at else None,
            "reason": certification.revoke_reason,
        }
    }


@router.get("/stats")
async def get_admin_stats_route(session: AsyncSession = Depends(get_db_session)) -> dict[str, dict[str, int]]:
    return {"data": await get_admin_stats(session)}
