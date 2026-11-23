'use strict';
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function readTemplate(file, stack = new Set()) {
    const resolved = path.resolve(file);
    if (stack.has(resolved)) throw new Error('Cyclic JavaScript template include: ' + resolved);
    const next = new Set(stack); next.add(resolved);
    return fs.readFileSync(resolved, 'utf8').replace(/\{%\s*include\s+["'](_[A-Za-z0-9_-]+\.js)["']\s*%\}/g,
        (_match, name) => readTemplate(path.join(path.dirname(resolved), name), next));
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
