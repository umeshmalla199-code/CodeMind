import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv

# Try loading root .env first, then Backend/.env
load_dotenv('.env')

from openai import OpenAI

groq_key = os.environ.get('GROQ_API_KEY')
print('Groq key:', groq_key[:10] if groq_key else None)
if groq_key:
    try:
        c = OpenAI(base_url='https://api.groq.com/openai/v1', api_key=groq_key)
        res = c.chat.completions.create(model='llama-3.3-70b-versatile', messages=[{'role': 'user', 'content': 'Say hi in one word'}], max_tokens=10)
        print('Groq llama-3.3 success:', res.choices[0].message.content)
    except Exception as e:
        print('Groq llama-3.3 error:', type(e).__name__, e)

nv_key = os.environ.get('NVIDIA_API_KEY', '').strip('"\'')
print('NVIDIA key:', nv_key[:10] if nv_key else None)
if nv_key:
    try:
        c = OpenAI(base_url='https://integrate.api.nvidia.com/v1', api_key=nv_key)
        res = c.chat.completions.create(model='meta/llama-3.1-8b-instruct', messages=[{'role': 'user', 'content': 'Say hi in one word'}], max_tokens=10)
        print('NVIDIA success:', res.choices[0].message.content)
    except Exception as e:
        print('NVIDIA error:', type(e).__name__, e)
