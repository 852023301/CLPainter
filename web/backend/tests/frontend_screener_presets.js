'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const ids = ['screenerPanel', 'screenerFilters', 'screenerRun', 'screenerReset', 'screenerResults',
    'screenerCollapse', 'screenerExpand', 'screenerResizer', 'screenerPresetSelect', 'screenerPresetName',
    'screenerPresetSave', 'screenerPresetApply', 'screenerPresetUpdate', 'screenerPresetDelete',
    'screenerPresetStatus', 'screenerPresetRetry'];
ids.forEach(id => assert(html.includes('id="' + id + '"'), 'Missing preset UI: ' + id));
const start = html.indexOf('    const screenerPanel = ');
const end = html.indexOf("    document.querySelectorAll('#frequencyTabs", start);
assert(start >= 0 && end > start);
const source = html.slice(start, end);
class Element {
    constructor(tag = 'div') {
        this.tagName = tag; this.children = []; this.dataset = {}; this.listeners = {};
        this.disabled = false; this.hidden = false; this._value = ''; this._text = ''; this.scrollTop = 0;
        this.style = {setProperty() {}};
        const classes = new Set();
        this.classList = {add: value => classes.add(value), remove: value => classes.delete(value),
            contains: value => classes.has(value), toggle: (value, on) => on ? classes.add(value) : classes.delete(value)};
    }
    set value(value) {
        this._value = String(value);
        if (this.tagName === 'select' && !this.options.some(option => option.value === this._value)) this._value = '';
    }
    get value() { return this._value; }
    get options() { return this.children; }
    set textContent(text) { this._text = String(text); this.children = []; if (this.tagName === 'select') this._value = ''; }
    get textContent() { return this._text + this.children.map(node => node.textContent).join(''); }
    appendChild(node) { this.children.push(node); }
    append(...nodes) { this.children.push(...nodes); }
    setAttribute(name, value) { this[name] = String(value); }
    addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
    querySelectorAll(selector) {
        return this.children.flatMap(child => [...(child.tagName === selector ? [child] : []), ...child.querySelectorAll(selector)]);
    }
    async emit(type) { for (const callback of this.listeners[type] || []) await callback({target: this}); }
    async click() { if (!this.disabled) await this.emit('click'); }
}
const options = {
    dimensions: [
        {field: 'market', label: '市场', options: [{value: 'cn', label: '中国'}]},
        {field: 'asset_class', label: '种类', options: [{value: 'stock', label: '股票'}]},
        {field: 'frequency', label: '周期', options: [{value: '1day', label: '日K'}, {value: '1week', label: '周K'}]},
        {field: 'scope', label: '构件', options: [{value: 'bi', label: '笔'}]},
    ],
    states: ['second_point_type', 'third_point_type'].map(field => ({field, label: field,
        options: [0, 1, 2].map(value => ({value, label: String(value)}))})),
};
const fields = [...options.dimensions, ...options.states].map(item => item.field);
const emptyFilters = () => Object.fromEntries(fields.map(field => [field, null]));
const clone = value => JSON.parse(JSON.stringify(value));
const flush = async () => { for (let step = 0; step < 30; step++) await Promise.resolve(); };
function makeServer() {
    const server = {presets: [], requests: [], nextId: 1, failNext: null, holdNext: null};
    server.fetch = async (url, config = {}) => {
        const method = config.method || 'GET';
        const body = config.body ? JSON.parse(config.body) : null;
        server.requests.push({url, method, body});
        if (server.holdNext === method) {
            server.holdNext = null;
            await new Promise(resolve => { server.release = resolve; });
        }
        let status = 200; let payload;
        if (server.failNext && server.failNext.method === method) {
            status = server.failNext.status; payload = {detail: server.failNext.detail || 'simulated failure'}; server.failNext = null;
        } else if (url.endsWith('/options')) payload = options;
        else if (url.endsWith('/query')) payload = {count: 0, results: []};
        else if (method === 'GET') payload = {presets: server.presets};
        else if (method === 'POST') {
            const preset = {id: server.nextId++, name: body.name.trim(), filters: {...emptyFilters(), ...body.filters}};
            server.presets.push(preset); payload = preset; status = 201;
        } else {
            const id = Number(url.split('/').pop());
            const index = server.presets.findIndex(preset => preset.id === id);
            if (index < 0) { status = 404; payload = {detail: 'missing'}; }
            else if (method === 'PUT') {
                server.presets[index] = {...server.presets[index], name: body.name.trim(), filters: {...emptyFilters(), ...body.filters}};
                payload = server.presets[index];
            } else { server.presets.splice(index, 1); status = 204; payload = null; }
        }
        return {ok: status >= 200 && status < 300, status, json: async () => clone(payload)};
    };
    return server;
}
async function boot(server, storage = new Map()) {
    const elements = Object.fromEntries(ids.map(id => [id, new Element(id === 'screenerPresetSelect' ? 'select' : 'div')]));
    const document = {getElementById: id => elements[id], createElement: tag => new Element(tag)};
    const context = {document, console, appShell: new Element(), window: {innerWidth: 1200},
        requestAnimationFrame: callback => callback(), fetch: server.fetch, confirm: () => true,
        localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)),
            removeItem: key => storage.delete(key)},
        lsGetString: (key, fallback) => storage.get(key) ?? fallback,
        lsSetString: (key, value) => storage.set(key, String(value)),
        lsGetBool: (key, fallback) => storage.has(key) ? storage.get(key) === '1' : fallback,
        lsSetBool: (key, value) => storage.set(key, value ? '1' : '0'), syncChartWidth() {},
    };
    vm.createContext(context); vm.runInContext(source, context); await flush();
    return {elements, context, storage, field: key => elements.screenerFilters.querySelectorAll('select').find(select => select.dataset.field === key)};
}
async function choose(page, id) {
    page.elements.screenerPresetSelect.value = String(id);
    await page.elements.screenerPresetSelect.emit('change');
}
(async () => {
    const server = makeServer(); const first = await boot(server);
    for (const field of fields) first.field(field).value = '';
    first.field('second_point_type').value = '0';
    first.elements.screenerPresetName.value = '  不限零值方案  ';
    await first.elements.screenerPresetSave.click(); await flush();
    assert.equal(server.presets.length, 1);
    const preset = server.presets[0];
    assert.equal(preset.filters.frequency, null);
    assert.equal(preset.filters.second_point_type, 0);
    assert(!('results' in server.requests.find(request => request.method === 'POST').body));
    const fresh = await boot(server); await choose(fresh, preset.id);
    const queryCount = () => server.requests.filter(request => request.url.endsWith('/query')).length;
    const beforeApply = queryCount();
    await fresh.elements.screenerPresetApply.click();
    assert.equal(queryCount(), beforeApply, 'Applying a preset must not query automatically');
    assert.equal(fresh.field('frequency').value, ''); assert.equal(fresh.field('market').value, '');
    assert.equal(fresh.field('second_point_type').value, '0');
    await fresh.elements.screenerRun.click(); await flush();
    assert.equal(queryCount(), beforeApply + 1);
    const query = server.requests.filter(request => request.url.endsWith('/query')).at(-1).body;
    assert.equal(query.frequency, null); assert.equal(query.second_point_type, 0);
    const reload = await boot(server, fresh.storage);
    assert.equal(reload.field('frequency').value, '', 'Refresh must preserve unlimited instead of defaulting to daily');
    await choose(fresh, preset.id); fresh.field('frequency').value = '1week';
    fresh.elements.screenerPresetName.value = '周线方案';
    await fresh.elements.screenerPresetUpdate.click();
    assert.equal(server.presets[0].id, preset.id); assert.equal(server.presets[0].filters.frequency, '1week');
    assert.equal(server.presets[0].name, '周线方案');
    const mutationsBeforeInvalidName = server.requests.length;
    fresh.elements.screenerPresetName.value = '   '; await fresh.elements.screenerPresetSave.click();
    fresh.elements.screenerPresetName.value = 'x'.repeat(65); await fresh.elements.screenerPresetSave.click();
    assert.equal(server.requests.length, mutationsBeforeInvalidName, 'Invalid names must not issue writes');
    fresh.elements.screenerPresetName.value = 'duplicate';
    server.failNext = {method: 'POST', status: 409}; await fresh.elements.screenerPresetSave.click();
    assert.equal(server.presets.length, 1, 'Create failure must preserve the saved list');
    server.failNext = {method: 'POST', status: 422, detail: [{msg: 'invalid name'}]};
    await fresh.elements.screenerPresetSave.click();
    assert(fresh.elements.screenerPresetStatus.textContent.includes('invalid name'), 'Validation errors must be readable');
    server.holdNext = 'POST'; const querying = fresh.elements.screenerRun.click(); await flush();
    assert(fresh.elements.screenerPresetApply.disabled && fresh.elements.screenerPresetSave.disabled);
    assert(fresh.elements.screenerPresetName.disabled && fresh.elements.screenerPresetSelect.disabled);
    const requestsWhileQuerying = server.requests.length;
    await fresh.elements.screenerPresetApply.click(); await fresh.elements.screenerPresetSave.click();
    assert.equal(server.requests.length, requestsWhileQuerying);
    server.release(); await querying;
    fresh.context.confirm = () => false;
    const count = server.requests.length;
    await fresh.elements.screenerPresetUpdate.click(); await fresh.elements.screenerPresetDelete.click();
    assert.equal(server.requests.length, count, 'Cancelled mutations must not send requests');
    fresh.context.confirm = () => true;
    server.failNext = {method: 'PUT', status: 409};
    fresh.field('frequency').value = '1day'; await fresh.elements.screenerPresetUpdate.click();
    assert.equal(server.presets[0].filters.frequency, '1week'); assert.equal(fresh.field('frequency').value, '1day');
    assert(fresh.elements.screenerPresetStatus.textContent.includes('simulated failure'));
    await fresh.elements.screenerReset.click();
    assert.equal(server.presets.length, 1, 'Reset must not delete saved presets');
    assert.equal(fresh.field('frequency').value, '1day');
    await choose(fresh, preset.id);
    server.failNext = {method: 'DELETE', status: 500}; await fresh.elements.screenerPresetDelete.click();
    assert.equal(fresh.elements.screenerPresetSelect.options.length, 2, 'Delete failure must keep the option');
    await fresh.elements.screenerPresetDelete.click();
    assert.equal(server.presets.length, 0); assert.equal(fresh.elements.screenerPresetSelect.options.length, 1);
    fresh.elements.screenerPresetName.value = 'slow'; server.holdNext = 'POST';
    const saving = fresh.elements.screenerPresetSave.click(); await flush();
    assert(fresh.elements.screenerPresetSave.disabled && fresh.elements.screenerPresetApply.disabled);
    await fresh.elements.screenerPresetSave.click();
    server.release(); await saving;
    assert.equal(server.presets.length, 1, 'Double click must not create two presets');
    server.presets[0].filters.frequency = '1min';
    const unsupported = await boot(server); await choose(unsupported, server.presets[0].id);
    await unsupported.elements.screenerPresetApply.click();
    assert.equal(unsupported.field('frequency').value, '1day');
    assert(unsupported.elements.screenerPresetStatus.textContent.includes('不可用'));
    const unavailable = makeServer(); unavailable.failNext = {method: 'GET', status: 500};
    const failed = await boot(unavailable);
    assert(failed.elements.screenerPresetSave.disabled, 'Initial load failure must not permit writes');
    assert.equal(failed.elements.screenerPresetRetry.hidden, false);
    await failed.elements.screenerPresetRetry.click(); await flush();
    assert.equal(failed.elements.screenerPresetSave.disabled, false);
    fresh.elements.screenerPresetName.value = '<img src=x onerror=alert(1)>';
    await fresh.elements.screenerPresetSave.click();
    assert(fresh.elements.screenerPresetSelect.options.some(option => option.textContent === '<img src=x onerror=alert(1)>'));
    assert(!fresh.elements.screenerPresetSelect.children.some(node => node.tagName === 'img'));
    console.log('Saved screener preset behavior passed');
})().catch(error => {console.error(error.stack || error); process.exitCode = 1;});
