'use strict';
// Opt-in contracts against original template functions; no browser or live I/O.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const args = process.argv.slice(2);
const option = name => { const i = args.indexOf(name); return i < 0 ? undefined : args[i + 1]; };
const template = option('--template') || path.resolve(__dirname, '../../app/templates/lightweight_charts_demo.html');
const source = fs.readFileSync(template, 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));
const flush = async () => { for (let i = 0; i < 40; i++) await Promise.resolve(); };
function declaration(name, arrow = false) {
    const pattern = arrow ? new RegExp('\\bconst\\s+' + name + '\\s*=') : new RegExp('\\b(?:async\\s+)?function\\s+' + name + '\\s*\\(');
    const found = pattern.exec(source);
    if (!found) throw new Error('Source function not found: ' + name);
    for (let end = source.indexOf('}', found.index); end >= 0; end = source.indexOf('}', end + 1)) {
        const candidate = source.slice(found.index, end + 1);
        try { new vm.Script(candidate); return candidate; } catch (error) { if (!(error instanceof SyntaxError)) throw error; }
    }
    throw new Error('Source function could not be isolated: ' + name);
}
function context(values = {}) {
    return vm.createContext({console: {log() {}, error() {}, warn() {}}, URLSearchParams, AbortController, setTimeout, clearTimeout, ...values});
}
function storageContext(unavailable) {
    const values = new Map();
    const fail = () => { const error = new Error('Storage unavailable'); error.name = 'SecurityError'; throw error; };
    const localStorage = unavailable ? {getItem: fail, setItem: fail} : {getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value))};
    const scope = context({localStorage});
    const start = source.indexOf('    // localStorage 持久化辅助');
    const end = source.indexOf('    const searchInput =', start);
    if (start < 0 || end < start) throw new Error('Storage helpers not found');
    vm.runInContext(source.slice(start, end), scope);
    return scope;
}
function indicatorContext(waitForData = async () => {}) {
    const state = {series: [], range: {from: 100, to: 150}, errors: []};
    const timeScale = {getVisibleLogicalRange: () => ({...state.range}), setVisibleLogicalRange: range => { state.range = {...range}; }, fitContent() {}};
    const add = kind => {
        const item = {kind, setData(data) { this.data = data; }, setMarkers() {}, applyOptions() {}, createPriceLine() {}};
        state.series.push(item); return item;
    };
    const chart = {addHistogramSeries: () => add('histogram'), addCandlestickSeries: () => add('candlestick'), removeSeries: item => { state.series = state.series.filter(value => value !== item); }, applyOptions() {}, priceScale: () => ({applyOptions() {}}), timeScale: () => timeScale};
    const meta = {idx: 0, chart, container: {style: {}}, valueLabel: {style: {}}, select: {value: 'volume'}, addedSeries: [], primarySeries: null, lookup: {}};
    const scope = context({meta, chart, isSyncingTimeRange: false, ensureIndicatorData: waitForData, INDICATOR_HEIGHT: {volume: 120, boll: 120}, PRICE_SCALE_WIDTH: 60, currentPrecision: 2, candleData: [{time: '2026-11-20', open: 1, high: 2, low: 1, close: 2}], volumeData: [], volumeLookup: {}, volumeColorLookup: {}, formatVolume: String, bollData: [], bollLookup: {}, resizeMainChart() {}, buildSubSeries: () => ({}), panels: [meta], initialPanelsReady: true, getInitialLogicalRange: () => ({from: 900, to: 949}), applyInitialLogicalRange() {}, console: {error: (...items) => state.errors.push(items.map(String).join(' ')), log() {}, warn() {}}});
    vm.runInContext(declaration('buildIndicator'), scope);
    return {scope, meta, state};
}
function assertBuildSucceeded(state) {
    if (state.errors.length) throw new Error('Unexpected build/harness error: ' + state.errors.join('; '));
}

