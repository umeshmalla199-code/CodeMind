// Verify: no empty languageSelect branch remains, and parse every script block.
import { readFileSync } from 'fs';
import vm from 'vm';

const html = readFileSync('Frontend/index.html', 'utf8');
const blockRe = /<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/g;
let m, i = 0, bad = 0;
while ((m = blockRe.exec(html)) !== null) {
  const attrs = m[1] || '';
  const code = m[2];
  const kind = attrs.includes('importmap') ? 'importmap(JSON)'
             : attrs.includes('module') ? 'module'
             : 'classic';
  if (kind === 'module') {
    try { new vm.SourceTextModule ? null : null; } catch {}
    console.log(`[${i}] ${kind}: ${code.length} bytes (skipped: needs import resolution)`);
  } else {
    try {
      if (kind === 'importmap(JSON)') JSON.parse(code);
      else new vm.Script(code, { filename: `block${i}.js` });
      console.log(`[${i}] ${kind}: PARSE OK (${code.length} bytes)`);
    } catch (e) {
      bad++;
      console.log(`[${i}] ${kind}: PARSE FAIL -> ${e.message}`);
    }
  }
  i++;
}

// Specific structural check for the repaired branch.
const emptyBranch = "} else if (document.getElementById('languageSelect')) {\r\n                } else if";
console.log('empty languageSelect branches remaining:', (html.split(emptyBranch).length - 1));

const dupUser = (html.match(/const user = getAuthUser\(\);/g) || []).length;
console.log('const user declarations in file:', dupUser);
console.log(bad === 0 ? 'ALL PARSEABLE BLOCKS OK' : `${bad} BLOCK(S) FAILED`);
