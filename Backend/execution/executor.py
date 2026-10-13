import os
import sys
import time
import json
import math
import re
import ast
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .languages import resolve_language, LanguageSpec, find_tool

DEFAULT_TIMEOUT_SECONDS = 4.0
DEFAULT_COMPILE_TIMEOUT_SECONDS = 10.0
MAX_SOURCE_CODE_BYTES = 65536

def _init_windows_error_mode():
    """Ensure Windows does not display WerFault dialogs or freeze crashed processes."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        except Exception:
            pass

_init_windows_error_mode()

def _format_exit_code_message(code: int) -> str:
    """Provide descriptive explanation for common crash codes and signals."""
    unsigned_code = code if code >= 0 else (code + (1 << 32))
    known_windows_signals = {
        0xC0000005: "Segmentation fault / Access violation (0xC0000005)",
        0xC0000094: "Integer division by zero (0xC0000094)",
        0xC00000FD: "Stack overflow / Infinite recursion (0xC00000FD)",
        0xC0000025: "Noncontinuable exception (0xC0000025)",
        0xC0000409: "Stack buffer overrun (0xC0000409)",
        0x80000003: "Breakpoint reached (0x80000003)",
        3: "Aborted (SIGABRT)",
    }
    if unsigned_code in known_windows_signals:
        return known_windows_signals[unsigned_code]
    return f"Process exited with code {code}"

def normalize_output(s: Optional[str]) -> str:
    """Normalize string for robust test case comparison."""
    if s is None:
        return ""
    text = str(s).replace("\r\n", "\n").strip()
    # Strip wrapping quotes if present
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        if len(text) >= 2:
            text = text[1:-1].strip()
    return text

def compare_outputs(actual: str, expected: str) -> bool:
    """
    Compare actual output against expected output with tolerance for whitespace,
    boolean casing, and JSON structural equivalence.
    """
    act_norm = normalize_output(actual)
    exp_norm = normalize_output(expected)

    # 1. Exact or normalized string equality
    if act_norm == exp_norm:
        return True

    # 2. Case-insensitive equality (e.g. true/True, yes/YES)
    if act_norm.lower() == exp_norm.lower():
        return True

    # 3. JSON structural equivalence (e.g., [0, 1] vs [0,1])
    try:
        act_json = json.loads(act_norm)
        exp_json = json.loads(exp_norm)
        if act_json == exp_json:
            return True
    except Exception:
        pass

    # 4. Numeric float tolerance
    try:
        act_float = float(act_norm)
        exp_float = float(exp_norm)
        if math.isclose(act_float, exp_float, rel_tol=1e-5, abs_tol=1e-7):
            return True
    except Exception:
        pass

    return False

def prepare_stdin(raw_input: Optional[str]) -> str:
    """
    Prepare standard input stream. Handles raw input lines as well as
    sample assignments like 'w = 8' or 'nums = [2, 7], target = 9'.
    """
    if not raw_input:
        return "\n"
    raw = str(raw_input).strip()

    # Look for variable assignment patterns: name = value
    assignments = re.findall(r'(\w+)\s*=\s*("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\[.*?\]|\{.*?\}|\S+)', raw)
    if assignments:
        extracted = []
        for var, val in assignments:
            val_clean = val.strip()
            if (val_clean.startswith('"') and val_clean.endswith('"')) or (val_clean.startswith("'") and val_clean.endswith("'")):
                val_clean = val_clean[1:-1]
            extracted.append(val_clean)
        # Provide extracted values first, followed by the raw line
        return "\n".join(extracted) + "\n" + raw + "\n"

    return raw + "\n"

def _inject_python_harness(source_code: str) -> str:
    """
    If the Python source defines a solution function (LeetCode style) and does NOT
    read from stdin/input directly, append an automated test harness to call it.
    """
    # Check if user already uses input() or sys.stdin or has a __main__ entry point
    if "input(" in source_code or "sys.stdin" in source_code or "__main__" in source_code:
        return source_code

    harness = r'''
# --- CodeMind Auto Execution Harness ---
if __name__ == '__main__':
    import sys, ast, json, re, inspect

    _raw = sys.stdin.read().strip()
    if not _raw:
        sys.exit(0)

    # Find the user-defined callable
    _candidates = [
        _obj for _name, _obj in list(globals().items())
        if callable(_obj) and not _name.startswith('_') and getattr(_obj, '__module__', None) == '__main__'
    ]

    if not _candidates:
        sys.exit(0)

    _target_func = _candidates[-1]

    # Try matching variable assignments: key = val
    _kwargs = {}
    _matches = re.findall(r'(\w+)\s*=\s*(.*?)(?:,\s*(?=\w+\s*=)|$)', _raw)
    if _matches:
        for _k, _v in _matches:
            _v_str = _v.strip()
            try:
                _kwargs[_k] = ast.literal_eval(_v_str)
            except Exception:
                if len(_v_str) >= 2 and ((_v_str[0] == '"' and _v_str[-1] == '"') or (_v_str[0] == "'" and _v_str[-1] == "'")):
                    _kwargs[_k] = _v_str[1:-1]
                else:
                    _kwargs[_k] = _v_str

    try:
        _sig = inspect.signature(_target_func)
        if _kwargs and all(_k in _sig.parameters for _k in _kwargs):
            _res = _target_func(**_kwargs)
        else:
            _args = []
            for _line in _raw.splitlines():
                _line = _line.strip()
                if not _line:
                    continue
                try:
                    _args.append(ast.literal_eval(_line))
                except Exception:
                    _args.append(_line)
            _res = _target_func(*_args)

        if isinstance(_res, bool):
            print("true" if _res else "false")
        elif isinstance(_res, (list, dict)):
            print(json.dumps(_res))
        else:
            print(_res)
    except Exception as _e:
        sys.stderr.write(f"Runtime Exception: {_e}\n")
        sys.exit(1)
'''
    return source_code + "\n" + harness

def _get_isolated_env() -> Dict[str, str]:
    """Provide a sanitized environment for child process execution without secret leakage."""
    extra_paths = [
        r"C:\TDM-GCC-32\bin",
        r"C:\TDM-GCC-64\bin",
        r"C:\MinGW\bin",
        r"C:\Users\manoj\jdk-17\bin",
        r"C:\Program Files\Java\jdk-17\bin",
        r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot\bin",
    ]
    curr_path = os.environ.get("PATH", "")
    augmented_path = ";".join(extra_paths) + ";" + curr_path
    return {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
        "PATH": augmented_path,
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }

def execute_code(
    language: str,
    source_code: str,
    test_cases: Optional[List[Dict[str, Any]]] = None,
    custom_input: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    compile_timeout_seconds: float = DEFAULT_COMPILE_TIMEOUT_SECONDS
) -> Dict[str, Any]:
    """
    Execute submitted source code against test cases in an isolated temporary working directory.
    
    Returns structured result dictionary:
    {
        "status": "accepted" | "wrong_answer" | "compile_error" | "runtime_error" | "time_limit" | "no_test_cases" | "unsupported_language" | "execution_error",
        "language": "...",
        "test_results": [...]
    }
    """
    # 1. Resolve and validate language
    lang_spec = resolve_language(language)
    if not lang_spec:
        return {
            "status": "unsupported_language",
            "language": language,
            "error": f"Unsupported language '{language}'. Supported languages: python, c, cpp, java.",
            "test_results": [],
            "passed_count": 0,
            "total_test_cases": 0
        }

    # 2. Check source code size & presence
    if not source_code or not source_code.strip():
        return {
            "status": "runtime_error",
            "language": lang_spec.id,
            "error": "Source code cannot be empty.",
            "test_results": [],
            "passed_count": 0,
            "total_test_cases": 0
        }

    if len(source_code.encode("utf-8")) > MAX_SOURCE_CODE_BYTES:
        return {
            "status": "execution_error",
            "language": lang_spec.id,
            "error": f"Source code exceeds maximum size limit of {MAX_SOURCE_CODE_BYTES} bytes.",
            "test_results": [],
            "passed_count": 0,
            "total_test_cases": 0
        }

    # 3. Check compiler / runtime availability
    available, info = lang_spec.is_available()
    if not available:
        return {
            "status": "compile_error",
            "language": lang_spec.id,
            "error": f"{lang_spec.name} environment error: {info}",
            "test_results": [],
            "passed_count": 0,
            "total_test_cases": 0
        }

    # 4. Check for test cases presence
    if not test_cases and custom_input is None:
        return {
            "status": "no_test_cases",
            "language": lang_spec.id,
            "error": "This problem does not have any executable test cases in the database.",
            "test_results": [],
            "passed_count": 0,
            "total_test_cases": 0
        }

    # 5. Create isolated temporary working directory
    with tempfile.TemporaryDirectory(prefix="codemind_exec_", ignore_cleanup_errors=True) as temp_dir_str:
        workdir = Path(temp_dir_str)
        source_filename = lang_spec.get_source_filename(source_code)
        source_path = workdir / source_filename

        code_to_write = source_code
        if lang_spec.id == "python":
            code_to_write = _inject_python_harness(source_code)

        try:
            source_path.write_text(code_to_write, encoding="utf-8")
        except Exception as e:
            return {
                "status": "execution_error",
                "language": lang_spec.id,
                "error": f"Failed to write source code: {e}",
                "test_results": [],
                "passed_count": 0,
                "total_test_cases": 0
            }

        env = _get_isolated_env()

        # 6. Compilation phase
        if lang_spec.needs_compilation:
            compile_cmd = lang_spec.get_compile_command(workdir, source_filename)
            if compile_cmd:
                try:
                    compile_proc = subprocess.run(
                        compile_cmd,
                        cwd=str(workdir),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=compile_timeout_seconds,
                        env=env
                    )
                    if compile_proc.returncode != 0:
                        compile_err = (compile_proc.stderr or compile_proc.stdout or "Compilation failed").strip()
                        return {
                            "status": "compile_error",
                            "language": lang_spec.id,
                            "error": compile_err,
                            "stderr": compile_err,
                            "test_results": [],
                            "passed_count": 0,
                            "total_test_cases": len(test_cases) if test_cases else 0
                        }
                except subprocess.TimeoutExpired:
                    err_msg = f"Compilation timed out after {compile_timeout_seconds} seconds."
                    return {
                        "status": "compile_error",
                        "language": lang_spec.id,
                        "error": err_msg,
                        "stderr": err_msg,
                        "test_results": [],
                        "passed_count": 0,
                        "total_test_cases": len(test_cases) if test_cases else 0
                    }
                except Exception as e:
                    err_msg = f"Compiler execution error: {e}"
                    return {
                        "status": "compile_error",
                        "language": lang_spec.id,
                        "error": err_msg,
                        "stderr": err_msg,
                        "test_results": [],
                        "passed_count": 0,
                        "total_test_cases": len(test_cases) if test_cases else 0
                    }

        # 7. Execution phase
        run_cmd = lang_spec.get_run_command(workdir, source_filename)

        # Case A: Custom input mode
        if not test_cases and custom_input is not None:
            stdin_payload = prepare_stdin(custom_input)
            t0 = time.perf_counter()
            try:
                proc = subprocess.Popen(
                    run_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(workdir),
                    env=env
                )
                stdout, stderr = proc.communicate(input=stdin_payload, timeout=timeout_seconds)
                exec_time = round(time.perf_counter() - t0, 4)

                if proc.returncode != 0:
                    err_msg = stderr.strip() or _format_exit_code_message(proc.returncode)
                    return {
                        "status": "runtime_error",
                        "language": lang_spec.id,
                        "error": err_msg,
                        "stderr": err_msg,
                        "actual_output": stdout.strip(),
                        "execution_time": exec_time,
                        "test_results": []
                    }

                return {
                    "status": "accepted",
                    "language": lang_spec.id,
                    "actual_output": stdout.strip(),
                    "stderr": stderr.strip(),
                    "execution_time": exec_time,
                    "test_results": []
                }
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                return {
                    "status": "time_limit",
                    "language": lang_spec.id,
                    "error": f"Execution timed out ({timeout_seconds}s limit exceeded).",
                    "test_results": []
                }
            except Exception as e:
                return {
                    "status": "runtime_error",
                    "language": lang_spec.id,
                    "error": f"Execution failed: {e}",
                    "test_results": []
                }

        # Case B: Execution against problem test cases
        test_results = []
        overall_status = "accepted"

        for idx, tc in enumerate(test_cases or [], start=1):
            if isinstance(tc, dict):
                raw_input = tc.get("input", "")
                expected_output = str(tc.get("output", ""))
            else:
                raw_input = getattr(tc, "input", "")
                expected_output = str(getattr(tc, "output", ""))
            stdin_payload = prepare_stdin(raw_input)

            t0 = time.perf_counter()
            try:
                proc = subprocess.Popen(
                    run_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=str(workdir),
                    env=env
                )
                stdout, stderr = proc.communicate(input=stdin_payload, timeout=timeout_seconds)
                exec_time = round(time.perf_counter() - t0, 4)

                if proc.returncode != 0:
                    err_msg = stderr.strip() or _format_exit_code_message(proc.returncode)
                    test_results.append({
                        "test_case": idx,
                        "passed": False,
                        "input": raw_input,
                        "actual_output": stdout.strip(),
                        "expected_output": normalize_output(expected_output),
                        "execution_time": exec_time,
                        "exit_code": proc.returncode,
                        "stdout": stdout.strip(),
                        "stderr": err_msg,
                        "error": err_msg
                    })
                    overall_status = "runtime_error"
                    break  # Stop on first runtime error

                # Successful execution: compare outputs
                passed = compare_outputs(stdout, expected_output)
                test_results.append({
                    "test_case": idx,
                    "passed": passed,
                    "input": raw_input,
                    "actual_output": stdout.strip(),
                    "expected_output": normalize_output(expected_output),
                    "execution_time": exec_time,
                    "exit_code": proc.returncode,
                    "stdout": stdout.strip(),
                    "stderr": stderr.strip()
                })

                if not passed and overall_status == "accepted":
                    overall_status = "wrong_answer"

            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.communicate(timeout=0.2)
                except Exception:
                    pass
                proc.wait()
                exec_time = round(timeout_seconds, 4)
                test_results.append({
                    "test_case": idx,
                    "passed": False,
                    "actual_output": "Time Limit Exceeded",
                    "expected_output": normalize_output(expected_output),
                    "execution_time": exec_time,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "Time Limit Exceeded",
                    "error": f"Time limit exceeded ({timeout_seconds}s)"
                })
                overall_status = "time_limit"
                break  # Stop on timeout

            except Exception as e:
                test_results.append({
                    "test_case": idx,
                    "passed": False,
                    "actual_output": "",
                    "expected_output": normalize_output(expected_output),
                    "execution_time": 0.0,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(e),
                    "error": str(e)
                })
                overall_status = "runtime_error"
                break

        err_val = next((r.get("error") for r in test_results if r.get("error")), None)
        stderr_val = next((r.get("stderr") for r in test_results if r.get("stderr")), None)
        actual_val = test_results[0].get("actual_output") if test_results else None
        return {
            "status": overall_status,
            "language": lang_spec.id,
            "test_results": test_results,
            "passed_count": sum(1 for r in test_results if r["passed"]),
            "total_test_cases": len(test_cases or []),
            "error": err_val,
            "stderr": stderr_val or err_val,
            "actual_output": actual_val
        }

