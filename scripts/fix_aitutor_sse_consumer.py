"""Replace the AI-tutor-panel SSE consumer with the shared parser.

Also fixes the fake-completion bug: the old code set the lifecycle to COMPLETED
whenever a `done` event merely carried a `message` field, regardless of the
server-reported status.

Idempotent.
"""
import sys

PATH = "Frontend/index.html"

OLD = """                    // FAST SSE STREAMING:
                    requestLifecycleState = 'STREAMING';
                    if (bubbleMetricsEl) bubbleMetricsEl.textContent = '\u25cf Streaming...';
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    let isFirstDelta = true;
                    let currentEvent = 'message';

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\\n');
                        buffer = lines.pop();

                        for (const line of lines) {
                            const trimmed = line.trim();
                            if (!trimmed) continue;
                            if (trimmed.startsWith('event:')) {
                                currentEvent = trimmed.slice(6).trim();
                            } else if (trimmed.startsWith('data:')) {
                                const dataRaw = trimmed.slice(5).trim();
                                try {
                                    const dataObj = JSON.parse(dataRaw);
                                    if (currentEvent === 'delta') {
                                        if (dataObj.text) {
                                            if (isFirstDelta) {
                                                isFirstDelta = false;
                                                if (bubbleTextEl) {
                                                    bubbleTextEl.style.color = '#e2e8f0';
                                                    bubbleTextEl.style.fontStyle = 'normal';
                                                }
                                            }
                                            accumulatedText += dataObj.text;
                                            if (bubbleTextEl) bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText);
                                            stream.scrollTop = stream.scrollHeight;
                                        }
                                    } else if (currentEvent === 'error') {
                                        const errMsg = dataObj.message || dataObj.error || 'AI generation encountered an issue.';
                                        if (bubbleTextEl) {
                                            bubbleTextEl.style.color = '#f87171';
                                            bubbleTextEl.style.fontStyle = 'normal';
                                            bubbleTextEl.innerHTML = `\u26a0\ufe0f ${escapeHtml(errMsg)}`;
                                        }
                                        if (bubbleMetricsEl) bubbleMetricsEl.textContent = 'ERROR';
                                    } else if (currentEvent === 'visualization') {
                                        if (typeof renderCompanionVisualization === 'function') {
                                            renderCompanionVisualization(dataObj);
                                        }
                                    } else if (currentEvent === 'metrics') {
                                        if (bubbleMetricsEl && dataObj) {
                                            const parts = [];
                                            if (dataObj.ttft) parts.push(`${dataObj.ttft}s TTFT`);
                                            if (dataObj.total_time) parts.push(`${dataObj.total_time}s`);
                                            bubbleMetricsEl.textContent = `\u26a1 ${parts.join(' | ')}`;
                                        }
                                    } else if (currentEvent === 'done') {
                                        finalDoneData = dataObj;
                                        if (dataObj.status === 'COMPLETED' || dataObj.message) {
                                            requestLifecycleState = 'COMPLETED';
                                        }
                                        if (dataObj.message && (!accumulatedText || accumulatedText.length < dataObj.message.length)) {
                                            accumulatedText = dataObj.message;
                                            if (bubbleTextEl) {
                                                bubbleTextEl.style.color = '#e2e8f0';
                                                bubbleTextEl.style.fontStyle = 'normal';
                                                bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText);
                                            }
                                        }
                                        if (dataObj.visualization && typeof renderCompanionVisualization === 'function') {
                                            renderCompanionVisualization(dataObj.visualization);
                                        }
                                        if (bubbleExtrasEl) {
                                            bubbleExtrasEl.innerHTML = buildAssistantExtrasHTML(dataObj.recommended_problems, dataObj.visualization);
                                        }
                                    }
                                } catch (parseErr) {}
                            }
                        }
                    }
"""

