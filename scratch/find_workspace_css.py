with open('Frontend/index.html', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if any(k in line for k in ['.workspace-3col', '.practice-3panel-header', 'main.practice', '.practice {', '#editorPanelWs', '#codeEditorWrapper', '#code {', '.code-editor-wrapper']):
        print(f"{i}: {line.strip()[:120]}")
