import fs from 'fs';
import { readFileSync } from 'fs';
import vm from 'vm';
const src = readFileSync('scratch/cur1.js','utf8');
try { new vm.Script(src, {filename:'cur1.js'}); console.log('PARSE OK'); }
catch(e){ console.log('PARSE ERROR:', e.message); console.log(e.stack.split('\n').slice(0,6).join('\n')); }