// Exercise the original builders with deterministic, independently gated requests.
function deferred() {
    let resolve; let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return {promise, resolve, reject};
}
function concurrencyContext(waitForData = async () => {}) {
    const h = indicatorContext(waitForData);
    const {scope, meta, state} = h;
    const chart = meta.chart;
    state.rangeWrites = []; state.options = []; state.initializations = 0;
    const oldSetRange = chart.timeScale().setVisibleLogicalRange;
    chart.timeScale().setVisibleLogicalRange = range => { state.rangeWrites.push(plain(range)); oldSetRange(range); };
    chart.applyOptions = options => state.options.push(plain(options));
    chart.addLineSeries = () => {
        const item = {kind: 'line', setData(data) { this.data = data; }, setMarkers() {}, applyOptions() {}, createPriceLine() {}};
        state.series.push(item); return item;
    };
    const values = [{time: '2026-11-20', value: 1}];
    scope.bollData = [{key: 'BOLL_UP', color: '#111', values}, {key: 'BOLL_DOWN', color: '#222', values}];
    scope.rsiData = [{key: 'RSI6', color: '#333', values}];
    scope.rsiLookup = {}; scope.macdLookup = {}; scope.macdStatLookup = {};
    scope.macdData = {stats: [{time: '2026-11-20', macd: 1, color: '#444'}], lines: [{key: 'DIFF', color: '#555', values}, {key: 'DEA', color: '#666', values}], markers: []};
    scope.INDICATOR_HEIGHT = {volume: 120, boll: 120, rsi: 120, macd: 180};
    scope.applyInitialLogicalRange = () => { state.initializations++; };
    vm.runInContext(declaration('alignToCandles') + '\n' + declaration('buildSubSeries'), scope);
    meta.ready = false;
    return h;
}
function chooseIndicator(h, indicator, meta = h.meta) {
    meta.select.value = indicator;
    h.scope.requestMeta = meta; h.scope.requestIndicator = indicator;
    return vm.runInContext('buildIndicator(requestMeta, requestIndicator)', h.scope);
}
function assertOnlyCurrentSeries(h, indicator, kinds) {
    assertBuildSucceeded(h.state);
    assert.equal(h.meta.indicator, indicator);
    assert.deepEqual(h.state.series.map(item => item.kind), kinds);
    assert.equal(h.meta.addedSeries.length, h.state.series.length);
    h.meta.addedSeries.forEach(item => assert(h.state.series.includes(item), 'Tracked and actual chart series must agree'));
}
function initialBarrier(h) {
    h.scope.panels = [h.meta, {ready: true}, {ready: true}, {ready: true}];
    h.scope.initialPanelsReady = false;
}
const concurrencyCases = [
    {id: 'indicator_keeps_visible_while_loading', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = concurrencyContext(name => name === 'boll' ? gate.promise : Promise.resolve());
        chooseIndicator(h, 'volume'); await flush(); const primary = h.meta.primarySeries;
        chooseIndicator(h, 'boll'); await flush();
        assert.equal(h.meta.primarySeries, primary, 'Loading must not remove the displayed graph before replacement data is ready');
        assert.deepEqual(h.state.series.map(item => item.kind), ['histogram']);
        assert.equal(h.meta.indicator, 'volume'); assert.equal(h.meta.ready, false);
        gate.resolve(); await flush(); assertOnlyCurrentSeries(h, 'boll', ['candlestick', 'line', 'line']);
        evidence.replaced_after_data_ready = true;
    }},
    {id: 'indicator_failed_latest_keeps_visible', kind: 'contract', async run(evidence) {
        const h = concurrencyContext(name => name === 'boll' ? Promise.reject(new Error('current load failed')) : Promise.resolve());
        chooseIndicator(h, 'volume'); await flush(); const primary = h.meta.primarySeries;
        chooseIndicator(h, 'boll'); await flush();
        assert.equal(h.meta.primarySeries, primary); assert.equal(h.meta.indicator, 'volume');
        assert.deepEqual(h.state.series.map(item => item.kind), ['histogram']);
        assert.equal(h.state.errors.length, 1); assert(h.state.errors[0].includes('current load failed'));
        assert.equal(h.meta.ready, true); evidence.existing_graph_retained = true;
    }},
    {id: 'indicator_stale_success_waits_for_latest', kind: 'contract', async run(evidence) {
        const old = deferred(); const latest = deferred();
        const h = concurrencyContext(name => name === 'boll' ? old.promise : latest.promise); initialBarrier(h);
        chooseIndicator(h, 'boll'); chooseIndicator(h, 'rsi'); old.resolve(); await flush();
        assert.equal(h.meta.ready, false, 'An obsolete finally must not mark the current request ready');
        assert.equal(h.state.series.length, 0); assert.equal(h.state.rangeWrites.length, 0);
        assert.equal(h.state.options.length, 0); assert.equal(h.state.initializations, 0);
        assert.equal(h.scope.initialPanelsReady, false);
        latest.resolve(); await flush(); assertOnlyCurrentSeries(h, 'rsi', ['line']);
        assert.equal(h.scope.initialPanelsReady, true);
        assert.equal(h.state.initializations, 0, 'Completing initialization must not reapply the startup window');
        evidence.latest_readiness_without_range_reset = true;
    }},
    {id: 'indicator_stale_failure_has_no_side_effects', kind: 'contract', async run(evidence) {
        const old = deferred(); const latest = deferred();
        const h = concurrencyContext(name => name === 'boll' ? old.promise : latest.promise); initialBarrier(h);
        chooseIndicator(h, 'boll'); chooseIndicator(h, 'rsi'); old.reject(new Error('obsolete load failed')); await flush();
        assert.equal(h.state.errors.length, 0, 'Obsolete failures must not report an error for the current selection');
        assert.equal(h.meta.ready, false); assert.equal(h.state.rangeWrites.length, 0); assert.equal(h.state.initializations, 0);
        latest.resolve(); await flush(); assertOnlyCurrentSeries(h, 'rsi', ['line']);
        evidence.obsolete_failure_ignored = true;
    }},
    {id: 'indicator_failed_latest_blocks_older_success', kind: 'contract', async run(evidence) {
        const old = deferred();
        const h = concurrencyContext(name => name === 'boll' ? old.promise : name === 'rsi' ? Promise.reject(new Error('newest load failed')) : Promise.resolve());
        chooseIndicator(h, 'volume'); await flush(); const primary = h.meta.primarySeries;
        chooseIndicator(h, 'boll'); chooseIndicator(h, 'rsi'); await flush();
        const writes = h.state.rangeWrites.length; old.resolve(); await flush();
        assert.equal(h.meta.indicator, 'volume', 'Failure of the newest selection must not revive an older pending selection');
        assert.equal(h.meta.primarySeries, primary); assert.deepEqual(h.state.series.map(item => item.kind), ['histogram']);
        assert.equal(h.state.errors.length, 1); assert(h.state.errors[0].includes('newest load failed'));
        assert.equal(h.state.rangeWrites.length, writes); evidence.older_request_stayed_invalid = true;
    }},
    {id: 'indicator_repeated_selection_single_commit', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = concurrencyContext(name => name === 'boll' ? gate.promise : Promise.resolve());
        chooseIndicator(h, 'boll'); chooseIndicator(h, 'volume'); await flush(); chooseIndicator(h, 'boll');
        gate.resolve(); await flush(); assertOnlyCurrentSeries(h, 'boll', ['candlestick', 'line', 'line']);
        evidence.same_indicator_round_trip_has_no_duplicate_series = true;
    }},
    {id: 'indicator_panels_independent', kind: 'control', async run(evidence) {
        const gate = deferred(); const h = concurrencyContext(name => name === 'boll' ? gate.promise : Promise.resolve());
        const other = concurrencyContext(); other.meta.idx = 1; h.scope.panels = [h.meta, other.meta];
        chooseIndicator(h, 'boll'); chooseIndicator(h, 'volume', other.meta); await flush();
        const otherPrimary = other.meta.primarySeries; gate.resolve(); await flush();
        assertOnlyCurrentSeries(h, 'boll', ['candlestick', 'line', 'line']);
        assert.equal(other.meta.indicator, 'volume'); assert.equal(other.meta.primarySeries, otherPrimary);
        assert.deepEqual(other.state.series.map(item => item.kind), ['histogram']); evidence.per_panel_generation = true;
    }},
    {id: 'indicator_shared_module_survives_switch', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = concurrencyContext(); const other = concurrencyContext(); other.meta.idx = 1;
        const scope = h.scope; scope.panels = [h.meta, other.meta]; const data = scope.bollData; scope.bollData = [];
        let requests = 0;
        Object.assign(scope, {currentSymbol: 'SAMPLE', currentFrequency: 'freq=1day', currentMarket: 'market=cn', currentAssetClass: 'asset_class=stock', fetch: async (_url, options = {}) => {
            requests++;
            await new Promise((resolve, reject) => {
                if (options.signal?.aborted) { reject(new Error('shared request aborted')); return; }
                options.signal?.addEventListener('abort', () => reject(new Error('shared request aborted')), {once: true});
                gate.promise.then(resolve, reject);
            });
            return {ok: true, json: async () => ({data})};
        }});
        vm.runInContext('const chartModulePromises = {};\n' + declaration('fetchChartModule') + '\n' + declaration('updateIndicatorLookups') + '\n' + declaration('ensureIndicatorData'), scope);
        chooseIndicator(h, 'boll'); chooseIndicator(h, 'boll', other.meta); chooseIndicator(h, 'volume'); await flush();
        gate.resolve(); await flush(); assertOnlyCurrentSeries(h, 'volume', ['histogram']);
        assert.equal(other.meta.indicator, 'boll'); assert.deepEqual(other.state.series.map(item => item.kind), ['candlestick', 'line', 'line']);
        assert.equal(requests, 1, 'A switch in one panel must not cancel or duplicate another panel shared request'); evidence.shared_network_requests = requests;
    }},
    {id: 'indicator_stale_macd_cannot_mutate_volume', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = concurrencyContext(name => name === 'macd' ? gate.promise : Promise.resolve());
        chooseIndicator(h, 'macd'); chooseIndicator(h, 'volume'); await flush();
        const primary = h.meta.primarySeries; const lookup = h.meta.lookup; const label = h.meta.labelRenderer;
        const writes = h.state.rangeWrites.length; const options = h.state.options.length;
        gate.resolve(); await flush(); assertOnlyCurrentSeries(h, 'volume', ['histogram']);
        assert.equal(h.meta.primarySeries, primary); assert.equal(h.meta.lookup, lookup); assert.equal(h.meta.labelRenderer, label);
        assert.equal(h.meta.container.style.height, '120px'); assert.equal(h.state.options.length, options); assert.equal(h.state.rangeWrites.length, writes);
        evidence.height_labels_lookup_and_range_unchanged = true;
    }},
    ...[
        ['indicator_rapid_latest_first', ['rsi', 'boll', 'macd']],
        ['indicator_rapid_latest_last', ['boll', 'macd', 'rsi']],
    ].map(([id, order]) => ({id, kind: 'contract', async run(evidence) {
        const gates = {macd: deferred(), boll: deferred(), rsi: deferred()};
        const h = concurrencyContext(name => gates[name].promise);
        for (const name of ['macd', 'boll', 'rsi']) chooseIndicator(h, name);
        for (const name of order) { gates[name].resolve(); await flush(); }
        assertOnlyCurrentSeries(h, 'rsi', ['line']); evidence.completion_order = order;
    }})),
    {id: 'control_all_indicators_build', kind: 'control', async run(evidence) {
        const h = concurrencyContext();
        const kinds = {volume: ['histogram'], macd: ['histogram', 'line', 'line'], boll: ['candlestick', 'line', 'line'], rsi: ['line']};
        for (const name of Object.keys(kinds)) { chooseIndicator(h, name); await flush(); assertOnlyCurrentSeries(h, name, kinds[name]); }
        evidence.indicators = Object.keys(kinds);
    }},
];


