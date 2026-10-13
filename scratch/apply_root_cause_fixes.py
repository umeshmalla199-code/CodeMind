# -*- coding: utf-8 -*-
"""Targeted root-cause repair patcher. Exact-string replacements with uniqueness asserts."""
import io, sys

def rep(path, old, new, expect=1):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()
    count = content.count(old)
    if count != expect:
        # Retry with CRLF line endings (frontend file uses \r\n)
        old_crlf = old.replace("\n", "\r\n")
        new_crlf = new.replace("\n", "\r\n")
        count2 = content.count(old_crlf)
        if count2 != expect:
            print(f"FAIL [{path}]: pattern found {count}x (LF) / {count2}x (CRLF), expected {expect}")
            print("--- old snippet head ---")
            print(old[:200])
            sys.exit(1)
        content = content.replace(old_crlf, new_crlf)
    else:
        content = content.replace(old, new)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    print(f"OK   [{path}]: replaced {expect} occurrence(s)")

GW = "Backend/ai/companion/gateway.py"
TUTOR = "Backend/ai/tutor.py"
AIROUTE = "Backend/routes/ai.py"
FE = "Frontend/index.html"

# ---------------------------------------------------------------- gateway.py
# A1: explicit-language + code-first prompt rules
rep(GW,
'''    def _get_system_instruction(self, bot_name: str, student_name: str, lang: Optional[str] = None) -> str:
        if lang:
            lang_upper = "C++" if lang.lower() == "cpp" else lang.upper()
            lang_rule = (
                f"7. STRICT PROGRAMMING LANGUAGE:\\n"
                f"The active programming language is {lang_upper}. "
                f"You MUST write all code examples, syntax, implementations, types, and explanations strictly in {lang_upper}. "
                f"Do NOT switch to or use any other language.\\n"
            )
''',
'''    def _get_system_instruction(self, bot_name: str, student_name: str, lang: Optional[str] = None, explicit_in_message: bool = False) -> str:
        if lang:
            lang_upper = "C++" if lang.lower() == "cpp" else lang.upper()
            lang_rule = (
                f"7. STRICT PROGRAMMING LANGUAGE:\\n"
                f"The active programming language is {lang_upper}. "
                f"You MUST write all code examples, syntax, implementations, types, and explanations strictly in {lang_upper}. "
                f"Do NOT switch to or use any other language.\\n"
            )
            if explicit_in_message:
                lang_rule += (
                    f"7a. The student EXPLICITLY requested {lang_upper} in their message. This explicit request is "
                    f"authoritative and overrides any language seen in workspace context, editor code, or history. "
                    f"Even if the editor code is written in another language, every program you produce in this turn "
                    f"MUST be written in {lang_upper}.\\n"
                )
                lang_rule += (
                    f"7b. When the student asks for code or a solution in {lang_upper}, the FIRST thing in your response must be "
                    f"the COMPLETE program inside exactly one fenced code block: every required include/import, the entry "
                    f"point (main() for {lang_upper} where applicable), input handling, the full algorithm, and the output. "
                    f"The code must be complete and compilable/runnable as-is. NEVER stop halfway, NEVER return only "
                    f"pseudocode or a mathematical derivation, and do not use LaTeX for a programming answer. If an "
                    f"explanation is useful, give it AFTER the complete program.\\n"
                )
''')

# A2: pass explicit_in_message through
rep(GW,
'''        # 6. Build Compact Context and History
        system_instruction = self._get_system_instruction(bot_name, student_name, resolved_lang)
''',
'''        # 6. Build Compact Context and History
        system_instruction = self._get_system_instruction(
            bot_name, student_name, resolved_lang,
            explicit_in_message=bool(explicit_lang),
        )
''')

# A3: detect "c solution" / "c implementation" as explicit C
rep(GW,
'''            or re.search(r"\\bc\\s+(?:language|programming|program|code|queue|stack|pointer|array|struct)\\b", t)
''',
'''            or re.search(r"\\bc\\s+(?:language|programming|program|code|solution|implementation|queue|stack|pointer|array|struct)\\b", t)
''')

# A0: timeout classifier helper (placed next to the rate-limit classifier)
rep(GW,
'''def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect HTTP 429 or rate-limit errors from providers cleanly."""
''',
'''def _is_timeout_error(exc: Exception) -> bool:
    """
    Detect request timeouts from providers cleanly (openai.APITimeoutError and
    generic timeout exceptions). Used to retire a key/provider for this request
    when it stalls BEFORE the first token, without corrupting anything.
    """
    if exc is None:
        return False
    type_name = type(exc).__name__
    if "Timeout" in type_name or "TimeoutExpired" in type_name:
        return True
    msg = str(exc).lower()
    return (
        "timed out" in msg
        or "timeout" in msg
        or "time out" in msg
    )


def _is_rate_limit_error(exc: Exception) -> bool:
    """Detect HTTP 429 or rate-limit errors from providers cleanly."""
''')

