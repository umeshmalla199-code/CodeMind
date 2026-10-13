import sys
from pathlib import Path
from sqlalchemy.orm import Session

# Add project root to sys.path to allow running as standalone script
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.session import engine, SessionLocal
from db.migrate import upgrade_database
from models import Problem, Domain, Tag
from seed.seed_data import SEED_PROBLEMS

ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@codemind.com"
ADMIN_PASSWORD = "Admin@CodeMind2026!"  # documented bootstrap password
ADMIN_DISPLAY_NAME = "CodeMind Administrator"
ADMIN_ROLE = "super_admin"

def init_db():
    """Upgrade the database to the latest versioned schema."""
    upgrade_database()


def _bootstrap_admin(db: Session) -> None:
    """Ensure the platform administrator bootstrap account exists.

    The documented admin account is username `admin` / password `Admin@CodeMind2026!`
    with role `super_admin`. It is created only once so repeated boots are idempotent.
    """
    from models.user import UserAccount, hash_password

    existing = db.query(UserAccount).filter(UserAccount.username == ADMIN_USERNAME).first()
    if existing:
        return

    pw_hash, salt = hash_password(ADMIN_PASSWORD)
    from uuid import uuid4
    admin = UserAccount(
        id=f"usr-{uuid4().hex[:8]}",
        username=ADMIN_USERNAME,
        email=ADMIN_EMAIL,
        display_name=ADMIN_DISPLAY_NAME,
        password_hash=pw_hash,
        salt=salt,
        role=ADMIN_ROLE,
        is_verified=True,
        is_active=True,
        created_at=None,
        last_login=None,
        last_login_at=None,
        last_activity_at=None,
    )
    db.add(admin)
    db.commit()
    print(f"Bootstrapped admin account: {ADMIN_USERNAME} ({ADMIN_EMAIL})")


def seed_database(db: Session, force: bool = False) -> int:
    """Populate database with seed problems if empty or if force is True."""
    try:
        existing_count = db.query(Problem).count()
    except Exception:
        init_db()
        existing_count = 0

    if existing_count > 0 and not force:
        print(f"Database already contains {existing_count} problems. Skipping seed.")
        return existing_count

    if force:
        init_db()

    print(f"Seeding {len(SEED_PROBLEMS)} original problems into database...")
    added_count = 0


    for item in SEED_PROBLEMS:
        # Resolve domains
        domain_objs = []
        for d_name in item.get("domains", []):
            name_clean = d_name.strip()
            domain_obj = db.query(Domain).filter(Domain.name == name_clean).first()
            if not domain_obj:
                domain_obj = Domain(name=name_clean)
                db.add(domain_obj)
                db.flush()
            domain_objs.append(domain_obj)

        # Resolve tags
        tag_objs = []
        for t_name in item.get("tags", []):
            tag_clean = t_name.strip().lower()
            tag_obj = db.query(Tag).filter(Tag.name == tag_clean).first()
            if not tag_obj:
                tag_obj = Tag(name=tag_clean)
                db.add(tag_obj)
                db.flush()
            tag_objs.append(tag_obj)

        # Upsert problem
        existing = db.query(Problem).filter(Problem.id == item["id"]).first()
        if existing:
            existing.title = item["title"]
            existing.source = item["source"]
            existing.source_url = item["source_url"]
            existing.external_id = item.get("external_id")
            existing.problem_type = item["problem_type"]
            existing.difficulty = item["difficulty"]
            existing.rating = item.get("rating")
            existing.description = item["description"]
            existing.input_format = item.get("input_format")
            existing.output_format = item.get("output_format")
            existing.examples = item.get("examples", [])
            existing.constraints = item.get("constraints", [])
            existing.concepts = item.get("concepts", [])
            existing.prerequisites = item.get("prerequisites", [])
            existing.starter_code = item.get("starter_code", {})
            existing.supported_languages = item.get("supported_languages", [])
            existing.domains = domain_objs
            existing.tags = tag_objs
        else:
            problem = Problem(
                id=item["id"],
                title=item["title"],
                source=item["source"],
                source_url=item["source_url"],
                external_id=item.get("external_id"),
                problem_type=item["problem_type"],
                difficulty=item["difficulty"],
                rating=item.get("rating"),
                description=item["description"],
                input_format=item.get("input_format"),
                output_format=item.get("output_format"),
                examples=item.get("examples", []),
                constraints=item.get("constraints", []),
                concepts=item.get("concepts", []),
                prerequisites=item.get("prerequisites", []),
                starter_code=item.get("starter_code", {}),
                supported_languages=item.get("supported_languages", []),
                domains=domain_objs,
                tags=tag_objs,
                is_active=True,
            )
            db.add(problem)
            added_count += 1

    db.commit()
    print(f"Successfully seeded database. Total problems now: {db.query(Problem).count()}.")
    return added_count

if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_database(db, force=True)
    finally:
        db.close()
