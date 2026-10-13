import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.session import engine, SessionLocal
from db.base import Base
from models import Problem, Test, TestQuestion
from routes.tests import create_test, get_test_admin
from schemas.test import TestCreateSchema, QuestionInputSchema

def seed_and_verify_test():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Check if already seeded
        existing = db.query(Test).filter(Test.title == "CodeMind Core Assessment 2026").first()
        if existing:
            print(f"Test already exists: {existing.id} - '{existing.title}'")
            test_id = existing.id
        else:
            print("Creating test with 1 existing problem + 1 custom question...")
            payload = TestCreateSchema(
                title="CodeMind Core Assessment 2026",
                description="Official assessment testing array manipulation and string algorithmic logic.",
                duration_minutes=75,
                # All options OFF / unselected by default
                allowed_languages=[],
                restrict_copy_paste=False,
                enable_camera=False,
                enable_microphone=False,
                require_fullscreen=False,
                enable_proctoring=False,
                questions=[
                    # 1. Existing problem
                    QuestionInputSchema(
                        problem_id="two-sum-target",
                        is_custom=False,
                        points=25,
                        order=0
                    ),
                    # 2. Custom question
                    QuestionInputSchema(
                        is_custom=True,
                        title="Reverse Words in Sentence",
                        description="Given a string `s`, reverse the order of the words. A word is defined as a sequence of non-space characters. The words in `s` will be separated by at least one space. Return a string of the words in reverse order concatenated by a single space.",
                        difficulty="Medium",
                        input_format="Single string s.",
                        output_format="Reversed words string.",
                        examples=[
                            {
                                "input": "s = 'the sky is blue'",
                                "output": "blue is sky the",
                                "explanation": "Words reversed."
                            },
                            {
                                "input": "s = '  hello world  '",
                                "output": "world hello",
                                "explanation": "Leading/trailing spaces trimmed."
                            }
                        ],
                        constraints=["1 <= s.length <= 10^4"],
                        starter_code={
                            "python": "def reverse_words(s: str) -> str:\n    # Write solution here\n    pass\n"
                        },
                        points=35,
                        order=1
                    )
                ]
            )
            created = create_test(payload, db)
            test_id = created["id"]
            print(f"Successfully created test ID: {test_id}")

        # VERIFY SAVED SETTINGS FROM DATABASE
        print("\n--- VERIFYING SAVED SETTINGS ---")
        test = get_test_admin(test_id, db)
        print("Test ID:", test["id"])
        print("Title:", test["title"])
        print("Duration (minutes):", test["duration_minutes"])
        print("Question Count:", len(test["questions"]))
        print("\nSettings Verification (ALL MUST BE OFF / UNSELECTED):")
        print("  - allowed_languages:", test["allowed_languages"])
        print("  - restrict_copy_paste:", test["restrict_copy_paste"])
        print("  - enable_camera:", test["enable_camera"])
        print("  - enable_microphone:", test["enable_microphone"])
        print("  - require_fullscreen:", test["require_fullscreen"])
        print("  - enable_proctoring:", test["enable_proctoring"])

        assert test["allowed_languages"] == [], "allowed_languages must be empty"
        assert test["restrict_copy_paste"] is False
        assert test["enable_camera"] is False
        assert test["enable_microphone"] is False
        assert test["require_fullscreen"] is False
        assert test["enable_proctoring"] is False

        print("\nQuestions Verification (1 Existing + 1 Custom):")
        for idx, q in enumerate(test["questions"], 1):
            print(f"  Question {idx}:")
            print(f"    - Title: {q['title']}")
            print(f"    - Is Custom: {q['is_custom']}")
            print(f"    - Problem ID: {q['problem_id']}")
            print(f"    - Points: {q['points']}")
            print(f"    - Examples: {len(q['examples'])} test case(s)")

        assert len(test["questions"]) == 2
        assert test["questions"][0]["is_custom"] is False
        assert test["questions"][0]["problem_id"] == "two-sum-target"
        assert test["questions"][1]["is_custom"] is True
        assert test["questions"][1]["problem_id"].startswith("custom-")

        print("\nALL SAVED SETTINGS AND QUESTIONS VERIFIED SUCCESSFULLY!")

    finally:
        db.close()

if __name__ == "__main__":
    seed_and_verify_test()