# A4/A5: main stream loop — content only, bounded full-limit continuation
rep(GW,
'''                    last_finish_reason = None
                    for chunk in stream:
                        if chunk.choices:
                            fr = getattr(chunk.choices[0], 'finish_reason', None)
                            if fr:
                                last_finish_reason = fr
                        delta_obj = chunk.choices[0].delta if chunk.choices else None
                        if not delta_obj:
                            continue
                        delta = (
                            getattr(delta_obj, 'content', None)
                            or getattr(delta_obj, 'reasoning_content', None)
                            or getattr(delta_obj, 'reasoning', None)
                        )
                        if not delta:
                            continue
                        if not first_token_received:
                            ttft = round(time.perf_counter() - model_request_start, 3)
                            first_token_received = True

                        yield from _process_stream_delta(delta)

                    # Controlled continuation if provider genuinely stopped due to output length
                    if last_finish_reason == "length":
                        logger.info("Provider %s reached output limit. Executing single continuation.", current_p_name)
                        try:
                            cont_messages = list(messages) + [
                                {"role": "assistant", "content": accumulated_text},
                                {"role": "user", "content": "Continue exactly from where the previous response stopped. Do not repeat previous content."}
                            ]
                            cont_stream = cur_client.chat.completions.create(
                                model=cur_model,
                                messages=cont_messages,
                                max_tokens=min(cur_limit, 2048),
                                temperature=0.2,
                                stream=True,
                                timeout=cur_timeout
                            )
                            for cont_chunk in cont_stream:
                                cont_delta_obj = cont_chunk.choices[0].delta if cont_chunk.choices else None
                                if not cont_delta_obj:
                                    continue
                                cont_delta = (
                                    getattr(cont_delta_obj, 'content', None)
                                    or getattr(cont_delta_obj, 'reasoning_content', None)
                                    or getattr(cont_delta_obj, 'reasoning', None)
                                )
                                if not cont_delta:
                                    continue
                                yield from _process_stream_delta(cont_delta)
                        except Exception as cont_exc:
                            logger.warning("Continuation stream encountered error: %s", cont_exc)
''',
'''                    last_finish_reason = None
                    for chunk in stream:
                        if chunk.choices:
                            fr = getattr(chunk.choices[0], 'finish_reason', None)
                            if fr:
                                last_finish_reason = fr
                        delta_obj = chunk.choices[0].delta if chunk.choices else None
                        if not delta_obj:
                            continue
                        # ROOT-CAUSE FIX (bad/garbled answers): stream ONLY the visible
                        # answer content. The reasoning/thinking channels are the model's
                        # internal scratchpad; streaming them injected math/LaTeX
                        # derivations into student answers and displaced real code.
                        delta = getattr(delta_obj, 'content', None)
                        if not delta:
                            continue
                        if not first_token_received:
                            ttft = round(time.perf_counter() - model_request_start, 3)
                            first_token_received = True

                        yield from _process_stream_delta(delta)

                    # ROOT-CAUSE FIX (cut-off responses): bounded multi-round continuation
                    # at the provider's safe maximum. A single capped continuation truncated
                    # long programs; unbounded looping would hang the turn.
                    MAX_CONTINUATIONS = 2
                    continuation_rounds = 0
                    while last_finish_reason == "length" and continuation_rounds < MAX_CONTINUATIONS:
                        continuation_rounds += 1
                        logger.info("Provider %s reached output limit. Continuation %d/%d.", current_p_name, continuation_rounds, MAX_CONTINUATIONS)
                        try:
                            cont_messages = list(messages) + [
                                {"role": "assistant", "content": accumulated_text},
                                {"role": "user", "content": "Continue exactly from where the previous response stopped. Do not repeat previous content."}
                            ]
                            cont_stream = cur_client.chat.completions.create(
                                model=cur_model,
                                messages=cont_messages,
                                max_tokens=cur_limit,
                                temperature=0.2,
                                stream=True,
                                timeout=cur_timeout
                            )
                            last_finish_reason = None
                            for cont_chunk in cont_stream:
                                if cont_chunk.choices:
                                    cont_fr = getattr(cont_chunk.choices[0], 'finish_reason', None)
                                    if cont_fr:
                                        last_finish_reason = cont_fr
                                cont_delta_obj = cont_chunk.choices[0].delta if cont_chunk.choices else None
                                if not cont_delta_obj:
                                    continue
                                cont_delta = getattr(cont_delta_obj, 'content', None)
                                if not cont_delta:
                                    continue
                                yield from _process_stream_delta(cont_delta)
                        except Exception as cont_exc:
                            logger.warning("Continuation stream encountered error: %s", cont_exc)
                            break
''')

