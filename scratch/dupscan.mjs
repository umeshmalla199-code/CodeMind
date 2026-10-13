// Report every duplicate `const X` declaration that shares a lexical scope,
// by scanning function bodies for repeated const names at the same depth.
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

let depth = 0;
const seen = new Map(); // depth -> Map(name -> [lines])
for (let i = 0; i < lines.length; i++) {
  const s = strip(lines[i]);
  let d = depth;
  const m = s.match(/^(\s*)(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=/);
  if (m) {
    const name = m[2];
    const key = d;
    if (!seen.has(key)) seen.set(key, new Map());
    const bucket = seen.get(key);
    if (bucket.has(name)) {
      console.log(`DUP depth=${d} name=${name} first=${bucket.get(name)} again=${i + 1}`);
      console.log('   ', lines[bucket.get(name) - 1].trim().slice(0, 80));
      console.log('   ', lines[i].trim().slice(0, 80));
    } else {
      bucket.set(name, i + 1);
    }
  }
  for (const ch of s) {
    if (ch === '{') depth++;
    else if (ch === '}') depth--;
  }
}