function moduleResponse(data, overrides = {}) {
    return {ok: true, status: 200, json: async () => ({data}), ...overrides};
}
function retryContext(fetcher) {
    const h = concurrencyContext(); const {scope, state, meta} = h;
    const storage = new Map(); state.network = []; state.markers = [];
    Object.assign(scope, {currentSymbol: 'SAMPLE', currentFrequency: 'freq=1day', currentMarket: 'market=cn', currentAssetClass: 'asset_class=stock', chart: meta.chart, showGapsToggle: {checked: false},
        lsGetBool: (key, fallback) => storage.has(key) ? storage.get(key) === '1' : fallback,
        lsSetBool: (key, value) => storage.set(key, value ? '1' : '0'),
        fetch: (url, options) => { const module = new URL(url, 'http://local').searchParams.get('module'); state.network.push(module); return fetcher(module, state.network.length, options); },
        candlestickSeries: {setMarkers: markers => { state.markers = plain(markers); }},
    });
    const line = scope.chart.addLineSeries;
    scope.chart.addLineSeries = options => { const item = line(options); item.options = {...options}; item.applyOptions = next => Object.assign(item.options, next); return item; };
    scope.chart.timeScale().getVisibleRange = () => ({from: '2026-11-20', to: '2026-11-20'});
    scope.bollData = []; scope.rsiData = []; scope.macdData = {lines: [], stats: [], markers: []};
    vm.runInContext('const chartModulePromises = {}; const maSeriesMap = {}; let gapPromise = null; let gapMarkers = []; let gapsData = [];\n' +
        ['createCandleAccess','fetchChartModule','ensureMaSeries','ensureIndicatorData','updateIndicatorLookups','displayGapsWithMarkers','ensureGapMarkers','updateHighLowMarkers'].map(name => declaration(name)).join('\n') + '\nconst candleAccess = createCandleAccess(candleData);\n' + declaration('applyGapVisibility', true), scope);
    return {...h, storage};
}
function requestModule(h, name) { h.scope.requestedModule = name; return vm.runInContext('fetchChartModule(requestedModule)', h.scope); }
const maFixture = [{key: 'MA5', color: '#123', values: [{time: '2026-11-20', value: 1}]}];
const gapFixture = [{trade_datetime: '2026-11-20', position: 'aboveBar', color: '#123', shape: 'arrowUp', text: 'RetryGap'}];
async function failureThenRecovery(first, evidence) {
    let calls = 0;
    const h = retryContext(() => ++calls === 1 ? first() : Promise.resolve(moduleResponse([])));
    let failed = false;
    try { await requestModule(h, 'ma'); } catch (_) { failed = true; }
    assert(failed, 'The malformed or failed response must reject, not poison the successful cache');
    let recovered; let recoveryError = null;
    try { recovered = await requestModule(h, 'ma'); } catch (error) { recoveryError = error.message; }
    Object.assign(evidence, {network_calls: calls, recovery_error: recoveryError});
    assert.equal(recoveryError, null, 'A failed cached request must allow a fresh attempt');
    assert(Array.isArray(recovered.data)); assert.equal(calls, 2);
}
const retryCases = [
    {id: 'retry_http_failure', kind: 'contract', async run(evidence) {
        await failureThenRecovery(() => Promise.resolve(moduleResponse([], {ok: false, status: 503})), evidence);
    }},
    {id: 'retry_outer_json_failure', kind: 'contract', async run(evidence) {
        await failureThenRecovery(() => Promise.resolve(moduleResponse([], {json: async () => { throw new SyntaxError('invalid response JSON'); }})), evidence);
    }},
    {id: 'retry_embedded_json_failure', kind: 'contract', async run(evidence) {
        await failureThenRecovery(() => Promise.resolve(moduleResponse('{invalid module JSON')), evidence);
    }},
    {id: 'retry_invalid_response', kind: 'contract', async run(evidence) {
        for (const payload of [null, {}, {data: {}}, {data: '123'}]) {
            await failureThenRecovery(() => Promise.resolve(moduleResponse([], {json: async () => payload})), evidence);
        }
        let calls = 0;
        const h = retryContext(() => Promise.resolve(moduleResponse(++calls === 1 ? {stats: 'bad'} : {lines: [], stats: [], markers: []})));
        let failed = false; try { await requestModule(h, 'macd'); } catch (_) { failed = true; }
        assert(failed); await requestModule(h, 'macd'); assert.equal(calls, 2); evidence.invalid_shapes = 5;
    }},
    {id: 'retry_sync_fetch_throw', kind: 'contract', async run(evidence) {
        let calls = 0; const h = retryContext(() => { if (++calls === 1) throw new Error('sync fetch failure'); return Promise.resolve(moduleResponse([])); });
        let pending; let synchronous = false;
        try { pending = requestModule(h, 'ma'); } catch (_) { synchronous = true; }
        assert.equal(synchronous, false, 'The request interface must return a rejection, not throw synchronously');
        assert(pending && typeof pending.then === 'function'); await pending.catch(() => {});
        await requestModule(h, 'ma'); assert.equal(calls, 2); evidence.network_calls = calls;
    }},
    {id: 'retry_shared_failure_recovery', kind: 'contract', async run(evidence) {
        const first = deferred(); let calls = 0;
        const h = retryContext(() => ++calls === 1 ? first.promise : Promise.resolve(moduleResponse([])));
        const a = requestModule(h, 'ma'); const b = requestModule(h, 'ma'); assert.equal(a, b);
        first.reject(new Error('shared failure')); const failures = await Promise.allSettled([a, b]);
        assert(failures.every(item => item.status === 'rejected'));
        const c = requestModule(h, 'ma'); const d = requestModule(h, 'ma'); assert.equal(c, d);
        const recovered = await Promise.allSettled([c, d]);
        assert(recovered.every(item => item.status === 'fulfilled'), 'All new callers must share a fresh successful attempt');
        assert.equal(requestModule(h, 'ma'), c); assert.equal(calls, 2);
        evidence.shared_attempts = calls;
    }},
    {id: 'retry_old_failure_keeps_newer_cache', kind: 'control', async run(evidence) {
        const first = deferred(); let calls = 0;
        const h = retryContext(() => ++calls === 1 ? first.promise : Promise.resolve(moduleResponse([])));
        const old = requestModule(h, 'ma'); await flush();
        vm.runInContext('delete chartModulePromises.ma', h.scope);
        const current = requestModule(h, 'ma'); await current;
        first.reject(new Error('old failure')); await old.catch(() => {});
        assert.equal(requestModule(h, 'ma'), current, 'An older rejection must not evict the replacement cache');
        assert.equal(calls, 2); evidence.newer_cache_preserved = true;
    }},
    {id: 'retry_gap_toggle_recovers', kind: 'contract', async run(evidence) {
        const h = retryContext((_name, count) => count === 1 ? Promise.reject(new Error('gap network failure')) : Promise.resolve(moduleResponse(JSON.stringify(gapFixture))));
        h.scope.showGapsToggle.checked = true; vm.runInContext('applyGapVisibility()', h.scope); await flush();
        assert.equal(h.state.errors.length, 1);
        h.scope.showGapsToggle.checked = false; vm.runInContext('applyGapVisibility()', h.scope); await flush();
        h.scope.showGapsToggle.checked = true; vm.runInContext('applyGapVisibility()', h.scope); await flush();
        assert.equal(h.state.network.length, 2); assert(h.state.markers.some(item => item.text === 'RetryGap'));
        h.scope.showGapsToggle.checked = false; vm.runInContext('applyGapVisibility()', h.scope); await flush();
        assert(!h.state.markers.some(item => item.text === 'RetryGap')); assert.equal(h.storage.get('gaps:visible'), '0');
        assert.equal(h.state.network.length, 2); evidence.reopened_without_refresh = true;
    }},
    {id: 'retry_gap_result_respects_switch', kind: 'control', async run(evidence) {
        const gate = deferred(); const h = retryContext(() => gate.promise);
        h.scope.showGapsToggle.checked = true; vm.runInContext('applyGapVisibility()', h.scope); await flush();
        h.scope.showGapsToggle.checked = false; vm.runInContext('applyGapVisibility()', h.scope);
        gate.resolve(moduleResponse(gapFixture)); await flush(); assert(!h.state.markers.some(item => item.text === 'RetryGap'));
        h.scope.showGapsToggle.checked = true; vm.runInContext('applyGapVisibility()', h.scope); await flush();
        assert(h.state.markers.some(item => item.text === 'RetryGap')); assert.equal(h.state.network.length, 1); evidence.latest_switch_respected = true;
    }},
    {id: 'retry_ma_toggle_recovers', kind: 'contract', async run(evidence) {
        const h = retryContext((_name, count) => count === 1 ? Promise.reject(new Error('MA network failure')) : Promise.resolve(moduleResponse(JSON.stringify(maFixture))));
        h.scope.item = maFixture[0]; h.storage.set('ma:MA5', '1'); vm.runInContext('ensureMaSeries(item, true)', h.scope); await flush();
        assert.equal(vm.runInContext('Object.keys(maSeriesMap).length', h.scope), 0);
        h.storage.set('ma:MA5', '0'); vm.runInContext('ensureMaSeries(item, false)', h.scope); await flush();
        assert.equal(h.state.network.length, 1, 'Hiding an unloaded MA must not start a request');
        h.storage.set('ma:MA5', '1'); vm.runInContext('ensureMaSeries(item, true)', h.scope); await flush();
        assert.equal(h.state.network.length, 2); assert.equal(h.state.series.length, 1); assert.equal(h.state.series[0].options.visible, true);
        h.storage.set('ma:MA5', '0'); vm.runInContext('ensureMaSeries(item, false)', h.scope);
        assert.equal(h.state.series[0].options.visible, false); assert.equal(h.state.network.length, 2); evidence.rechecked_without_refresh = true;
    }},
    {id: 'retry_ma_result_respects_switch', kind: 'control', async run(evidence) {
        const gate = deferred(); const h = retryContext(() => gate.promise); h.scope.item = maFixture[0];
        h.storage.set('ma:MA5', '1'); vm.runInContext('ensureMaSeries(item, true)', h.scope); await flush();
        h.storage.set('ma:MA5', '0'); vm.runInContext('ensureMaSeries(item, false)', h.scope);
        gate.resolve(moduleResponse(maFixture)); await flush(); assert.equal(h.state.series.length, 1); assert.equal(h.state.series[0].options.visible, false);
        h.storage.set('ma:MA5', '1'); vm.runInContext('ensureMaSeries(item, true)', h.scope); await flush();
        assert.equal(h.state.series[0].options.visible, true); assert.equal(h.state.network.length, 1); evidence.latest_visibility_respected = true;
    }},
    {id: 'retry_indicators_recover', kind: 'contract', async run(evidence) {
        for (const name of ['boll', 'rsi', 'macd']) {
            const h = retryContext((_module, count) => count === 1 ? Promise.reject(new Error('indicator network failure')) : Promise.resolve(moduleResponse(data)));
            const data = name === 'macd' ? {lines: [], stats: [], markers: []} : [{key: name, color: '#123', values: [{time: '2026-11-20', value: 1}]}];
            chooseIndicator(h, 'volume'); await flush(); chooseIndicator(h, name); await flush();
            assert.equal(h.meta.indicator, 'volume'); assert.equal(h.state.network.length, 1);
            chooseIndicator(h, 'volume'); await flush(); chooseIndicator(h, name); await flush();
            assert.equal(h.meta.indicator, name); assert.equal(h.state.network.length, 2);
            assert.equal(h.state.errors.length, 1);
        }
        evidence.recovered_indicators = ['boll', 'rsi', 'macd'];
    }},
    {id: 'control_empty_success_cached', kind: 'control', async run(evidence) {
        for (const name of ['ma', 'gaps', 'boll', 'rsi', 'macd']) {
            for (const empty of [name === 'macd' ? {lines: [], stats: [], markers: []} : [], null]) {
                const h = retryContext(() => Promise.resolve(moduleResponse(empty)));
                const first = requestModule(h, name); await first;
                assert.equal(requestModule(h, name), first); assert.equal(h.state.network.length, 1);
            }
        }
        for (const data of [{}, {lines: null, stats: null, markers: null}]) {
            const h = retryContext(() => Promise.resolve(moduleResponse(data)));
            chooseIndicator(h, 'macd'); await flush(); chooseIndicator(h, 'volume'); await flush();
            chooseIndicator(h, 'macd'); await flush();
            assert.equal(h.state.errors.length, 0, 'Legacy empty MACD objects must not poison later switching');
            assert.equal(h.meta.indicator, 'macd'); assert.equal(h.state.network.length, 1);
        }
        evidence.successful_empty_and_legacy_null_stay_cached = true;
    }},
    {id: 'control_failed_module_isolated', kind: 'control', async run(evidence) {
        const h = retryContext(name => name === 'ma' ? Promise.reject(new Error('MA failure')) : Promise.resolve(moduleResponse([])));
        const good = requestModule(h, 'rsi'); await good;
        await requestModule(h, 'ma').catch(() => {});
        assert.equal(requestModule(h, 'rsi'), good); assert.equal(h.state.network.filter(name => name === 'rsi').length, 1);
        evidence.other_module_cache_preserved = true;
    }},
    {id: 'control_gap_failure_keeps_replacement', kind: 'control', async run(evidence) {
        const gate = deferred(); const h = retryContext(() => gate.promise);
        const old = vm.runInContext('ensureGapMarkers()', h.scope); await flush();
        const replacement = Promise.resolve([]); h.scope.replacement = replacement; vm.runInContext('gapPromise = replacement', h.scope);
        gate.reject(new Error('obsolete gap failure')); await old.catch(() => {});
        assert.equal(vm.runInContext('gapPromise', h.scope), replacement); evidence.replacement_gap_promise_preserved = true;
    }},
];


