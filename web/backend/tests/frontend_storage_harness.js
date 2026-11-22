'use strict';
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function readTemplate(file) {
    const source = fs.readFileSync(file, 'utf8');
    return source.replace(/\{%\s*include\s+["']_chart_workspace\.js["']\s*%\}/g,
        () => fs.readFileSync(path.join(path.dirname(file), '_chart_workspace.js'), 'utf8'));
}

function storageSource(html) {
    const start = html.indexOf('    // localStorage 持久化辅助');
    const end = html.indexOf('    const searchInput =', start);
    if (start < 0 || end < start) throw new Error('Storage source block not found');
    return html.slice(start, end);
}
function installStorage(context, html) {
    vm.runInContext(storageSource(html), context);
    return vm.runInContext("typeof browserStorage === 'undefined' ? null : browserStorage", context);
}
function declaration(html, name, arrow = false) {
    const found = (arrow ? new RegExp('\\bconst\\s+' + name + '\\s*=') : new RegExp('\\bfunction\\s+' + name + '\\s*\\(')).exec(html);
    if (!found) throw new Error('Source declaration missing: ' + name);
    for (let end = html.indexOf('}', found.index); end >= 0; end = html.indexOf('}', end + 1)) {
        const value = html.slice(found.index, end + 1);
        try { new vm.Script(value); return value; } catch (error) { if (!(error instanceof SyntaxError)) throw error; }
    }
    throw new Error('Incomplete source declaration: ' + name);
}
module.exports = {readTemplate, storageSource, installStorage, declaration};
