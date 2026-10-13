import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv

load_dotenv('Backend/.env')

from openai import OpenAI

groq_key = os.environ.get('GROQ_API_KEY')
print('Groq key:', groq_key[:10] if groq_key else None)
if groq_key:
    for m in ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'qwen/qwen3.8-27b', 'openai/gpt-oss-20b']:
        try:
            c = OpenAI(base_url='https://api.groq.com/openai/v1', api_key=groq_key)
            res = c.chat.completions.create(model=m, messages=[{'role': 'user', 'content': 'Say hi in one word'}], max_tokens=10)
            print(f'Groq {m} success: {res.choices[0].message.content}')
        except Exception as e:
            print(f'Groq {m} error:', type(e).__name__, e)