NEW = """                    // FAST SSE STREAMING:
                    requestLifecycleState = 'STREAMING';
                    if (bubbleMetricsEl) bubbleMetricsEl.textContent = '\u25cf Streaming...';
                    let isFirstDelta = true;
                    let receivedDone = false;
                    let serverError = null;

                    // Shared parser guarantees the terminal `done` frame is
                    // processed even if the stream ends without a trailing newline.
                    await readSSEStream(res, (eventName, dataObj) => {
                        if (eventName === 'delta') {
                            if (dataObj.text) {
                                if (isFirstDelta) {
                                    isFirstDelta = false;
                                    if (bubbleTextEl) {
                                        bubbleTextEl.style.color = '#e2e8f0';
                                        bubbleTextEl.style.fontStyle = 'normal';
                                    }
                                }
                                accumulatedText += dataObj.text;
                                if (bubbleTextEl) bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText);
                                stream.scrollTop = stream.scrollHeight;
                            }
                        } else if (eventName === 'error') {
                            serverError = dataObj;
                            if (bubbleMetricsEl) bubbleMetricsEl.textContent = 'ERROR';
                        } else if (eventName === 'visualization') {
                            // Contained so a viz failure cannot break text streaming.
                            try {
                                if (typeof renderCompanionVisualization === 'function') {
                                    renderCompanionVisualization(dataObj);
                                }
                            } catch (vizErr) {
                                console.warn('Maya visualization render failed', vizErr);
                            }
                        } else if (eventName === 'metrics') {
                            if (bubbleMetricsEl && dataObj) {
                                const parts = [];
                                if (dataObj.ttft) parts.push(`${dataObj.ttft}s TTFT`);
                                if (dataObj.total_time) parts.push(`${dataObj.total_time}s`);
                                bubbleMetricsEl.textContent = `\u26a1 ${parts.join(' | ')}`;
                            }
                        } else if (eventName === 'done') {
                            receivedDone = true;
                            finalDoneData = dataObj;
                            if (dataObj.message && (!accumulatedText || accumulatedText.length < dataObj.message.length)) {
                                accumulatedText = dataObj.message;
                                if (bubbleTextEl) {
                                    bubbleTextEl.style.color = '#e2e8f0';
                                    bubbleTextEl.style.fontStyle = 'normal';
                                    bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText);
                                }
                            }
                            if (dataObj.visualization && typeof renderCompanionVisualization === 'function') {
                                try { renderCompanionVisualization(dataObj.visualization); } catch (vizErr) {
                                    console.warn('Maya visualization render failed', vizErr);
                                }
                            }
                            if (bubbleExtrasEl) {
                                bubbleExtrasEl.innerHTML = buildAssistantExtrasHTML(dataObj.recommended_problems, dataObj.visualization);
                            }
                        }
                    });

                    // Terminal state comes from the server, never from the mere
                    // presence of a message. This is the fake-completion fix.
                    requestLifecycleState = resolveMayaTerminalState(finalDoneData, receivedDone);
                    if (serverError && requestLifecycleState === MAYA_TERMINAL.COMPLETED) {
                        // Defensive: a server that flags an error is never a success.
                        requestLifecycleState = MAYA_TERMINAL.INTERRUPTED;
                    }
"""


def main():
    with open(PATH, "r", encoding="utf-8", newline="") as f:
        data = f.read()

    # Guard on a marker unique to the AI-tutor block (the companion panel uses a
    # different indentation and variable name for the same concept).
    if "requestLifecycleState = resolveMayaTerminalState(finalDoneData, receivedDone);" in data:
        print("ALREADY_REPLACED")
        return 0

    old = OLD.replace("\n", "\r\n")
    new = NEW.replace("\n", "\r\n")

    if old not in data:
        print("OLD_BLOCK_NOT_FOUND")
        return 1
    if data.count(old) != 1:
        print("OLD_BLOCK_AMBIGUOUS count=%d" % data.count(old))
        return 1

    data = data.replace(old, new, 1)
    with open(PATH, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    print("REPLACED ai-tutor SSE consumer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
