"""
Comprehensive Unit Tests for CodeMind REPAIR 8:
Workspace, UI Stability, and Security Hardening.

Required Test Cases:
1. Desktop workspace (layout structure, 3 panels present, min-width: 0 support)
2. Narrow viewport (responsive media query rules and stacking behavior)
3. Problem + editor + Maya simultaneous layout (ratio, flex priorities, no overflow)
4. X-Ray collapsed/expanded state and compact vertical footprint
5. Execution output drawer collapsed/expanded state
6. Loading state (clear indicators, retry functionality)
7. API failure state (graceful fallback with retry actions)
8. Admin authentication (server-side authorization and session admin detection)
9. Frontend source contains no admin/API secrets
10. Backend starts from declared dependencies (requirements.txt completeness)
"""
import re
import os
import pytest
from fastapi.testclient import TestClient

from main import app
from auth import (
    ADMIN_KEY,
    get_current_user,
    require_admin,
    AuthenticatedUser,
)
from models.user import UserAccount
from db.session import SessionLocal

client = TestClient(app)

# Resolve paths relative to the project root (two levels up from this test file:
# Backend/tests/test_workspace_security_repair8.py -> Backend/tests -> Backend -> project root)
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_FRONTEND_HTML = os.path.join(_PROJECT_ROOT, "Frontend", "index.html")
_REQUIREMENTS_TXT = os.path.join(_PROJECT_ROOT, "requirements.txt")


# ── TEST 1: DESKTOP WORKSPACE LAYOUT ─────────────────────────────────────────
def test_desktop_workspace_layout():
    """Verify that the desktop workspace has a stable 3-panel grid and min-width: 0."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Verify workspace grid element exists
    assert 'id="workspace3ColGrid"' in html
    assert 'class="workspace-3col"' in html

    # Verify grid template defines 3 columns with code editor priority (~45-50%)
    match = re.search(r'\.workspace-3col\s*\{([^}]*)\}', html)
    assert match is not None
    rules = match.group(1)
    assert 'grid-template-columns:' in rules
    assert 'minmax(0,' in rules

    # Verify min-width: 0 is enforced on children
    child_match = re.search(r'\.workspace-3col\s*>\s*\*[^\{]*\{([^}]*)\}', html)
    assert child_match is not None
    assert 'min-width: 0' in child_match.group(1)


# ── TEST 2: NARROW VIEWPORT RESPONSIVENESS ───────────────────────────────────
def test_narrow_viewport_responsive():
    """Verify responsive breakpoints collapse 3-column workspace to single column on mobile/tablet."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Verify unified @media (max-width: 1024px) rule collapses to 1fr
    media_match = re.search(r'@media\s*\(max-width:\s*1024px\)\s*\{([\s\S]*?)\n\s*\}', html)
    assert media_match is not None
    media_rules = media_match.group(1)
    assert 'grid-template-columns: 1fr' in media_rules


# ── TEST 3: PROBLEM + EDITOR + MAYA SIMULTANEOUS EXISTENCE ───────────────────
def test_three_panels_simultaneous():
    """Verify Problem, Editor, and Maya panels exist simultaneously with proper ws-panel attributes."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Panel 1: Problem panel
    assert 'id="problemPanelWs"' in html
    # Panel 2: Editor panel
    assert 'id="editorPanelWs"' in html
    # Panel 3: Maya AI panel
    assert 'id="aiPanelWs"' in html

    # Verify .ws-panel has min-width: 0 to prevent grid item blowout
    ws_panel_match = re.search(r'\.ws-panel\s*\{([^}]*)\}', html)
    assert ws_panel_match is not None
    assert 'min-width: 0' in ws_panel_match.group(1)


# ── TEST 4: CODE X-RAY FOOTPRINT & COLLAPSIBILITY ────────────────────────────
def test_xray_compact_and_collapsible():
    """Verify Code X-Ray has a bounded height (not consuming workspace) and toggle function exists."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # X-Ray container must be bounded (max-height <= 260px)
    xray_css = re.search(r'\.xray-container\s*\{([^}]*)\}', html)
    assert xray_css is not None
    rules = xray_css.group(1)
    max_h = re.search(r'max-height:\s*(\d+)px', rules)
    assert max_h is not None
    assert int(max_h.group(1)) <= 260  # Controlled, not 520px

    # Toggle collapse function exists
    assert 'function toggleXrayCollapse()' in html
    assert 'function closeXray()' in html


