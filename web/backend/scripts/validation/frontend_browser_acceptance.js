'use strict';
// Opt-in real Chromium acceptance. Uses a disposable profile and blocks business writes.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); return i < 0 ? fallback : args[i + 1]; };
const output = path.resolve(option('--output', '/tmp/clpainter-browser-acceptance'));
const base = new URL(option('--url', 'http://127.0.0.1:15001'));
const {chromium} = require(option('--playwright', 'playwright'));
const executablePath = option('--chromium', undefined);
const libraries = option('--library-path', undefined);
const candidate = option('--candidate-style', undefined);
const stabilityMs = Number(option('--stability-ms', '45000'));
const selection = option('--case', 'all');
assert(['all', 'layout', 'workspace', 'faults'].includes(selection), 'Unknown browser case');
const chartPath = '/api/v1/test_api/lightweight_charts_demo?symbol=000400SZ&frequency=1day&market=cn&asset_class=stock&screener_mode=realtime';
const chartURL = new URL(chartPath, base).href;
fs.mkdirSync(output, {recursive: true});
const report = {browser: null, layout: [], checks: [], faults: [], network: [], consoleErrors: [], consoleWarnings: [], pageErrors: [], blockedWrites: [], blockedExternal: [], performance: null};
let browser;
function attach(page, faults = false) {
    page.on('pageerror', error => report.pageErrors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') (faults ? report.faults : report.consoleErrors).push(message.text()); else if (['warning', 'warn'].includes(message.type())) (faults ? report.faults : report.consoleWarnings).push(message.text()); });
    page.on('response', response => { if (response.url().startsWith(base.origin)) report.network.push({status: response.status(), path: new URL(response.url()).pathname}); });
}
async function context(options = {}) {
    const value = await browser.newContext({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1, ...options});
    await value.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (['http:', 'https:'].includes(url.protocol) && url.origin !== base.origin) { report.blockedExternal.push(url.origin); return route.abort('blockedbyclient'); }
        if (!['GET', 'HEAD'].includes(request.method()) && url.pathname !== '/api/v1/test_api/stock_screener/query') { report.blockedWrites.push(url.pathname); return route.abort('blockedbyclient'); }
        if (candidate && request.resourceType() === 'document' && url.pathname.endsWith('/lightweight_charts_demo')) {
            const response = await route.fetch(); const raw = fs.readFileSync(candidate, 'utf8');
            const style = raw.match(/<style>[\s\S]*?<\/style>/)[0];
            return route.fulfill({response, body: (await response.text()).replace(/<style>[\s\S]*?<\/style>/, () => style)});
        }
        return route.continue();
    });
    return value;
}
async function open(value, faults = false) {
    const page = await value.newPage(); attach(page, faults);
    const response = await page.goto(chartURL, {waitUntil: 'networkidle', timeout: 60000});
    assert.equal(response.status(), 200); assert.equal(new URL(page.url()).origin, base.origin);
    await page.waitForFunction(() => !document.getElementById('screenerPresetNew').disabled);
    return page;
}
async function geometry(page) {
    return page.evaluate(() => {
        const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return {width: r.width, height: r.height, x: r.x, y: r.y}; };
        return {width: innerWidth, scrollWidth: document.documentElement.scrollWidth, title: rect('h1'), search: rect('.instrument-search'), results: rect('#screenerResults'), filters: rect('#screenerFilters')};
    });
}
async function apply(page) {
    await page.locator('#screenerPresetSelect').selectOption({index: 1});
    let calls = 0;
    const record = request => { if (new URL(request.url()).pathname.endsWith('/stock_screener/query') && request.method() === 'POST') calls++; };
    page.on('request', record);
    const [response] = await Promise.all([page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/stock_screener/query') && r.request().method() === 'POST'), page.locator('#screenerPresetApply').click()]);
    assert.equal(response.status(), 200); const data = await response.json();
    await page.waitForFunction(() => !document.getElementById('screenerRun').disabled);
    assert.equal(calls, 1); assert.equal(await page.locator('#screenerResults .screener-result').count(), data.count);
    page.off('request', record); return data.count;
}
async function draw(page, button, selector) {
    await page.bringToFront();
    const before = await page.locator(selector).count(); await page.locator(button).click();
    const box = await page.locator('#chart').boundingBox();
    await page.mouse.click(box.x + box.width * 0.23, box.y + box.height * 0.35);
    await page.waitForTimeout(700);
    await page.mouse.click(box.x + box.width * 0.63, box.y + box.height * 0.62);
    if (button === '#toolRectangle') await page.waitForFunction(() => document.getElementById('toolRectangleHint').textContent.includes('可继续'));
    else await page.waitForTimeout(100);
    await page.waitForFunction(({selector, before}) => document.querySelectorAll(selector).length > before, {selector, before});
}
async function trace(page) {
    const client = await page.context().newCDPSession(page);
    await client.send('Performance.enable');
    const before = await client.send('Performance.getMetrics');
    await client.send('Tracing.start', {categories: 'devtools.timeline,toplevel,blink.user_timing,disabled-by-default-devtools.timeline.frame', transferMode: 'ReturnAsStream'});
    const box = await page.locator('#chart').boundingBox();
    const started = Date.now(); let cycles = 0;
    while (Date.now() - started < stabilityMs) {
        await page.mouse.move(box.x + 50 + (cycles % 15) * Math.max(8, (box.width - 150) / 15), box.y + box.height * 0.55);
        await page.mouse.wheel(0, cycles % 2 ? -25 : 25);
        if (cycles % 12 === 0) await page.locator('#panelSelect3').selectOption(cycles % 24 ? 'volume' : 'rsi');
        await page.waitForTimeout(90); cycles++;
    }
    const completion = new Promise(resolve => client.once('Tracing.tracingComplete', resolve));
    await client.send('Tracing.end'); const {stream} = await completion;
    let text = '';
    for (;;) { const part = await client.send('IO.read', {handle: stream}); text += part.base64Encoded ? Buffer.from(part.data, 'base64').toString() : part.data; if (part.eof) break; }
    await client.send('IO.close', {handle: stream}); fs.writeFileSync(path.join(output, 'chromium-trace.json'), text);
    const after = await client.send('Performance.getMetrics');
    const convert = item => Object.fromEntries(item.metrics.map(value => [value.name, value.value]));
    const a = convert(before), b = convert(after), events = JSON.parse(text).traceEvents;
    const mainThreads = new Set(events.filter(event => event.name === 'thread_name' && event.args?.name === 'CrRendererMain').map(event => event.pid + ':' + event.tid));
    const tasks = events.filter(event => event.ph === 'X' && ['RunTask', 'ThreadControllerImpl::RunTask'].includes(event.name) && mainThreads.has(event.pid + ':' + event.tid));
    const long = tasks.filter(event => event.dur >= 50000);
    const timing = await page.evaluate(() => ({navigation: performance.getEntriesByType('navigation')[0]?.toJSON(), paints: performance.getEntriesByType('paint').map(item => ({name: item.name, startTime: item.startTime}))}));
    await client.detach();
    return {label: 'Headless Chromium lab data, not field INP/FPS',durationMs: Date.now() - started, cycles, longTasks: long.length, longestTaskMs: Math.max(0, ...tasks.map(item => item.dur / 1000)), taskDurationSeconds: b.TaskDuration - a.TaskDuration, scriptDurationSeconds: b.ScriptDuration - a.ScriptDuration, layoutDurationSeconds: b.LayoutDuration - a.LayoutDuration, heapStartBytes: a.JSHeapUsedSize, heapEndBytes: b.JSHeapUsedSize, nodesStart: a.Nodes, nodesEnd: b.Nodes, timing};
}
(async () => {
    browser = await chromium.launch({headless: true, executablePath, env: {...process.env, ...(libraries ? {LD_LIBRARY_PATH: libraries} : {})}});
    report.browser = browser.version(); report.candidateStyleOnly = Boolean(candidate);
    for (const width of (selection === 'all' || selection === 'layout' ? [1440, 1024, 390, 320] : [])) {
        const value = await context({viewport: {width, height: 1000}, isMobile: width < 500, hasTouch: width < 500}); const page = await open(value);
        const initial = await geometry(page); assert(initial.scrollWidth <= initial.width + 1); assert(initial.title.width >= 100);
        await page.locator('#screenerPresetNew').click(); await page.locator('#screenerPresetName').fill('browser draft - not saved');
        assert(await page.locator('#screenerPresetName').evaluate(element => element === document.activeElement));
        await page.locator('#screenerPresetName').press('Escape'); assert(await page.locator('#screenerPresetCreatePanel').isHidden());
        const count = await apply(page); const queried = await geometry(page);
        if (width < 500) { assert(queried.results.height >= 140); assert(queried.filters.height >= 100); }
        await page.locator('#maTrigger').focus(); await page.locator('#maTrigger').press('ArrowDown');
        assert(await page.evaluate(() => document.querySelector('#maDropdown input[type=checkbox]:not(:disabled)') === document.activeElement));
        await page.keyboard.press('Escape'); assert(await page.locator('#maTrigger').evaluate(element => element === document.activeElement));
        await page.locator('#layerTrigger').focus(); await page.locator('#layerTrigger').press('ArrowDown');
        assert(await page.evaluate(() => document.querySelector('#layerDropdown input[type=checkbox]:not(:disabled)') === document.activeElement));
        await page.keyboard.press('Escape'); assert(await page.locator('#layerTrigger').evaluate(element => element === document.activeElement));
        if (width === 1440) { const tree = await page.accessibility.snapshot(); assert(tree && tree.role === 'WebArea'); fs.writeFileSync(path.join(output, 'accessibility-tree.json'), JSON.stringify(tree, null, 2)); }
        await page.screenshot({path: path.join(output, 'queried-' + width + '.png'), fullPage: true});
        await page.locator('#screenerHistoryTab').click(); await page.waitForFunction(() => !document.getElementById('screenerHistoryRefresh').disabled);
        const versions = await page.locator('#screenerHistoryVersion option').count(); assert(versions <= 5);
        await page.screenshot({path: path.join(output, 'accepted-' + width + '.png'), fullPage: true});
        report.layout.push({width, initial, queried, queryCount: count, historyVersions: versions});
        if (width === 1440) { await page.locator('#screenerRealtimeTab').click(); report.performance = await trace(page); }
        await value.close();
    }
    if (selection === 'all' || selection === 'workspace') {
        const value = await context(); const a = await open(value), b = await open(value);
        await draw(a, '#toolRectangle', '#chart rect[stroke="#00838f"]');
        await b.bringToFront();
        const box = await b.locator('#chart').boundingBox(); await b.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await b.mouse.wheel(0, 40); await b.waitForTimeout(350);
        await b.reload({waitUntil: 'networkidle'}); assert.equal(await b.locator('#chart rect[stroke="#00838f"]').count(), 1);
        await draw(b, '#toolTrend', '#chart line[stroke="#111"]');
        await a.reload({waitUntil: 'networkidle'}); assert.equal(await a.locator('#chart rect[stroke="#00838f"]').count(), 1); assert.equal(await a.locator('#chart line[stroke="#111"]').count(), 1);
        report.checks.push('native multi-tab drawings survive viewport changes and reload'); await value.close();
    }
    if (selection === 'all' || selection === 'faults') {
        const value = await context(); const page = await value.newPage(); attach(page, true);
        await page.route('**/lightweight_charts_module?**', route => new URL(route.request().url()).searchParams.get('module') === 'boll' ? route.fulfill({status: 503, contentType: 'application/json', body: '{"detail":"browser fault probe"}'}) : route.continue());
        await page.goto(chartURL, {waitUntil: 'networkidle'}); await page.locator('#panelRetry1').waitFor({state: 'visible'});
        await page.locator('#panelSelect1').selectOption('volume'); await page.waitForFunction(() => document.getElementById('panelRequestStatus1').hidden);
        await page.locator('#panelSelect1').selectOption('boll'); await page.locator('#panelRetry1').waitFor({state: 'visible'});
        assert.equal(await page.locator('#panelSelect1').inputValue(), 'volume'); assert((await page.locator('#panelRequestMessage1').innerText()).includes('成交量'));
        await page.unroute('**/lightweight_charts_module?**'); await page.locator('#panelRetry1').click(); await page.waitForFunction(() => document.getElementById('panelRequestStatus1').hidden);
        assert.equal(await page.locator('#panelSelect1').inputValue(), 'boll'); report.checks.push('real indicator failure, selector rollback and retry'); await value.close();
    }
    if (selection === 'all' || selection === 'faults') {
        const value = await context(); const page = await open(value, true);
        await page.route('**/stock_screener/query', async route => { await new Promise(resolve => setTimeout(resolve, 900)); try { await route.fulfill({status: 200, contentType: 'application/json', body: '{"count":1,"results":[{"code":"LATE","display_name":"LATE_BROWSER_PROBE","frequencies":["1day"],"url":"/chart"}]}' }); } catch (_) {} });
        await page.locator('#screenerRun').click(); await page.locator('#screenerCancel').waitFor({state: 'visible'}); await page.locator('#screenerCancel').click();
        await page.waitForFunction(() => !document.getElementById('screenerRun').disabled); await page.waitForTimeout(1200);
        assert(!(await page.locator('#screenerResults').innerText()).includes('LATE_BROWSER_PROBE')); assert((await page.locator('#screenerResults').innerText()).includes('取消'));
        report.checks.push('real query cancellation releases controls and rejects late response'); await value.close();
    }
    assert.equal(report.pageErrors.length, 0); assert.equal(report.consoleErrors.length, 0); assert.equal(report.consoleWarnings.length, 0); assert.equal(report.blockedWrites.length, 0); assert.equal(report.blockedExternal.length, 0);
    report.status = 'passed';
})().catch(async error => { report.status = 'failed'; report.error = error.stack || String(error); process.exitCode = 1;
    report.debug = []; if (browser) for (const context of browser.contexts()) for (const page of context.pages()) {
        try { report.debug.push(await page.evaluate(() => ({url: location.href, rectangleHint: document.getElementById('toolRectangleHint')?.textContent, rectangleCount: document.querySelectorAll('#chart rect[stroke="#00838f"]').length, storageWarning: !document.getElementById('browserStorageNotice')?.hidden}))); await page.screenshot({path: path.join(output, 'failure-' + report.debug.length + '.png'), fullPage: true}); } catch (_) {}
    }
}).finally(async () => {
    if (browser) await browser.close(); fs.writeFileSync(path.join(output, 'browser-acceptance.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify({status: report.status, layouts: report.layout.length, checks: report.checks, performance: report.performance, error: report.error}, null, 2));
});
