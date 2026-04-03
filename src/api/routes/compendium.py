"""SRD compendium search endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from src.data.srd_client import lookup_srd, search_srd

router = APIRouter()


@router.get("/compendium/{category}")
async def compendium(category: str, q: str = "") -> dict | list:
    """Search or look up SRD entries.

    - No query: list all entries in category
    - Query starting with '?': search within category
    - Other query: exact lookup by name/index
    """
    if q.startswith("?"):
        return search_srd(category, q[1:].strip())
    elif q:
        return lookup_srd(category, q)
    else:
        return search_srd(category, "")
