from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter

router = APIRouter(prefix="/courses", tags=["courses"])

_COURSES_YAML = Path("packages/ingest/courses.yaml")


@router.get("")
async def list_courses() -> list[dict]:
    data = yaml.safe_load(_COURSES_YAML.read_text()).get("courses", {})
    return [
        {"id": cid, "name": cfg["name"], "color": cfg.get("color", "#003262")}
        for cid, cfg in data.items()
    ]
