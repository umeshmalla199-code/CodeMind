with open("Frontend/index.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

def find_lines(pattern):
    print(f"=== Pattern: {pattern} ===")
    for i, line in enumerate(lines):
        if pattern in line:
            print(f"Line {i+1}: {line.strip()[:140]}")

find_lines("function authFetch")
find_lines("function getAuthToken")
find_lines("function getStudentId")
find_lines("function loadProgressData")
find_lines("error_dna")
find_lines("skillGraph")
find_lines("skill_graph")
