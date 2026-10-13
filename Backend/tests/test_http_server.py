import os
import sys
import time
import subprocess
import urllib.request
import json
from pathlib import Path

def test_live_server():
    project_root = Path(__file__).resolve().parent.parent.parent
    python_exe = project_root / "Backend" / "venv" / "Scripts" / "python.exe"

    print("Launching Uvicorn backend server on 127.0.0.1:8000...")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root / "Backend")
    proc = subprocess.Popen(
        [str(python_exe), "-m", "uvicorn", "main:app", "--app-dir", str(project_root / "Backend"), "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        # Wait for server to start
        time.sleep(3)

        base_url = "http://127.0.0.1:8000"

        # 1. Health check
        req = urllib.request.Request(f"{base_url}/")
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            print(f"[OK] GET / -> {data}")
            assert data["message"] == "CodeMind backend is working!"

        # 2. GET /problems (with Origin header to verify CORS)
        req = urllib.request.Request(
            f"{base_url}/problems?page=1&page_size=5",
            headers={"Origin": "http://localhost:3000"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            print(f"[OK] GET /problems -> Total: {data['total']}, Items on page: {len(data['items'])}")
            assert data["total"] >= 20
            assert len(data["items"]) == 5
            # Verify CORS headers
            assert "access-control-allow-origin" in [h.lower() for h in res.headers.keys()]

        # 3. GET /problems/two-sum-target
        req = urllib.request.Request(f"{base_url}/problems/two-sum-target")
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            print(f"[OK] GET /problems/two-sum-target -> Title: {data['title']}, Difficulty: {data['difficulty']}")
            assert data["title"] == "Two Sum Target"
            assert "python" in data["starter_code"]

        # 4. GET /topics
        req = urllib.request.Request(f"{base_url}/topics")
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            print(f"[OK] GET /topics -> {len(data)} topics returned")
            assert len(data) >= 10

        # 5. GET /sources
        req = urllib.request.Request(f"{base_url}/sources")
        with urllib.request.urlopen(req, timeout=5) as res:
            assert res.status == 200
            data = json.loads(res.read().decode())
            print(f"[OK] GET /sources -> {len(data)} sources: {[s['name'] for s in data]}")
            assert len(data) >= 2

        print("All HTTP endpoints responded successfully with valid JSON and CORS headers!")
    finally:
        print("Terminating test Uvicorn server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("Server stopped cleanly.")

if __name__ == "__main__":
    test_live_server()
