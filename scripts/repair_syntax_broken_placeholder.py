"""Repair a pre-existing syntax-breaking deletion in the uncommitted frontend work.

The line
    trimmedCode === '// Select a problem to view starter code';
is missing from sendCompanionMessage()'s placeholder check. Without it the
expression ends with a bare `||` followed by `let lang = null;`, which is a
SyntaxError, so the ENTIRE main application script fails to parse and no Maya
feature works at all.

This restores only that one line. It does not revert, stash, or discard any
other uncommitted work.
"""
import sys

PATH = "Frontend/index.html"

BROKEN = """            const isPlaceholderCode = !trimmedCode ||
                trimmedCode === '# Select a problem to view starter code' ||

            let lang = null;"""

FIXED = """            const isPlaceholderCode = !trimmedCode ||
                trimmedCode === '# Select a problem to view starter code' ||
                trimmedCode === '// Select a problem to view starter code';

            let lang = null;"""


def main():
    with open(PATH, "r", encoding="utf-8", newline="") as f:
        data = f.read()

    if FIXED.replace("\n", "\r\n") in data:
        print("ALREADY_FIXED")
        return 0

    broken = BROKEN.replace("\n", "\r\n")
    fixed = FIXED.replace("\n", "\r\n")

    if data.count(broken) != 1:
        print("BROKEN_BLOCK_NOT_FOUND count=%d" % data.count(broken))
        return 1

    data = data.replace(broken, fixed, 1)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    print("REPAIRED missing C++ placeholder line")
    return 0


if __name__ == "__main__":
    sys.exit(main())
