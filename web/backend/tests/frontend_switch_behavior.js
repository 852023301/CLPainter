'use strict';

const fs = require('fs');
const vm = require('vm');

const templatePath = process.argv[2];
const {readTemplate} = require('./frontend_storage_harness.js');
const html = readTemplate(templatePath);

function stripJinja(source) {
    let output = '';
    let index = 0;
    while (index < source.length) {
        if (source.startsWith('{{', index)) {
            index += 2;
            let depth = 0;
            while (index < source.length) {
                const char = source[index];
                if (char === '{') depth += 1;
                else if (char === '}') {
                    if (depth === 0 && source.startsWith('}}', index)) break;
                    depth = Math.max(0, depth - 1);
                }
                index += 1;
            }
            output += 'null';
            if (source.startsWith('}}', index)) index += 2;
            continue;
        }
        if (source.startsWith('{%', index) || source.startsWith('{#', index)) {
            const closer = source.startsWith('{%', index) ? '%}' : '#}';
            const end = source.indexOf(closer, index + 2);
            if (end < 0) throw new Error('未闭合的模板标记');
            index = end + 2;
            continue;
        }
        output += source[index];
        index += 1;
    }
    return output;
}

function prepareScript(source, frequency, settings = {}) {
    let script = stripJinja(source);
    const replacements = [
        ['const candleData = null;', 'const candleData = ' + JSON.stringify(settings.candles ?? [{time:'2024-01-02',open:10,high:11,low:9,close:10},{time:'2024-01-03',open:10,high:12,low:9,close:11}]) + ';'],
        ['const changeData = null;', 'const changeData = [];'],
        ['const biData = null;', 'const biData = [];'],
        ['const xdData = null;', 'const xdData = [];'],
        ['const zhongshuData = null;', 'const zhongshuData = [];'],
        ['const zhongshuInXianduanData = null;', 'const zhongshuInXianduanData = [];'],
        ['const xianduanZhongshuData = null;', 'const xianduanZhongshuData = [];'],
        ['const xianduanZhongshuAnotherData = null;', 'const xianduanZhongshuAnotherData = [];'],
        ['let gapsData = null;', 'let gapsData = [];'],
        ['const volumeData = null;', 'const volumeData = [];'],
        ['let macdData = null;', 'let macdData = {lines:[],stats:[],markers:[]};'],
        ['let maData = null;', 'let maData = [];'],
        ['let bollData = null;', 'let bollData = [];'],
        ['let rsiData = null;', 'let rsiData = [];'],
        ['const indicatorParams = null;', 'const indicatorParams = {ma:{periods:[5,10]},boll:{n:26,k:2},rsi:{periods:[6,12,24]},macd:{short:12,long:26,mid:9}};'],
        ['const currentPrecision = null;', 'const currentPrecision = 2;'],
        ['const currentSymbol = null;', 'const currentSymbol = ' + JSON.stringify(settings.symbol || 'AAA') + ';'],
        ['const currentFrequency = null;', `const currentFrequency = ${JSON.stringify(frequency)};`],
        ['const currentMarket = null;', 'const currentMarket = ' + JSON.stringify(settings.market || 'market=cn') + ';'],
        ['const currentAssetClass = null;', 'const currentAssetClass = ' + JSON.stringify(settings.assetClass || 'asset_class=stock') + ';'],
        ['window.currentInstrumentId = null;', 'window.currentInstrumentId = 1;'],
    ];
    if (script.includes('const candleData = null;') || (settings.workspaceData && script.includes('const candleData ='))) {
        replacements.forEach(([from, to]) => {
            if (script.includes(from)) script = script.replace(from, to);
            else if (settings.workspaceData) {
                const needle = from.slice(0, from.lastIndexOf('null;'));
                const start = script.indexOf(needle);
                if (start < 0) throw new Error('Missing trusted backend data declaration: ' + from);
                let end = script.indexOf(';', start);
                while (end >= 0) {
                    try { new vm.Script(script.slice(start, end + 1)); break; }
                    catch (error) { if (!(error instanceof SyntaxError)) throw error; end = script.indexOf(';', end + 1); }
                }
                if (end < 0) throw new Error('Incomplete backend data declaration: ' + from);
                script = script.slice(0, start) + to + script.slice(end + 1);
            } else throw new Error('找不到数据占位: ' + from);
        });
    }
    return script;
}

