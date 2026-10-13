import sys
import time
import argparse
import urllib.request
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

# Add project root to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session
from sqlalchemy import or_
from db.session import SessionLocal
from models import Problem, Domain, Tag, Difficulty, ProblemType
from schemas.problem import ProblemCreate
from ingestion.base import BaseIngestionAdapter, IngestionSourceType

CF_API_PROBLEMS_URL = "https://codeforces.com/api/problemset.problems"
MIN_REQUEST_INTERVAL = 2.0  # Respect Codeforces API rate limit (max 1 req per 2 seconds)

_last_request_time = 0.0

TAG_TO_DOMAIN_MAP: Dict[str, List[str]] = {
    "math": ["Mathematics"],
    "number theory": ["Mathematics", "Number Theory"],
    "dp": ["Dynamic Programming"],
    "greedy": ["Greedy"],
    "graphs": ["Graphs"],
    "trees": ["Trees", "Graphs"],
    "dfs and similar": ["DFS", "BFS", "Graphs"],
    "data structures": ["Data Structures"],
    "strings": ["Strings"],
    "binary search": ["Binary Search", "Searching"],
    "two pointers": ["Two Pointers"],
    "bitmasks": ["Bit Manipulation"],
    "combinatorics": ["Combinatorics", "Mathematics"],
    "geometry": ["Geometry", "Mathematics"],
    "sortings": ["Sorting"],
    "implementation": ["Implementation"],
    "brute force": ["Algorithms"],
    "constructive algorithms": ["Algorithms"],
    "divide and conquer": ["Divide and Conquer", "Algorithms"],
    "dsu": ["Data Structures"],
    "shortest paths": ["Shortest Path", "Graphs"],
    "probabilities": ["Probability", "Mathematics"],
    "flows": ["Graphs"],
    "matrices": ["Mathematics"],
    "games": ["Mathematics"],
    "string suffix structures": ["Strings", "Data Structures"],
    "expression parsing": ["Stack", "Strings"],
    "2-sat": ["Graphs"],
    "hashing": ["Hash Map", "Strings"],
    "ternary search": ["Searching"],
    "meet-in-the-middle": ["Algorithms"],
    "graph matchings": ["Graphs"],
    "interactive": ["Competitive Programming"],
}

def get_difficulty_from_rating(rating: Optional[int]) -> str:
    """Map Codeforces numeric rating to CodeMind Difficulty enum."""
    if rating is None:
        return Difficulty.MEDIUM.value
    if rating < 1200:
        return Difficulty.BEGINNER.value
    elif rating < 1600:
        return Difficulty.EASY.value
    elif rating < 2000:
        return Difficulty.MEDIUM.value
    elif rating < 2400:
        return Difficulty.HARD.value
    else:
        return Difficulty.EXPERT.value

