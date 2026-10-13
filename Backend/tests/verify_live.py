import urllib.request
import json

base = "http://127.0.0.1:8000"

# 1. Health
with urllib.request.urlopen(f"{base}/") as r:
    assert r.status == 200
    print("[OK] Backend health:", json.loads(r.read().decode()))

# 2. Problems count and list
with urllib.request.urlopen(f"{base}/problems?page=1&page_size=10") as r:
    assert r.status == 200
    pdata = json.loads(r.read().decode())
    total = pdata["total"]
    items = pdata["items"]
    print(f"[OK] Problems loaded: {len(items)} on page 1, Total in database: {total}")

# 3. Search
with urllib.request.urlopen(f"{base}/problems?page=1&page_size=10&search=palindrome") as r:
    assert r.status == 200
    sdata = json.loads(r.read().decode())
    print(f"[OK] Search working: found {sdata['total']} matching problem(s)")
    assert sdata["total"] >= 1

# 4. Filter - Difficulty
with urllib.request.urlopen(f"{base}/problems?page=1&page_size=10&difficulty=Easy") as r:
    assert r.status == 200
    fdata = json.loads(r.read().decode())
    print(f"[OK] Difficulty filter working: {fdata['total']} Easy problems found")
    assert fdata["total"] > 0

# 5. Filter - Domain
with urllib.request.urlopen(f"{base}/problems?page=1&page_size=10&domain=Arrays") as r:
    assert r.status == 200
    ddata = json.loads(r.read().decode())
    print(f"[OK] Domain filter working: {ddata['total']} Arrays problems found")
    assert ddata["total"] > 0

# 6. Filter - Source
with urllib.request.urlopen(f"{base}/problems?page=1&page_size=10&source=Codeforces") as r:
    assert r.status == 200
    cdata = json.loads(r.read().decode())
    print(f"[OK] Source filter working: {cdata['total']} Codeforces problems found")
    assert cdata["total"] >= 3

# 7. Pagination
with urllib.request.urlopen(f"{base}/problems?page=2&page_size=10") as r:
    assert r.status == 200
    page2 = json.loads(r.read().decode())
    print(f"[OK] Pagination working: page 2 returned {len(page2['items'])} items, page indicator: {page2['page']}/{page2['total_pages']}")
    assert len(page2["items"]) > 0

# 8. Detail view
with urllib.request.urlopen(f"{base}/problems/two-sum-target") as r:
    assert r.status == 200
    detail = json.loads(r.read().decode())
    print(f"[OK] Problem detail view: '{detail['title']}' loaded successfully with {len(detail['examples'])} examples")

print("ALL LIVE CHECKS COMPLETED SUCCESSFULLY.")
