"""Breaking router — trigger breaking news interrupts."""

import asyncio

from fastapi import APIRouter, Depends

from core.routers.admin import require_api_key
from core.services import liquidsoap_client, break_builder
from core.services.degradation import get_sting_path

router = APIRouter(prefix="/api/breaking", tags=["breaking"])


@router.post("/trigger")
async def trigger_breaking(body: dict, _=Depends(require_api_key)):
    """Trigger a breaking news interrupt."""
    reason = body.get("reason", "MANUAL")
    note = body.get("note", "")

    # Step A: Inject sting immediately
    sting_path = get_sting_path("quick_update")
    if not sting_path:
        sting_path = get_sting_path("station_id")

    sting_injected = False
    if sting_path:
        sting_injected = await liquidsoap_client.push_sting(sting_path)

    # Step B: Start async break generation
    asyncio.create_task(
        break_builder.prepare_break(is_breaking=True, breaking_note=note)
    )

    return {
        "status": "triggered",
        "reason": reason,
        "sting_injected": sting_injected,
        "clip_eta_seconds": 25,
    }
