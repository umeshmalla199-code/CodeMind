import sys
import time
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "Backend"
sys.path.insert(0, str(backend_dir))

from starlette.testclient import TestClient
from main import app
from db.session import SessionLocal
from models import Problem, Test, TestQuestion

client = TestClient(app)

print("=" * 60)
print("CODEMIND DIRECT API STABILITY & ENDPOINT VERIFICATION")
print("=" * 60)

# 1. Health endpoints
print("\n[1] Health Check Endpoints")
for path in ["/api/health", "/health"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    data = res.json()
    assert data["status"] == "healthy"
    print(f"  [OK] GET {path:<25} -> 200 OK (service: {data['service']})")

# 2. Problem endpoints with and without /api prefix
print("\n[2] Problem Endpoints (/problems vs /api/problems)")
for path in ["/problems", "/api/problems"]:
    res = client.get(path, params={"page": 1, "page_size": 5})
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    data = res.json()
    assert "items" in data and "total" in data
    assert len(data["items"]) > 0
    print(f"  [OK] GET {path:<25} -> 200 OK (items: {len(data['items'])}, total: {data['total']})")

db = SessionLocal()
first_prob = db.query(Problem).filter(Problem.is_active == True).first()
pid = first_prob.id
db.close()

for path in [f"/problems/{pid}", f"/api/problems/{pid}"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    data = res.json()
    assert data["id"] == pid
    print(f"  [OK] GET {path:<25} -> 200 OK (title: {data['title']})")

# 3. Topic & Domain endpoints
print("\n[3] Topic & Domain Endpoints")
for path in ["/topics", "/api/topics", "/domains", "/api/domains"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    data = res.json()
    assert isinstance(data, list) and len(data) > 0
    assert "name" in data[0] and "problem_count" in data[0]
    print(f"  [OK] GET {path:<25} -> 200 OK (count: {len(data)})")

# 4. Source endpoints
print("\n[4] Source Endpoints")
for path in ["/sources", "/api/sources"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    data = res.json()
    assert isinstance(data, list) and len(data) > 0
    print(f"  [OK] GET {path:<25} -> 200 OK (sources: {len(data)})")

for path in ["/sources/Codeforces", "/api/sources/Codeforces"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    data = res.json()
    assert data["name"] == "Codeforces"
    print(f"  [OK] GET {path:<25} -> 200 OK (problems: {data.get('problem_count')})")

# 5. Execution endpoints
print("\n[5] Execution & Languages Endpoints")
for path in ["/api/execution/languages", "/execution/languages", "/languages"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    print(f"  [OK] GET {path:<25} -> 200 OK")

exec_payload = {
    "language": "python",
    "source_code": "print('hello from codemind')",
    "custom_input": ""
}
for path in ["/api/execute", "/execute", "/api/execution/run", "/run"]:
    res = client.post(path, json=exec_payload)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    data = res.json()
    assert data["success"] is True
    assert "hello from codemind" in data["output"]
    print(f"  [OK] POST {path:<24} -> 200 OK (output: {data['output'].strip()})")

prob_exec_payload = {
    "language": "python",
    "source_code": "print('prob test')",
}
for path in [f"/problems/{pid}/execute", f"/problems/{pid}/run", f"/api/problems/{pid}/execute", f"/api/problems/{pid}/run"]:
    res = client.post(path, json=prob_exec_payload)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    print(f"  [OK] POST {path:<24} -> 200 OK")

# 6. Test taking & Assessment endpoints
print("\n[6] Test & Assessment Endpoints")
for path in ["/api/tests", "/tests"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    print(f"  [OK] GET {path:<25} -> 200 OK (tests: {len(res.json())})")

# Test-specific retrieval and submission
db = SessionLocal()
test_obj = db.query(Test).filter(Test.is_active == True).first()
if not test_obj:
    test_obj = Test(id="stability-test-1", title="Stability Test", duration_minutes=30, is_active=True)
    db.merge(test_obj)
    db.commit()
test_id = test_obj.id
db.close()

for path in [f"/api/tests/{test_id}", f"/tests/{test_id}"]:
    res = client.get(path)
    assert res.status_code == 200, f"{path} failed: {res.status_code}"
    assert res.json()["id"] == test_id
    print(f"  [OK] GET {path:<25} -> 200 OK")

for path in [f"/api/tests/{test_id}/submission", f"/tests/{test_id}/submission"]:
    res = client.get(path)
    assert res.status_code in (200, 404, 401), f"{path} unexpected status: {res.status_code}"
    print(f"  [OK] GET {path:<25} -> {res.status_code}")

for path in ["/api/tests/history", "/tests/history", "/api/assessment/history", "/assessment/history"]:
    res = client.get(path)
    assert res.status_code in (200, 401), f"{path} failed: {res.status_code}"
    print(f"  [OK] GET {path:<25} -> {res.status_code}")

for path in ["/api/tests/unsolved", "/tests/unsolved", "/api/assessment/unsolved", "/assessment/unsolved"]:
    res = client.get(path)
    assert res.status_code in (200, 401), f"{path} failed: {res.status_code}"
    print(f"  [OK] GET {path:<25} -> {res.status_code}")

# 7. AI similar problems speed & bounded memory
print("\n[7] AI Similar Problems Bounded Latency")
t0 = time.perf_counter()
res = client.get(f"/api/ai/similar-problems?problem_id={pid}&limit=5")
t1 = time.perf_counter()
assert res.status_code == 200
data = res.json()
assert "similar_problems" in data
latency = t1 - t0
print(f"  [OK] GET /api/ai/similar-problems  -> 200 OK ({len(data['similar_problems'])} items in {latency:.3f}s)")
assert latency < 3.0, f"Latency {latency:.3f}s exceeded bounded threshold!"

# 8. Structured Error Handling
print("\n[8] Structured Error Handling (JSON {detail: ...})")
res_404 = client.get("/api/problems/non-existent-problem-id-xyz")
assert res_404.status_code == 404
assert "detail" in res_404.json()
print(f"  [OK] 404 Structured JSON -> {res_404.json()}")

res_400 = client.post("/api/execute", json={"invalid": "payload"})
assert res_400.status_code == 400
assert "detail" in res_400.json()
print(f"  [OK] 400 Bad Request -> structured: {res_400.json()}")

res_422 = client.get("/api/problems?page=notanumber")
assert res_422.status_code == 422
assert "detail" in res_422.json()
print(f"  [OK] 422 Validation Error -> structured: {res_422.json()['detail'][0]['msg']}")

print("\n" + "=" * 60)
print("ALL DIRECT API STABILITY CHECKS PASSED PERFECTLY!")
print("=" * 60)