function rangeContext(waitForData = async () => {}, options = {}) {
    const h = concurrencyContext(waitForData);
    const others = Array.from({length: 3}, (_, i) => { const item = concurrencyContext(); item.meta.idx = i + 1; return item; });
    const state = {initializations: 0, externalRejections: []};
    const mainState = {range: null, rangeWrites: [], fitCalls: 0};
    function install(chart, model) {
        model.handlers = []; model.fitCalls = 0; model.failSetOnce = false; model.failDataOnce = false;
        const equal = (a, b) => a === b || (a && b && a.from === b.from && a.to === b.to);
        const emit = range => model.handlers.forEach(handler => handler(range ? {...range} : null));
        const assign = range => {
            const changed = !equal(model.range, range);
            if (options.mutable && model.range && range) Object.assign(model.range, range);
            else model.range = range ? {...range} : null;
            if (changed) emit(model.range);
        };
        const scale = {
            getVisibleLogicalRange: () => options.mutable ? model.range : model.range ? {...model.range} : null,
            setVisibleLogicalRange: range => { if (model.failSetOnce) { model.failSetOnce = false; throw new Error('range restore failed'); } model.rangeWrites.push(plain(range)); assign(range); },
            subscribeVisibleLogicalRangeChange: handler => model.handlers.push(handler),
            fitContent: () => { model.fitCalls++; assign({from: 0, to: 999}); },
        };
        chart.timeScale = () => scale;
        model.gesture = range => assign(range);
        model.staleEvent = range => emit(range);
        model.auto = () => assign({from: 0, to: 999});
        const apply = chart.applyOptions;
        chart.applyOptions = value => { if (apply) apply(value); model.auto(); };
        if (chart.removeSeries) {
            const remove = chart.removeSeries;
            chart.removeSeries = item => { remove(item); model.auto(); };
        }
        for (const name of ['addHistogramSeries', 'addCandlestickSeries', 'addLineSeries']) {
            if (!chart[name]) continue;
            const add = chart[name];
            chart[name] = value => {
                const series = add(value); const set = series.setData;
                series.setData = data => { set.call(series, data); model.auto(); if (model.failDataOnce) { model.failDataOnce = false; throw new Error('render failed after range changed'); } };
                return series;
            };
        }
        return chart;
    }
    const main = install({}, mainState);
    install(h.meta.chart, h.state); others.forEach(item => install(item.meta.chart, item.state));
    const metas = [h.meta, ...others.map(item => item.meta)]; metas.forEach(meta => { meta.ready = true; });
    h.scope.chart = main; h.scope.panels = metas; h.scope.initialPanelsReady = options.initialReady !== false;
    h.scope.candleData = Array.from({length: 1000}, (_, i) => ({time: 1700000000 + i * 86400, open: 1, high: 2, low: 1, close: 2}));
    const last = h.scope.candleData.at(-1).time; const values = [{time: last, value: 1}];
    h.scope.volumeData = h.scope.candleData.map(row => ({time: row.time, value: 1}));
    h.scope.bollData.forEach(row => { row.values = values; }); h.scope.rsiData.forEach(row => { row.values = values; });
    h.scope.macdData.lines.forEach(row => { row.values = values; }); h.scope.macdData.stats = [{time: last, macd: 1, color: '#123'}];
    h.scope.resizeMainChart = () => { if (options.mainResize) mainState.auto(); };
    const start = source.indexOf('        const subChartList = panels.map');
    const end = source.indexOf('        function resizeMainChart()', start);
    if (start < 0 || end < start) throw new Error('Original range controller not found');
    const block = source.slice(start, end); const call = block.lastIndexOf('applyInitialLogicalRange();');
    if (call < 0) throw new Error('Original startup range call not found');
    vm.runInContext(block.slice(0, call), h.scope);
    const initial = h.scope.applyInitialLogicalRange;
    h.scope.applyInitialLogicalRange = () => { state.initializations++; return initial(); };
    vm.runInContext('applyInitialLogicalRange()', h.scope);
    const models = [mainState, h.state, ...others.map(item => item.state)];
    const window = range => { mainState.gesture(range); };
    const same = range => models.forEach(model => assert.deepEqual(plain(model.range), range));
    const build = (indicator, meta = h.meta) => {
        const result = chooseIndicator(h, indicator, meta);
        if (result?.catch) result.catch(error => state.externalRejections.push(error.message));
        return result;
    };
    return {...h, others, metas, main, mainState, models, rangeState: state, window, same, build,
        lock: () => vm.runInContext('isSyncingTimeRange', h.scope),
        setLock: value => { h.scope.forcedLock = value; vm.runInContext('isSyncingTimeRange = forcedLock', h.scope); },
    };
}
const rangeCases = [
    {id: 'range_main_is_authority', kind: 'contract', async run(evidence) {
        const h = rangeContext(); h.window({from: 100, to: 150}); h.state.range = {from: 200, to: 250};
        h.build('boll'); await flush(); h.same({from: 100, to: 150}); assert.equal(h.lock(), false);
        evidence.main_view_restored_not_panel_autofit = true;
    }},
    {id: 'range_pan_while_loading_main', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = rangeContext(() => gate.promise); h.window({from: 100, to: 150});
        h.build('boll'); await flush(); h.window({from: 400, to: 460}); gate.resolve(); await flush();
        h.same({from: 400, to: 460}); evidence.latest_window_at_commit = true;
    }},
    {id: 'range_pan_while_loading_sub', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = rangeContext(() => gate.promise); h.window({from: 100, to: 150});
        h.build('boll'); await flush(); h.others[1].state.gesture({from: 310, to: 370}); gate.resolve(); await flush();
        h.same({from: 310, to: 370}); evidence.subchart_user_pan_retained = true;
    }},
    {id: 'range_early_main_pan_preserved', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = rangeContext(() => gate.promise, {initialReady: false});
        h.build('boll'); await flush(); h.window({from: 200, to: 260}); gate.resolve(); await flush();
        h.same({from: 200, to: 260}); assert.equal(h.rangeState.initializations, 1); assert.equal(h.scope.initialPanelsReady, true);
        evidence.late_initial_data_does_not_reapply_default = true;
    }},
    {id: 'range_early_sub_pan_syncs', kind: 'contract', async run(evidence) {
        const gate = deferred(); const h = rangeContext(() => gate.promise, {initialReady: false});
        h.build('boll'); await flush(); h.others[0].state.gesture({from: 220, to: 280});
        h.same({from: 220, to: 280}); gate.resolve(); await flush(); h.same({from: 220, to: 280});
        evidence.main_has_window_before_all_panels_ready = true;
    }},
    {id: 'range_load_failure_keeps_window', kind: 'contract', async run(evidence) {
        const h = rangeContext(() => Promise.reject(new Error('load failed'))); h.window({from: 120, to: 170});
        h.build('boll'); await flush(); h.same({from: 120, to: 170}); assert.equal(h.state.errors.length, 1); assert.equal(h.lock(), false);
        evidence.no_reset_on_load_failure = true;
    }},
    {id: 'range_render_failure_restores_window', kind: 'contract', async run(evidence) {
        const h = rangeContext(); h.window({from: 130, to: 180}); h.state.failDataOnce = true;
        h.build('boll'); await flush(); h.same({from: 130, to: 180}); assert.equal(h.state.errors.length, 1); assert.equal(h.lock(), false);
        evidence.no_reset_on_render_failure = true;
    }},
    {id: 'range_restore_error_releases_sync', kind: 'contract', async run(evidence) {
        const h = rangeContext(); h.window({from: 140, to: 190}); h.others[1].state.failSetOnce = true;
        h.build('boll'); await flush(); assert.equal(h.lock(), false, 'A failed range setter must not deadlock future synchronization');
        h.window({from: 250, to: 300}); h.same({from: 250, to: 300}); evidence.future_pan_still_operates = true;
    }},
    {id: 'range_ignores_delayed_stale_event', kind: 'contract', async run(evidence) {
        const h = rangeContext(); h.window({from: 150, to: 200});
        const writes = h.models.map(model => model.rangeWrites.length);
        h.state.staleEvent({from: 0, to: 999}); h.same({from: 150, to: 200});
        assert.deepEqual(h.models.map(model => model.rangeWrites.length), writes); evidence.obsolete_signal_ignored = true;
    }},
    {id: 'range_snapshot_preserves_exact_values', kind: 'contract', async run(evidence) {
        const h = rangeContext(undefined, {mutable: true, mainResize: true}); const wanted = {from: -12.5, to: 43.75}; h.window(wanted);
        h.build('macd'); await flush(); h.same(wanted); evidence.mutable_api_snapshot_copied_without_rounding = true;
    }},
    {id: 'range_no_window_does_not_force_fit', kind: 'contract', async run(evidence) {
        const fallback = rangeContext(); fallback.window({from: 155, to: 205}); fallback.mainState.range = null;
        fallback.build('boll'); await flush(); fallback.same({from: 155, to: 205});
        const h = rangeContext(); h.models.forEach(model => { model.range = null; model.rangeWrites.length = 0; });
        h.build('volume'); await flush(); assert.equal(h.rangeState.initializations, 1); assert.equal(h.mainState.range, null);
        assert(h.models.every(model => model.fitCalls === 0)); assert.equal(h.lock(), false); evidence.unknown_window_does_not_force_default = true;
    }},
    {id: 'range_initial_default_runs_once', kind: 'contract', async run(evidence) {
        const h = rangeContext(undefined, {initialReady: false}); h.metas.forEach(meta => { meta.ready = false; });
        for (let i = 0; i < h.metas.length; i++) h.build(['volume', 'macd', 'boll', 'rsi'][i], h.metas[i]);
        await flush(); h.same({from: 950, to: 1001}); assert.equal(h.rangeState.initializations, 1);
        assert.equal(h.scope.initialPanelsReady, true); evidence.startup_default_not_reapplied = true;
    }},
    {id: 'range_main_resize_keeps_window', kind: 'contract', async run(evidence) {
        const h = rangeContext(undefined, {mainResize: true}); h.window({from: 160, to: 210});
        h.build('macd'); await flush(); h.same({from: 160, to: 210}); evidence.layout_autorange_did_not_escape = true;
    }},
    {id: 'range_preserves_existing_sync_guard', kind: 'contract', async run(evidence) {
        const h = rangeContext(); h.window({from: 170, to: 220}); h.setLock(true);
        h.build('boll'); await flush(); assert.equal(h.lock(), true); h.same({from: 170, to: 220}); h.setLock(false);
        evidence.preexisting_guard_not_released_by_nested_build = true;
    }},
    {id: 'range_layout_notification_keeps_window', kind: 'contract', async run(evidence) {
        const h = rangeContext(); const frames = []; const notifications = []; h.window({from: 190, to: 240});
        h.scope.chartContainer = {clientWidth: 800, clientHeight: 600, dispatchEvent: event => notifications.push({type: event.type, range: plain(h.mainState.range)})};
        h.scope.Event = class { constructor(type) { this.type = type; } };
        h.scope.requestAnimationFrame = callback => frames.push(callback);
        vm.runInContext(declaration('resizeMainChart'), h.scope);
        h.build('macd'); await flush(); h.same({from: 190, to: 240});
        assert.equal(notifications.length, 0, 'Layout notifications must wait until after chart geometry updates');
        frames.forEach(callback => callback());
        assert.equal(notifications.length, 1); assert.equal(notifications[0].type, 'chartlayoutchange');
        assert.deepEqual(notifications[0].range, {from: 190, to: 240});
        evidence.overlay_layout_updated_without_time_reset = true;
    }},
    {id: 'control_range_user_sync_still_works', kind: 'control', async run(evidence) {
        const h = rangeContext(); h.same({from: 950, to: 1001}); assert.equal(h.rangeState.initializations, 1);
        h.window({from: 180, to: 230}); h.same({from: 180, to: 230});
        h.others[2].state.gesture({from: 280, to: 330}); h.same({from: 280, to: 330});
        assert.equal(h.lock(), false); evidence.main_and_sub_user_pan_sync = true;
    }},
];

