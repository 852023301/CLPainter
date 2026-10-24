'use strict';

const fs = require('fs');
const vm = require('vm');

const templatePath = process.argv[2];
const html = fs.readFileSync(templatePath, 'utf8');

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

function prepareScript(source, frequency) {
    let script = stripJinja(source);
    const replacements = [
        ['const candleData = null;', "const candleData = [{time:'2024-01-02',open:10,high:11,low:9,close:10},{time:'2024-01-03',open:10,high:12,low:9,close:11}];"],
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
        ['const currentSymbol = null;', "const currentSymbol = 'AAA';"],
        ['const currentFrequency = null;', `const currentFrequency = ${JSON.stringify(frequency)};`],
        ['const currentMarket = null;', "const currentMarket = 'market=cn';"],
        ['const currentAssetClass = null;', "const currentAssetClass = 'asset_class=stock';"],
        ['window.currentInstrumentId = null;', 'window.currentInstrumentId = 1;'],
    ];
    if (script.includes('const candleData = null;')) {
        replacements.forEach(([from, to]) => {
            if (!script.includes(from)) throw new Error('找不到数据占位: ' + from);
            script = script.replace(from, to);
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
    }

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

    dispatch(type, event) {
        const current = Object.assign({
            type,
            target: this,
            currentTarget: this,
            preventDefault() {},
            stopPropagation() { this.cancelBubble = true; },
        }, event || {});
        (this.listeners[type] || []).forEach(handler => handler(current));
        if (!current.cancelBubble && this.parentNode) this.parentNode.dispatch(type, current);
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

function createChart() {
    const chart = {
        series: [],
        _rangeHandlers: [],
    };
    const timeScale = {
        subscribeVisibleLogicalRangeChange(handler) { chart._rangeHandlers.push(handler); },
        subscribeVisibleTimeRangeChange() {},
        getVisibleLogicalRange() { return {from: 0, to: 1}; },
        getVisibleRange() { return {from: '2024-01-02', to: '2024-01-03'}; },
        setVisibleLogicalRange() {},
        coordinateToLogical(x) { return x > 100 ? 1 : 0; },
        logicalToCoordinate(index) { return 40 + index * 20; },
        options() { return {barSpacing: 4}; },
        applyOptions() {},
    };
    chart.timeScale = () => timeScale;
    chart.priceScale = () => ({applyOptions() {}, options() { return {}; }, width: () => 70});
    chart.applyOptions = () => {};
    chart.subscribeClick = () => {};
    chart.subscribeCrosshairMove = () => {};
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
        createElement: tag => new ElementNode(tag),
        createElementNS: () => new ElementNode('svg'),
        createTextNode: text => ({nodeType: 3, textContent: String(text), parentNode: null, contains() { return false; }}),
        getElementById: id => root.querySelector('#' + id),
        querySelector: selector => root.querySelector(selector),
        querySelectorAll: selector => root.querySelectorAll(selector),
        addEventListener(type, handler) { root.addEventListener(type, handler); },
    };
    return document;
}

async function flush() {
    for (let step = 0; step < 10; step += 1) await Promise.resolve();
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

async function boot(frequency, storageSeed) {
    const storage = new Map(Object.entries(storageSeed || {}));
    const document = installDom(html);
    const charts = [];
    const windowListeners = {};
    const context = {
        console,
        document,
        window: {},
        addEventListener(type, handler) { (windowListeners[type] || (windowListeners[type] = [])).push(handler); },
        removeEventListener(type, handler) {
            windowListeners[type] = (windowListeners[type] || []).filter(item => item !== handler);
        },
        location: {search: '', href: 'http://local/demo', assign() {}},
        localStorage: {
            getItem: key => storage.has(key) ? storage.get(key) : null,
            setItem: (key, value) => storage.set(key, String(value)),
            removeItem: key => storage.delete(key),
        },
        URLSearchParams,
        fetch: async url => ({
            ok: true,
            status: 200,
            json: async () => {
                const text = String(url);
                if (text.includes('/watchlists')) return {boards: []};
                if (text.includes('module=gaps')) {
                    return {data: [{trade_datetime: '2024-01-02', position: 'aboveBar', color: '#111', shape: 'arrowUp', text: '缺口'}]};
                }
                if (text.includes('module=ma')) {
                    return {data: [{key: 'MA5', color: '#e11', values: [{time: '2024-01-02', value: 10}, {time: '2024-01-03', value: 11}]}, {key: 'MA10', color: '#19e', values: [{time: '2024-01-02', value: 9}, {time: '2024-01-03', value: 10}]}]};
                }
                if (text.includes('module=macd')) return {data: {lines: [], stats: [], markers: []}};
                return {data: []};
            },
        }),
        alert() {},
        requestAnimationFrame: fn => fn(),
        LightweightCharts: {
            CrosshairMode: {Normal: 0},
            createChart(container) {
                const chart = createChart();
                chart.container = container;
                charts.push(chart);
                return chart;
            },
        },
        NodeFilter: {},
        navigator: {userAgent: 'node'},
    };
    context.window = context;
    context.globalThis = context;
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]);
    vm.createContext(context);
    scripts.forEach((source, index) => {
        try {
            vm.runInContext(prepareScript(source, frequency), context, {filename: `template-${index}.js`});
        } catch (error) {
            error.message = `模板脚本第 ${index + 1} 段执行失败: ${error.message}`;
            throw error;
        }
    });
    await flush();
    return {document, charts, storage};
}

function assert(condition, message) {
    if (!condition) throw new Error(message);
}

(async () => {
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
