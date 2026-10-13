"""Insert the shared Maya SSE parser + terminal-state helpers into Frontend/index.html.

Idempotent: refuses to insert twice.
"""
import io
import sys

PATH = "Frontend/index.html"
ANCHOR = b"        let companionCurrentRequestId = 0;\r\n"
MARKER = b"function createSSEParser(onEvent)"

HELPER = b"""        // Monotonic sequence for shared request-identity handling. The companion
        // panel and the AI-tutor panel both route through these so a newer request
        // can never be overwritten by an older in-flight response.
        let mayaCurrentRequestSeq = 0;
        window.__currentMayaAbortController = null;

        const MAYA_TERMINAL = Object.freeze({
            COMPLETED: 'COMPLETED',
            INTERRUPTED: 'INTERRUPTED',
            FAILED: 'FAILED',
            CANCELLED: 'CANCELLED'
        });
        window.MAYA_TERMINAL = MAYA_TERMINAL;

        /**
         * Parses an SSE byte stream into discrete frames.
         *
         * ROOT CAUSE this replaces: every Maya consumer had its own inline parser
         * that split on '\\n' and parked the trailing partial line in `buffer`.
         * When the server's final frame arrived without a trailing newline, that
         * event was silently dropped and the turn looked incomplete or hung. A
         * multi-byte character straddling a chunk boundary was also lost.
         *
         * flush() at end-of-stream guarantees the final buffered frame is
         * emitted, and TextDecoder runs with {stream:true} plus a final decode()
         * so split multi-byte characters are never corrupted.
         */
        function createSSEParser(onEvent) {
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let currentEvent = 'message';

            function dispatchOne(rawLine) {
                const line = rawLine.replace(/\\r$/, '');
                if (!line) return;
                if (line.startsWith(':')) return; // SSE comment / keep-alive

                if (line.startsWith('event:')) {
                    currentEvent = line.slice(6).trim();
                    return;
                }
                if (line.startsWith('data:')) {
                    const dataRaw = line.slice(5).trim();
                    if (!dataRaw) return;
                    try {
                        onEvent(currentEvent, JSON.parse(dataRaw));
                    } catch (e) {
                        // A malformed frame must never abort the rest of the stream.
                        console.warn('Maya SSE: ignoring unparseable frame', e);
                    }
                }
            }

            function feedLines(final) {
                const lines = buffer.split('\\n');
                // Without a trailing newline the last element is an incomplete
                // frame, so hold it back unless this is the final flush.
                buffer = final ? '' : (lines.pop() || '');
                for (const line of lines) dispatchOne(line);
            }

            return {
                push(value) {
                    buffer += decoder.decode(value, { stream: true });
                    feedLines(false);
                },
                /** Flush decoder + trailing buffer. MUST be called after done. */
                flush() {
                    try { buffer += decoder.decode(); } catch (e) { /* no-op */ }
                    feedLines(true);
                    if (buffer) {
                        // Last line arrived with no newline terminator at all.
                        const tail = buffer;
                        buffer = '';
                        dispatchOne(tail);
                    }
                }
            };
        }

        /** Reads an SSE response body, guaranteeing the final frame is processed. */
        async function readSSEStream(response, onEvent) {
            const parser = createSSEParser(onEvent);
            const reader = response.body.getReader();
            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    if (value) parser.push(value);
                }
            } finally {
                // Always flush: this is what guarantees the terminal `done` event
                // is seen even when the server closed without a trailing newline.
                parser.flush();
            }
        }

        /**
         * Classifies the terminal state of a Maya turn.
         * COMPLETED only when the server said so. A stream that simply stopped
         * without a done event is INTERRUPTED, never a silent success.
         */
        function resolveMayaTerminalState(doneData, receivedDone) {
            if (doneData && doneData.status) {
                const s = String(doneData.status).toUpperCase();
                if (s === 'COMPLETED') return MAYA_TERMINAL.COMPLETED;
                if (s === 'INTERRUPTED' || s === 'FAILED' || s === 'CANCELLED') return s;
            }
            if (receivedDone) return MAYA_TERMINAL.COMPLETED;
            return MAYA_TERMINAL.INTERRUPTED;
        }

        /** Student-safe status-pill label for a terminal state. */
        function mayaTerminalLabel(state) {
            switch (state) {
                case MAYA_TERMINAL.COMPLETED: return '\\u25cf Idle';
                case MAYA_TERMINAL.INTERRUPTED: return '\\u26a0\\ufe0f Interrupted';
                case MAYA_TERMINAL.FAILED: return '\\u26a0\\ufe0f Unavailable';
                case MAYA_TERMINAL.CANCELLED: return '\\u25cf Cancelled';
                default: return '\\u25cf Idle';
            }
        }
"""

def main():
    with open(PATH, "rb") as f:
        data = f.read()

    if MARKER in data:
        print("ALREADY_INSERTED")
        return 0

    if ANCHOR not in data:
        print("ANCHOR_NOT_FOUND")
        return 1

    if data.count(ANCHOR) != 1:
        print("ANCHOR_AMBIGUOUS count=%d" % data.count(ANCHOR))
        return 1

    # Normalise the helper block to CRLF to match the file.
    helper = HELPER.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    data = data.replace(ANCHOR, ANCHOR + helper, 1)

    with open(PATH, "wb") as f:
        f.write(data)
    print("INSERTED helper_bytes=%d" % len(helper))
    return 0


if __name__ == "__main__":
    sys.exit(main())
