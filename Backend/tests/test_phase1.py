import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.orm import Session
from db.session import SessionLocal, engine
from db.base import Base
from models import Problem, Domain, Tag
from seed.seed_runner import seed_database
from routes.problems import list_problems, get_problem
from routes.topics import list_topics
from routes.sources import list_sources
from ingestion.base import BaseIngestionAdapter, IngestionSourceType
from ingestion.sample_feed import PermittedFeedAdapter
from schemas.problem import ProblemCreate

def run_tests():
    print("========================================")
    print("Running CodeMind Phase 1 Verification Tests")
    print("========================================")

    # 1. Verify Database Initialization & Seed
    db: Session = SessionLocal()
    try:
        total_problems = db.query(Problem).count()
        print(f"[*] Total Problems in DB: {total_problems}")
        assert total_problems >= 15, f"Expected at least 15 problems, found {total_problems}"

        total_domains = db.query(Domain).count()
        print(f"[*] Total Domains in DB: {total_domains}")
        assert total_domains >= 10, f"Expected at least 10 domains, found {total_domains}"

        total_tags = db.query(Tag).count()
        print(f"[*] Total Tags in DB: {total_tags}")
        assert total_tags >= 10, f"Expected at least 10 tags, found {total_tags}"

        # 2. Test GET /problems default pagination
        res_default = list_problems(
            search=None, difficulty=None, domain=None, source=None,
            problem_type=None, tag=None, page=1, page_size=10,
            sort_by="id", order="asc", db=db
        )
        print(f"[*] Default page 1: returned {len(res_default.items)} items, total: {res_default.total}, pages: {res_default.total_pages}")
        assert len(res_default.items) == 10
        assert res_default.page == 1
        assert res_default.total == total_problems

        # 3. Test Search
        res_search = list_problems(
            search="Sum", difficulty=None, domain=None, source=None,
            problem_type=None, tag=None, page=1, page_size=10,
            sort_by="id", order="asc", db=db
        )
        print(f"[*] Search 'Sum': found {res_search.total} matching problems")
        assert res_search.total >= 2
        # Verify matched items contain 'sum' in title, id, or description
        for item in res_search.items:
            # Look up problem to verify match
            p = db.query(Problem).filter(Problem.id == item.id).first()
            assert "sum" in p.title.lower() or "sum" in p.id.lower() or "sum" in p.description.lower()

        # 4. Test Difficulty Filter
        res_easy = list_problems(
            search=None, difficulty="Easy", domain=None, source=None,
            problem_type=None, tag=None, page=1, page_size=10,
            sort_by="id", order="asc", db=db
        )
        print(f"[*] Filter difficulty 'Easy': found {res_easy.total} problems")
        assert res_easy.total > 0
        for item in res_easy.items:
            assert item.difficulty.lower() == "easy"

        # 5. Test Domain Filter
        res_dp = list_problems(
            search=None, difficulty=None, domain="Dynamic Programming", source=None,
            problem_type=None, tag=None, page=1, page_size=10,
            sort_by="id", order="asc", db=db
        )
        print(f"[*] Filter domain 'Dynamic Programming': found {res_dp.total} problems")
        assert res_dp.total > 0
        for item in res_dp.items:
            assert "Dynamic Programming" in item.domains

        # 6. Test Source Filter
        res_cf = list_problems(
            search=None, difficulty=None, domain=None, source="Codeforces",
            problem_type=None, tag=None, page=1, page_size=10,
            sort_by="id", order="asc", db=db
        )
        print(f"[*] Filter source 'Codeforces': found {res_cf.total} problems")
        assert res_cf.total >= 3
        for item in res_cf.items:
            assert item.source == "Codeforces"
            assert item.rating is not None, "Codeforces problem should have numeric rating"

        # 7. Test Problem Type Filter
        res_cp = list_problems(
            search=None, difficulty=None, domain=None, source=None,
            problem_type="Competitive Programming", tag=None, page=1, page_size=10,
            sort_by="id", order="asc", db=db
        )
        print(f"[*] Filter problem_type 'Competitive Programming': found {res_cp.total} problems")
        assert res_cp.total >= 3

        # 8. Test Pagination Page 2
        res_page2 = list_problems(
            search=None, difficulty=None, domain=None, source=None,
            problem_type=None, tag=None, page=2, page_size=10,
            sort_by="id", order="asc", db=db
        )
        print(f"[*] Page 2 (size 10): returned {len(res_page2.items)} items")
        assert len(res_page2.items) > 0
        assert res_page2.items[0].id != res_default.items[0].id

        # 9. Test GET /problems/{id}
        prob_detail = get_problem("two-sum-target", db=db)
        print(f"[*] Problem detail for 'two-sum-target': title='{prob_detail.title}', examples={len(prob_detail.examples)}, constraints={len(prob_detail.constraints)}")
        assert prob_detail.title == "Two Sum Target"
        assert len(prob_detail.examples) > 0
        assert len(prob_detail.constraints) > 0
        assert "python" in prob_detail.starter_code
        assert "Arrays" in prob_detail.domains

        # 10. Test GET /topics
        topics = list_topics(db=db)
        print(f"[*] Topics endpoint returned {len(topics)} topics")
        assert len(topics) >= 10
        for t in topics:
            assert t.name
            assert t.problem_count >= 0

        # 11. Test GET /sources
        sources = list_sources(db=db)
        print(f"[*] Sources endpoint returned {len(sources)} sources: {[s.name for s in sources]}")
        assert len(sources) >= 2
        source_names = [s.name for s in sources]
        assert "CodeMind Original" in source_names
        assert "Codeforces" in source_names

        # 12. Test Ingestion Adapter Framework
        print("[*] Testing future ingestion foundation...")
        adapter = PermittedFeedAdapter()
        assert adapter.source_type == IngestionSourceType.PERMITTED_FEED
        sample_raw = {
            "id": "sample-ingested-binary-search",
            "title": "Sample Ingested Binary Search",
            "source_url": "https://opencontests.org/archive/sample-bs",
            "problem_type": "Algorithms",
            "difficulty": "Easy",
            "description": "Given a sorted array, find index of target value.",
            "domains": ["Binary Search", "Arrays"],
            "tags": ["binary-search"],
            "starter_code": {"python": "def search(nums, target):\n    pass\n"},
            "examples": [{"input": "nums = [-1,0,3,5,9,12], target = 9", "output": "4"}]
        }
        normalized = adapter.normalize_problem(sample_raw)
        assert isinstance(normalized, ProblemCreate)
        assert adapter.validate_problem(normalized) is True

        ingested_ids = adapter.ingest_to_db(db, [sample_raw])
        assert "sample-ingested-binary-search" in ingested_ids
        # Verify it was added to the database
        ingested_prob = db.query(Problem).filter(Problem.id == "sample-ingested-binary-search").first()
        assert ingested_prob is not None
        assert ingested_prob.title == "Sample Ingested Binary Search"
        print(f"[*] Ingestion pipeline successfully verified for id: {ingested_prob.id}")

        print("========================================")
        print("ALL 12 VERIFICATION TESTS PASSED SUCCESSFULLY! [OK]")
        print("========================================")
    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