const cases = [
    {id: 'module_retry', group: 'module_retry_lifecycle', kind: 'contract', async run(evidence) {
        let calls = 0;
        const scope = context({currentSymbol: 'SAMPLE', currentFrequency: 'freq=1day', currentMarket: 'market=cn', currentAssetClass: 'asset_class=stock', fetch: async () => { calls++; if (calls === 1) throw new Error('Transient network failure'); return {ok: true, json: async () => ({data: '[]'})}; }});
        vm.runInContext('const chartModulePromises = {};\n' + declaration('fetchChartModule'), scope);
        await vm.runInContext("fetchChartModule('ma')", scope).catch(() => {});
        let recovered = false;
        await vm.runInContext("fetchChartModule('ma')", scope).then(() => { recovered = true; }, () => {});
        Object.assign(evidence, {network_calls: calls, recovered});
        assert.equal(recovered, true, 'A failed chart-module request must be retried without a page refresh');
        assert.equal(calls, 2);
    }},
    {id: 'gap_retry', group: 'module_retry_lifecycle', kind: 'contract', async run(evidence) {
        let calls = 0;
        const scope = context({fetchChartModule: async () => { calls++; if (calls === 1) throw new Error('Transient gap failure'); return {data: '[]'}; }, displayGapsWithMarkers() {}, updateHighLowMarkers() {}});
        vm.runInContext('let gapPromise = null; let gapsData = [];\n' + declaration('ensureGapMarkers'), scope);
        await vm.runInContext('ensureGapMarkers()', scope).catch(() => {});
        let recovered = false;
        await vm.runInContext('ensureGapMarkers()', scope).then(() => { recovered = true; }, () => {});
        Object.assign(evidence, {module_calls: calls, recovered});
        assert.equal(recovered, true, 'The extra gap Promise cache must also permit retry');
        assert.equal(calls, 2);
    }},
    {id: 'indicator_latest_wins', group: 'indicator_concurrency', kind: 'contract', async run(evidence) {
        let release;
        const slow = new Promise(resolve => { release = resolve; });
        const {scope, meta, state} = indicatorContext(name => name === 'boll' ? slow : Promise.resolve());
        meta.select.value = 'boll'; vm.runInContext("buildIndicator(meta, 'boll')", scope); await flush();
        meta.select.value = 'volume'; vm.runInContext("buildIndicator(meta, 'volume')", scope); await flush();
        assertBuildSucceeded(state);
        assert.equal(meta.indicator, 'volume', 'Control: the newest selection must build before the delayed response');
        release(); await flush(); assertBuildSucceeded(state);
        Object.assign(evidence, {selected: meta.select.value, displayed: meta.indicator, remaining_series: state.series.map(item => item.kind)});
        assert.equal(meta.indicator, 'volume', 'A delayed BOLL response must not replace the later volume selection');
        assert.deepEqual(state.series.map(item => item.kind), ['histogram']);
    }},
    {id: 'indicator_preserves_range', group: 'viewport_preservation', kind: 'contract', async run(evidence) {
        const {scope, state} = indicatorContext();
        vm.runInContext("buildIndicator(meta, 'volume')", scope); await flush(); assertBuildSucceeded(state);
        Object.assign(evidence, {expected_range: {from: 100, to: 150}, observed_range: plain(state.range)});
        assert.deepEqual(plain(state.range), {from: 100, to: 150}, 'Switching an initialized indicator must preserve the visible range');
    }},
    ...[
        ['storage_bool_read', "lsGetBool('test', false)", false],
        ['storage_string_read', "lsGetString('test', 'fallback')", 'fallback'],
        ['storage_bool_write', "lsSetBool('test', true)", undefined],
        ['storage_string_write', "lsSetString('test', 'value')", undefined],
    ].map(([id, expression, expected]) => ({id, kind: 'contract', async run(evidence) {
        const scope = storageContext(true); let failure = null; let actual;
        try { actual = vm.runInContext(expression, scope); } catch (error) { failure = {name: error.name, message: error.message}; }
        evidence.failure = failure;
        assert.equal(failure, null, 'Unavailable browser storage must not interrupt initialization or interaction');
        assert.equal(actual, expected);
    }})),
    {id: 'realtime_result_keyboard', kind: 'contract', async run(evidence) {
        const element = tag => ({tagName: tag.toUpperCase(), children: [], attrs: {}, listeners: {}, tabIndex: -1, classList: {add() {}}, append(...items) { this.children.push(...items); }, appendChild(item) { this.children.push(item); }, setAttribute(name, value) { this.attrs[name] = String(value); }, addEventListener(name, handler) { this.listeners[name] = handler; }});
        const results = element('div');
        const scope = context({screenerResults: results, document: {createElement: element}, lsGetString: () => '', SCREENER_LAST_CLICKED_KEY: 'last', queueScreenerScrollRestore() {}, window: {location: {assign() {}}}});
        vm.runInContext(declaration('renderScreenerResults', true), scope);
        scope.payload = {count: 1, results: [{code: 'SAMPLE', display_name: 'Sample', asset_class: 'stock', frequencies: ['1day'], url: '/chart?symbol=SAMPLE'}]};
        vm.runInContext('renderScreenerResults(payload)', scope);
        const row = results.children.find(item => item.className === 'screener-result');
        if (!row) throw new Error('Result row not rendered by source function');
        const native = row.tagName === 'BUTTON' || (row.tagName === 'A' && Boolean(row.href || row.attrs.href));
        const accessibleRole = ['link', 'button'].includes(row.attrs.role) && (row.tabIndex >= 0 || Number(row.attrs.tabindex ?? -1) >= 0) && Boolean(row.listeners.keydown || row.listeners.keyup);
        Object.assign(evidence, {tag: row.tagName, attributes: row.attrs, event_types: Object.keys(row.listeners)});
        assert(native || accessibleRole, 'Real-time result rows must be operable without a mouse');
    }},
    {id: 'control_volume_build', kind: 'control', async run(evidence) {
        const {scope, meta, state} = indicatorContext();
        vm.runInContext("buildIndicator(meta, 'volume')", scope); await flush(); assertBuildSucceeded(state);
        assert.equal(meta.indicator, 'volume'); assert.deepEqual(state.series.map(item => item.kind), ['histogram']);
        evidence.displayed = meta.indicator;
    }},
    {id: 'control_shared_request', group: 'module_retry_lifecycle', kind: 'control', async run(evidence) {
        let calls = 0; let release;
        const pending = new Promise(resolve => { release = resolve; });
        const scope = context({currentSymbol: 'SAMPLE', currentFrequency: 'freq=1day', currentMarket: 'market=cn', currentAssetClass: 'asset_class=stock', fetch: async () => { calls++; await pending; return {ok: true, json: async () => ({data: '[]'})}; }});
        vm.runInContext('const chartModulePromises = {};\n' + declaration('fetchChartModule'), scope);
        const first = vm.runInContext("fetchChartModule('ma')", scope); const second = vm.runInContext("fetchChartModule('ma')", scope);
        assert.equal(first, second); release(); await Promise.all([first, second]); assert.equal(calls, 1);
        evidence.network_calls = calls;
    }},
    {id: 'control_available_storage', kind: 'control', async run(evidence) {
        const scope = storageContext(false);
        assert.equal(vm.runInContext("lsGetString('missing', 'fallback')", scope), 'fallback');
        vm.runInContext("lsSetBool('flag', true); lsSetString('name', 'sample');", scope);
        assert.equal(vm.runInContext("lsGetBool('flag', false)", scope), true);
        assert.equal(vm.runInContext("lsGetString('name', '')", scope), 'sample');
        evidence.round_trip = true;
    }},
    {id: 'cache_freshness_observation', kind: 'observation', async run(evidence) {
        const requests = []; const restored = [];
        const options = {dimensions: [], states: []};
        const scope = context({screenerState: {options, filters: {frequency: '1day'}, results: {count: 1, results: [{code: 'FROM_EARLIER_SESSION'}]}}, screenerOptionsReady: false, renderScreenerFilters() {}, renderScreenerResults: (payload, settings) => restored.push({payload, settings}), requestScreener: async url => { requests.push(url); return options; }, saveScreenerState: updates => { scope.screenerState = {...scope.screenerState, ...updates}; }, syncScreenerPresetControls() {}, screenerFilters: {appendChild() {}}, document: {createElement: () => ({})}});
        vm.runInContext(declaration('loadScreenerOptions', true), scope);
        await vm.runInContext('loadScreenerOptions()', scope);
        Object.assign(evidence, {restored_codes: restored.flatMap(item => item.payload.results.map(row => row.code)), request_paths: requests, fresh_query_calls: requests.filter(url => url.endsWith('/query')).length, cache_payload_keys: Object.keys(scope.screenerState.results), note: 'Observation only: expiry/version policy has not been selected; no invented TTL assertion.'});
    }},
];
(async () => {
    const selected = option('--case');
    const group = option('--group');
    const all = [...cases, ...concurrencyCases.map(item => ({...item, group: 'indicator_concurrency'})), ...retryCases.map(item => ({...item, group: 'module_retry_lifecycle'})), ...rangeCases.map(item => ({...item, group: 'viewport_preservation'}))];
    const chosen = all.filter(item => (!selected || item.id === selected) && (!group || item.group === group));
    if (!chosen.length) throw new Error('Unknown case: ' + selected);
    const results = [];
    for (const item of chosen) {
        const evidence = {};
        try { await item.run(evidence); results.push({id: item.id, kind: item.kind, status: item.kind === 'observation' ? 'observed' : 'passed', evidence}); }
        catch (error) { results.push({id: item.id, kind: item.kind, status: error.name === 'AssertionError' ? 'failed' : 'harness_error', message: error.message, evidence}); }
    }
    process.stdout.write(JSON.stringify({template, results}, null, 2) + '\n');
    if (results.some(item => item.status === 'harness_error')) process.exitCode = 2;
    else if (args.includes('--check') && results.some(item => item.status === 'failed')) process.exitCode = 1;
})().catch(error => { console.error(error.stack || error); process.exitCode = 2; });
