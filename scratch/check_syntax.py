with open(r'Frontend/index.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Let's extract script 2 content
start_idx = text.find('<script>', text.find('regSubmitBtn'))
end_idx = text.find('</script>', start_idx)

script_code = text[start_idx + len('<script>'):end_idx]
print(f"Script 2 slice length: {len(script_code)} chars")

# Use node.js or a robust JS parser if available, or write a state machine
import subprocess
# Check if node is available
try:
    p = subprocess.run(["node", "-e", script_code], capture_output=True, text=True)
    print("Node check exit code:", p.returncode)
    print("Node stdout:", p.stdout)
    print("Node stderr:", p.stderr)
except Exception as e:
    print("Node not available or failed:", e)
