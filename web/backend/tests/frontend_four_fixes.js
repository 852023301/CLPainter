'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {readTemplate, declaration, installStorage} = require('./frontend_storage_harness.js');
const template = process.argv[2];
const group = process.argv[3];
const html = readTemplate(template);
const plain = value => JSON.parse(JSON.stringify(value));
const flush = async () => { for (let i = 0; i < 80; i++) await Promise.resolve(); };
const gate = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; };
const bars = [1, 2, 3, 4].map(day => ({time: '2024-01-0' + day, open: 10, high: 12, low: 9, close: 11}));
const identity = {market: 'cn', assetClass: 'stock', symbol: 'AAA', frequency: '1day'};
function nativeStore() {
    const values = new Map();
    return {values, getItem: key => values.get(String(key)) ?? null,
        setItem(key, value) { if (this.beforeSet) this.beforeSet(String(key), value); values.set(String(key), String(value)); },
        removeItem: key => values.delete(String(key)), keys: prefix => [...values.keys()].filter(key => key.startsWith(prefix))};
}
function workspace(storage) {
    const scope = vm.createContext({}); vm.runInContext(declaration(html, 'createChartWorkspace'), scope);
    return scope.createChartWorkspace(storage, identity, bars);
}
function snapshot(kind = 'rect', price = 10) {
    return {rectangles: kind === 'rect' ? [{start: {index: 0, price}, end: {index: 2, price: 12}}] : [],
        trends: kind === 'trend' ? [{start: {index: 1, price}, end: {index: 3, price: 13}}] : [], fibs: [], measure: null, order: [kind]};
}
function indicatorHarness() {
    const file = path.join(__dirname, 'repros/frontend_contracts.js');
    const text = fs.readFileSync(file, 'utf8'); const end = text.lastIndexOf('\n(async () => {');
    assert(end > 0);
    return new Function('require', '__dirname', 'process', text.slice(0, end) + '\nreturn {concurrencyContext, chooseIndicator, deferred};')(
        require, path.dirname(file), {argv: ['node', file, '--template', template]});
}
function indicator(load) {
    const harness = indicatorHarness(); const h = harness.concurrencyContext(load);
    h.scope.INDICATOR_LABEL = {volume: '成交量', boll: 'BOLL', rsi: 'RSI', macd: 'MACD'};
    h.meta.requestStatus = {hidden: true, dataset: {}};
    h.meta.requestMessage = {textContent: ''};
    h.meta.retryButton = {hidden: true}; h.meta.cancelButton = {hidden: true};
    return {...h, choose: key => harness.chooseIndicator(h, key)};
}
function requestWorld(fetcher) {
    const timers = new Map(); let next = 0;
    const scope = vm.createContext({AbortController, console, fetch: fetcher,
        setTimeout: (fn, ms) => { const id = ++next; timers.set(id, {fn, ms}); return id; }, clearTimeout: id => timers.delete(id)});
    vm.runInContext(declaration(html, 'requestJson'), scope);
    return {scope, timers, call: (url = '/query', options = {}) => scope.requestJson(url, options),
        expire() { for (const [id, value] of [...timers]) { timers.delete(id); value.fn(); } }};
}
const cases = [
    ['workspace', 'a second tab saving only viewport never deletes drawings', async () => {
        const storage = nativeStore(), a = workspace(storage), b = workspace(storage);
        a.saveDrawings(snapshot()); b.saveViewport({from: 0, to: 3});
        assert.equal(workspace(storage).restore().rectangles.length, 1);
    }],
    ['workspace', 'two stale tabs append independent drawings without ID collision', async () => {
        const storage = nativeStore(), a = workspace(storage), b = workspace(storage);
        a.saveDrawings(snapshot()); b.saveDrawings(snapshot('trend'));
        const restored = workspace(storage).restore();
        assert.equal(restored.rectangles.length, 1); assert.equal(restored.trends.length, 1);
        assert.notEqual(restored.rectangles[0].workspaceId, restored.trends[0].workspaceId);
    }],
    ['workspace', 'a stale tab cannot resurrect a remotely removed drawing', async () => {
        const storage = nativeStore(); workspace(storage).saveDrawings(snapshot());
        const a = workspace(storage), b = workspace(storage), previous = b.restore();
        a.saveDrawings({rectangles: [], trends: [], fibs: [], order: [], measure: null});
        previous.trends.push(snapshot('trend').trends[0]); previous.order.push('trend'); b.saveDrawings(previous);
        const restored = workspace(storage).restore();
        assert.equal(restored.rectangles.length, 0); assert.equal(restored.trends.length, 1);
    }],
    ['workspace', 'interleaved writes from different tabs preserve both changes', async () => {
        const storage = nativeStore(), a = workspace(storage), b = workspace(storage); let nested = false;
        storage.beforeSet = () => { if (!nested) { nested = true; b.saveDrawings(snapshot('trend')); } };
        a.saveDrawings(snapshot()); storage.beforeSet = null;
        const restored = workspace(storage).restore();
        assert.equal(restored.rectangles.length, 1); assert.equal(restored.trends.length, 1);
    }],
    ['workspace', 'unchanged stale geometry cannot overwrite a newer explicit edit', async () => {
        const storage = nativeStore(); workspace(storage).saveDrawings(snapshot());
        const a = workspace(storage), b = workspace(storage), edited = a.restore(), stale = b.restore();
        edited.rectangles[0].start.price = 25; a.saveDrawings(edited);
        stale.trends.push(snapshot('trend').trends[0]); stale.order.push('trend'); b.saveDrawings(stale);
        assert.equal(workspace(storage).restore().rectangles[0].start.price, 25);
    }],
    ['workspace', 'legacy v1 geometry migrates without losing anchors, ordering or measurement', async () => {
        const storage = nativeStore(), empty = workspace(storage);
        const point = (index, price) => ({time: Date.parse(bars[index].time) / 1000, price});
        storage.setItem(empty.key, JSON.stringify({schema: 1, identity: ['cn', 'stock', 'AAA', '1day'],
            shapes: [{id: 1, kind: 'rect', start: point(0, 9), end: point(2, 12)}], measure: {start: point(0, 10), end: point(3, 13)}}));
        const a = workspace(storage), b = workspace(storage), state = a.restore();
        state.trends.push(snapshot('trend').trends[0]); state.order.push('trend'); a.saveDrawings(state); b.saveViewport({from: 0, to: 3});
        const restored = workspace(storage).restore();
        assert.equal(restored.rectangles[0].workspaceId, 1); assert.equal(restored.trends.length, 1);
        assert.equal(restored.measure.end.index, 3); assert.deepEqual(plain(restored.order), ['rect', 'trend']);
    }],
    ['workspace', 'a clock moving backwards cannot reorder new drawings before legacy geometry', async () => {
        const storage = nativeStore(), empty = workspace(storage);
        const point = index => ({time: Date.parse(bars[index].time) / 1000, price: 10});
        storage.setItem(empty.key, JSON.stringify({schema: 1, identity: ['cn', 'stock', 'AAA', '1day'],
            shapes: ['rect', 'trend', 'fib'].map((kind, index) => ({id: index + 1, kind, start: point(0), end: point(3)}))}));
        class OldClock extends Date { static now() { return 0; } }
        const scope = vm.createContext({Date: OldClock}); vm.runInContext(declaration(html, 'createChartWorkspace'), scope);
        const w = scope.createChartWorkspace(storage, identity, bars), state = w.restore();
        state.rectangles.push(snapshot().rectangles[0]); state.order.push('rect'); w.saveDrawings(state);
        assert.deepEqual(plain(workspace(storage).restore().order), ['rect', 'trend', 'fib', 'rect']);
    }],
    ['workspace', 'malformed actor records cannot break restoration or erase valid drawings', async () => {
        const storage = nativeStore(); workspace(storage).saveDrawings(snapshot());
        const prefix = 'chart:workspace-drawings:v1:' + JSON.stringify(['cn', 'stock', 'AAA', '1day']) + ':';
        storage.setItem(prefix + 'bad', JSON.stringify({schema: 1, identity: ['cn', 'stock', 'AAA', '1day'], actor: {toString: null}, changes: []}));
        assert.equal(workspace(storage).restore().rectangles.length, 1);
    }],
    ['indicator', 'failed BOLL is labelled and selector returns to the displayed graph', async () => {
        const h = indicator(name => name === 'boll' ? Promise.reject(new Error('offline')) : Promise.resolve());
        await h.choose('volume'); await h.choose('boll');
        assert.equal(h.meta.select.value, 'volume'); assert.equal(h.meta.indicator, 'volume');
        assert.equal(h.meta.requestStatus.hidden, false);
        assert(h.meta.requestMessage.textContent.includes('BOLL') && h.meta.requestMessage.textContent.includes('成交量'));
        assert.equal(h.meta.retryButton.hidden, false);
    }],
    ['indicator', 'retry replaces the old graph and clears the error notice', async () => {
        let fail = true; const h = indicator(name => name === 'boll' && fail ? Promise.reject(new Error('offline')) : Promise.resolve());
        await h.choose('volume'); await h.choose('boll'); fail = false;
        assert.equal(typeof h.meta.retryBuild, 'function'); await h.meta.retryBuild();
        assert.equal(h.meta.select.value, 'boll'); assert.equal(h.meta.indicator, 'boll'); assert(h.meta.requestStatus.hidden);
    }],
    ['indicator', 'cancel one consumer without aborting another consumer of shared data', async () => {
        const pending = gate(); const h = indicator(name => name === 'boll' ? pending.promise : Promise.resolve());
        await h.choose('volume'); const first = h.choose('boll'); await flush();
        const other = indicator(() => Promise.resolve()).meta; other.select.value = 'boll'; h.scope.otherMeta = other;
        const second = vm.runInContext("buildIndicator(otherMeta, 'boll')", h.scope); await flush();
        assert.equal(typeof h.meta.cancelBuild, 'function'); h.meta.cancelBuild(); await first;
        assert.equal(h.meta.select.value, 'volume'); assert.equal(h.meta.indicator, 'volume');
        pending.resolve(); await second; assert.equal(other.indicator, 'boll');
        assert.equal(h.meta.indicator, 'volume'); assert.equal(h.state.errors.length, 0);
    }],
    ['indicator', 'obsolete failure cannot replace feedback from a newer selection', async () => {
        const pending = gate(); const h = indicator(name => name === 'boll' ? pending.promise : Promise.resolve());
        await h.choose('volume'); const old = h.choose('boll'); await flush(); await h.choose('volume');
        pending.reject(new Error('obsolete')); await old; await flush();
        assert.equal(h.meta.indicator, 'volume'); assert(h.meta.requestStatus.hidden); assert.equal(h.state.errors.length, 0);
    }],
    ['requests', 'timeout rejects even if transport ignores abort and permits retry', async () => {
        const pending = gate(); let signal, calls = 0;
        const h = requestWorld((_url, options) => { signal = options.signal; calls++; return calls === 1 ? pending.promise : Promise.resolve({ok: true, status: 200, json: async () => ({ok: true})}); });
        const first = h.call('/query', {timeoutMs: 20}); const rejected = assert.rejects(first, error => error.name === 'TimeoutError');
        await flush(); h.expire(); await rejected; assert(signal.aborted); assert.equal(h.timers.size, 0);
        assert.equal((await h.call()).ok, true);
        pending.resolve({ok: true, json: async () => ({late: true})}); await flush(); assert.equal(calls, 2);
    }],
    ['requests', 'timeout also bounds response JSON parsing', async () => {
        const body = gate(); const h = requestWorld(async () => ({ok: true, json: () => body.promise}));
        const request = h.call('/query', {timeoutMs: 20}); const rejected = assert.rejects(request, error => error.name === 'TimeoutError');
        await flush(); h.expire(); await rejected; body.resolve({late: true}); await flush(); assert.equal(h.timers.size, 0);
    }],
    ['requests', 'manual abort releases waiting requests without stale success', async () => {
        const pending = gate(); const controller = new AbortController(); let signal;
        const h = requestWorld((_url, options) => { signal = options.signal; return pending.promise; });
        const request = h.call('/query', {signal: controller.signal}); const rejected = assert.rejects(request, error => error.name === 'AbortError');
        await flush(); controller.abort(); await rejected; assert(signal.aborted); assert.equal(h.timers.size, 0);
        pending.resolve({ok: true, json: async () => ({late: true})}); await flush();
    }],
    ['requests', 'already-cancelled requests do not start the transport', async () => {
        let calls = 0; const h = requestWorld(async () => { calls++; }); const controller = new AbortController(); controller.abort();
        await assert.rejects(h.call('/query', {signal: controller.signal}), error => error.name === 'AbortError');
        assert.equal(calls, 0); assert.equal(h.timers.size, 0);
    }],
    ['requests', 'query cancel control restores UI and ignores a late server response', async () => {
        const {boot} = require('./frontend_switch_behavior.js'); const pending = gate();
        const p = await boot('freq=1day', {}, 'available', {quiet: true, beforeResponse: async url => { if (String(url).endsWith('/query')) await pending.promise; }});
        await flush(); const run = p.document.getElementById('screenerRun'), cancel = p.document.getElementById('screenerCancel');
        assert(cancel, 'A visible query cancellation control is required');
        run.dispatch('click'); await flush(); assert(!cancel.hidden); assert(run.disabled);
        cancel.focus(); cancel.dispatch('click'); await flush(); assert(!run.disabled && cancel.hidden);
        assert.equal(p.document.activeElement, run, 'Cancellation must return focus to a visible control');
        assert(p.document.getElementById('screenerResults').textContent.includes('取消'));
        pending.resolve(); await flush(); assert(!p.document.getElementById('screenerResults').textContent.includes('StorageProbeResult'));
    }],
    ['requests', 'a shared module timeout evicts only its failed cache and retries once', async () => {
        let calls = 0;
        const h = requestWorld(async () => { calls++; return calls === 1 ? await new Promise(() => {}) : {ok: true, json: async () => ({data: '[]'})}; });
        Object.assign(h.scope, {currentSymbol: 'AAA', currentFrequency: 'freq=1day', currentMarket: 'market=cn', currentAssetClass: 'asset_class=stock'});
        vm.runInContext('const chartModulePromises = {};\n' + declaration(html, 'fetchChartModule'), h.scope);
        const first = vm.runInContext("fetchChartModule('boll')", h.scope), shared = vm.runInContext("fetchChartModule('boll')", h.scope);
        assert.equal(first, shared); const rejected = assert.rejects(first, error => error.name === 'TimeoutError');
        await flush(); h.expire(); await rejected;
        const recovered = await vm.runInContext("fetchChartModule('boll')", h.scope);
        assert.deepEqual(plain(recovered.data), []); await vm.runInContext("fetchChartModule('boll')", h.scope); assert.equal(calls, 2);
    }],
    ['requests', 'write timeouts explain that server-side mutations may have completed', async () => {
        const h = requestWorld(async () => await new Promise(() => {}));
        const request = h.call('/api/v1/test_api/stock_screener/presets', {method: 'POST', timeoutMs: 20});
        const rejected = assert.rejects(request, error => error.name === 'TimeoutError' && error.message.includes('核对'));
        await flush(); h.expire(); await rejected;
    }],
    ['requests', 'real panel cancel leaves the shared transport and peer panel running', async () => {
        const {boot} = require('./frontend_switch_behavior.js'); const pending = gate(); let sharedSignal;
        const p = await boot('freq=1day', {}, 'available', {quiet: true, beforeResponse: async (url, options) => {
            if (new URL(String(url), 'http://local').searchParams.get('module') === 'boll') { sharedSignal = options.signal; await pending.promise; }
        }});
        await flush(); const select = p.document.getElementById('panelSelect0'); select.value = 'boll'; select.dispatch('change'); await flush();
        assert.equal(p.requests.filter(item => new URL(item.url, 'http://local').searchParams.get('module') === 'boll').length, 1);
        p.document.getElementById('panelCancel0').dispatch('click'); await flush();
        assert.equal(select.value, 'macd'); assert(sharedSignal && !sharedSignal.aborted);
        pending.resolve(); await flush();
        assert(p.charts[2].series.some(item => item.kind === 'candle'), 'The other BOLL panel must finish loading');
        assert(!p.charts[1].series.some(item => item.kind === 'candle'), 'The cancelled panel must keep MACD');
        assert.equal(p.errors.length, 0);
    }],
    ['requests', 'a timed-out query cannot unlock or replace a newer query', async () => {
        const {boot} = require('./frontend_switch_behavior.js'); const old = gate(), latest = gate(); let calls = 0;
        const p = await boot('freq=1day', {}, 'available', {quiet: true, beforeResponse: async url => {
            if (String(url).endsWith('/query')) { calls++; await (calls === 1 ? old.promise : latest.promise); }
        }});
        await flush(); const run = p.document.getElementById('screenerRun'), cancel = p.document.getElementById('screenerCancel');
        run.dispatch('click'); await flush(); p.runTimers(); await flush();
        assert(!run.disabled); assert(p.document.getElementById('screenerResults').textContent.includes('超时'));
        run.dispatch('click'); await flush(); old.resolve(); await flush();
        assert(run.disabled && !cancel.hidden, 'A late old response cannot finish the new request');
        latest.resolve(); await flush(); assert(!run.disabled && cancel.hidden); assert.equal(calls, 2);
    }],
    ['storage', 'healthy storage keeps the warning hidden', async () => {
        const {boot} = require('./frontend_switch_behavior.js');
        const p = await boot('freq=1day', {}, 'available', {quiet: true}); await flush();
        assert.equal(p.document.getElementById('browserStorageNotice').hidden, true); assert.equal(p.errors.length, 0);
    }],
    ['storage', 'failed persistence is observable and workspace does not report success', async () => {
        const values = new Map(); const scope = vm.createContext({localStorage: {getItem: key => values.get(key) ?? null, setItem() { throw new Error('quota'); }, removeItem() {}}});
        const adapter = installStorage(scope, html); const states = []; assert.equal(typeof adapter.subscribe, 'function');
        adapter.subscribe(temporary => states.push(temporary));
        assert.equal(adapter.setItem('key', 'value'), false);
        assert.equal(states.at(-1), true);
        const w = workspace(adapter); assert.equal(w.saveDrawings(snapshot()), false);
        assert.equal(w.restore().rectangles.length, 1, 'Persistence failure must preserve current-page drawing functionality');
    }],
    ['storage', 'warning remains until all failed keys are explicitly recovered', async () => {
        const values = new Map(); let denied = true;
        const scope = vm.createContext({localStorage: {getItem: key => values.get(key) ?? null, setItem(key, value) { if (denied && key === 'bad') throw new Error('quota'); values.set(key, value); }, removeItem: key => values.delete(key)}});
        const adapter = installStorage(scope, html); const states = []; assert.equal(typeof adapter.subscribe, 'function'); adapter.subscribe(value => states.push(value));
        adapter.setItem('bad', 'draft'); adapter.setItem('good', 'ok'); assert.equal(states.at(-1), true);
        denied = false; assert.equal(adapter.setItem('bad', 'saved'), true); assert.equal(states.at(-1), false);
    }],
    ['storage', 'storage-restricted pages show a persistent and accessible warning', async () => {
        const {boot} = require('./frontend_switch_behavior.js');
        for (const mode of ['quota', 'denied', 'getter']) {
            const p = await boot('freq=1day', {}, mode, {quiet: true}); await flush();
            const notice = p.document.getElementById('browserStorageNotice'); assert(notice, 'Storage degradation notice is required');
            assert.equal(notice.hidden, false); const caption = html.match(/<p[^>]*id="browserStorageNotice"[^>]*>([^<]*)<\/p>/)[1];
            assert(caption.includes('临时') && caption.includes('丢失'), 'The literal notice caption must explain data-loss risk');
            assert.equal(notice.getAttribute('role'), 'status'); assert.equal(p.errors.length, 0);
        }
    }],
];
(async () => {
    const results = [];
    for (const [category, name, run] of cases) {
        if (group && group !== category) continue;
        try { await run(); results.push({category, name, status: 'passed'}); }
        catch (error) { results.push({category, name, status: 'failed', error: error.stack || String(error)}); }
    }
    assert(results.length, 'No tests selected'); console.log(JSON.stringify({results}, null, 2));
    if (results.some(item => item.status !== 'passed')) process.exitCode = 1;
})();
