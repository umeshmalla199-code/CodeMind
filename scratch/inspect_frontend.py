import re

with open("Frontend/index.html", "r", encoding="utf-8") as f:
    content = f.read()

print(f"Frontend length: {len(content)}")
for term in ["authFetch", "getAuthToken", "getStudentId", "student_demo", "/api/progress", "/api/mastery", "/api/ai/companion", "loadProgressData", "error_dna", "skill_graph", "skillGraph", "Refresh"]:
    matches = [m.start() for m in re.finditer(re.escape(term), content)]
    print(f"{term}: {len(matches)} occurrences")
