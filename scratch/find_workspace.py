with open('Frontend/index.html', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if 'id="practice"' in line or "id='practice'" in line or 'class="workspace' in line or 'id="workspace' in line:
            print(f"{i}: {line.strip()[:100]}")
