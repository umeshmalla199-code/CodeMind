const fs = require('fs');
const vm = require('vm');
const html = fs.readFileSync('Frontend/index.html', 'utf8');
const scriptRegex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
let match;
let count = 0;
let errors = 0;
while ((match = scriptRegex.exec(html)) !== null) {
    count++;
    const attrs = match[1];
    const code = match[2];
    if (!code.trim()) continue;
    
    // Check type attribute
    const typeMatch = attrs.match(/type\s*=\s*["']([^"']+)["']/i);
    const scriptType = typeMatch ? typeMatch[1].toLowerCase() : 'text/javascript';
    
    if (scriptType === 'importmap' || scriptType === 'application/json' || scriptType === 'application/ld+json') {
        try {
            JSON.parse(code);
            console.log(`Script ${count} (${scriptType}) valid JSON.`);
        } catch (e) {
            errors++;
            console.error(`Script ${count} (${scriptType}) JSON ERROR:`, e.message);
        }
        continue;
    }
    
    if (scriptType === 'module') {
        try {
            new vm.SourceTextModule(code);
            console.log(`Script ${count} (module) parsed successfully.`);
        } catch (e) {
            errors++;
            console.error(`Script ${count} (module) SYNTAX ERROR: ${e.message}`);
            const offset = match.index;
            const lineNum = html.substring(0, offset).split('\n').length;
            console.error(`Starts around line ${lineNum} of index.html`);
        }
        continue;
    }

    try {
        new Function(code);
        console.log(`Script ${count} (classic) parsed successfully.`);
    } catch (e) {
        errors++;
        console.error(`Script ${count} (classic) SYNTAX ERROR: ${e.message}`);
        const offset = match.index;
        const lineNum = html.substring(0, offset).split('\n').length;
        console.error(`Starts around line ${lineNum} of index.html`);
    }
}
if (errors === 0) {
    console.log(`All scripts validated with 0 syntax errors!`);
} else {
    console.log(`Found ${errors} syntax errors.`);
}
