"""Restore the body of the empty `else if (languageSelect)` branch.

This is a pre-existing truncation in the uncommitted work: the branch has no
body, so the selected language silently never reaches the request context.

The fix is anchored on the preceding `takingLanguageSelect` line so it can only
ever match the intended site.
"""
import sys

PATH = "Frontend/index.html"

OLD = (
    "                    lang = document.getElementById('takingLanguageSelect').value;\n"
    "                } else if (document.getElementById('languageSelect')) {\n"
    "                } else if (typeof getActiveLanguage === 'function') {"
)

NEW = (
    "                    lang = document.getElementById('takingLanguageSelect').value;\n"
    "                } else if (document.getElementById('languageSelect')) {\n"
    "                    lang = document.getElementById('languageSelect').value;\n"
    "                } else if (typeof getActiveLanguage === 'function') {"
)


def main():
    with open(PATH, "r", encoding="utf-8", newline="") as f:
        data = f.read()

    old = OLD.replace("\n", "\r\n")
    new = NEW.replace("\n", "\r\n")

    if new in data:
        print("ALREADY_FIXED")
        return 0

    n = data.count(old)
    if n != 1:
        print("ANCHOR_PROBLEM count=%d" % n)
        return 1

    data = data.replace(old, new, 1)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    print("REPAIRED empty languageSelect branch")
    return 0


if __name__ == "__main__":
    sys.exit(main())