class ElementNode {
    constructor(tag) {
        this.tagName = String(tag || 'div').toUpperCase();
        this.id = '';
        this.className = '';
        this.children = [];
        this.parentNode = null;
        this.attributes = {};
        this.dataset = {};
        this.listeners = {};
        this.type = '';
        this.value = '';
        this.checked = false;
        this.hidden = false;
        this.disabled = false;
        this.draggable = false;
        this.textContent = '';
        this.clientWidth = 800;
        this.clientHeight = 600;
        this.nodeType = 1;
        const styles = {};
        this.style = new Proxy(styles, {
            get: (target, key) => target[key] || '',
            set: (target, key, value) => {
                target[key] = value == null ? '' : String(value);
                return true;
            },
        });
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
        if (name === 'id') this.id = String(value);
        if (name === 'class') this.className = String(value);
        if (name === 'type') this.type = String(value);
        if (name === 'hidden') this.hidden = true;
        if (name === 'disabled') this.disabled = true;
        if (name === 'style') String(value).split(';').forEach(item => {
            const at = item.indexOf(':');
            if (at < 0) return;
            const property = item.slice(0, at).trim().replace(/-([a-z])/g, (_value, letter) => letter.toUpperCase());
            this.style[property] = item.slice(at + 1).trim();
        });
    }

    get firstChild() { return this.children[0] || null; }
    get offsetWidth() { return 120; }
    get offsetHeight() { return 48; }
    get options() { return this.children.filter(child => child.tagName === 'OPTION'); }
    get htmlFor() { return this.getAttribute('for') || ''; }
    set htmlFor(value) { this.attributes['for'] = String(value); }
    get href() { return this.getAttribute('href') || ''; }
    set href(value) { this.attributes.href = String(value); }
    get tabIndex() {
        const explicit = this.getAttribute('tabindex');
        if (explicit !== null) return Number(explicit);
        return ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(this.tagName) || (this.tagName === 'A' && this.href) ? 0 : -1;
    }
    set tabIndex(value) { this.attributes.tabindex = String(value); }
    focus() {
        if (this.disabled) return;
        for (let parent = this; parent; parent = parent.parentNode) if (parent.hidden || parent.style?.display === 'none') return;
        const document = this.ownerDocument, previous = document?.activeElement;
        this.focused = true;
        if (!document || previous === this) return;
        document.activeElement = this;
        if (previous) {
            previous.dispatch('blur', {relatedTarget: this});
            previous.dispatch('focusout', {relatedTarget: this});
        }
        this.dispatch('focus', {relatedTarget: previous});
        this.dispatch('focusin', {relatedTarget: previous});
    }
    get textContent() { return (this._text || '') + this.children.map(child => child.textContent || '').join(''); }
    set textContent(value) { this._text = String(value); this.children = []; }

    getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    }

    appendChild(child) {
        if (child.parentNode) child.parentNode.removeChild(child);
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    append(...children) {
        children.forEach(child => this.appendChild(child));
    }

    removeChild(child) {
        this.children = this.children.filter(item => item !== child);
        child.parentNode = null;
    }

    addEventListener(type, handler) {
        (this.listeners[type] || (this.listeners[type] = [])).push(handler);
    }

    removeEventListener(type, handler) {
        this.listeners[type] = (this.listeners[type] || []).filter(item => item !== handler);
    }

    dispatchEvent(event) { this.dispatch(event.type, event); return true; }

    dispatch(type, event) {
        const current = event?.mockDispatchEvent ? event : Object.assign({
            type, target: this, button: 0, defaultPrevented: false,
            bubbles: !['focus', 'blur'].includes(type), mockDispatchEvent: true,
            preventDefault() { this.defaultPrevented = true; },
            stopPropagation() { this.cancelBubble = true; },
        }, event || {});
        current.currentTarget = this;
        (this.listeners[type] || []).forEach(handler => handler(current));
        if (!current.cancelBubble && current.bubbles && this.parentNode) this.parentNode.dispatch(type, current);
        return current;
    }

    get classList() {
        const element = this;
        const read = () => element.className.split(/\s+/).filter(Boolean);
        return {
            add(...names) {
                const values = new Set(read());
                names.forEach(name => values.add(name));
                element.className = [...values].join(' ');
            },
            remove(...names) {
                const values = new Set(read());
                names.forEach(name => values.delete(name));
                element.className = [...values].join(' ');
            },
            toggle(name, force) {
                const has = read().includes(name);
                const next = force === undefined ? !has : Boolean(force);
                if (next) this.add(name);
                else this.remove(name);
                return next;
            },
            contains(name) {
                return read().includes(name);
            },
        };
    }

    matches(selector) {
        return selector.split(',').some(part => matchesSimple(this, part.trim()));
    }

    closest(selector) {
        let node = this;
        while (node) {
            if (node.matches && node.matches(selector)) return node;
            node = node.parentNode;
        }
        return null;
    }

    contains(node) {
        if (node === this) return true;
        return this.children.some(child => child.contains && child.contains(node));
    }

    querySelectorAll(selector) {
        const found = [];
        const visit = node => {
            node.children.forEach(child => {
                if (child.matches && child.matches(selector)) found.push(child);
                if (child.querySelectorAll) visit(child);
            });
        };
        visit(this);
        return found;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }

    getBoundingClientRect() {
        return {width: this.clientWidth, height: this.clientHeight, top: 0, left: 0, right: this.clientWidth, bottom: this.clientHeight};
    }

    setPointerCapture() {}

    get innerHTML() { return this._html || ''; }

    set innerHTML(value) {
        this._html = String(value);
        this.children = [];
    }
}

