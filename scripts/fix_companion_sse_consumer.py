"""Replace the companion-panel SSE consumer with the shared parser.

Idempotent: bails out if the new code is already present.
"""
import sys

PATH = "Frontend/index.html"

OLD = """                // Check if response is SSE stream
                const contentType = res.headers.get('content-type') || '';
                if (contentType.includes('text/event-stream') && res.body) {
                    const streamUi = createStreamingCompanionBubble();
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';
                    let accumulatedText = '';
                    let finalDoneData = null;

                    if (statusPill) {
                        statusPill.className = 'companion-status-pill speaking';
                        statusPill.textContent = '\u25cf Streaming';
                    }
                    if (window.setCompanionExpression) {
                        window.setCompanionExpression('speaking');
                    }

                    let currentEvent = 'message';
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\\n');
                        buffer = lines.pop(); // retain partial line

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
                                            accumulatedText += dataObj.text;
                                            if (streamUi) streamUi.updateText(accumulatedText);
                                        }
                                    } else if (currentEvent === 'visualization') {
                                        renderCompanionVisualization(dataObj);
                                    } else if (currentEvent === 'metrics') {
                                        if (streamUi) streamUi.setMetrics(dataObj);
                                    } else if (currentEvent === 'done') {
                                        finalDoneData = dataObj;
                                        if (dataObj.message && (!accumulatedText || accumulatedText.length < dataObj.message.length)) {
                                            accumulatedText = dataObj.message;
                                            if (streamUi) streamUi.updateText(accumulatedText);
                                        }
                                        if (dataObj.visualization) {
                                            renderCompanionVisualization(dataObj.visualization);
                                        }
                                        if (dataObj.recommended_problems && streamUi) {
                                            streamUi.setRecommendations(dataObj.recommended_problems);
                                        }
                                    }
                                } catch (parseErr) {
                                    // Ignore non-fatal JSON parse fragments
                                }
                            }
                        }
                    }

                    // Completed stream: only persist to history if completion was confirmed via done event
                    if (thisRequestId !== companionCurrentRequestId) return;

                    if (finalDoneData && accumulatedText) {
                        companionChatHistory.push({ role: 'user', content: messageText });
                        const histMessage = (accumulatedText && accumulatedText.length > 2500)
                            ? (accumulatedText.slice(0, 2500) + '...')
                            : accumulatedText;
                        companionChatHistory.push({ role: 'companion', content: histMessage });
                    }

                    const shouldSpeak = (window.voiceAssistantActive || window._lastQueryWasVoice) && !window.companionAudioMuted;
                    window._lastQueryWasVoice = false;
                    if (shouldSpeak && accumulatedText) {
                        speakCompanionResponse(accumulatedText, (finalDoneData && finalDoneData.expression) || 'speaking');
                    } else {
                        if (window.setCompanionExpression) window.setCompanionExpression('idle');
                        if (statusPill) {
                            statusPill.className = 'companion-status-pill';
                            statusPill.textContent = '\u25cf Idle';
                        }
                    }

                } else {"""

NEW = """                // Check if response is SSE stream
                const contentType = res.headers.get('content-type') || '';
                if (contentType.includes('text/event-stream') && res.body) {
                    const streamUi = createStreamingCompanionBubble();
                    let accumulatedText = '';
                    let finalDoneData = null;
                    let receivedDone = false;
                    let serverError = null;

                    if (statusPill) {
                        statusPill.className = 'companion-status-pill speaking';
                        statusPill.textContent = '\u25cf Streaming';
                    }
                    if (window.setCompanionExpression) {
                        window.setCompanionExpression('speaking');
                    }

                    // Shared parser guarantees the final frame is processed even
                    // when the server closes the stream without a trailing newline.
                    await readSSEStream(res, (eventName, dataObj) => {
                        if (eventName === 'delta') {
                            if (dataObj.text) {
                                accumulatedText += dataObj.text;
                                if (streamUi) streamUi.updateText(accumulatedText);
                            }
                        } else if (eventName === 'visualization') {
                            // A visualization must never be able to break text
                            // streaming, so failures here are contained.
                            try { renderCompanionVisualization(dataObj); } catch (vizErr) {
                                console.warn('Maya visualization render failed', vizErr);
                            }
                        } else if (eventName === 'metrics') {
                            if (streamUi) streamUi.setMetrics(dataObj);
                        } else if (eventName === 'error') {
                            serverError = dataObj;
                        } else if (eventName === 'done') {
                            receivedDone = true;
                            finalDoneData = dataObj;
                            if (dataObj.message && (!accumulatedText || accumulatedText.length < dataObj.message.length)) {
                                accumulatedText = dataObj.message;
                                if (streamUi) streamUi.updateText(accumulatedText);
                            }
                            if (dataObj.visualization) {
                                try { renderCompanionVisualization(dataObj.visualization); } catch (vizErr) {
                                    console.warn('Maya visualization render failed', vizErr);
                                }
                            }
                            if (dataObj.recommended_problems && streamUi) {
                                streamUi.setRecommendations(dataObj.recommended_problems);
                            }
                        }
                    });

                    // Stale-response guard: a newer Send already won.
                    if (thisRequestId !== companionCurrentRequestId) return;

                    // COMPLETED only when the server actually said so.
                    const terminalState = resolveMayaTerminalState(finalDoneData, receivedDone);

                    if (terminalState === MAYA_TERMINAL.COMPLETED) {
                        if (accumulatedText) {
                            companionChatHistory.push({ role: 'user', content: messageText });
                            const histMessage = accumulatedText.length > 2500
                                ? (accumulatedText.slice(0, 2500) + '...')
                                : accumulatedText;
                            companionChatHistory.push({ role: 'companion', content: histMessage });
                        }
                    } else if (accumulatedText) {
                        // Partial output is useful: keep it visible and let the
                        // next turn continue from it, but never store it as a
                        // completed turn.
                        companionChatHistory.push({ role: 'user', content: messageText });
                        const histMessage = accumulatedText.length > 2500
                            ? (accumulatedText.slice(0, 2500) + '...')
                            : accumulatedText;
                        companionChatHistory.push({ role: 'companion', content: histMessage });
                    }

                    const shouldSpeak = (window.voiceAssistantActive || window._lastQueryWasVoice) && !window.companionAudioMuted;
                    window._lastQueryWasVoice = false;
                    if (shouldSpeak && accumulatedText && terminalState === MAYA_TERMINAL.COMPLETED) {
                        speakCompanionResponse(accumulatedText, (finalDoneData && finalDoneData.expression) || 'speaking');
                    } else {
                        if (window.setCompanionExpression) {
                            window.setCompanionExpression(
                                terminalState === MAYA_TERMINAL.COMPLETED ? 'idle' : 'confused'
                            );
                        }
                        if (statusPill) {
                            statusPill.className = (terminalState === MAYA_TERMINAL.COMPLETED)
                                ? 'companion-status-pill'
                                : 'companion-status-pill error';
                            statusPill.textContent = mayaTerminalLabel(terminalState);
                        }
                    }

                    // FAILED with no text at all: surface the friendly message.
                    if (terminalState !== MAYA_TERMINAL.COMPLETED && !accumulatedText && streamUi) {
                        const msg = (serverError && serverError.message)
                            ? serverError.message
                            : 'Maya could not complete that response. Please try again.';
                        streamUi.updateText(msg);
                    }

                } else {"""


def main():
    with open(PATH, "r", encoding="utf-8", newline="") as f:
        data = f.read()

    if "readSSEStream(res, (eventName, dataObj)" in data:
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
    print("REPLACED companion SSE consumer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
