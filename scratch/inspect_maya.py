import re

with open('Frontend/index.html', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

targets = [
    'companionWidget',
    'companionVrmCanvas',
    'companion-expr-bar',
    'initCompanion',
    'sendCompanionMessage',
    'voice-active',
    'SpeechRecognition',
    'speechSynthesis',
    'mira vrm.vrm',
    'companion/chat',
    'renderCompanionBubble',
    'companion_status'
]

print(f"Total lines in index.html: {len(lines)}")
for idx, line in enumerate(lines):
    for t in targets:
        if t in line:
            clean = line.strip().encode('ascii', errors='replace').decode('ascii')
            print(f"{idx+1}: [{t}] {clean[:100]}")
            break
