import os
from dotenv import load_dotenv
load_dotenv('Backend/.env')
from openai import OpenAI

groq_key = os.environ.get('GROQ_API_KEY')
print('Testing Groq key:', groq_key[:10] if groq_key else None)
try:
    c = OpenAI(base_url='https://api.groq.com/openai/v1', api_key=groq_key)
    res = c.chat.completions.create(model='openai/gpt-oss-20b', messages=[{'role': 'user', 'content': 'hi'}], max_tokens=10)
    print('Groq success:', res.choices[0].message.content)
except Exception as e:
    print('Groq error:', type(e).__name__, e)

nv_key = os.environ.get('NVIDIA_API_KEY', '').strip('"\'')
print('Testing NVIDIA key:', nv_key[:10] if nv_key else None)
try:
    c = OpenAI(base_url='https://integrate.api.nvidia.com/v1', api_key=nv_key)
    res = c.chat.completions.create(model='openai/gpt-oss-20b', messages=[{'role': 'user', 'content': 'hi'}], max_tokens=10)
    print('NVIDIA success:', res.choices[0].message.content)
except Exception as e:
    print('NVIDIA error:', type(e).__name__, e)

oai_key = os.environ.get('OPENAI_API_KEY')
print('Testing OpenAI key:', oai_key[:10] if oai_key else None)
try:
    c = OpenAI(api_key=oai_key)
    res = c.chat.completions.create(model='gpt-4o', messages=[{'role': 'user', 'content': 'hi'}], max_tokens=10)
    print('OpenAI success:', res.choices[0].message.content)
except Exception as e:
    print('OpenAI error:', type(e).__name__, e)
