"""Apply the same two repairs to every occurrence of the damaged block.

The uncommitted work truncated the same code shape in BOTH Maya consumers
(sendCompanionMessage and the AI-tutor streaming path):
  1. `else if (document.getElementById('languageSelect')) {` with an empty body
  2. a second `const user = getAuthUser();` in the same function scope

Both are SyntaxErrors that prevent the whole application script from parsing.

Idempotent.
"""
import re
import sys

PATH = "Frontend/index.html"

EMPTY_BRANCH_OLD = (
    "                } else if (document.getElementById('languageSelect')) {\n"
    "                } else if (typeof getActiveLanguage === 'function') {"
)
EMPTY_BRANCH_NEW = (
    "                } else if (document.getElementById('languageSelect')) {\n"
    "                    lang = document.getElementById('languageSelect').value;\n"
    "                } else if (typeof getActiveLanguage === 'function') {"
)

DUP_USER_OLD = (
    "            }\n"
    "            const user = getAuthUser();\n"
    "            let studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';\n"
)
DUP_USER_NEW = (
    "            }\n"
    "            let studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';\n"
)


def main():
    with open(PATH, "r", encoding="utf-8", newline="") as f:
        data = f.read()

    report = []

    # Repair 1: fill every empty languageSelect branch.
    empty = EMPTY_BRANCH_OLD.replace("\n", "\r\n")
    filled = EMPTY_BRANCH_NEW.replace("\n", "\r\n")
    n_empty = data.count(empty)
    if n_empty:
        data = data.replace(empty, filled)
        report.append("filled %d empty languageSelect branch(es)" % n_empty)
    else:
        report.append("empty languageSelect branch: already repaired")

    # Repair 2: drop the duplicated `const user` declarations.
    dup = DUP_USER_OLD.replace("\n", "\r\n")
    dedup = DUP_USER_NEW.replace("\n", "\r\n")
    n_dup = data.count(dup)
    if n_dup:
        data = data.replace(dup, dedup)
        report.append("removed %d duplicate const user" % n_dup)
    else:
        report.append("duplicate const user: already repaired")

    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(data)

    for r in report:
        print(" -", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
