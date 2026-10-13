import { readFileSync } from 'fs';
const lines = readFileSync('scratch/cur1.js', 'utf8').split('\n');

let depth = 0;
for (let i = 4780; i < 4900; i++) {
  const l = lines[i];
  // strip line comments and string literals crudely
  let s = l;
  s = s.replace(/\/\/.*$/, '');
  s = s.replace(/'[^']*'/g, "''");
  s = s.replace(/"[^"]*"/g, '""');
  s = s.replace(/`[^`]*`/g, '``');
  for (const ch of s) {
    if (ch === '{') depth++;
    else if (ch === '}') depth--;
  }
  console.log(String(i + 1).padStart(5), 'd=' + String(depth).padStart(2), '|', l.trim().slice(0, 72));
}