function matchesSimple(element, selector) {
    if (!selector) return false;
    if (selector.includes(' ')) {
        const parts = selector.split(/\s+/);
        const last = parts.pop();
        if (!matchesSimple(element, last)) return false;
        const ancestor = parts.join(' ');
        let parent = element.parentNode;
        while (parent) {
            if (parent.matches && parent.matches(ancestor)) return true;
            parent = parent.parentNode;
        }
        return false;
    }
    const attr = selector.match(/^([a-zA-Z0-9]+)?\[([^=]+)=["']?([^"'\]]+)["']?\]$/);
    if (attr) {
        if (attr[1] && element.tagName !== attr[1].toUpperCase()) return false;
        return element.getAttribute(attr[2]) === attr[3] || element[attr[2]] === attr[3];
    }
    return selector.split(/(?=[#.])/).every(token => {
        if (!token) return true;
        if (token.startsWith('#')) return element.id === token.slice(1);
        if (token.startsWith('.')) return element.classList.contains(token.slice(1));
        return element.tagName === token.toUpperCase();
    });
}

function parseHtml(html) {
    const root = new ElementNode('document');
    const stack = [root];
    const pattern = /<\/?([a-zA-Z0-9:-]+)([^>]*)>|<!--[\s\S]*?-->/g;
    let match;
    while ((match = pattern.exec(html))) {
        if (match[0].startsWith('<!--')) continue;
        const tag = match[1].toLowerCase();
        const closing = match[0].startsWith('</');
        const selfClosing = /\/>$/.test(match[0]) || ['input', 'meta', 'link', 'br', 'img'].includes(tag);
        if (closing) {
            while (stack.length > 1 && stack[stack.length - 1].tagName !== tag.toUpperCase()) stack.pop();
            if (stack.length > 1) stack.pop();
            continue;
        }
        const element = new ElementNode(tag);
        const attrs = match[2] || '';
        for (const attr of attrs.matchAll(/([:@\w-]+)(?:="([^"]*)")?/g)) {
            element.setAttribute(attr[1], attr[2] == null ? '' : attr[2]);
        }
        stack[stack.length - 1].appendChild(element);
        if (!selfClosing) stack.push(element);
    }
    return root;
}

function createChart(settings = {}) {
    const chart = {
        series: [],
        _rangeHandlers: [],
        _clickHandlers: [],
        _crosshairHandlers: [],
        _range: null,
        _rangeSets: 0,
    };
    const timeScale = {
        subscribeVisibleLogicalRangeChange(handler) { chart._rangeHandlers.push(handler); },
        subscribeVisibleTimeRangeChange() {},
        getVisibleLogicalRange() { return chart._range ? {...chart._range} : null; },
        getVisibleRange() { return {from: '2024-01-02', to: '2024-01-03'}; },
        setVisibleLogicalRange(range) {
            chart._rangeSets++;
            if (settings.failRestore && settings.chartIndex === 0 && chart._rangeSets === 2) throw new Error('Simulated range restore failure');
            if (chart._range && chart._range.from === range.from && chart._range.to === range.to) return;
            chart._range = {from: range.from, to: range.to};
            chart._rangeHandlers.forEach(handler => handler({...chart._range}));
        },
        coordinateToLogical(x) { const range = chart._range || {from: 0, to: 1}; return range.from + x / 800 * (range.to - range.from); },
        logicalToCoordinate(index) { const range = chart._range || {from: 0, to: 1}; return (index - range.from) / (range.to - range.from) * 800; },
        options() { return {barSpacing: 4}; },
        applyOptions() {},
    };
    chart.timeScale = () => timeScale;
    chart.priceScale = () => ({applyOptions() {}, options() { return {}; }, width: () => 70});
    chart.applyOptions = () => {};
    chart.subscribeClick = handler => chart._clickHandlers.push(handler);
    chart.subscribeCrosshairMove = handler => chart._crosshairHandlers.push(handler);
    chart.setCrosshairPosition = () => {};
    chart.clearCrosshairPosition = () => {};
    chart.emitClick = value => chart._clickHandlers.forEach(handler => handler(value));
    chart.emitCrosshair = value => chart._crosshairHandlers.forEach(handler => handler(value));
    chart.addCandlestickSeries = options => makeSeries(chart, 'candle', options);
    chart.addLineSeries = options => makeSeries(chart, 'line', options);
    chart.addHistogramSeries = options => makeSeries(chart, 'histogram', options);
    return chart;
}

function makeSeries(chart, kind, options) {
    const series = {
        kind,
        options: Object.assign({visible: true}, options || {}),
        data: null,
        markers: null,
        applyOptions(next) { Object.assign(this.options, next); },
        setData(data) { this.data = data; },
        coordinateToPrice: y => 100 - y / 10,
        priceToCoordinate: price => (100 - price) * 10,
        setMarkers(markers) { this.markers = markers; },
        createPriceLine() { return {}; },
        attachPrimitive() {},
        priceScale: chart.priceScale,
    };
    chart.series.push(series);
    return series;
}

function installDom(html) {
    const root = parseHtml(html.replace(/<script[\s\S]*?<\/script>/g, ''));
    const document = {
        documentElement: root,
        body: root.querySelector('body') || root,
        createElement(tag) { const element = new ElementNode(tag); element.ownerDocument = document; return element; },
        createElementNS(_namespace, tag) { const element = new ElementNode(tag); element.ownerDocument = document; return element; },
        createTextNode: text => ({nodeType: 3, textContent: String(text), parentNode: null, contains() { return false; }}),
        getElementById: id => root.querySelector('#' + id),
        querySelector: selector => root.querySelector(selector),
        querySelectorAll: selector => root.querySelectorAll(selector),
        addEventListener(type, handler) { root.addEventListener(type, handler); },
    };
    const attach = element => { element.ownerDocument = document; (element.children || []).forEach(attach); };
    attach(root);
    document.activeElement = document.body;
    return document;
}

async function flush() {
    for (let step = 0; step < 60; step += 1) await Promise.resolve();
}

function checkbox(document, containerId, key) {
    const found = document.getElementById(containerId).querySelectorAll('input').find(item => item.dataset.key === key);
    if (!found) throw new Error(`找不到开关 ${containerId}:${key}`);
    return found;
}

function setChecked(box, checked) {
    box.checked = checked;
    box.dispatch('change', {target: box});
}

async function boot(frequency, storageSeed, storageFault = 'available', settings = {}) {
    const storage = new Map(Object.entries(storageSeed || {}));
    const document = installDom(html);
    const charts = [];
    const windowListeners = {};
    const requests = [];
    const errors = [];
    const writes = [];
    const navigation = [];
    const timers = new Map();
    let nextTimer = 0;
    const storageError = operation => { const error = new Error(operation + ' browser storage failure'); error.name = storageFault === 'quota' ? 'QuotaExceededError' : 'SecurityError'; throw error; };
    const context = {
        console: {...console, log: (...items) => { if (!settings.quiet) console.log(...items); }, error: (...items) => { errors.push(items.map(String).join(" ")); console.error(...items); }},
        document,
        window: {},
        addEventListener(type, handler) { (windowListeners[type] || (windowListeners[type] = [])).push(handler); },
        removeEventListener(type, handler) {
            windowListeners[type] = (windowListeners[type] || []).filter(item => item !== handler);
        },
        location: {search: '', href: 'http://local/demo', assign: value => navigation.push(String(value))},
        localStorage: {
            get length() { return storage.size; },
            key: index => [...storage.keys()][index] ?? null,
            getItem: key => { if (storageFault === 'denied') storageError('read'); return storage.has(key) ? storage.get(key) : null; },
            setItem: (key, value) => { writes.push(key); if (storageFault === 'denied' || storageFault === 'quota') storageError('write'); storage.set(key, String(value)); },
            removeItem: key => { if (storageFault === 'denied' || storageFault === 'delete') storageError('delete'); storage.delete(key); },
        },
        URLSearchParams, AbortController,
        Event: class { constructor(type) { this.type = type; } },
        fetch: async (url, options = {}) => {
            requests.push({url: String(url), method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : null});
            if (settings.beforeResponse) await settings.beforeResponse(url, options);
            return ({
            ok: true,
            status: 200,
            json: async () => {
                const text = String(url);
                const module = new URL(text, "http://local").searchParams.get("module");
                if (text.includes('/watchlists')) return {boards: []};
                if (text.includes('/stock_screener/presets')) return {presets: [{id: 1, name: 'Storage preset', filters: {frequency: '1day', second_point_type: 0}}]};
                if (text.includes('/stock_screener/options')) return {dimensions: [{field: 'frequency', options: [{value: '1day', label: 'Day'}]}], states: [{field: 'second_point_type', options: [{value: 0, label: 'Zero'}]}]};
                if (text.includes('/stock_screener/query')) return {count: 1, results: [{code: 'AAA', display_name: 'StorageProbeResult', asset_class: 'stock', frequencies: ['1day'], url: '/chart?symbol=AAA'}]};
                if (module === 'gaps') {
                    return {data: [{trade_datetime: '2024-01-02', position: 'aboveBar', color: '#111', shape: 'arrowUp', text: '缺口'}]};
                }
                if (module === 'ma') {
                    return {data: [{key: 'MA5', color: '#e11', values: [{time: '2024-01-02', value: 10}, {time: '2024-01-03', value: 11}]}, {key: 'MA10', color: '#19e', values: [{time: '2024-01-02', value: 9}, {time: '2024-01-03', value: 10}]}]};
                }
                if (module === 'macd') return {data: {lines: [], stats: [], markers: []}};
                return {data: []};
            },
        });
        },
        alert() {},
        requestAnimationFrame: fn => fn(),
        setTimeout: fn => { const id = ++nextTimer; timers.set(id, fn); return id; },
        clearTimeout: id => timers.delete(id),
        LightweightCharts: {
            CrosshairMode: {Normal: 0},
            createChart(container) {
                const chart = createChart({...settings, chartIndex: charts.length});
                chart.container = container;
                charts.push(chart);
                return chart;
            },
        },
        NodeFilter: {},
        navigator: {userAgent: 'node'},
    };
    if (storageFault === 'getter') Object.defineProperty(context, 'localStorage', {get() { return storageError('accessor'); }});
    context.window = context;
    context.globalThis = context;
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(require('node:path').join(require('node:path').dirname(templatePath), '../static/js/screener-history.js'), 'utf8'), context);
    scripts.forEach((source, index) => {
        try {
            vm.runInContext(prepareScript(source, frequency, settings), context, {filename: `template-${index}.js`});
        } catch (error) {
            error.message = `模板脚本第 ${index + 1} 段执行失败: ${error.message}`;
            throw error;
        }
    });
    await flush();
    return {document, charts, storage, context, requests, errors, writes, navigation,
        pendingTimers: () => timers.size,
        runTimers() { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(callback => callback()); },
        async fireWindow(type, event = {}) { for (const handler of windowListeners[type] || []) await handler({type, ...event}); },
    };
}