# A6: release the key lease when a mid-stream failure is a timeout before advancing
rep(GW,
'''                except Exception as exc:
                    primary_error = exc
                    if first_token_received:
                        # Tokens reached student; cannot retry without corrupting output
                        active_lease.release()
                        logger.error("Provider %s key %s connection dropped mid-stream: %s", current_p_name, active_lease.key_id, exc)
                        break
''',
'''                except Exception as exc:
                    primary_error = exc
                    if first_token_received:
                        # Tokens reached student; cannot retry without corrupting output
                        active_lease.release()
                        logger.error("Provider %s key %s connection dropped mid-stream: %s", current_p_name, active_lease.key_id, exc)
                        break
                    if _is_timeout_error(exc):
                        # Timeout before any token: nothing streamed, so this key/provider
                        # can be retired for this request without corrupting output.
                        active_lease.release()
                        logger.warning("Provider %s key %s timed out before first token. Trying next key/provider.", current_p_name, active_lease.key_id)
                        continue
''')

# ---------------------------------------------------------------- tutor.py
# Budget: provider-safe maximum (matches gateway long-generation budget), no artificial 2500 cap
with io.open(TUTOR, "r", encoding="utf-8", newline="") as f:
    t_content = f.read()
n2500 = t_content.count(", 2500))")
if n2500 != 4:
    print(f"FAIL [{TUTOR}]: expected 4 budget occurrences of ', 2500))', found {n2500}")
    sys.exit(1)
t_content = t_content.replace(", 2500))", ", 4096))")
with io.open(TUTOR, "w", encoding="utf-8", newline="") as f:
    f.write(t_content)
print(f"OK   [{TUTOR}]: full-solution budget raised to 4096 on 4 provider entries")

# Bounded multi-round continuation at provider-safe maximum
rep(TUTOR,
'''                content = resp.choices[0].message.content or ""
                # Check finish reason: controlled one-shot continuation if truncated
                if resp.choices and getattr(resp.choices[0], "finish_reason", None) == "length":
                    logger.info("Provider %s hit max_tokens on solution. Performing continuation.", p_name)
                    try:
                        cont_resp = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": contract},
                                {"role": "assistant", "content": content},
                                {"role": "user", "content": "Continue exactly from where the previous response stopped. Do not repeat previous content."}
                            ],
                            temperature=0.1,
                            max_tokens=1500,
                            timeout=20
                        )
                        content += (cont_resp.choices[0].message.content or "")
                    except Exception as cont_e:
                        logger.warning("Solution continuation failed: %s", cont_e)
''',
'''                content = resp.choices[0].message.content or ""
                # ROOT-CAUSE FIX (truncated full solutions): bounded multi-round
                # continuation at the provider's safe maximum. Long C/C++/Java programs
                # were previously cut halfway by a single capped 1500-token continuation.
                MAX_SOLUTION_CONTINUATIONS = 2
                continuation_round = 0
                while (
                    resp.choices
                    and getattr(resp.choices[0], "finish_reason", None) == "length"
                    and continuation_round < MAX_SOLUTION_CONTINUATIONS
                ):
                    continuation_round += 1
                    logger.info("Provider %s hit max_tokens on solution. Continuation round %d/%d.", p_name, continuation_round, MAX_SOLUTION_CONTINUATIONS)
                    try:
                        cont_resp = client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": contract},
                                {"role": "assistant", "content": content},
                                {"role": "user", "content": "Continue exactly from where the previous response stopped. Do not repeat previous content."}
                            ],
                            temperature=0.1,
                            max_tokens=m_tokens,
                            timeout=20
                        )
                        content += (cont_resp.choices[0].message.content or "")
                        resp = cont_resp
                    except Exception as cont_e:
                        logger.warning("Solution continuation failed: %s", cont_e)
                        break
''')

# ---------------------------------------------------------------- routes/ai.py
# Wall-clock deadline so the endpoint always answers inside the client's window
rep(AIROUTE,
'''    candidate_code: str = solution_data.get("code") or ""
    MAX_REPAIR_ATTEMPTS = 2
    last_exec_result: Optional[Dict[str, Any]] = None
''',
'''    candidate_code: str = solution_data.get("code") or ""
    MAX_REPAIR_ATTEMPTS = 2
    last_exec_result: Optional[Dict[str, Any]] = None

    # ROOT-CAUSE FIX (infinite validation spinner): bound the whole
    # generate -> execute -> repair pipeline with a wall-clock deadline. The client
    # aborts at its 120s request timeout; past this deadline we stop starting new
    # repair rounds and return the REAL validation state, so the endpoint always
    # answers and the UI never races an unbounded backend.
    VALIDATION_DEADLINE_SECONDS = 90.0
    validation_started = time.perf_counter()

    def _validation_time_left() -> float:
        return VALIDATION_DEADLINE_SECONDS - (time.perf_counter() - validation_started)
''')