# ── TEST 5: EXECUTION OUTPUT COLLAPSIBLE ──────────────────────────────────────
def test_execution_output_collapsible():
    """Verify execution drawer has a collapsible toggle function and drawer markup."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="executionOutputDrawer"' in html
    assert 'id="outputDrawerBody"' in html
    assert 'function toggleOutputDrawer()' in html
    assert '.output-drawer-body.collapsed' in html


# ── TEST 6: LOADING UX DISTINCTION ───────────────────────────────────────────
def test_loading_ux_distinction():
    """Verify distinct loading indicators for dashboard, problems, and VRM companion."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Loading states defined and distinct from static failure
    assert 'class="loading-cell"' in html
    assert 'class="dash-loading"' in html
    assert 'id="companionLoadingOverlay"' in html


# ── TEST 7: API FAILURE UX & RETRY STATES ────────────────────────────────────
def test_api_failure_ux_with_retry():
    """Verify failed API operations present actionable retry buttons and clear error messaging."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Problem library network failure has Retry button
    assert 'Retry Connection' in html
    # loadAdminTests has retry UI
    assert 'Error Loading Assessment Tests' in html
    assert 'loadAdminTests()' in html


# ── TEST 8: ADMIN AUTHENTICATION SERVER-SIDE ─────────────────────────────────
def test_admin_authentication_server_side():
    """Verify that admin access is strictly controlled by the backend."""
    # 1. Anonymous access to admin endpoints must be rejected (401 or 403)
    resp = client.get("/api/admin/tests")
    assert resp.status_code in (401, 403)

    # 2. Standard student session must be rejected with 403 Forbidden
    student_user = AuthenticatedUser(
        user_id="student_123",
        role="student",
        is_admin=False,
        student_id="student_123"
    )
    with pytest.raises(Exception):
        require_admin(student_user)

    # 3. Admin user passes require_admin check
    admin_user = AuthenticatedUser(
        user_id="admin_123",
        role="admin",
        is_admin=True,
        student_id="admin_123"
    )
    result = require_admin(admin_user)
    assert result.is_admin is True

    # 4. Valid ADMIN_KEY header allows access
    admin_resp = client.get("/api/admin/tests", headers={"X-Admin-Key": ADMIN_KEY})
    assert admin_resp.status_code == 200


# ── TEST 9: FRONTEND SOURCE CONTAINS NO ADMIN OR API SECRETS ──────────────────
def test_frontend_source_contains_no_secrets():
    """Verify that Frontend/index.html contains zero hardcoded admin keys or cloud provider secrets."""
    with open(_FRONTEND_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Zero occurrences of X-Admin-Key
    assert "X-Admin-Key" not in html

    # 2. Zero occurrences of default admin secret value
    assert "codemind-admin" not in html

    # 3. Zero real provider API key prefixes
    assert not re.search(r'gsk_[a-zA-Z0-9_\-]{20,}', html)
    assert not re.search(r'nvapi-[a-zA-Z0-9_\-]{20,}', html)
    assert not re.search(r'sk-proj-[a-zA-Z0-9_\-]{20,}', html)


# ── TEST 10: BACKEND STARTS FROM DECLARED DEPENDENCIES ───────────────────────
def test_backend_dependencies_declared():
    """Verify that all core runtime imports needed by FastAPI backend are declared in requirements.txt."""
    with open(_REQUIREMENTS_TXT, "r", encoding="utf-8") as f:
        reqs = f.read().lower()

    # Ensure required packages are declared
    required_packages = [
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "pydantic",
        "alembic",
        "openai",
        "python-dotenv",
        "pytest",
    ]

    for pkg in required_packages:
        assert pkg in reqs, f"Required package '{pkg}' missing from requirements.txt"
