"""Repair two pre-existing SyntaxErrors in the uncommitted frontend work.

The uncommitted Antigravity changes added a Groq-key gate at the top of
sendCompanionMessage() (declaring `const user`) and separately truncated the
`else if (document.getElementById('languageSelect'))` branch, leaving an empty
branch and a second `const user` declaration later in the same function scope.

Both make the ENTIRE main application script fail to parse, so no Maya feature
works at all. This restores only those two spots and touches nothing else.
"""
import sys

PATH = "Frontend/index.html"

# Repair 1: the empty `else if` branch needs its body back.
OLD1 = """                } else if (document.getElementById('languageSelect')) {
                } else if (typeof getActiveLanguage === 'function') {"""

NEW1 = """                } else if (document.getElementById('languageSelect')) {
                    lang = document.getElementById('languageSelect').value;
                } else if (typeof getActiveLanguage === 'function') {"""

# Repair 2: remove the duplicated `const user` (the earlier Groq-gate one stays,
# it is what `hasGroq` below it depends on).
OLD2 = """            }
            const user = getAuthUser();
            let studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
            const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
            const sid = getStudentId();
            const token = getAuthToken();"""

NEW2 = """            }
            let studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
            const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
            const sid = getStudentId();
            const token = getAuthToken();"""


def main():
    with open(PATH, "r", encoding="utf-8", newline="") as f:
        data = f.read()

    changed = []

    if NEW1.replace("\n", "\r\n") in data:
        print("REPAIR1 already applied")
    else:
        o = OLD1.replace("\n", "\r\n")
        n = NEW1.replace("\n", "\r\n")
        if data.count(o) != 1:
            print("REPAIR1 anchor problem count=%d" % data.count(o))
            return 1
        data = data.replace(o, n, 1)
        changed.append("empty else-if branch")

    if NEW2.replace("\n", "\r\n") in data:
        print("REPAIR2 already applied")
    else:
        o = OLD2.replace("\n", "\r\n")
        n = NEW2.replace("\n", "\r\n")
        if data.count(o) != 1:
            print("REPAIR2 anchor problem count=%d" % data.count(o))
            return 1
        data = data.replace(o, n, 1)
        changed.append("duplicate const user")

    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    print("REPAIRED:", ", ".join(changed) if changed else "nothing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
