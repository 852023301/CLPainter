    const screenerPanel = document.getElementById('screenerPanel');
    const screenerFilters = document.getElementById('screenerFilters');
    const screenerRun = document.getElementById('screenerRun');
    const screenerCancel = document.getElementById('screenerCancel');
    let screenerQueryController = null;
    const screenerReset = document.getElementById('screenerReset');
    const screenerResults = document.getElementById('screenerResults');
    const screenerCacheStatus = document.getElementById('screenerCacheStatus');
    const screenerCollapse = document.getElementById('screenerCollapse');
    const screenerExpand = document.getElementById('screenerExpand');
    const screenerResizer = document.getElementById('screenerResizer');
    const screenerPresetSelect = document.getElementById('screenerPresetSelect');
    const screenerPresetName = document.getElementById('screenerPresetName');
    const screenerPresetNew = document.getElementById('screenerPresetNew');
    const screenerPresetCreatePanel = document.getElementById('screenerPresetCreatePanel');
    const screenerPresetCancel = document.getElementById('screenerPresetCancel');
    const screenerPresetSave = document.getElementById('screenerPresetSave');
    const screenerPresetApply = document.getElementById('screenerPresetApply');
    const screenerPresetUpdate = document.getElementById('screenerPresetUpdate');
    const screenerPresetDelete = document.getElementById('screenerPresetDelete');
    const screenerPresetStatus = document.getElementById('screenerPresetStatus');
    const screenerPresetRetry = document.getElementById('screenerPresetRetry');
    let screenerPresets = [];
    let screenerPresetsLoaded = false;
    let screenerOptionsReady = false;
    let screenerPresetBusy = false;
    let screenerQueryBusy = false;
    let screenerResize = null;
    const SCREENER_STATE_KEY = 'screener:state';
    const SCREENER_CACHE_MAX_AGE_MS = 5 * 60 * 1000;
    let screenerCacheEpoch = 0;
    let screenerCacheRequest = null;
    let displayedScreenerCache = null;
    // 点击结果跳转前记录滚动位置，目标页渲染选股结果后一次性恢复
    const SCREENER_SCROLL_KEY = 'screener:results-scroll';
    // 记录最后点击的标的，跳转后继续在选股结果中标记
    const SCREENER_LAST_CLICKED_KEY = 'screener:last-clicked';
    let pendingScreenerScroll = null;
    const SCREENER_DEFAULTS = {
        market: 'cn',
        asset_class: 'stock',
        frequency: '1day',
        scope: 'bi',
    };
    const readScreenerState = () => {
        try {
            return JSON.parse(lsGetString(SCREENER_STATE_KEY, '')) || null;
        } catch (_) {
            return null;
        }
    };
    let screenerState = readScreenerState();
    const saveScreenerState = updates => {
        try {
            screenerState = {...screenerState, ...updates};
            lsSetString(SCREENER_STATE_KEY, JSON.stringify(screenerState));
        } catch (_) {}
    };
    const scheduleScreenerScrollRestore = () => {
        if (pendingScreenerScroll == null || appShell.classList.contains('screener-collapsed')) return;
        const target = pendingScreenerScroll;
        pendingScreenerScroll = null;
        requestAnimationFrame(() => requestAnimationFrame(() => {
            screenerResults.scrollTop = target;
        }));
    };
    const queueScreenerScrollRestore = () => {
        const saved = Number(lsGetString(SCREENER_SCROLL_KEY, ''));
        lsRemove(SCREENER_SCROLL_KEY);
        if (!Number.isFinite(saved) || saved <= 0) return;
        pendingScreenerScroll = saved;
        scheduleScreenerScrollRestore();
    };
    appShell.classList.toggle('screener-collapsed', lsGetBool('screener:collapsed', false));
    const savedScreenerWidth = Number(lsGetString('screener:width', ''));
    if (savedScreenerWidth >= 220) {
        appShell.style.setProperty('--screener-width', Math.round(savedScreenerWidth) + 'px');
    }

    const requestScreener = (url, options = {}) => requestJson(url, options);

    const renderScreenerField = (item, kind) => {
        const field = document.createElement('div');
        field.className = 'screener-field';
        const label = document.createElement('label');
        label.textContent = item.label;
        const select = document.createElement('select');
        select.id = 'screener-filter-' + kind + '-' + item.field;
        label.htmlFor = select.id;
        select.dataset.field = item.field;
        select.dataset.kind = kind;
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = '不限';
        select.appendChild(empty);
        const options = [...(item.options || [])];
        if (item.field === 'frequency') {
            const frequencyOrder = ['1day', '1week', '1month', '1quarter', '1year'];
            const rank = value => {
                const index = frequencyOrder.indexOf(value);
                return index < 0 ? frequencyOrder.length : index;
            };
            options.sort((a, b) => rank(a.value) - rank(b.value));
        }
        options.forEach(option => {
            const node = document.createElement('option');
            node.value = String(option.value);
            node.textContent = option.label;
            select.appendChild(node);
        });
        field.append(label, select);
        return field;
    };

    const renderScreenerFilters = payload => {
        screenerFilters.textContent = '';
        [...(payload.dimensions || []), ...(payload.states || [])].forEach(item => {
            const kind = (payload.dimensions || []).includes(item) ? 'dimension' : 'state';
            screenerFilters.appendChild(renderScreenerField(item, kind));
        });
        const desired = {...SCREENER_DEFAULTS, ...(screenerState?.filters || {})};
        screenerFilters.querySelectorAll('select').forEach(select => {
            const value = desired[select.dataset.field];
            if (value == null) return;
            const stringValue = String(value);
            if ([...select.options].some(option => option.value === stringValue)) {
                select.value = stringValue;
            }
        });
    };

    const setScreenerCacheStatus = message => {
        screenerCacheStatus.textContent = message;
        screenerCacheStatus.hidden = !message;
    };
    const showScreenerCacheMessage = message => {
        screenerResults.textContent = '';
        const empty = document.createElement('div');
        empty.className = 'screener-empty';
        empty.textContent = message;
        screenerResults.appendChild(empty);
    };
    const cacheableScreenerResult = payload => {
        if (!payload || !Array.isArray(payload.results) || !Number.isInteger(payload.count)
            || payload.count !== payload.results.length || typeof payload.data_version !== 'string'
            || !payload.data_version.trim() || typeof payload.queried_at !== 'string') return false;
        const age = Date.now() - Date.parse(payload.queried_at);
        return Number.isFinite(age) && age >= -60000 && age < SCREENER_CACHE_MAX_AGE_MS;
    };
    const cancelScreenerCacheCheck = () => {
        screenerCacheEpoch += 1;
        screenerCacheRequest = null;
        displayedScreenerCache = null;
    };
    const discardScreenerCache = message => {
        const returnFocus = typeof screenerResults.contains === 'function' && screenerResults.contains(document.activeElement);
        cancelScreenerCacheCheck();
        saveScreenerState({results: null});
        pendingScreenerScroll = null;
        lsRemove(SCREENER_SCROLL_KEY);
        lsRemove(SCREENER_LAST_CLICKED_KEY);
        showScreenerCacheMessage(message);
        setScreenerCacheStatus(message);
        screenerResults.scrollTop = 0;
        if (returnFocus && !screenerRun.disabled) screenerRun.focus();
    };
    const restoreScreenerCache = () => {
        const cached = screenerState?.results;
        if (!cached || !screenerOptionsReady || screenerQueryBusy) return;
        if (!cacheableScreenerResult(cached)) {
            discardScreenerCache('上次选股结果已过期或缺少有效版本，请点击确认重新查询');
            return;
        }
        if (screenerCacheRequest?.cached === cached) return screenerCacheRequest.promise;
        const check = {cached, epoch: screenerCacheEpoch};
        screenerCacheRequest = check;
        if (displayedScreenerCache !== cached) showScreenerCacheMessage('正在核验上次选股结果，请稍候');
        setScreenerCacheStatus('正在核验选股数据版本…');
        const current = () => check.epoch === screenerCacheEpoch && screenerState?.results === cached && !screenerQueryBusy;
        check.promise = (async () => {
            try {
                const metadata = await requestScreener('/api/v1/test_api/stock_screener/version', {cache: 'no-store'});
                if (!current()) return;
                if (typeof metadata?.data_version !== 'string' || !metadata.data_version.trim()) throw new Error('无效版本响应');
                if (metadata.data_version !== cached.data_version) {
                    discardScreenerCache('选股数据已更新，上次结果已失效，请点击确认重新查询');
                    return;
                }
                if (!cacheableScreenerResult(cached)) {
                    discardScreenerCache('上次选股结果已过期，请点击确认重新查询');
                    return;
                }
                if (displayedScreenerCache !== cached) {
                    renderScreenerResults(screenerState.results, {restoreScroll: true});
                    displayedScreenerCache = cached;
                }
                setScreenerCacheStatus('查询时间：' + new Date(cached.queried_at).toLocaleString('zh-CN', {hour12: false}) + '；数据版本已核对');
            } catch (_) {
                if (current()) discardScreenerCache('暂时无法确认选股数据版本，请点击确认重新查询');
            } finally {
                if (screenerCacheRequest === check) screenerCacheRequest = null;
            }
        })();
        return check.promise;
    };

    const loadScreenerOptions = async () => {
        if (screenerState?.options) renderScreenerFilters(screenerState.options);
        if (screenerState?.results) showScreenerCacheMessage('正在核验上次选股结果，请稍候');
        try {
            const payload = await requestScreener('/api/v1/test_api/stock_screener/options', {cache: 'no-store'});
            const optionsChanged = JSON.stringify(payload) !== JSON.stringify(screenerState?.options);
            saveScreenerState({options: payload});
            if (optionsChanged) renderScreenerFilters(payload);
            screenerOptionsReady = true;
            syncScreenerPresetControls();
            await restoreScreenerCache();
        } catch (error) {
            screenerOptionsReady = false;
            screenerFilters.textContent = '';
            const message = document.createElement('div');
            message.className = 'screener-empty';
            message.textContent = '选股选项加载失败: ' + error.message;
            screenerFilters.appendChild(message);
            if (screenerState?.results) discardScreenerCache('暂时无法确认选股数据版本，请点击确认重新查询');
        } finally {
            syncScreenerPresetControls();
        }
    };

    const renderScreenerPlaceholder = () => {
        screenerResults.textContent = '';
        const empty = document.createElement('div');
        empty.className = 'screener-empty';
        empty.textContent = '选择条件后点击确认';
        screenerResults.appendChild(empty);
        screenerResults.scrollTop = 0;
    };

    const renderScreenerResults = (payload, {restoreScroll = false} = {}) => {
        screenerResults.textContent = '';
        const results = payload.results || [];
        if (!results.length) {
            const empty = document.createElement('div');
            empty.className = 'screener-empty';
            empty.textContent = '没有匹配的标的';
            screenerResults.appendChild(empty);
            return;
        }
        const count = document.createElement('div');
        count.className = 'screener-empty';
        count.textContent = `共 ${payload.count || results.length} 个标的`;
        screenerResults.appendChild(count);
        const lastClickedCode = lsGetString(SCREENER_LAST_CLICKED_KEY, '');
        results.forEach((item, index) => {
            const row = document.createElement('a');
            row.href = item.url;
            row.setAttribute('aria-label', '查看' + item.display_name + ' ' + item.code + '的K线与指标');
            row.className = 'screener-result';
            row.title = `${item.code} · ${item.asset_class} · ${item.frequencies.join(', ')}`;
            const isLatest = Boolean(lastClickedCode) && item.code === lastClickedCode;
            if (isLatest) {
                row.classList.add('screener-result-latest');
                row.setAttribute('aria-current', 'true');
            }
            const sequence = document.createElement('span');
            sequence.className = 'screener-result-index';
            sequence.textContent = String(index + 1);
            const name = document.createElement('span');
            name.className = 'screener-result-name';
            name.textContent = item.display_name;
            const meta = document.createElement('span');
            meta.className = 'screener-result-meta';
            meta.textContent = item.code;
            row.append(sequence, name);
            if (isLatest) {
                const latestTag = document.createElement('span');
                latestTag.className = 'screener-result-latest-tag';
                latestTag.textContent = '最近';
                row.appendChild(latestTag);
            }
            row.appendChild(meta);
            row.addEventListener('click', event => {
                if (event.defaultPrevented || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                lsSetString(SCREENER_SCROLL_KEY, String(screenerResults.scrollTop));
                lsSetString(SCREENER_LAST_CLICKED_KEY, item.code);
                row.classList.add('screener-result-latest');
                window.location.assign(item.url);
            });
            screenerResults.appendChild(row);
        });
        if (restoreScroll) queueScreenerScrollRestore();
    };

    // null 明确表示不限，不能因缺字段在刷新时被默认值覆盖；0 是有效状态。
    const collectScreenerFilters = () => Object.fromEntries(
        [...screenerFilters.querySelectorAll('select')].map(select => [
            select.dataset.field,
            select.value === '' ? null : select.dataset.kind === 'state' ? Number(select.value) : select.value,
        ])
    );
    const selectedScreenerPreset = () => screenerPresets.find(
        preset => String(preset.id) === screenerPresetSelect.value
    );
    const showScreenerPresetStatus = (message, error = false) => {
        screenerPresetStatus.textContent = message;
        screenerPresetStatus.dataset.error = String(error);
    };
    const syncScreenerPresetControls = () => {
        const busy = screenerPresetBusy || screenerQueryBusy;
        const selected = Boolean(selectedScreenerPreset());
        const writable = !busy && screenerPresetsLoaded && screenerOptionsReady;
        const creating = !screenerPresetCreatePanel.hidden;
        screenerPresetSelect.disabled = busy || !screenerPresetsLoaded || creating;
        screenerPresetNew.disabled = !writable || creating;
        screenerPresetName.disabled = !writable || !creating;
        screenerPresetSave.disabled = !writable || !creating;
        screenerPresetCancel.disabled = busy;
        screenerPresetApply.disabled = !writable || !selected || creating;
        screenerPresetUpdate.disabled = !writable || !selected || creating;
        screenerPresetDelete.disabled = busy || !screenerPresetsLoaded || !selected || creating;
        screenerPresetRetry.disabled = busy;
        screenerRun.disabled = busy || !screenerOptionsReady;
        screenerReset.disabled = busy || !screenerOptionsReady;
    };
    const setScreenerPresetCreateOpen = open => {
        screenerPresetCreatePanel.hidden = !open;
        screenerPresetNew.setAttribute('aria-expanded', String(open));
        if (!open) screenerPresetName.value = '';
        syncScreenerPresetControls();
    };
    const cancelScreenerPresetCreate = () => {
        if (screenerPresetBusy || screenerQueryBusy) return;
        setScreenerPresetCreateOpen(false);
        showScreenerPresetStatus('已取消新增，当前筛选条件保持不变');
        screenerPresetNew.focus();
    };
    const renderScreenerPresets = (selectedId = '') => {
        screenerPresetSelect.textContent = '';
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = '选择已保存方案';
        screenerPresetSelect.appendChild(empty);
        screenerPresets.forEach(preset => {
            const option = document.createElement('option');
            option.value = String(preset.id);
            option.textContent = preset.name;
            screenerPresetSelect.appendChild(option);
        });
        screenerPresetSelect.value = String(selectedId);
    };
    const loadScreenerPresets = async () => {
        if (screenerPresetBusy || screenerQueryBusy) return;
        screenerPresetBusy = true;
        syncScreenerPresetControls();
        showScreenerPresetStatus('方案加载中...');
        try {
            const payload = await requestScreener('/api/v1/test_api/stock_screener/presets');
            screenerPresets = payload.presets || [];
            screenerPresetsLoaded = true;
            screenerPresetRetry.hidden = true;
            renderScreenerPresets(screenerPresetSelect.value);
            showScreenerPresetStatus(screenerPresets.length ? '选择方案后点击应用' : '暂无方案，点击新增保存当前条件');
        } catch (error) {
            screenerPresetsLoaded = false;
            screenerPresetRetry.hidden = false;
            showScreenerPresetStatus('方案加载失败：' + error.message, true);
        } finally {
            screenerPresetBusy = false;
            syncScreenerPresetControls();
        }
    };
    const saveScreenerPreset = async (update) => {
        if (screenerPresetBusy || screenerQueryBusy || !screenerOptionsReady || !screenerPresetsLoaded) return;
        const selected = selectedScreenerPreset();
        if (update ? !selected || !screenerPresetCreatePanel.hidden : screenerPresetCreatePanel.hidden) return;
        const name = update ? selected.name : screenerPresetName.value.trim();
        if (!name || name.length > 64) {
            showScreenerPresetStatus('请输入 1–64 字的方案名称', true);
            return;
        }
        if (update && !confirm('确定用当前条件更新方案“' + selected.name + '”？')) return;
        const filters = collectScreenerFilters();
        screenerPresetBusy = true;
        syncScreenerPresetControls();
        showScreenerPresetStatus(update ? '方案更新中...' : '方案保存中...');
        try {
            const url = '/api/v1/test_api/stock_screener/presets' + (update ? '/' + selected.id : '');
            const saved = await requestScreener(url, {
                method: update ? 'PUT' : 'POST', body: JSON.stringify({name, filters}),
            });
            if (update) screenerPresets = screenerPresets.map(item => item.id === saved.id ? saved : item);
            else screenerPresets.push(saved);
            renderScreenerPresets(saved.id);
            if (!update) setScreenerPresetCreateOpen(false);
            showScreenerPresetStatus('方案“' + saved.name + '”已保存');
        } catch (error) {
            screenerPresetRetry.hidden = false;
            showScreenerPresetStatus('保存失败：' + error.message, true);
        } finally {
            screenerPresetBusy = false;
            syncScreenerPresetControls();
            if (!update && screenerPresetCreatePanel.hidden) screenerPresetNew.focus();
        }
    };
    const applyScreenerPreset = () => {
        if (screenerPresetBusy || screenerQueryBusy || !screenerOptionsReady) return;
        const preset = selectedScreenerPreset();
        if (!preset) return;
        const selects = [...screenerFilters.querySelectorAll('select')];
        for (const [field, value] of Object.entries(preset.filters)) {
            if (value == null) continue;
            const select = selects.find(item => item.dataset.field === field);
            if (!select || ![...select.options].some(option => option.value === String(value))) {
                showScreenerPresetStatus('方案中的条件“' + field + '”当前不可用，未应用', true);
                return;
            }
        }
        selects.forEach(select => {
            const value = preset.filters[select.dataset.field];
            select.value = value == null ? '' : String(value);
        });
        pendingScreenerScroll = null;
        lsRemove(SCREENER_SCROLL_KEY);
        lsRemove(SCREENER_LAST_CLICKED_KEY);
        saveScreenerState({filters: collectScreenerFilters(), results: null});
        renderScreenerPlaceholder();
        showScreenerPresetStatus('已应用“' + preset.name + '”');
        return runScreener();
    };
    const deleteScreenerPreset = async () => {
        if (screenerPresetBusy || screenerQueryBusy || !screenerPresetsLoaded) return;
        const preset = selectedScreenerPreset();
        if (!preset || !confirm('确定删除方案“' + preset.name + '”？此操作不会删除自选或行情数据。')) return;
        screenerPresetBusy = true;
        syncScreenerPresetControls();
        try {
            await requestScreener('/api/v1/test_api/stock_screener/presets/' + preset.id, {method: 'DELETE'});
            screenerPresets = screenerPresets.filter(item => item.id !== preset.id);
            renderScreenerPresets();
            showScreenerPresetStatus('方案已删除，当前筛选条件保持不变');
        } catch (error) {
            screenerPresetRetry.hidden = false;
            showScreenerPresetStatus('删除失败：' + error.message, true);
        } finally {
            screenerPresetBusy = false;
            syncScreenerPresetControls();
        }
    };

    const runScreener = async () => {
        if (screenerPresetBusy || screenerQueryBusy || !screenerOptionsReady) return;
        const filters = collectScreenerFilters();
        const controller = new AbortController();
        screenerQueryController = controller;
        screenerCancel.hidden = false;
        cancelScreenerCacheCheck();
        saveScreenerState({filters, results: null});
        showScreenerCacheMessage('正在查询最新选股结果…');
        setScreenerCacheStatus('正在查询最新选股结果…');
        screenerQueryBusy = true;
        syncScreenerPresetControls();
        screenerRun.disabled = true;
        screenerReset.disabled = true;
        screenerRun.textContent = '查询中...';
        try {
            const payload = await requestScreener('/api/v1/test_api/stock_screener/query', {
                method: 'POST',
                body: JSON.stringify(filters), signal: controller.signal,
            });
            pendingScreenerScroll = null;
            lsRemove(SCREENER_SCROLL_KEY);
            renderScreenerResults(payload);
            const cacheable = cacheableScreenerResult(payload);
            saveScreenerState({filters, results: cacheable ? payload : null});
            displayedScreenerCache = cacheable ? payload : null;
            setScreenerCacheStatus(cacheable
                ? '查询时间：' + new Date(payload.queried_at).toLocaleString('zh-CN', {hour12: false}) + '；本次查询已完成'
                : '本次结果未提供可核验版本，刷新后请重新查询');
        } catch (error) {
            screenerResults.textContent = '';
            const message = document.createElement('div');
            message.className = 'screener-empty';
            message.textContent = error.name === 'AbortError' ? '已取消查询，可重新查询' : `查询失败: ${error.message}`;
            screenerResults.appendChild(message);
            setScreenerCacheStatus(error.name === 'AbortError' ? '查询已取消' : '查询未完成，请重新查询');
        } finally {
            const returnFocus = document.activeElement === screenerCancel;
            screenerRun.disabled = false;
            screenerReset.disabled = false;
            screenerRun.textContent = '确认';
            if (screenerQueryController === controller) {
                screenerQueryController = null;
                screenerCancel.hidden = true;
            }
            screenerQueryBusy = false;
            syncScreenerPresetControls();
            if (returnFocus && !screenerRun.disabled) screenerRun.focus();
        }
    };

    const resetScreener = () => {
        if (screenerPresetBusy || screenerQueryBusy) return;
        cancelScreenerCacheCheck();
        setScreenerCacheStatus('');
        screenerPresetSelect.value = '';
        setScreenerPresetCreateOpen(false);
        showScreenerPresetStatus('已重置当前条件，已保存方案不变');
        syncScreenerPresetControls();
        pendingScreenerScroll = null;
        lsRemove(SCREENER_SCROLL_KEY);
        lsRemove(SCREENER_LAST_CLICKED_KEY);
        saveScreenerState({filters: {}, results: null});
        screenerFilters.querySelectorAll('select').forEach(select => {
            const value = SCREENER_DEFAULTS[select.dataset.field];
            const stringValue = value == null ? '' : String(value);
            select.value = [...select.options].some(option => option.value === stringValue)
                ? stringValue
                : '';
        });
        renderScreenerPlaceholder();
    };

    const applyScreenerWidth = width => {
        const maxWidth = Math.max(220, Math.min(640, window.innerWidth - 420));
        const next = Math.round(Math.max(220, Math.min(maxWidth, width)));
        appShell.style.setProperty('--screener-width', next + 'px');
        return next;
    };

    screenerCollapse.addEventListener('click', () => {
        appShell.classList.add('screener-collapsed');
        lsSetBool('screener:collapsed', true);
        syncChartWidth();
    });
    screenerExpand.addEventListener('click', () => {
        appShell.classList.remove('screener-collapsed');
        lsSetBool('screener:collapsed', false);
        syncChartWidth();
        scheduleScreenerScrollRestore();
    });
    screenerRun.addEventListener('click', runScreener);
    screenerCancel.addEventListener('click', () => screenerQueryController?.abort());
    screenerReset.addEventListener('click', resetScreener);
    screenerResizer.addEventListener('pointerdown', event => {
        if (event.button !== 0 || appShell.classList.contains('screener-collapsed')) return;
        event.preventDefault();
        screenerResize = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startWidth: screenerPanel.getBoundingClientRect().width,
        };
        appShell.classList.add('screener-resizing');
        screenerResizer.setPointerCapture(event.pointerId);
    });
    screenerResizer.addEventListener('pointermove', event => {
        if (!screenerResize || event.pointerId !== screenerResize.pointerId) return;
        applyScreenerWidth(screenerResize.startWidth - (event.clientX - screenerResize.startX));
        syncChartWidth();
    });
    const finishScreenerResize = event => {
        if (!screenerResize || (event && event.pointerId !== screenerResize.pointerId)) return;
        const width = applyScreenerWidth(
            screenerResize.startWidth - (event.clientX - screenerResize.startX)
        );
        screenerResize = null;
        appShell.classList.remove('screener-resizing');
        lsSetString('screener:width', String(width));
        syncChartWidth();
    };
    screenerResizer.addEventListener('pointerup', finishScreenerResize);
    screenerResizer.addEventListener('pointercancel', finishScreenerResize);
    screenerPresetSelect.addEventListener('change', () => {
        showScreenerPresetStatus('选择方案后点击应用；更新会覆盖所选方案');
        syncScreenerPresetControls();
    });
    screenerPresetNew.addEventListener('click', () => {
        if (screenerPresetNew.disabled) return;
        setScreenerPresetCreateOpen(true);
        showScreenerPresetStatus('输入新方案名称，保存当前筛选条件');
        screenerPresetName.focus();
    });
    screenerPresetCancel.addEventListener('click', cancelScreenerPresetCreate);
    screenerPresetName.addEventListener('keydown', event => {
        if (event.isComposing) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            cancelScreenerPresetCreate();
        } else if (event.key === 'Enter') {
            event.preventDefault();
            return saveScreenerPreset(false);
        }
    });
    screenerPresetSave.addEventListener('click', () => saveScreenerPreset(false));
    screenerPresetApply.addEventListener('click', applyScreenerPreset);
    screenerPresetUpdate.addEventListener('click', () => saveScreenerPreset(true));
    screenerPresetDelete.addEventListener('click', deleteScreenerPreset);
    screenerPresetRetry.addEventListener('click', loadScreenerPresets);
    try {
        new window.ScreenerHistory({
            request: requestScreener,
            storage: browserStorage,
            getPresetId: () => Number(screenerPresetSelect.value) || 0,
            getChartContext: () => ({symbol: currentSymbol, market: currentMarket.replace('market=', ''), asset_class: currentAssetClass.replace('asset_class=', ''), frequency: currentFrequency.replace('freq=', '')}),
        });
    } catch (error) {
        console.error('历史组件加载失败:', error);
        const tab = document.getElementById('screenerHistoryTab');
        tab.disabled = true;
        tab.title = '历史组件加载失败，请刷新';
        document.getElementById('screenerRealtimePanel').hidden = false;
        document.getElementById('screenerHistoryPanel').hidden = true;
    }
    loadScreenerPresets();
    loadScreenerOptions();
    const recheckScreenerCache = () => {
        if (document.visibilityState === 'hidden') return;
        return restoreScreenerCache();
    };
    if (typeof window.addEventListener === 'function') {
        window.addEventListener('focus', recheckScreenerCache);
        window.addEventListener('pageshow', recheckScreenerCache);
    }
    if (typeof document.addEventListener === 'function') document.addEventListener('visibilitychange', recheckScreenerCache);
    if (typeof window.setInterval === 'function') window.setInterval(recheckScreenerCache, 60000);

    document.querySelectorAll('#frequencyTabs .frequency-tab').forEach(button => {
        button.addEventListener('click', () => {
            if (button.classList.contains('active') || button.disabled) return;
            const params = new URLSearchParams(window.location.search);
            params.set('frequency', button.dataset.frequency);
            window.location.search = params.toString();
        });
    });