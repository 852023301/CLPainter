'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const ids = ['screenerPanel', 'screenerFilters', 'screenerRun', 'screenerReset', 'screenerResults',
    'screenerCollapse', 'screenerExpand', 'screenerResizer', 'screenerPresetSelect', 'screenerPresetName',
    'screenerPresetSave', 'screenerPresetApply', 'screenerPresetUpdate', 'screenerPresetDelete',
    'screenerPresetNew', 'screenerPresetCreatePanel', 'screenerPresetCancel', 'screenerPresetStatus', 'screenerPresetRetry', 'screenerRealtimeTab', 'screenerHistoryTab', 'screenerRealtimePanel', 'screenerHistoryPanel', 'screenerHistoryLink', 'screenerHistoryPreset', 'screenerHistoryFrequency', 'screenerHistoryVersion', 'screenerHistoryRefresh', 'screenerHistoryPage', 'screenerHistoryStatus', 'screenerHistoryChartHint', 'screenerHistorySummary', 'screenerHistoryResults', 'screenerHistoryViewResults', 'screenerHistoryViewAdded', 'screenerHistoryViewRemoved', 'screenerHistoryViewRetained'];
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
    focus() { this.focused = true; }
    async emit(type, extra = {}) { for (const callback of this.listeners[type] || []) await callback({target: this, preventDefault() {}, ...extra}); }
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
        else if (url.endsWith('/query')) payload = server.queryPayload || {count: 0, results: []};
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
    for (const [id, element] of Object.entries(elements)) {
        const tag = html.match(new RegExp('<[^>]+\\bid="' + id + '"[^>]*>'));
        element.hidden = Boolean(tag && /\bhidden(?:\s|>|=)/.test(tag[0]));
    }
    const document = {getElementById: id => elements[id], createElement: tag => new Element(tag)};
    const context = {document, console, URLSearchParams, appShell: new Element(), window: {innerWidth: 1200, location: {search: '', pathname: '/api/v1/test_api/lightweight_charts_demo', assign() {}}, history: {replaceState() {}}},
        requestAnimationFrame: callback => callback(), fetch: server.fetch, confirm: () => true,
        localStorage: {getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)),
            removeItem: key => storage.delete(key)},
        lsGetString: (key, fallback) => storage.get(key) ?? fallback,
        lsSetString: (key, value) => storage.set(key, String(value)),
        lsGetBool: (key, fallback) => storage.has(key) ? storage.get(key) === '1' : fallback,
        lsSetBool: (key, value) => storage.set(key, value ? '1' : '0'), syncChartWidth() {},
    };
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]), '../static/js/screener-history.js'), 'utf8'), context);
    vm.runInContext(source, context); await flush();
    return {elements, context, storage, field: key => elements.screenerFilters.querySelectorAll('select').find(select => select.dataset.field === key)};
}
async function choose(page, id) {
    page.elements.screenerPresetSelect.value = String(id);
    await page.elements.screenerPresetSelect.emit('change');
}
(async () => {
    const server = makeServer(); const first = await boot(server);
    assert(first.elements.screenerPresetCreatePanel.hidden, 'New-preset editor must not occupy space on startup');
    assert(first.elements.screenerPresetSave.disabled, 'Closed editor must not allow saving');
    await first.elements.screenerPresetNew.click();
    assert.equal(first.elements.screenerPresetCreatePanel.hidden, false);
    assert.equal(first.elements.screenerPresetNew['aria-expanded'], 'true');
    assert(first.elements.screenerPresetName.focused, 'Opening creation must focus the name input');
    const beforeCancel = server.requests.length;
    first.elements.screenerPresetName.value = 'discard';
    await first.elements.screenerPresetCancel.click();
    assert(first.elements.screenerPresetCreatePanel.hidden);
    assert.equal(first.elements.screenerPresetName.value, '');
    assert.equal(first.elements.screenerPresetNew['aria-expanded'], 'false');
    assert(first.elements.screenerPresetNew.focused);
    assert.equal(server.requests.length, beforeCancel, 'Cancel must not issue requests');
    await first.elements.screenerPresetNew.click();
    for (const field of fields) first.field(field).value = '';
    first.field('second_point_type').value = '0';
    first.elements.screenerPresetName.value = '  不限零值方案  ';
    await first.elements.screenerPresetSave.click(); await flush();
    assert.equal(server.presets.length, 1);
    assert(first.elements.screenerPresetCreatePanel.hidden, 'Successful save must collapse the editor');
    const preset = server.presets[0];
    assert.equal(preset.filters.frequency, null);
    assert.equal(preset.filters.second_point_type, 0);
    assert(!('results' in server.requests.find(request => request.method === 'POST').body));
    const fresh = await boot(server); await choose(fresh, preset.id);
    const queryCount = () => server.requests.filter(request => request.url.endsWith('/query')).length;
    const beforeApply = queryCount();
    server.queryPayload = {count: 1, results: [{code: 'AAA', display_name: 'Applied match', asset_class: 'stock', frequencies: ['1day'], url: '/chart?symbol=AAA'}]};
    await fresh.elements.screenerPresetApply.click();
    assert.equal(queryCount(), beforeApply + 1, 'Applying a preset must query exactly once automatically');
    assert(fresh.elements.screenerResults.textContent.includes('Applied match'), 'Application must render the returned results without another click');
    const automaticQuery = server.requests.filter(request => request.url.endsWith('/query')).at(-1).body;
    assert.equal(automaticQuery.frequency, null); assert.equal(automaticQuery.second_point_type, 0);
    assert.equal(fresh.field('frequency').value, ''); assert.equal(fresh.field('market').value, '');
    assert.equal(fresh.field('second_point_type').value, '0');
    await fresh.elements.screenerRun.click(); await flush();
    assert.equal(queryCount(), beforeApply + 2, 'Manual confirmation must remain available after automatic query');
    const query = server.requests.filter(request => request.url.endsWith('/query')).at(-1).body;
    assert.equal(query.frequency, null); assert.equal(query.second_point_type, 0);
    const reload = await boot(server, fresh.storage);
    assert.equal(reload.field('frequency').value, '', 'Refresh must preserve unlimited instead of defaulting to daily');
    await choose(fresh, preset.id); fresh.field('frequency').value = '1week';
    fresh.elements.screenerPresetName.value = 'unrelated hidden draft';
    await fresh.elements.screenerPresetUpdate.click();
    assert.equal(server.presets[0].id, preset.id); assert.equal(server.presets[0].filters.frequency, '1week');
    assert.equal(server.presets[0].name, preset.name, 'Updating conditions must retain the selected preset name');
    await fresh.elements.screenerPresetNew.click();
    assert(fresh.elements.screenerPresetUpdate.disabled && fresh.elements.screenerPresetDelete.disabled, 'Creating must not mutate another preset');
    const mutationsBeforeInvalidName = server.requests.length;
    fresh.elements.screenerPresetName.value = '   '; await fresh.elements.screenerPresetSave.click();
    fresh.elements.screenerPresetName.value = 'x'.repeat(65); await fresh.elements.screenerPresetSave.click();
    assert.equal(server.requests.length, mutationsBeforeInvalidName, 'Invalid names must not issue writes');
    fresh.elements.screenerPresetName.value = 'duplicate';
    server.failNext = {method: 'POST', status: 409}; await fresh.elements.screenerPresetSave.click();
    assert.equal(server.presets.length, 1, 'Create failure must preserve the saved list');
    assert.equal(fresh.elements.screenerPresetCreatePanel.hidden, false, 'Save failure must keep the editor and draft');
    assert.equal(fresh.elements.screenerPresetName.value, 'duplicate');
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
    await fresh.elements.screenerPresetName.emit('keydown', {key: 'Escape'});
    assert(fresh.elements.screenerPresetCreatePanel.hidden);
    fresh.context.confirm = () => false;
    const count = server.requests.length;
    await fresh.elements.screenerPresetUpdate.click(); await fresh.elements.screenerPresetDelete.click();
    assert.equal(server.requests.length, count, 'Cancelled mutations must not send requests');
    fresh.context.confirm = () => true;
    server.failNext = {method: 'PUT', status: 409};
    fresh.field('frequency').value = '1day'; await fresh.elements.screenerPresetUpdate.click();
    assert.equal(server.presets[0].filters.frequency, '1week'); assert.equal(fresh.field('frequency').value, '1day');
    assert(fresh.elements.screenerPresetStatus.textContent.includes('simulated failure'));
    await fresh.elements.screenerPresetNew.click();
    await fresh.elements.screenerReset.click();
    assert(fresh.elements.screenerPresetCreatePanel.hidden, 'Reset must close the draft without deleting presets');
    assert.equal(server.presets.length, 1, 'Reset must not delete saved presets');
    assert.equal(fresh.field('frequency').value, '1day');
    await choose(fresh, preset.id);
    server.failNext = {method: 'DELETE', status: 500}; await fresh.elements.screenerPresetDelete.click();
    assert.equal(fresh.elements.screenerPresetSelect.options.length, 2, 'Delete failure must keep the option');
    await fresh.elements.screenerPresetDelete.click();
    assert.equal(server.presets.length, 0); assert.equal(fresh.elements.screenerPresetSelect.options.length, 1);
    await fresh.elements.screenerPresetNew.click();
    fresh.elements.screenerPresetName.value = 'slow'; server.holdNext = 'POST';
    const saving = fresh.elements.screenerPresetSave.click(); await flush();
    assert(fresh.elements.screenerPresetSave.disabled && fresh.elements.screenerPresetApply.disabled);
    assert(fresh.elements.screenerPresetCancel.disabled, 'Saving must disable cancellation');
    await fresh.elements.screenerPresetSave.click();
    server.release(); await saving;
    assert.equal(server.presets.length, 1, 'Double click must not create two presets');
    server.presets[0].filters.frequency = '1min';
    const unsupported = await boot(server); await choose(unsupported, server.presets[0].id);
    const beforeUnsupported = queryCount();
    await unsupported.elements.screenerPresetApply.click();
    assert.equal(queryCount(), beforeUnsupported, 'Unsupported preset filters must not issue a query');
    assert.equal(unsupported.field('frequency').value, '1day');
    assert(unsupported.elements.screenerPresetStatus.textContent.includes('不可用'));
    const unavailable = makeServer(); unavailable.failNext = {method: 'GET', status: 500};
    const failed = await boot(unavailable);
    assert(failed.elements.screenerPresetSave.disabled, 'Initial load failure must not permit writes');
    assert.equal(failed.elements.screenerPresetRetry.hidden, false);
    await failed.elements.screenerPresetRetry.click(); await flush();
    assert.equal(failed.elements.screenerPresetNew.disabled, false);
    assert(failed.elements.screenerPresetSave.disabled, 'Loading recovery must not open the editor automatically');
    await fresh.elements.screenerPresetNew.click();
    fresh.elements.screenerPresetName.value = '<img src=x onerror=alert(1)>';
    await fresh.elements.screenerPresetSave.click();
    assert(fresh.elements.screenerPresetSelect.options.some(option => option.textContent === '<img src=x onerror=alert(1)>'));
    assert(!fresh.elements.screenerPresetSelect.children.some(node => node.tagName === 'img'));
    const keyboardServer = makeServer(); const keyboardPage = await boot(keyboardServer);
    await keyboardPage.elements.screenerPresetNew.click();
    keyboardPage.elements.screenerPresetName.value = 'Keyboard preset';
    await keyboardPage.elements.screenerPresetName.emit('keydown', {key: 'Enter', isComposing: true});
    assert.equal(keyboardServer.presets.length, 0, 'IME confirmation must not submit a preset');
    await keyboardPage.elements.screenerPresetName.emit('keydown', {key: 'Enter'}); await flush();
    assert.equal(keyboardServer.presets.length, 1, 'Enter must save the new preset');
    assert(keyboardPage.elements.screenerPresetCreatePanel.hidden);
    const autoServer = makeServer();
    autoServer.presets = [{id: 1, name: 'Auto query', filters: {...emptyFilters(), frequency: '1week', second_point_type: 0}}];
    const autoPage = await boot(autoServer); await choose(autoPage, 1);
    const autoQueries = () => autoServer.requests.filter(request => request.url.endsWith('/query'));
    assert.equal(autoQueries().length, 0, 'Selecting a preset alone must not query');
    autoPage.elements.screenerResults.textContent = 'stale cached result';
    autoServer.holdNext = 'POST';
    const applying = autoPage.elements.screenerPresetApply.click(); await flush();
    assert.equal(autoQueries().length, 1);
    assert.equal(autoQueries()[0].body.frequency, '1week');
    assert.equal(autoQueries()[0].body.second_point_type, 0);
    assert(autoPage.elements.screenerPresetApply.disabled && autoPage.elements.screenerRun.disabled && autoPage.elements.screenerPresetSelect.disabled);
    assert.equal(autoPage.elements.screenerRun.textContent, '查询中...');
    assert(!autoPage.elements.screenerResults.textContent.includes('stale cached result'));
    await autoPage.elements.screenerPresetApply.click(); await autoPage.elements.screenerRun.click();
    assert.equal(autoQueries().length, 1, 'Repeated apply/confirm while loading must not duplicate requests');
    autoServer.release(); await applying;
    assert(autoPage.elements.screenerResults.textContent.includes('没有匹配的标的'), 'Successful empty results must be displayed');
    assert(!autoPage.elements.screenerPresetApply.disabled && !autoPage.elements.screenerRun.disabled);
    autoServer.failNext = {method: 'POST', status: 503, detail: 'query temporarily unavailable'};
    await autoPage.elements.screenerPresetApply.click();
    assert.equal(autoQueries().length, 2);
    assert(autoPage.elements.screenerResults.textContent.includes('query temporarily unavailable'));
    assert(!autoPage.elements.screenerPresetApply.disabled && !autoPage.elements.screenerRun.disabled);
    assert.equal(autoPage.field('frequency').value, '1week', 'Query failure must retain applied filters');
    assert.equal(JSON.parse(autoPage.storage.get('screener:state')).results, null, 'Failure must not resurrect cached results');
    await autoPage.elements.screenerPresetApply.click();
    assert.equal(autoQueries().length, 3, 'Applying again after failure must retry once');
    assert(autoPage.elements.screenerResults.textContent.includes('没有匹配的标的'));
    console.log('Saved screener preset behavior passed, including automatic query, results, loading guards, empty results and retry');
})().catch(error => {console.error(error.stack || error); process.exitCode = 1;});
