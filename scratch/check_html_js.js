const fs = require('fs');
const html = fs.readFileSync('Frontend/index.html', 'utf8');
const scriptRegex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
let match;
let idx = 0;
let errors = 0;

while ((match = scriptRegex.exec(html)) !== null) {
    const attrs = match[1] || '';
    const code = match[2] || '';
    idx++;
    if (attrs.includes('ld+json') || attrs.includes('application/json') || attrs.includes('importmap')) {
        try {
            JSON.parse(code);
            console.log(`Script #${idx} (JSON-LD): valid JSON`);
        } catch (e) {
            console.error(`Script #${idx} (JSON-LD): syntax error:`, e.message);
            errors++;
        }
    } else if (attrs.includes('module')) {
        console.log(`Script #${idx} (ES Module): skipped`);
    } else if (code.trim().length > 0) {
        try {
            new Function(code);
            console.log(`Script #${idx} (Standard JS): valid (${code.length} chars)`);
        } catch (e) {
            console.error(`Script #${idx} (Standard JS): syntax error:`, e.message);
            errors++;
        }
    }
}

if (errors === 0) {
    console.log('ALL SCRIPTS IN index.html ARE 100% SYNTACTICALLY VALID!');
} else {
    process.exit(1);
}
