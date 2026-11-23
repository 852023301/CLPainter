        const maSeriesMap = {};
        const maPeriods = (indicatorParams.ma || {}).periods || [];
        const chartModulePromises = {};

        function fetchChartModule(module) {
            if (!chartModulePromises[module]) {
                const pending = Promise.resolve().then(() => requestJson(
                    `/api/v1/test_api/lightweight_charts_module`
                    + `?symbol=${encodeURIComponent(currentSymbol)}`
                    + `&frequency=${encodeURIComponent(currentFrequency.replace('freq=', ''))}`
                    + `&market=${encodeURIComponent(currentMarket.replace('market=', ''))}`
                    + `&asset_class=${encodeURIComponent(currentAssetClass.replace('asset_class=', ''))}`
                    + `&module=${encodeURIComponent(module)}`
                )).then(payload => {
                    if (!payload || typeof payload !== 'object' || Array.isArray(payload) || !('data' in payload)) {
                        throw new Error('图表模块响应缺少数据');
                    }
                    // 将内嵌 JSON 解码纳入共享请求，解析失败也必须释放失败缓存。
                    let data = typeof payload.data === 'string' ? JSON.parse(payload.data) : payload.data;
                    if (data != null) {
                        const valid = module === 'macd'
                            ? typeof data === 'object' && !Array.isArray(data)
                                && ['lines', 'stats', 'markers'].every(key => data[key] == null || Array.isArray(data[key]))
                            : Array.isArray(data);
                        if (!valid) throw new Error('图表模块数据格式错误');
                        if (module === 'macd') {
                            data = {...data, lines: data.lines || [], stats: data.stats || [], markers: data.markers || []};
                        }
                    }
                    return {...payload, data};
                }).catch(error => {
                    if (chartModulePromises[module] === pending) delete chartModulePromises[module];
                    throw error;
                });
                chartModulePromises[module] = pending;
            }
            return chartModulePromises[module];
        }

        function ensureMaSeries(item, visible) {
            if (!item) return;
            if (maSeriesMap[item.key]) {
                maSeriesMap[item.key].applyOptions({ visible });
                return;
            }
            if (!visible) return;
            fetchChartModule('ma').then(payload => {
                const moduleData = typeof payload.data === 'string' ? JSON.parse(payload.data) : payload.data || [];
                const moduleItem = moduleData.find(data => data.key === item.key);
                if (!moduleItem) return;
                const wanted = lsGetBool('ma:' + moduleItem.key, false);
                if (maSeriesMap[moduleItem.key]) {
                    maSeriesMap[moduleItem.key].applyOptions({ visible: wanted });
                    return;
                }
                const series = chart.addLineSeries({
                    color: moduleItem.color,
                    lineWidth: 1,
                    lastValueVisible: true,
                    priceLineVisible: false,
                    lineStyle: 0,
                    crosshairMarkerVisible: true,
                    visible: wanted,
                });
                series.setData(moduleItem.values);
                maSeriesMap[moduleItem.key] = series;
            }).catch(error => console.error(error));
        }

        // 通用下拉控件: 点击触发器仅展开/收起(不改变显隐); 复选框控制单条显隐; 全选联动
        function setupIndicatorGroup(cfg) {
            const trigger = document.getElementById(cfg.triggerId);
            const dropdown = document.getElementById(cfg.dropdownId);
            const itemsContainer = document.getElementById(cfg.itemsId);
            const selectAll = document.getElementById(cfg.selectAllId);
            const defaultVisible = cfg.defaultVisible !== false;

            const container = trigger.parentNode;
            let opened = false;
            const setOpen = value => {
                opened = value;
                dropdown.hidden = !value;
                dropdown.style.display = value ? 'block' : 'none';
                trigger.setAttribute('aria-expanded', String(value));
            };
            const controls = () => Array.from(dropdown.querySelectorAll('input[type=checkbox]')).filter(box => !box.disabled);
            trigger.addEventListener('click', () => setOpen(!opened));
            trigger.addEventListener('keydown', event => {
                if (event.altKey || event.ctrlKey || event.metaKey || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
                event.preventDefault();
                setOpen(true);
                const list = controls();
                list[event.key === 'ArrowDown' ? 0 : list.length - 1]?.focus();
            });
            container.addEventListener('keydown', event => {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    event.stopPropagation();
                    setOpen(false);
                    trigger.focus();
                    return;
                }
                if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || !opened || !dropdown.contains(event.target)) return;
                if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
                const list = controls();
                if (!list.length) return;
                const index = list.indexOf(event.target);
                const next = event.key === 'Home' ? 0 : event.key === 'End' ? list.length - 1
                    : (index + (event.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length;
                event.preventDefault();
                list[next].focus();
            });
            container.addEventListener('focusout', event => {
                if (!event.relatedTarget || !container.contains(event.relatedTarget)) setOpen(false);
            });
            document.addEventListener('click', event => {
                if (!container.contains(event.target)) setOpen(false);
            });
            setOpen(false);

            const boxes = () => itemsContainer.querySelectorAll('input[type=checkbox]');
            const syncSelectAll = () => {
                const list = Array.from(boxes());
                selectAll.checked = list.length > 0 && list.every(b => b.checked);
                selectAll.indeterminate = list.some(b => b.checked) && !selectAll.checked;
            };

            cfg.data.forEach((item, index) => {
                const visible = lsGetBool(cfg.prefix + item.key, defaultVisible);
                const lbl = document.createElement('label');
                lbl.style.cssText = 'display:block;font-size:13px;padding:2px 0;cursor:pointer;';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.id = cfg.itemsId + '-option-' + index;
                lbl.htmlFor = cb.id;
                cb.checked = visible;
                cb.dataset.key = String(item.key);
                cb.style.cssText = 'margin-right:6px;cursor:pointer;';
                const dot = document.createElement('span');
                dot.setAttribute('aria-hidden', 'true');
                dot.style.cssText = "display:inline-block;width:10px;height:10px;border-radius:50%;background:" + item.color + ";margin-right:6px;vertical-align:middle;";
                lbl.appendChild(cb);
                lbl.appendChild(dot);
                lbl.appendChild(document.createTextNode(item.label));
                itemsContainer.appendChild(lbl);
                if (cfg.seriesMap[item.key]) cfg.seriesMap[item.key].applyOptions({ visible });
                else if (cfg.prefix === 'ma:' && visible) ensureMaSeries(item, true);

                cb.addEventListener('change', () => {
                    lsSetBool(cfg.prefix + item.key, cb.checked);
                    if (cfg.seriesMap[item.key]) cfg.seriesMap[item.key].applyOptions({ visible: cb.checked });
                    else if (cfg.prefix === 'ma:') ensureMaSeries(item, cb.checked);
                    syncSelectAll();
                });
            });

            selectAll.addEventListener('change', () => {
                boxes().forEach(b => {
                    b.checked = selectAll.checked;
                    lsSetBool(cfg.prefix + b.dataset.key, selectAll.checked);
                    if (cfg.seriesMap[b.dataset.key]) cfg.seriesMap[b.dataset.key].applyOptions({ visible: selectAll.checked });
                    else if (cfg.prefix === 'ma:') {
                        const item = cfg.data.find(data => data.key === b.dataset.key);
                        ensureMaSeries(item, selectAll.checked);
                    }
                });
                syncSelectAll();
            });

            syncSelectAll();
            trigger.disabled = cfg.data.length === 0;
        }

        setupIndicatorGroup({
            triggerId: 'maTrigger',
            dropdownId: 'maDropdown',
            itemsId: 'maItems',
            selectAllId: 'maSelectAll',
            data: maPeriods.map((period, index) => ({
                key: `MA${period}`,
                label: `MA${period}`,
                color: `hsl(${(index * 27) % 360},65%,45%)`,
            })),
            seriesMap: maSeriesMap,
            prefix: 'ma:',
            defaultVisible: false,
        });


        // 3. 创建四个可切换指标面板(成交量/MACD/BOLL/RSI), 每个面板左上角有下拉框选择当前指标,
        //    下拉框收起时显示当前指标名(同花顺风格), 选择状态持久化到 localStorage.
        const PRICE_SCALE_WIDTH = 70;  // 统一右侧价格刻度宽度, 保证各面板绘图区等宽、垂直对齐
        // 主图右侧价格刻度也设为相同宽度, 保证主图与各副图绘图区等宽、横向严格对齐(否则副图会整体左移)
        chart.priceScale('right').applyOptions({ minimumWidth: PRICE_SCALE_WIDTH });

        // 时间 -> 数值 查找表(用于跨面板十字光标定位)
        const volumeLookup = {};
        volumeData.forEach(v => { volumeLookup[v.time] = v.value; });
        const volumeColorLookup = {};
        volumeData.forEach(v => { volumeColorLookup[v.time] = v.color; });
        const bollLookup = {};
        candleData.forEach(v => { bollLookup[v.time] = v.close; });
        const rsiLookup = {};
        (rsiData[0] || { values: [] }).values.forEach(v => { rsiLookup[v.time] = v.value; });
        const macdLookup = {};
        const macdStatLookup = {};
        (macdData.stats || []).forEach(s => { macdLookup[s.time] = s.macd; macdStatLookup[s.time] = s; });

        // 将指标序列对齐到完整 K 线时间轴(热身期补空白点), 使子图逻辑索引与主图严格一致,
        // 杜绝副图整体偏移(如 RSI 偏左一个交易日).
        function alignToCandles(values) {
            const map = {};
            values.forEach(v => { map[v.time] = v.value; });
            return candleData.map(c => (c.time in map ? { time: c.time, value: map[c.time] } : { time: c.time }));
        }

        // 创建指标子图(配置与主图一致: 统一 barSpacing/rightOffset/价格刻度宽度;
        // 开启水平十字线, 悬停副图时显示水平影线)
        function createSubChart(container, height) {
            return LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: height,
                layout: { background: { color: '#ffffff' }, textColor: '#333' },
                grid: { vertLines: { visible: false }, horzLines: { visible: false } },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: { width: 1, color: '#758694', style: 2 },
                    horzLine: { width: 1, color: '#758694', style: 2 },
                },
                timeScale: {
                    visible: false, timeVisible: true,
                    rightOffset: 0, barSpacing: 4, minBarSpacing: 0.2,
                    fixLeftEdge: false, fixRightEdge: false,
                    ticksVisible: false, borderVisible: false,
                },
                rightPriceScale: { visible: true, autoScale: true, minimumWidth: PRICE_SCALE_WIDTH },
                leftPriceScale: { visible: false },
                handleScroll: { vertTouchDrag: false },
                localization: { timeFormatter: (time) => formatDateTime(time) },
            });
        }

        // 在子图上渲染多条折线(数据已对齐到 K 线时间轴), 返回 key->series
        function buildSubSeries(subChart, data) {
            const map = {};
            data.forEach(item => {
                const s = subChart.addLineSeries({
                    color: item.color, lineWidth: 1,
                    lastValueVisible: false, priceLineVisible: false,
                    crosshairMarkerVisible: true,
                });
                s.setData(alignToCandles(item.values));
                map[item.key] = s;
            });
            return map;
        }

        // 指标注册表
        const INDICATOR_LABEL = {
            volume: '成交量',
            ma: 'MA(' + indicatorParams.ma.periods.join(',') + ')',
            boll: 'BOLL(' + indicatorParams.boll.n + ',' + indicatorParams.boll.k + ')',
            rsi: 'RSI(' + indicatorParams.rsi.periods.join(',') + ')',
            macd: 'MACD(' + indicatorParams.macd.short + ',' + indicatorParams.macd.long + ',' + indicatorParams.macd.mid + ')',
        };
        const INDICATOR_HEIGHT = { volume: 120, boll: 120, rsi: 120 };
        const INDICATOR_KEYS = ['volume', 'macd', 'boll', 'rsi'];
        const DEFAULT_PANELS = ['macd', 'boll', 'rsi', 'volume'];
        INDICATOR_HEIGHT.macd = 180;
        const panels = [];  // 各面板运行时状态
        let initialPanelsReady = false;

        function updateIndicatorLookups() {
            Object.keys(rsiLookup).forEach(key => delete rsiLookup[key]);
            (rsiData[0] || { values: [] }).values.forEach(v => { rsiLookup[v.time] = v.value; });
            Object.keys(macdLookup).forEach(key => delete macdLookup[key]);
            Object.keys(macdStatLookup).forEach(key => delete macdStatLookup[key]);
            (macdData.stats || []).forEach(s => {
                macdLookup[s.time] = s.macd;
                macdStatLookup[s.time] = s;
            });
        }

        async function ensureIndicatorData(indicator) {
            if (indicator === 'volume') return;
            if (indicator === 'boll' && bollData.length) return;
            if (indicator === 'rsi' && rsiData.length) return;
            if (indicator === 'macd' && macdData.stats.length) return;
            const payload = await fetchChartModule(indicator);
            const moduleData = typeof payload.data === 'string' ? JSON.parse(payload.data) : payload.data;
            if (indicator === 'boll') bollData = moduleData || [];
            else if (indicator === 'rsi') rsiData = moduleData || [];
            else if (indicator === 'macd') macdData = moduleData || { lines: [], stats: [], markers: [] };
            updateIndicatorLookups();
        }

        // 每个面板独立提交最新构建；新数据就绪前保留已显示的系列。
        function buildIndicator(meta, indicator) {
            meta.cancelBuild?.(true);
            const mainTimeScale = chart.timeScale();
            const buildVersion = (meta.buildVersion || 0) + 1;
            meta.buildVersion = buildVersion;
            meta.ready = false;
            const isCurrentBuild = () => meta.buildVersion === buildVersion;
            let cancelled = false, stopWaiting;
            const cancellation = new Promise(resolve => { stopWaiting = () => resolve(false); });
            const label = key => typeof INDICATOR_LABEL === 'object' ? INDICATOR_LABEL[key] || key : key;
            const restoreSelection = () => {
                if (!meta.indicator || !meta.primarySeries) return;
                meta.select.value = meta.indicator;
                if (typeof lsSetString === 'function') lsSetString('panel:v3:' + meta.idx, meta.indicator);
            };
            const status = (phase, error) => {
                if (!isCurrentBuild()) return;
                const returnFocus = typeof document !== 'undefined' && (document.activeElement === meta.cancelButton || document.activeElement === meta.retryButton);
                const visible = meta.indicator && meta.primarySeries ? '当前仍显示' + label(meta.indicator) : '当前没有已加载指标';
                if (phase === 'error' || phase === 'cancelled') restoreSelection();
                if (meta.requestStatus) {
                    meta.requestStatus.hidden = phase === 'success';
                    meta.requestStatus.dataset.error = String(phase === 'error' || phase === 'renderError');
                }
                if (meta.requestMessage) meta.requestMessage.textContent = phase === 'loading'
                    ? '正在加载 ' + label(indicator) + '；' + visible
                    : phase === 'cancelled' ? '已取消 ' + label(indicator) + ' 加载；' + visible
                    : phase === 'renderError' ? label(indicator) + ' 渲染失败：' + error.message + '；请重试'
                    : label(indicator) + ' 加载失败：' + (error?.message || '') + '；' + visible;
                if (meta.retryButton) meta.retryButton.hidden = phase === 'loading' || phase === 'success';
                if (meta.cancelButton) meta.cancelButton.hidden = phase !== 'loading';
                if (returnFocus && phase !== 'loading') meta.select.focus?.();
            };
            meta.cancelBuild = superseded => {
                if (cancelled || meta.ready) return;
                cancelled = true; stopWaiting();
                if (superseded || !isCurrentBuild()) return;
                status('cancelled'); meta.ready = true;
                meta.select.focus?.();
            };
            meta.retryBuild = () => {
                if (!isCurrentBuild()) return;
                meta.select.value = indicator;
                return buildIndicator(meta, indicator);
            };
            status('loading');
            const build = async () => {
            const { chart, container, valueLabel } = meta;
            try {
                const loaded = await Promise.race([Promise.resolve().then(() => ensureIndicatorData(indicator)).then(() => true), cancellation]);
                if (!loaded) return;
            } catch (error) {
                if (isCurrentBuild() && !cancelled) {
                    console.error('指标' + indicator + '加载失败:', error);
                    status('error', error);
                }
                return;
            }
            if (!isCurrentBuild() || cancelled) return;

            // 数据等待期间仍可滚动；提交时读取最新主图范围，并复制数值避免布局修改引用。
            const currentRange = mainTimeScale.getVisibleLogicalRange() || chart.timeScale().getVisibleLogicalRange();
            const visibleRange = currentRange ? {from: currentRange.from, to: currentRange.to} : null;
            const previousSyncState = isSyncingTimeRange;
            isSyncingTimeRange = true;
            try {
                meta.addedSeries.forEach(s => { try { chart.removeSeries(s); } catch (e) {} });
                meta.addedSeries = [];
                meta.primarySeries = null;
                meta.lookup = {};
                meta.labelRenderer = null;
                valueLabel.style.display = 'none';

                const h = INDICATOR_HEIGHT[indicator] || 120;
                chart.applyOptions({ height: h });
                container.style.height = h + 'px';
                resizeMainChart();

                if (indicator === 'volume') {
                    const s = chart.addHistogramSeries({
                        color: '#26a69a', priceFormat: { type: 'volume' },
                        lastValueVisible: false, priceLineVisible: false,
                    });
                    s.setData(volumeData);
                    meta.addedSeries.push(s);
                    meta.primarySeries = s;
                    meta.lookup = volumeLookup;
                    meta.labelRenderer = (t) => {
                        const vl = meta.valueLabel;
                        if (!(t in volumeLookup)) { vl.style.display = 'none'; return; }
                        vl.innerHTML = '成交量: <span style="color:' + (volumeColorLookup[t] || '#333') + ';font-weight:bold">' + formatVolume(volumeLookup[t]) + '</span>';
                        vl.style.display = 'block';
                    };
                } else if (indicator === 'boll') {
                    const cs = chart.addCandlestickSeries({
                        priceFormat: { type: 'price', precision: currentPrecision, minMove: 1 / Math.pow(10, currentPrecision) },
                        upColor: 'rgba(239, 83, 80, 0.5)', downColor: 'rgba(38, 166, 154, 0.5)',
                        borderVisible: false, wickUpColor: 'rgba(239, 83, 80, 0.5)', wickDownColor: 'rgba(38, 166, 154, 0.5)',
                        lastValueVisible: false, priceLineVisible: false,
                    });
                    cs.setData(candleData);
                    meta.addedSeries.push(cs);
                    meta.primarySeries = cs;
                    meta.lookup = bollLookup;
                    const _bollMaps = {};
                    (bollData || []).forEach(it => { const m = {}; (it.values || []).forEach(v => m[v.time] = v.value); _bollMaps[it.key] = m; });
                    const lines = buildSubSeries(chart, bollData);
                    Object.keys(lines).forEach(k => meta.addedSeries.push(lines[k]));
                    meta.labelRenderer = (t) => {
                        const vl = meta.valueLabel;
                        const upM = _bollMaps['BOLL_UP'], dnM = _bollMaps['BOLL_DOWN'];
                        if (!upM || !dnM || !(t in upM) || !(t in dnM)) { vl.style.display = 'none'; return; }
                        const bands = (bollData || []).map(it => { const m = _bollMaps[it.key]; return (m && (t in m)) ? '<span style="color:' + it.color + ';font-weight:bold">' + it.key.replace('BOLL_', '') + ':' + m[t].toFixed(currentPrecision) + '</span>' : null; }).filter(Boolean);
                        const width = upM[t] - dnM[t];
                        vl.innerHTML = (bands.length ? bands.join('  ') + '  ' : '') + '<span style="color:#666;font-weight:bold">通道宽:' + width.toFixed(currentPrecision) + '</span>';
                        vl.style.display = 'block';
                    };
                } else if (indicator === 'rsi') {
                    const lines = buildSubSeries(chart, rsiData);
                    const firstKey = Object.keys(lines)[0];
                    Object.keys(lines).forEach(k => meta.addedSeries.push(lines[k]));
                    const first = lines[firstKey];
                    if (first) {
                        first.createPriceLine({ price: 80, color: 'rgba(120,120,120,0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '80' });
                        first.createPriceLine({ price: 50, color: 'rgba(120,120,120,0.35)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '50' });
                        first.createPriceLine({ price: 20, color: 'rgba(120,120,120,0.45)', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '20' });
                    }
                    meta.primarySeries = first || null;
                    meta.lookup = rsiLookup;
                    const _rsiMaps = {};
                    (rsiData || []).forEach(it => { const m = {}; (it.values || []).forEach(v => m[v.time] = v.value); _rsiMaps[it.key] = m; });
                    meta.labelRenderer = (t) => {
                        const vl = meta.valueLabel;
                        const parts = (rsiData || []).map(it => { const m = _rsiMaps[it.key]; return (m && (t in m)) ? '<span style="color:' + it.color + ';font-weight:bold">' + it.key + ':' + m[t].toFixed(currentPrecision) + '</span>' : null; }).filter(Boolean);
                        if (!parts.length) { vl.style.display = 'none'; return; }
                        vl.innerHTML = parts.join('  ');
                        vl.style.display = 'block';
                    };
                } else if (indicator === 'macd') {
                    const _hist = chart.addHistogramSeries({ priceFormat: { type: 'price', precision: currentPrecision, minMove: 1 / Math.pow(10, currentPrecision) }, lastValueVisible: false, priceLineVisible: false });
                    const _hmap = {};
                    (macdData.stats || []).forEach(s => { _hmap[s.time] = { v: s.macd, c: s.color }; });
                    _hist.setData(candleData.map(k => (k.time in _hmap ? { time: k.time, value: _hmap[k.time].v, color: _hmap[k.time].c } : { time: k.time, value: 0 })));
                    meta.addedSeries.push(_hist);
                    if ((macdData.markers || []).length) _hist.setMarkers(macdData.markers);
                    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.05, bottom: 0.05 } });
                    const _mlines = buildSubSeries(chart, macdData.lines || []);
                    Object.keys(_mlines).forEach(k => meta.addedSeries.push(_mlines[k]));
                    // DIFF/DEA 线也挂同一 provider(见下方 _macdAsp), 与柱子共用同一价格范围。
                    // 范围 = 可见(柱子+DIFF+DEA)极值并强制含0 → 线条始终完整可见, 不再被裁切。
                    // 副图加高到180px 以补偿“含线条后柱子占比变小”的问题。
                    meta.primarySeries = _hist;
                    // ---- MACD 副图: autoscaleInfoProvider(序列级) 范围 = 可见(柱子+DIFF+DEA)极值, 强制含 0 ----
                    // v4.1.0 关键事实(已查 typings): IPriceScaleApi 只有 applyOptions/options/width, 无 setVisiblePriceRange(那是 v5)。
                    //   autoscaleInfoProvider 是【序列选项】, 入参 () => AutoscaleInfo; autoScale 必须为 true 才会调用。
                    // 反转根因: 库默认范围在“全正/全负”窗口不含 0 → 柱子翻转。这里强制 min≤0≤max 根除之。
                    // 线条可见性: 把 DIFF/DEA 极值也纳入范围 → 线条完整显示; 含线条后柱子占比变小, 用 180px 副图补偿。
                    const _lineMaps = {};
                    (macdData.lines || []).forEach(function (ln) { const m = {}; (ln.values || []).forEach(v => { m[v.time] = v.value; }); _lineMaps[ln.key] = m; });
                    function _macdAsp(base) {
                        // base 是【整条序列】的全局极值(库不按可见窗口算), 故忽略它, 自行按可见逻辑范围统计。
                        var lo = 0, hi = 0, have = false;
                        try {
                            var lr = chart.timeScale().getVisibleLogicalRange();
                            if (lr) {
                                var iFrom = Math.max(0, Math.ceil(lr.from));
                                var iTo = Math.min(candleData.length - 1, Math.floor(lr.to));
                                var mn = Infinity, mx = -Infinity;
                                for (var i = iFrom; i <= iTo; i++) {
                                    var t = candleData[i].time;
                                    var hv = _hmap[t];
                                    if (hv) { if (hv.v < mn) mn = hv.v; if (hv.v > mx) mx = hv.v; }
                                    Object.keys(_lineMaps).forEach(function (k) { var v = _lineMaps[k][t]; if (typeof v === 'number') { if (v < mn) mn = v; if (v > mx) mx = v; } });
                                }
                                if (isFinite(mn) && isFinite(mx)) { lo = mn; hi = mx; have = true; }
                            }
                        } catch (e) {}
                        if (!have) { try { var b = (typeof base === 'function') ? base() : base; if (b && typeof b.priceRange === 'object' && b.priceRange) { lo = b.priceRange.minValue; hi = b.priceRange.maxValue; } else if (b && typeof b.minValue === 'number') { lo = b.minValue; hi = b.maxValue; } } catch (e2) {} }
                        if (lo > 0) lo = 0; if (hi < 0) hi = 0;   // 强制含 0 → 杜绝放大反转
                        if (hi - lo < 1e-9) hi = lo + 0.01;
                        return { priceRange: { minValue: lo, maxValue: hi }, margins: { above: 0, below: 0 } };
                    }
                    _hist.applyOptions({ autoscaleInfoProvider: _macdAsp });
                    Object.keys(_mlines).forEach(function (k) { try { _mlines[k].applyOptions({ autoscaleInfoProvider: _macdAsp }); } catch (e) {} });
                                    meta.lookup = macdLookup;
                    meta.labelRenderer = (t) => {
                        const s = macdStatLookup[t]; const vl = meta.valueLabel;
                        if (!s) { vl.style.display = 'none'; return; }
                        const sp = (txt, color) => '<span style="color:' + color + ';font-weight:bold">' + txt + '</span>';
                        const rg = (v) => v >= 0 ? '#ef5350' : '#26a69a';
                        vl.innerHTML = sp('MACD ' + s.macd.toFixed(currentPrecision), rg(s.macd))
                            + '  ' + sp('连增 ' + (s.lianzeng > 0 ? '+' : '') + s.lianzeng, rg(s.lianzeng))
                            + '  ' + sp((s.area >= 0 ? '红柱面积 ' : '绿柱面积 ') + Math.abs(s.area).toFixed(1) + '  平均 ' + Math.abs(s.avg).toFixed(1), rg(s.area))
                            + '  ' + sp('DIFF ' + s.dif.toFixed(currentPrecision), '#ff9800')
                            + '  ' + sp('DEA ' + s.dea.toFixed(currentPrecision), '#5b9bd5');
                        vl.style.display = 'block';
                    };
                }

                meta.indicator = indicator;
                status('success');
                chart.priceScale('right').applyOptions({ minimumWidth: PRICE_SCALE_WIDTH });
            } finally {
                // 先释放本次保护，再用正确范围同步主副图；恢复接口抛错也不能锁死后续操作。
                isSyncingTimeRange = previousSyncState;
                if (visibleRange) {
                    mainTimeScale.setVisibleLogicalRange(visibleRange);
                    chart.timeScale().setVisibleLogicalRange(visibleRange);
                }
            }
            };
            return build()
                .catch(error => {
                    if (isCurrentBuild() && !cancelled) {
                        console.error(`面板${meta.idx + 1}渲染失败:`, error);
                        status('renderError', error);
                    }
                })
                .finally(() => {
                    if (!isCurrentBuild()) return;
                    meta.ready = true;
                    if (!initialPanelsReady && panels.length === 4 && panels.every(panel => panel.ready)) {
                        initialPanelsReady = true;
                    }
                });
        }

        // 初始化一个面板: 创建图表实例、填充下拉选项、绑定切换事件、构建初始指标
        function setupPanel(idx) {
            const container = document.getElementById('panel' + idx);
            const select = document.getElementById('panelSelect' + idx);
            const valueLabel = document.getElementById('panelValue' + idx);
            const subChart = createSubChart(container, INDICATOR_HEIGHT.volume);

            const meta = { idx, container, select, valueLabel, chart: subChart, indicator: null, addedSeries: [], primarySeries: null, lookup: {},
                requestStatus: document.getElementById('panelRequestStatus' + idx), requestMessage: document.getElementById('panelRequestMessage' + idx),
                retryButton: document.getElementById('panelRetry' + idx), cancelButton: document.getElementById('panelCancel' + idx) };
            meta.retryButton.addEventListener('click', event => { event.stopPropagation(); return meta.retryBuild?.(); });
            meta.cancelButton.addEventListener('click', event => { event.stopPropagation(); meta.cancelBuild?.(); });

            INDICATOR_KEYS.forEach(key => {
                const opt = document.createElement('option');
                opt.value = key;
                opt.textContent = INDICATOR_LABEL[key];
                select.appendChild(opt);
            });

            let initKey = lsGetString('panel:v3:' + idx, DEFAULT_PANELS[idx] || 'volume');
            if (!INDICATOR_LABEL[initKey]) initKey = DEFAULT_PANELS[idx] || 'volume';
            select.value = initKey;

            select.addEventListener('change', () => {
                lsSetString('panel:v3:' + idx, select.value);
            buildIndicator(meta, select.value);
            });

            buildIndicator(meta, initKey);
            panels.push(meta);
            return meta;
        }

        for (let i = 0; i < 4; i++) setupPanel(i);