function assert(condition, message) {
    if (!condition) throw new Error(message);
}

if (require.main === module) (async () => {
    if (process.argv[3] === '--storage-probe') {
        const mode = process.argv[4] || 'available';
        const page = await boot('freq=1day', {'ma:MA5': '0', 'gaps:visible': '0', 'screener:mode': 'realtime', 'screener:results-scroll': '99'}, mode);
        assert(page.charts.length === 5, 'Storage failure must not prevent main/subchart creation');
        setChecked(checkbox(page.document, 'maItems', 'MA5'), true); await flush(); await flush();
        const ma = page.charts[0].series.find(series => series.options.color === '#e11');
        assert(ma && ma.options.visible, 'MA must still be usable with unavailable persistence');
        assert(vm.runInContext("lsGetBool('ma:MA5', false)", page.context), 'Current checkbox state must survive in memory');
        setChecked(page.document.getElementById('showGapsToggle'), true); await flush(); await flush();
        const candles = page.charts[0].series.find(series => series.kind === 'candle');
        assert((candles.markers || []).some(item => item.text === '缺口'), 'Gap switch must remain usable');
        const select = page.document.getElementById('screenerPresetSelect'); select.value = '1'; select.dispatch('change');
        const apply = page.document.getElementById('screenerPresetApply');
        assert(!apply.disabled, 'Existing backend presets must remain applicable'); apply.dispatch('click'); await flush(); await flush();
        assert(page.document.getElementById('screenerResults').textContent.includes('StorageProbeResult'), 'Apply/query must not be blocked by failed cache removal');
        const queries = page.requests.filter(request => request.url.includes('/stock_screener/query'));
        assert(queries.length === 1 && queries[0].body.second_point_type === 0, 'Apply must query once with zero preserved');
        assert(vm.runInContext("lsGetString('screener:results-scroll', '')", page.context) === '', 'Failed deletion must not resurrect stale scroll state');
        page.document.getElementById('screenerReset').dispatch('click'); await flush();
        assert(page.document.getElementById('screenerResults').textContent.includes('选择条件后点击确认'), 'Reset must remain usable');
        assert(page.requests.filter(request => request.url.includes('/stock_screener/query')).length === 1, 'Reset must not send an extra query');
        assert(page.errors.length === 0, 'Healthy network plus storage degradation must not cause component errors: ' + page.errors.join('; '));
        console.log(JSON.stringify({mode, charts: page.charts.length, queries: 1, ui_usable: true}));
        return;
    }
    const first = await boot('freq=1day', {'ma:MA5': '1', 'layer:bi': '0', 'gaps:visible': '1'});
    const main = first.charts[0];
    const candle = main.series.find(series => series.kind === 'candle');
    const ma5 = main.series.find(series => series.options.color === '#e11');
    assert(ma5 && ma5.options.visible === true, '已保存的均线在新周期没有自动显示');
    assert(first.storage.get('ma:MA5') === '1', '均线开关没有按共通键保存');
    setChecked(checkbox(first.document, 'maItems', 'MA5'), false);
    await flush();
    assert(ma5.options.visible === false, '取消均线后仍然显示');
    assert(first.storage.get('ma:MA5') === '0', '取消均线没有写入共通存储');

    const bi = main.series.find(series => series.kind === 'line' && series !== ma5 && series.options.color === 'rgba(41, 98, 255, 0.8)');
    assert(bi && bi.options.visible === false, '已关闭的图层在新周期又显示了');
    setChecked(checkbox(first.document, 'layerItems', 'bi'), true);
    assert(bi.options.visible === true, '重新打开图层没有显示');
    assert(first.storage.get('layer:bi') === '1', '图层开关没有按共通键保存');

    const gapMarkers = () => (candle.markers || []).some(marker => marker.text === '缺口');
    assert(gapMarkers(), '已打开的缺口开关在加载后没有画出缺口');
    setChecked(first.document.getElementById('showGapsToggle'), false);
    await flush();
    assert(!gapMarkers(), '关闭缺口后标记还在');
    assert(first.storage.get('gaps:visible') === '0', '缺口开关没有保存');
    const shared = {
        'ma:MA5': first.storage.get('ma:MA5'),
        'layer:bi': first.storage.get('layer:bi'),
        'gaps:visible': first.storage.get('gaps:visible'),
    };
    setChecked(first.document.getElementById('showGapsToggle'), true);
    await flush();
    assert(gapMarkers(), '重新打开缺口后没有标记');

    // 分钟周期尚未交付，跨周期检查使用已经支持的周K。
    const second = await boot('freq=1week', shared);
    const secondMain = second.charts[0];
    const secondMa = secondMain.series.find(series => series.options.color === '#e11');
    const secondBi = secondMain.series.find(series => series.kind === 'line' && series.options.color === 'rgba(41, 98, 255, 0.8)');
    assert(!secondMa, '另一个周期错误地显示了已关闭的均线');
    assert(secondBi && secondBi.options.visible === true, '另一个周期没有沿用图层开关');
    assert(!((secondMain.series.find(series => series.kind === 'candle').markers || []).some(marker => marker.text === '缺口')), '另一个周期错误地显示了已关闭的缺口');

    console.log('缺口、均线、图层开关行为通过');
})().catch(error => {
    console.error(error.stack || error.message);
    process.exit(1);
});

module.exports = {boot, flush};
