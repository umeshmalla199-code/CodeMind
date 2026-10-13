"""Add per-request abort + identity isolation to the companion panel Send action.

ROOT CAUSE fixed here: the companion panel created no AbortController and no
request_id binding. An in-flight fetch kept streaming into the shared bubble even
after a newer Send started, and there was no way to cancel the superseded
upstream work. Every Send is now one logical request with its own identity,
and the previous request is aborted before a new one begins.

Idempotent.
"""
import sys

PATH = "Frontend/index.html"

# 1. Bind a request_id + AbortController at Send time.
OLD1 = """            isCompanionSending = true;
            const thisRequestId = ++companionCurrentRequestId;
"""

NEW1 = """            isCompanionSending = true;
            const thisRequestId = ++companionCurrentRequestId;

            // One Send click == one logical request. Abort any superseded
            // in-flight request so it cannot write into the shared bubble or
            // append a stale turn to history, and so the upstream provider work
            // is actually cancelled instead of running to completion unwatched.
            if (window.__currentMayaAbortController) {
                try { window.__currentMayaAbortController.abort('superseded'); } catch (e) {}
            }
            const companionAbortController = new AbortController();
            window.__currentMayaAbortController = companionAbortController;
            // Stable identity for this logical request, echoed back by the server
            // on every SSE frame so stale responses can be rejected precisely.
            const companionRequestId = generateMayaRequestId();
"""

# 2. Use the stable id in the payload and pass the abort signal to fetch.
OLD2 = """                conversation_id: getOrCreateMayaConversationId(),
                request_id: generateMayaRequestId(),
                context: {
                    student_id: sid,"""

NEW2 = """                conversation_id: getOrCreateMayaConversationId(),
                request_id: companionRequestId,
                context: {
                    student_id: sid,"""

OLD3 = """                const res = await fetch(`${API_BASE}/api/ai/companion/chat`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload)
                });
"""

NEW3 = """                const res = await fetch(`${API_BASE}/api/ai/companion/chat`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload),
                    signal: companionAbortController.signal
                });
"""

# 3. Treat an abort as cancellation, not as a connection error.
OLD4 = """            } catch (err) {
                if (thisRequestId === companionCurrentRequestId) {
                    console.error('Companion chat failed:', err);"""

NEW4 = """            } catch (err) {
                // A superseded request is cancelled, not failed: show nothing.
                if (err && (err.name === 'AbortError' || companionAbortController.signal.aborted)) {
                    return;
                }
                if (thisRequestId === companionCurrentRequestId) {
                    console.error('Companion chat failed:', err);"""


def main():
    with open(PATH, "r", encoding="utf-8", newline="") as f:
        data = f.read()

    if "const companionRequestId = generateMayaRequestId();" in data:
        print("ALREADY_REPLACED")
        return 0

    pairs = [(OLD1, NEW1), (OLD2, NEW2), (OLD3, NEW3), (OLD4, NEW4)]
    for old, new in pairs:
        o = old.replace("\n", "\r\n")
        n = new.replace("\n", "\r\n")
        if data.count(o) != 1:
            print("ANCHOR_PROBLEM count=%d for: %r" % (data.count(o), old[:60]))
            return 1
        data = data.replace(o, n, 1)

    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    print("APPLIED companion request isolation (%d edits)" % len(pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
