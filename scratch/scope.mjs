// For a given error line, find the enclosing function and list const decls inside it.
import { readFileSync } from 'fs';
const src = readFileSync('scratch/cur1.js', 'utf8');
const lines = src.split(/\r?\n/);

function strip(s) {
  return s
    .replace(/\/\/.*$/, '')
    .replace(/'[^']*'/g, "''")
    .replace(/"[^"]*"/g, '""')
    .replace(/`[^`]*`/g, '``');
}

const errLine = Number(process.argv[2] || 9708) - 1;

// Build depth per line (depth BEFORE processing that line).
const before = new Array(lines.length).fill(0);
let d = 0;
for (let i = 0; i < lines.length; i++) {
  before[i] = d;
  const s = strip(lines[i]);
  for (const ch of s) {
    if (ch === '{') d++;
    else if (ch === '}') d--;
  }
}
const targetDepth = before[errLine];

// Walk backwards to the line that opened this scope.
let start = errLine;
while (start > 0 && before[start] > targetDepth) start--;

console.log('error line', errLine + 1, 'depth', targetDepth);
console.log('scope starts at line', start + 1, ':', lines[start].trim().slice(0, 90));
console.log('--- const decls at same depth within scope ---');
for (let i = start; i <= errLine; i++) {
  if (before[i] !== targetDepth) continue;
  const m = lines[i].match(/^(\s*)(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/);
  if (m) console.log('  line', i + 1, m[2], '|', lines[i].trim().slice(0, 78));
}
