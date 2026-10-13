import urllib.request
import urllib.parse
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def request_json(path, method="GET", body=None, headers=None):
    url = BASE_URL + path
    headers = headers or {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_content)
        except Exception:
            return e.code, {"error": err_content}

def test_critical_acceptance():
    print("=" * 60)
    print("CODEMIND ACCEPTANCE VERIFICATION AGAINST RUNNING BACKEND")
    print(f"Target: {BASE_URL}")
    print("=" * 60)

    # 1. Health check
    status, health = request_json("/api/health")
    assert status == 200, f"Health check failed with {status}"
    assert health.get("status") == "healthy"
    print(f"[OK] 1. GET /api/health -> 200 OK: {health['status']}")

    # 2. Problem library listing
    status, problems = request_json("/problems?page=1&page_size=10")
    assert status == 200, f"/problems failed with {status}"
    items = problems.get("items", [])
    total = problems.get("total", 0)
    assert len(items) == 10, f"Expected 10 problems, got {len(items)}"
    assert total >= 11475, f"Expected >= 11475 problems, got {total}"
    print(f"[OK] 2. GET /problems?page=1&page_size=10 -> 200 OK: returned {len(items)} problems (Total in DB: {total})")

    # 3. Topics and Sources
    status, topics = request_json("/topics")
    assert status == 200
    status, sources = request_json("/sources")
    assert status == 200
    print(f"[OK] 3. GET /topics & /sources -> 200 OK: {len(topics)} topics, {len(sources)} sources")

    # 4. Open single problem detail
    first_pid = items[0]["id"]
    status, prob = request_json(f"/problems/{first_pid}")
    assert status == 200
    assert prob["id"] == first_pid
    assert "title" in prob
    assert "description" in prob
    print(f"[OK] 4. Open Problem -> GET /problems/{first_pid} -> 200 OK: '{prob['title']}'")

    # 5. Frontend index.html served at root
    req = urllib.request.Request(f"{BASE_URL}/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")
        assert "CodeMind" in html
        assert "API_BASE" in html
    print("[OK] 5. GET / -> 200 OK: Frontend served by FastAPI correctly")

    # 6. VRM model endpoint
    req_vrm = urllib.request.Request(f"{BASE_URL}/mira%20vrm.vrm")
    with urllib.request.urlopen(req_vrm) as resp:
        assert resp.status == 200
        content_len = int(resp.headers.get("Content-Length", 0))
        assert content_len > 10000000, f"VRM model file too small: {content_len} bytes"
    print(f"[OK] 6. GET /mira%20vrm.vrm -> 200 OK: ({content_len:,} bytes)")

    # 7. Register new user
    ts = int(time.time())
    reg_user = f"recov_{ts}"
    status, reg_data = request_json("/api/auth/register", method="POST", body={
        "username": reg_user,
        "email": f"{reg_user}@test.com",
        "display_name": f"Recover Learner {ts}",
        "password": "Password123!"
    })
    assert status == 201, f"Register failed: {reg_data}"
    token = reg_data["token"]
    user_id = reg_data["user"]["id"]
    print(f"[OK] 7. POST /api/auth/register -> 201 Created: user={reg_user}, token={token[:12]}...")

    # 8. Login with registered user
    status, login_data = request_json("/api/auth/login", method="POST", body={
        "username": reg_user,
        "password": "Password123!"
    })
    assert status == 200, f"Login failed: {login_data}"
    session_token = login_data["token"]
    print(f"[OK] 8. POST /api/auth/login -> 200 OK: session token issued")

    # 9. Authenticated profile /api/auth/me
    auth_headers = {"Authorization": f"Bearer {session_token}"}
    status, me_data = request_json("/api/auth/me", headers=auth_headers)
    assert status == 200, f"/api/auth/me failed: {me_data}"
    assert me_data["user"]["username"] == reg_user
    print(f"[OK] 9. GET /api/auth/me -> 200 OK: authenticated user is {me_data['user']['display_name']}")

    # 10. Dashboard progress & mastery for user
    status, prog = request_json(f"/api/progress?student_id={user_id}", headers=auth_headers)
    assert status == 200
    status, mastery = request_json(f"/api/mastery/dashboard?student_id={user_id}", headers=auth_headers)
    assert status == 200
    print(f"[OK] 10. Dashboard APIs -> progress & mastery 200 OK (meaningful initial state)")

    # 11. Maya AI companion endpoint
    status, maya_data = request_json("/api/ai/companion/chat", method="POST", body={
        "message": "Hello Maya, what is a binary tree?",
        "stream": False,
        "context": {
            "problem_id": first_pid,
            "problem_title": prob["title"],
            "selected_language": "python",
            "student_name": me_data["user"]["display_name"]
        }
    }, headers=auth_headers)
    assert status == 200, f"Maya chat failed: {maya_data}"
    assert "message" in maya_data
    print(f"[OK] 11. POST /api/ai/companion/chat -> 200 OK: Maya responded ({len(maya_data['message'])} chars)")

    # 12. Code Execution endpoint
    status, exec_data = request_json("/api/execute", method="POST", body={
        "language": "python",
        "source_code": "print('CodeMind Foundation Working 100%')",
        "custom_input": ""
    })
    assert status == 200, f"Execute failed: {exec_data}"
    assert "CodeMind Foundation Working 100%" in exec_data.get("output", "")
    print(f"[OK] 12. POST /api/execute -> 200 OK: Code execution engine responded correctly")

    print("=" * 60)
    print("ALL 12 ACCEPTANCE VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_critical_acceptance()
