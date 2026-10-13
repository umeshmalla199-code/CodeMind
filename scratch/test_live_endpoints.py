import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

def test_companion_chat():
    print("--- Testing /api/ai/companion/chat ---")
    url = "http://127.0.0.1:8000/api/ai/companion/chat"
    payload = {
        "message": "Explain arrays in simple terms.",
        "stream": False,
        "context": {
            "student_name": "TestUser",
            "bot_name": "Maya"
        }
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            print("Status:", resp.status)
            body = resp.read().decode('utf-8')
            res_json = json.loads(body)
            print("Response bot_name:", res_json.get("bot_name"))
            print("Response message preview:", res_json.get("message", "")[:200])
    except urllib.error.HTTPError as e:
        print("HTTPError:", e.code, e.reason)
        print("Body:", e.read().decode('utf-8'))
    except Exception as e:
        print("Error:", type(e).__name__, e)

def test_solution():
    print("\n--- Testing /api/ai/solution ---")
    url = "http://127.0.0.1:8000/api/ai/solution"
    # Get a problem ID first
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/problems") as p_resp:
            p_data = json.loads(p_resp.read().decode('utf-8'))
            items = p_data if isinstance(p_data, list) else p_data.get("items", [])
            if not items:
                print("No problems found")
                return
            prob_id = items[0]["id"]
            print("Using problem:", prob_id, items[0]["title"])
    except Exception as e:
        print("Failed getting problem:", e)
        return

    payload = {
        "problem_id": prob_id,
        "language": "python",
        "code": ""
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            print("Status:", resp.status)
            body = resp.read().decode('utf-8')
            res_json = json.loads(body)
            print("Solution keys:", list(res_json.keys()))
            print("Validation status:", res_json.get("validation_status"))
            print("Code preview:", res_json.get("code", "")[:200])
    except urllib.error.HTTPError as e:
        print("HTTPError:", e.code, e.reason)
        print("Body:", e.read().decode('utf-8'))
    except Exception as e:
        print("Error:", type(e).__name__, e)

if __name__ == "__main__":
    test_companion_chat()
    test_solution()