rep(AIROUTE,
'''                else:
                    # Repair loop (at most 2 attempts)
                    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
''',
'''                else:
                    # Repair loop (at most 2 attempts, bounded by the wall-clock deadline)
                    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                        if _validation_time_left() <= 0:
                            validation_status = status_res or "execution_error"
                            validation_label = f"Validation halted: repair budget exhausted ({status_res})"
                            validation_notes = validation_notes or (exec_result.get("error") or exec_result.get("stderr") or "")
                            break
''')

# ---------------------------------------------------------------- Frontend
# F1: declare timer handle before try so the outer finally can always clear it
rep(FE,
'''            container.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #94a3b8;">
                    <div style="font-size: 28px; margin-bottom: 8px;">🧠</div>
                    Analyzing problem with AI pedagogical engine...
                </div>
            `;

            try {
''',
'''            container.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #94a3b8;">
                    <div style="font-size: 28px; margin-bottom: 8px;">🧠</div>
                    Analyzing problem with AI pedagogical engine...
                </div>
            `;

            // ROOT-CAUSE FIX (infinite validation spinner): the Full Solution abort timer
            // must be clearable from the OUTER finally below. Previously clearTimeout ran
            // in a finally wrapped only around fetch(), so a late timer fire aborted the
            // completed request body and the catch handler returned silently — leaving the
            // "Generating & Validating..." spinner on screen forever.
            let solutionTabTimeoutId = null;

            try {
''')

# F2: timeout budget + abort reason
rep(FE,
'''                    const timeoutId = setTimeout(() => {
                        abortController.abort();
                    }, 60000);
                    let res;
''',
'''                    // AI generation + bounded validation is a long operation (provider
                    // chain + repair loop): give it the same 120s budget as Maya chat and
                    // abort with an explicit 'timeout' reason so the UI can distinguish a
                    // real timeout from a tab-switch abort.
                    const timeoutId = setTimeout(() => {
                        abortController.abort('timeout');
                    }, 120000);
                    solutionTabTimeoutId = timeoutId;
                    let res;
''')

# F3: outer finally always clears the timer
rep(FE,
'''            } finally {
                if (window._aiTabRequestIds[containerId] === reqId) {
                    window._aiTabActiveRequests[containerId] = null;
                }
            }
''',
'''            } finally {
                if (solutionTabTimeoutId) {
                    clearTimeout(solutionTabTimeoutId);
                    solutionTabTimeoutId = null;
                }
                if (window._aiTabRequestIds[containerId] === reqId) {
                    window._aiTabActiveRequests[containerId] = null;
                }
            }
''')

# F4: timeouts render a visible retry UI instead of silently returning
rep(FE,
'''            } catch (err) {
                if (abortController.signal.aborted || (err && err.name === 'AbortError')) {
                    return;
                }
                if (!isRequestValid()) return;
''',
'''            } catch (err) {
                // ROOT-CAUSE FIX (infinite spinner): a timed-out request must be VISIBLE.
                // Previously every abort returned silently and left the loading spinner up.
                const isAbort = (err && err.name === 'AbortError') || abortController.signal.aborted;
                if (isAbort && abortController.signal.reason === 'timeout') {
                    if (!isRequestValid()) return;
                    container.innerHTML = `
                        <div class="ai-card-box" style="border-color: #f59e0b; text-align:center; padding:24px 20px;">
                            <div style="font-size:28px; margin-bottom:10px;">⏱️</div>
                            <div style="font-weight:700; color:#f59e0b; font-size:15px; margin-bottom:6px;">Solution generation/validation timed out</div>
                            <div style="color:#94a3b8; font-size:13px; max-width:460px; margin:0 auto 14px auto; line-height:1.5;">
                                The AI provider or the validation executor did not respond within 120 seconds. Nothing was saved — please retry.
                            </div>
                            <button onclick="loadAITabContent('solution', '${escapeHtml(containerId)}')" style="background:linear-gradient(135deg,#0284c7,#0369a1); color:#fff; border:none; padding:8px 18px; border-radius:6px; font-size:12.5px; font-weight:700; cursor:pointer;">🔄 Retry Full Solution</button>
                        </div>
                    `;
                    return;
                }
                if (isAbort) {
                    // Tab switch / superseded request: cancel silently.
                    return;
                }
                if (!isRequestValid()) return;
''')

print("ALL EDITS APPLIED")
