'use strict';
const assert = require('node:assert/strict');
const vm = require('node:vm');
const {boot, makeServer, flush} = require('./frontend_screener_presets.js');
const NOW = Date.parse('2026-11-22T02:00:00Z');
const clone = value => JSON.parse(JSON.stringify(value));
const filters = {market: 'cn', asset_class: 'stock', frequency: '1day', scope: 'bi', second_point_type: 0, third_point_type: null};
const result = (changes = {}) => ({count: 1, results: [{code: 'AAA', display_name: 'Cached Alpha', asset_class: 'stock', frequencies: ['1day'], url: '/chart?symbol=AAA'}], data_version: 'version-A', queried_at: new Date(NOW - 1000).toISOString(), ...changes});
function environment() {
    const server = makeServer(), original = server.fetch;
    server.version = 'version-A'; server.versionCalls = 0; server.failVersion = false;
    server.fetch = async (url, config) => {
        if (url.endsWith('/version')) {
            server.versionCalls += 1;
            if (server.holdVersion) { server.holdVersion = false; await new Promise(resolve => server.releaseVersion = resolve); }
            if (server.failVersion) throw new Error('version offline');
            return {ok: true, status: 200, json: async () => ({data_version: server.version})};
        }
        const response = await original(url, config);
        if (url.endsWith('/query') && response.ok) return {...response, json: async () => clone(server.queryPayload || result({queried_at: new Date(NOW).toISOString()}))};
        return response;
    };
    return server;
}
async function page(server, cached, changes = {}) {
    const storage = new Map();
    if (cached !== null) storage.set('screener:state', JSON.stringify({filters, results: cached}));
    storage.set('screener:results-scroll', '40');
    const clock = {now: NOW}; const events = {}, timers = [];
    const value = await boot(server, storage, context => {
        context.Date = class extends Date { static now() { return clock.now; } };
        context.window.addEventListener = (name, fn) => events[name] = fn;
        context.document.visibilityState = changes.hidden ? 'hidden' : 'visible';
        context.document.addEventListener = (name, fn) => events[name] = fn;
        context.window.setInterval = (fn, interval) => { timers.push({fn, interval}); return timers.length; };
    });
    return {...value, clock, events, timers};
}
function names(value) { return value.elements.screenerResults.textContent; }
function queryCount(server) { return server.requests.filter(r => r.url.endsWith('/query')).length; }
async function check(value) { await vm.runInContext('restoreScreenerCache()', value.context); await flush(); }
const cases = [
    ['valid cache is checked before restoring', async () => { const s = environment(); s.holdVersion = true; const p = await page(s, result()); assert(!names(p).includes('Cached Alpha')); assert.equal(s.versionCalls, 1); s.releaseVersion(); await flush(); assert(names(p).includes('Cached Alpha')); assert.equal(queryCount(s), 0); assert.equal(p.elements.screenerResults.scrollTop, 40); assert(p.elements.screenerCacheStatus.textContent.includes('2026')); }],
    ['changed version clears old names and scroll', async () => { const s = environment(); s.version = 'version-B'; const p = await page(s, result()); assert(!names(p).includes('Cached Alpha')); assert(names(p).includes('重新查询')); assert.equal(JSON.parse(p.storage.get('screener:state')).results, null); assert.equal(p.field('second_point_type').value, '0'); assert.equal(p.storage.has('screener:results-scroll'), false); assert.equal(queryCount(s), 0); }],
    ['legacy unversioned cache is never shown', async () => { const s = environment(); const cached = result(); delete cached.data_version; const p = await page(s, cached); assert(!names(p).includes('Cached Alpha')); assert(names(p).includes('重新查询')); assert.equal(queryCount(s), 0); }],
    ['expired cache is rejected without network query', async () => { const s = environment(); const p = await page(s, result({queried_at: new Date(NOW - 5 * 60 * 1000 - 1).toISOString()})); assert(!names(p).includes('Cached Alpha')); assert(names(p).includes('重新查询')); assert.equal(queryCount(s), 0); }],
    ['future or malformed timestamps are not trusted', async () => { for (const timestamp of ['invalid', new Date(NOW + 10 * 60 * 1000).toISOString()]) { const p = await page(environment(), result({queried_at: timestamp})); assert(!names(p).includes('Cached Alpha')); assert(names(p).includes('重新查询')); } }],
    ['metadata failure is not mistaken for an empty result', async () => { const s = environment(); s.failVersion = true; const p = await page(s, result()); assert(!names(p).includes('Cached Alpha')); assert(names(p).includes('无法确认')); assert(!names(p).includes('没有匹配')); assert(!p.elements.screenerRun.disabled); assert.equal(queryCount(s), 0); }],
    ['successful empty result can be restored', async () => { const s = environment(); const p = await page(s, result({count: 0, results: []})); assert.equal(s.versionCalls, 1); assert(names(p).includes('没有匹配')); assert.equal(queryCount(s), 0); }],
    ['late validation cannot replace a new query', async () => { const s = environment(); s.holdVersion = true; const p = await page(s, result()); s.queryPayload = result({results: [{code: 'NEW', display_name: 'New query result', asset_class: 'stock', frequencies: ['1day'], url: '/chart?symbol=NEW'}], data_version: 'version-B', queried_at: new Date(NOW).toISOString()}); await p.elements.screenerRun.click(); assert(names(p).includes('New query result')); s.version = 'version-B'; s.releaseVersion(); await flush(); assert(names(p).includes('New query result')); assert.equal(queryCount(s), 1); }],
    ['reset invalidates a held validation', async () => { const s = environment(); s.holdVersion = true; const p = await page(s, result()); await p.elements.screenerReset.click(); s.releaseVersion(); await flush(); assert(!names(p).includes('Cached Alpha')); assert(names(p).includes('选择条件后点击确认')); assert.equal(queryCount(s), 0); }],
    ['focus and polling invalidate a changed dataset', async () => { const s = environment(); const p = await page(s, result()); assert(names(p).includes('Cached Alpha')); s.version = 'version-B'; await p.events.focus(); await flush(); assert(!names(p).includes('Cached Alpha')); assert.equal(queryCount(s), 0); const s2 = environment(); const p2 = await page(s2, result()); assert(p2.timers.some(item => item.interval === 60000)); s2.version = 'version-B'; await p2.timers[0].fn(); await flush(); assert(!names(p2).includes('Cached Alpha')); }],
    ['background checks are skipped until visible', async () => { const s = environment(); const p = await page(s, result()); const calls = s.versionCalls; p.context.document.visibilityState = 'hidden'; await p.timers[0].fn(); await flush(); assert.equal(s.versionCalls, calls); p.context.document.visibilityState = 'visible'; s.version = 'version-B'; await p.events.visibilitychange(); await flush(); assert(!names(p).includes('Cached Alpha')); }],
    ['expiry on an already open page clears the cache', async () => { const s = environment(); const p = await page(s, result()); p.clock.now += 5 * 60 * 1000 + 1; await check(p); assert(!names(p).includes('Cached Alpha')); assert(names(p).includes('重新查询')); }],
    ['parallel validation requests are deduplicated', async () => { const s = environment(); const p = await page(s, result()); s.holdVersion = true; const first = vm.runInContext('restoreScreenerCache()', p.context); const second = vm.runInContext('restoreScreenerCache()', p.context); await flush(); assert.equal(s.versionCalls, 2); s.releaseVersion(); await Promise.all([first, second]); }],
    ['manual query recovers after invalidation', async () => { const s = environment(); s.version = 'version-B'; const p = await page(s, result()); s.queryPayload = result({data_version: 'version-B', queried_at: new Date(NOW).toISOString()}); await p.elements.screenerRun.click(); assert(names(p).includes('Cached Alpha')); assert.equal(queryCount(s), 1); assert.equal(JSON.parse(p.storage.get('screener:state')).results.data_version, 'version-B'); }],
    ['a failed query cannot resurrect the old cache', async () => { const s = environment(); const p = await page(s, result()); s.failNext = {method: 'POST', status: 503}; await p.elements.screenerRun.click(); assert(names(p).includes('查询失败')); assert(!names(p).includes('Cached Alpha')); assert.equal(JSON.parse(p.storage.get('screener:state')).results, null); }],
];
(async () => {
    const report = [];
    for (const [name, run] of cases) {
        try { await run(); report.push({name, status: 'passed'}); }
        catch (error) { report.push({name, status: 'failed', error: error.stack || String(error)}); }
    }
    console.log(JSON.stringify(report, null, 2));
    if (report.some(item => item.status !== 'passed')) process.exitCode = 1;
})();
