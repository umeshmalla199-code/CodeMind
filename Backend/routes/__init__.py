from routes.problems import router as problems_router
from routes.topics import router as topics_router
from routes.sources import router as sources_router
from routes.execution import router as execution_router
from routes.tests import router as tests_router
from routes.ai import router as ai_router
from routes.progress import router as progress_router
from routes.mastery import mastery_router
from routes.auth import router as auth_router
from routes.admin import router as admin_router

__all__ = [
    "problems_router",
    "topics_router",
    "sources_router",
    "execution_router",
    "tests_router",
    "ai_router",
    "progress_router",
    "mastery_router",
    "auth_router",
    "admin_router",
]
