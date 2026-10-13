import { readFileSync } from 'fs';
const src = readFileSync('scratch/cur1.js', 'utf8');
const lines = src.split(/\r?\n/);
console.log('total lines', lines.length);
const idx = lines.findIndex(l => l.includes('isPlaceholderCode = !trimmedCode'));
console.log('decl index', idx);
for (let j = idx; j < idx + 8; j++) {
  console.log('  [' + j + ']', JSON.stringify(lines[j]));
}
console.log('--- C++ placeholder line indices ---');
lines.forEach((l, i) => {
  if (l.includes('// Select a problem to view starter code')) console.log('  [' + i + ']', JSON.stringify(l));
});
