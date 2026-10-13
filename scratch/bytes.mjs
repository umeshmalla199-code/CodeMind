import { readFileSync } from 'fs';
const buf = readFileSync('scratch/cur1.js');
const needle = Buffer.from("trimmedCode === '// Select a problem to view starter code';");
let pos = 0, n = 0;
while ((pos = buf.indexOf(needle, pos)) !== -1) {
  n++;
  // show surrounding context
  const start = Math.max(0, pos - 160);
  console.log('--- occurrence', n, 'at byte', pos, '---');
  console.log(JSON.stringify(buf.slice(start, pos + needle.length + 60).toString('utf8')));
  pos += needle.length;
}
console.log('TOTAL', n);
console.log('lone CR count:', (() => { let c = 0; for (let i = 0; i < buf.length; i++) if (buf[i] === 13 && buf[i+1] !== 10) c++; return c; })());
