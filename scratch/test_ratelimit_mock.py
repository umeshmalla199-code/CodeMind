import openai
import httpx

try:
    resp = httpx.Response(
        status_code=429,
        headers={"retry-after": "2.5", "x-ratelimit-reset-tokens": "1.2s"},
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    )
    raise openai.RateLimitError(
        message="Rate limit reached for model qwen/qwen3.8-27b",
        response=resp,
        body={"error": {"message": "Rate limit reached", "type": "tokens"}}
    )
except Exception as e:
    print("Caught:", type(e).__name__)
    print("isinstance RateLimitError:", isinstance(e, openai.RateLimitError))
    print("status_code:", getattr(e, "status_code", None))
    print("headers:", e.response.headers if hasattr(e, "response") else None)
    print("retry-after:", e.response.headers.get("retry-after"))
