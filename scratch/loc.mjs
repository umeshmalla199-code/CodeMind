import { readFileSync } from 'fs';
const lines = readFileSync('scratch/cur1.js','utf8').split('\n');
// Find every line declaring 'user' anywhere in sendCompanionMessage (4792 -> end)
for (let i = 4791; i < 5100; i++) {
  if (/\buser\b\s*=/.test(lines[i]) && /const|let|var/.test(lines[i])) {
    console.log(i+1, '|', lines[i]);
  }
}
