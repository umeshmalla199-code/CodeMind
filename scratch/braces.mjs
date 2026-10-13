import { readFileSync } from 'fs';
const lines = readFileSync('scratch/cur1.js','utf8').split('\n');
// Walk backwards from 4873 to find enclosing function start at 8-space indent
for (let i = 4872; i >= 0; i--) {
  if (/^ {8}(async )?function /.test(lines[i])) { console.log('ENCLOSING FN at', i+1, lines[i].trim()); break; }
}
// Find all 'const user' in that function range
let start = 0;
for (let i = 4872; i >= 0; i--) { if (/^ {8}(async )?function /.test(lines[i])) { start = i; break; } }
let depth = 0;
for (let i = start; i < 4900; i++) {
  for (const ch of lines[i]) { if (ch==='{') depth++; else if (ch==='}') depth--; }
  if (/const user\s*=/.test(lines[i])) console.log('  const user at', i+1, 'depth', depth, '|', lines[i].trim());
  if (/const\s+(user|messageText|thisRequestId)\s*=/.test(lines[i])) console.log('  decl at', i+1, '|', lines[i].trim().slice(0,70));
}
