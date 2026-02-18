"""Breaking router — trigger breaking news interrupts."""

import asyncio

from fastapi import APIRouter, Depends

from core.routers.admin import require_api_key
from core.services import break_builder

router = APIRouter(prefix="/api/breaking", tags=["breaking"])


@router.post("/trigger")
async def trigger_breaking(body: dict, _=Depends(require_api_key)):
    """Trigger a breaking news interrupt."""
    reason = body.get("reason", "MANUAL")
    note = body.get("note", "")

    # Start async break generation
    asyncio.create_task(
        break_builder.prepare_break(is_breaking=True, breaking_note=note)
    )

    return {
        "status": "triggered",
        "reason": reason,
    }
