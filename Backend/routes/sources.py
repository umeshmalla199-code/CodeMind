from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from db.session import get_db
from models import Problem
from schemas import SourceCountResponse, SourceMetadata

router = APIRouter(tags=["sources"])

# Known Source Registry: Standardized source metadata and external reference templates
# Note: HackerRank is configured strictly as reference-only metadata (no scraping/mirroring)
SOURCE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "Codeforces": {
        "display_name": "Codeforces",
        "category": "Competitive Programming",
        "description": "Global competitive programming platform hosting regular contests and an extensive problem archive.",
        "home_url": "https://codeforces.com",
        "url_template": "https://codeforces.com/problemset/problem/{id}",
        "is_external": True,
        "reference_only": False,
    },
    "CodeMind Original": {
        "display_name": "CodeMind Original",
        "category": "Curated Assessment & Learning",
        "description": "Curated problems with comprehensive unit test cases, harnesses, and starter templates.",
        "home_url": "",
        "url_template": "",
        "is_external": False,
        "reference_only": False,
    },
    "Admin Custom": {
        "display_name": "Admin Custom",
        "category": "Assessment Questions",
        "description": "Custom questions authored directly by administrators and instructors for assessment tests.",
        "home_url": "",
        "url_template": "",
        "is_external": False,
        "reference_only": False,
    },
    "OpenContestArchive": {
        "display_name": "Open Contest Archive",
        "category": "Collegiate & Open Contests",
        "description": "Public domain contest problems from regional programming competitions.",
        "home_url": "",
        "url_template": "",
        "is_external": True,
        "reference_only": False,
    },
    "HackerRank": {
        "display_name": "HackerRank",
        "category": "Developer Skills & Reference",
        "description": "Technical skill assessment platform. Supported as an external reference and metadata source (not mirrored or scraped).",
        "home_url": "https://www.hackerrank.com",
        "url_template": "https://www.hackerrank.com/challenges/{id}/problem",
        "is_external": True,
        "reference_only": True,
    },
    "LeetCode": {
        "display_name": "LeetCode",
        "category": "Technical Interviews",
        "description": "Software engineering interview preparation platform.",
        "home_url": "https://leetcode.com",
        "url_template": "https://leetcode.com/problems/{id}/",
        "is_external": True,
        "reference_only": True,
    }
}

def get_source_metadata(source_name: Optional[str]) -> Dict[str, Any]:
    """Safely retrieves metadata for a problem source, handling missing/invalid sources."""
    if not source_name or not str(source_name).strip():
        return {
            "name": "Unknown",
            "display_name": "Unknown Source",
            "category": "Unspecified",
            "description": "Source metadata not specified.",
            "home_url": "",
            "url_template": "",
            "is_external": False,
            "reference_only": False
        }

    s_clean = str(source_name).strip()
    for reg_key, meta in SOURCE_REGISTRY.items():
        if reg_key.lower() == s_clean.lower():
            res = dict(meta)
            res["name"] = reg_key
            return res

    return {
        "name": s_clean,
        "display_name": s_clean,
        "category": "External Source",
        "description": f"Problem repository source: {s_clean}",
        "home_url": "",
        "url_template": "",
        "is_external": True,
        "reference_only": False
    }

def resolve_source_url(source: Optional[str], source_url: Optional[str], external_id: Optional[str], problem_id: str) -> str:
    """Safely resolves or formats an external reference URL for a problem."""
    url = (source_url or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url

    meta = get_source_metadata(source)
    tpl = meta.get("url_template")
    if tpl:
        target_id = (external_id or "").strip() or problem_id
        if meta.get("name") == "Codeforces" and "-" in target_id:
            parts = target_id.split("-")
            if len(parts) >= 3 and parts[0].lower() == "codeforces":
                return f"https://codeforces.com/problemset/problem/{parts[1]}/{parts[2].upper()}"
        return tpl.format(id=target_id)

    return url

@router.get("/sources", response_model=List[SourceCountResponse])
@router.get("/api/sources", response_model=List[SourceCountResponse])
def list_sources(db: Session = Depends(get_db)):
    """Retrieve all distinct problem sources with problem counts and metadata."""
    results = (
        db.query(
            Problem.source,
            func.count(Problem.id).label("count")
        )
        .filter(Problem.is_active == True)
        .group_by(Problem.source)
        .order_by(func.count(Problem.id).desc())
        .all()
    )

    source_list = []
    seen = set()
    for source, count in results:
        meta = get_source_metadata(source)
        seen.add(meta["name"].lower())
        source_list.append(
            SourceCountResponse(
                name=source,
                problem_count=count,
                display_name=meta.get("display_name", source),
                category=meta.get("category", "General"),
                description=meta.get("description", ""),
                home_url=meta.get("home_url", ""),
                is_external=meta.get("is_external", False),
                reference_only=meta.get("reference_only", False)
            )
        )

    # Include reference-only sources with 0 problem count so consumers can browse supported sources
    for reg_key, reg_meta in SOURCE_REGISTRY.items():
        if reg_key.lower() not in seen:
            source_list.append(
                SourceCountResponse(
                    name=reg_key,
                    problem_count=0,
                    display_name=reg_meta["display_name"],
                    category=reg_meta["category"],
                    description=reg_meta["description"],
                    home_url=reg_meta["home_url"],
                    is_external=reg_meta["is_external"],
                    reference_only=reg_meta["reference_only"]
                )
            )

    return source_list

@router.get("/sources/{source_name}")
@router.get("/api/sources/{source_name}")
def get_source_detail(source_name: str, db: Session = Depends(get_db)):
    """Retrieve metadata and live problem count for a specific problem source."""
    meta = get_source_metadata(source_name)
    count = db.query(func.count(Problem.id)).filter(
        Problem.source.ilike(source_name.strip()),
        Problem.is_active == True
    ).scalar() or 0

    return {
        **meta,
        "problem_count": count
    }