class CodeforcesImporter(BaseIngestionAdapter):
    """
    Reusable importer for Codeforces problems via the official Codeforces problemset API.
    Enforces rate limits, preserves attribution, avoids duplicates, and maps tags to domains.
    """

    @property
    def source_name(self) -> str:
        return "Codeforces"

    @property
    def source_type(self) -> IngestionSourceType:
        return IngestionSourceType.OFFICIAL_API

    def _wait_for_rate_limit(self) -> None:
        """Ensure at least MIN_REQUEST_INTERVAL seconds between API calls."""
        global _last_request_time
        now = time.time()
        elapsed = now - _last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        _last_request_time = time.time()

    def fetch_raw_data(self, tag: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Fetch problems metadata from the official Codeforces problemset API."""
        self._wait_for_rate_limit()

        url = CF_API_PROBLEMS_URL
        if tag:
            url += f"?tags={urllib.parse.quote(tag)}"

        headers = {
            "User-Agent": "CodeMind-Importer/1.0 (Educational Coding Platform)",
            "Accept": "application/json"
        }
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as err:
            raise RuntimeError(f"Failed to fetch Codeforces problems from {url}: {err}") from err

        if payload.get("status") != "OK":
            comment = payload.get("comment", "Unknown API error")
            raise RuntimeError(f"Codeforces API error response: {comment}")

        problems = payload.get("result", {}).get("problems", [])
        return problems

    def normalize_problem(self, raw_item: Dict[str, Any]) -> ProblemCreate:
        """Convert a Codeforces API problem dictionary into a CodeMind ProblemCreate DTO."""
        contest_id = raw_item.get("contestId")
        index = str(raw_item.get("index", "")).strip().upper()
        name = str(raw_item.get("name", "")).strip()

        if not contest_id or not index or not name:
            raise ValueError(f"Incomplete Codeforces problem metadata: {raw_item}")

        external_id = f"CF-{contest_id}{index}"
        prob_id = f"codeforces-{contest_id}-{index.lower()}"
        source_url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        rating = raw_item.get("rating")
        difficulty = get_difficulty_from_rating(rating)

        # Original tags
        raw_tags = [str(t).strip().lower() for t in raw_item.get("tags", []) if str(t).strip()]

        # Map tags to CodeMind domains while preserving all original tags
        domains_set = {"Competitive Programming"}
        for tag in raw_tags:
            if tag in TAG_TO_DOMAIN_MAP:
                domains_set.update(TAG_TO_DOMAIN_MAP[tag])

        # If no specific domain found from tags, default to Algorithms
        if len(domains_set) == 1:
            domains_set.add("Algorithms")

        domains_list = sorted(list(domains_set))

        # Ingestion guard: If complete statement/input/output are not provided in raw_item,
        # store metadata cleanly as an INACTIVE record so it does NOT pollute the active student Problem Library.
        raw_desc = raw_item.get("description")
        raw_inp = raw_item.get("input_format")
        raw_out = raw_item.get("output_format")
        raw_examples = raw_item.get("examples") or []

        has_full_content = bool(raw_desc and len(str(raw_desc).strip()) > 30 and (raw_inp or raw_out or raw_examples))

        if has_full_content:
            desc = str(raw_desc).strip()
            input_format = str(raw_inp).strip() if raw_inp else None
            output_format = str(raw_out).strip() if raw_out else None
            examples = raw_examples
            is_active = True
        else:
            rating_str = f"Rating: {rating}" if rating is not None else "Unrated"
            desc = (
                f"Codeforces Problem {contest_id}{index}: {name} ({rating_str}).\n\n"
                f"[Statement Unavailable: This record contains catalog metadata only. "
                f"Refer to the official problem URL: {source_url}]"
            )
            input_format = None
            output_format = None
            examples = []
            is_active = False

        starter_code = {
            "python": (
                f"# Codeforces {contest_id}{index} - {name}\n"
                f"# Rating: {rating if rating else 'N/A'} | Difficulty: {difficulty}\n\n"
                f"def solve():\n"
                f"    pass\n\n"
                f"if __name__ == '__main__':\n"
                f"    solve()\n"
            ),
            "cpp": (
                f"// Codeforces {contest_id}{index} - {name}\n"
                f"#include <iostream>\n"
                f"using namespace std;\n\n"
                f"int main() {{\n"
                f"    ios_base::sync_with_stdio(false);\n"
                f"    cin.tie(NULL);\n"
                f"    // Solution here\n"
                f"    return 0;\n"
                f"}}\n"
            )
        }

        return ProblemCreate(
            id=prob_id,
            title=name,
            source="Codeforces",
            source_url=source_url,
            external_id=external_id,
            problem_type=ProblemType.COMPETITIVE_PROGRAMMING.value,
            difficulty=difficulty,
            rating=rating,
            description=desc,
            input_format=input_format,
            output_format=output_format,
            examples=examples,
            constraints=[],
            concepts=domains_list,
            prerequisites=["Competitive Programming Fundamentals"],
            starter_code=starter_code,
            supported_languages=["python", "cpp", "java"],
            domains=domains_list,
            tags=raw_tags,
            is_active=is_active
        )

    def import_problems(
        self,
        db: Session,
        limit: Optional[int] = None,
        batch_size: int = 500,
        tag: Optional[str] = None,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Synchronize/import problems from Codeforces problemset into the existing database.
        Uses batching to import efficiently and skips existing records by CF identifier.
        """
        if verbose:
            print("Fetching problem list from official Codeforces API...")

        raw_problems = self.fetch_raw_data(tag=tag)
        total_fetched = len(raw_problems)

        if verbose:
            print(f"Retrieved {total_fetched} problems from Codeforces API.")

        if limit is not None and limit > 0:
            raw_problems = raw_problems[:limit]
            if verbose:
                print(f"Limiting import to first {limit} problems.")

        # Pre-load existing IDs and external_IDs to avoid O(N) database queries
        existing_ext_ids: Set[str] = {
            row[0] for row in db.query(Problem.external_id).filter(Problem.external_id.isnot(None)).all()
        }
        existing_prob_ids: Set[str] = {
            row[0] for row in db.query(Problem.id).all()
        }

        # Cache existing domains and tags by lowercase name
        domain_cache: Dict[str, Domain] = {
            d.name.lower(): d for d in db.query(Domain).all()
        }
        tag_cache: Dict[str, Tag] = {
            t.name.lower(): t for t in db.query(Tag).all()
        }

        number_imported = 0
        duplicates_skipped = 0
        errors: List[str] = []

        pending_batch: List[Problem] = []

        for idx, raw_item in enumerate(raw_problems, start=1):
            contest_id = raw_item.get("contestId")
            index = str(raw_item.get("index", "")).strip().upper()

            if not contest_id or not index:
                continue

            cf_ext_id = f"CF-{contest_id}{index}"
            cf_prob_id = f"codeforces-{contest_id}-{index.lower()}"

            # Check duplicate by external_id or problem id
            if cf_ext_id in existing_ext_ids or cf_prob_id in existing_prob_ids:
                duplicates_skipped += 1
                continue

            try:
                dto = self.normalize_problem(raw_item)
                self.validate_problem(dto)

                # Resolve domain objects from cache or insert new
                problem_domains = []
                for d_name in dto.domains:
                    key = d_name.lower()
                    if key not in domain_cache:
                        new_domain = Domain(name=d_name)
                        db.add(new_domain)
                        db.flush()
                        domain_cache[key] = new_domain
                    problem_domains.append(domain_cache[key])

                # Resolve tag objects from cache or insert new
                problem_tags = []
                for t_name in dto.tags:
                    key = t_name.lower()
                    if key not in tag_cache:
                        new_tag = Tag(name=t_name)
                        db.add(new_tag)
                        db.flush()
                        tag_cache[key] = new_tag
                    problem_tags.append(tag_cache[key])

                problem = Problem(
                    id=dto.id,
                    title=dto.title,
                    source=dto.source,
                    source_url=dto.source_url,
                    external_id=dto.external_id,
                    problem_type=dto.problem_type,
                    difficulty=dto.difficulty,
                    rating=dto.rating,
                    description=dto.description,
                    input_format=dto.input_format,
                    output_format=dto.output_format,
                    examples=dto.examples,
                    constraints=dto.constraints,
                    concepts=dto.concepts,
                    prerequisites=dto.prerequisites,
                    starter_code=dto.starter_code,
                    supported_languages=dto.supported_languages,
                    domains=problem_domains,
                    tags=problem_tags,
                    is_active=True
                )

                db.add(problem)
                pending_batch.append(problem)
                existing_ext_ids.add(cf_ext_id)
                existing_prob_ids.add(cf_prob_id)
                number_imported += 1

                # Commit in batches for high performance and low memory consumption
                if len(pending_batch) >= batch_size:
                    db.commit()
                    if verbose:
                        print(f"[*] Committed batch: {number_imported} imported so far...")
                    pending_batch.clear()

            except Exception as e:
                err_msg = f"Failed to import problem {cf_ext_id}: {e}"
                errors.append(err_msg)

        # Final commit for remaining items
        if pending_batch:
            db.commit()
            pending_batch.clear()

        total_problems = db.query(Problem).count()

        result = {
            "number_imported": number_imported,
            "total_problems": total_problems,
            "duplicates_skipped": duplicates_skipped,
            "errors": errors
        }

        if verbose:
            print("\n========================================")
            print("Codeforces Import Summary:")
            print(f"- Number imported: {number_imported}")
            print(f"- Total problems in DB: {total_problems}")
            print(f"- Duplicates skipped: {duplicates_skipped}")
            print(f"- Errors: {len(errors)}")
            print("========================================")

        return result

def main():
    parser = argparse.ArgumentParser(description="CodeMind Codeforces Problem Importer")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of problems to import (optional)")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for database commits (default: 500)")
    parser.add_argument("--tag", type=str, default=None, help="Filter by specific tag from Codeforces API (optional)")
    args = parser.parse_args()

    importer = CodeforcesImporter()
    db: Session = SessionLocal()
    try:
        importer.import_problems(db, limit=args.limit, batch_size=args.batch_size, tag=args.tag, verbose=True)
    finally:
        db.close()

if __name__ == "__main__":
    main()
