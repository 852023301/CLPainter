'use strict';
(() => {
    const HISTORY_LIMIT = 5;
    const PERIODS = {'1day': '日', '1week': '周', '1month': '月', '1quarter': '季', '1year': '年'};
    const VIEWS = {results: '本期', added: '新增', removed: '移出', retained: '保留'};
    const PARAMS = {presetId: 'history_preset', frequency: 'history_frequency', runId: 'history_run_id', view: 'history_view', offset: 'history_offset', scrollTop: 'history_scroll'};
    const DEFAULTS = {presetId: 0, frequency: '', runId: 0, view: 'results', offset: 0, scrollTop: 0};
    const number = value => Math.max(0, Number.isSafeInteger(Number(value)) ? Number(value) : 0);

    class ScreenerHistory {
        constructor({request, getChartContext, getPresetId, storage}) {
            this.request = request;
            this.storage = storage;
            this.getChartContext = getChartContext;
            this.getPresetId = getPresetId;
            const get = suffix => document.getElementById('screener' + suffix);
            this.el = {
                panel: get('Panel'),
                realtimeTab: get('RealtimeTab'),
                historyTab: get('HistoryTab'),
                realtimePanel: get('RealtimePanel'),
                historyPanel: get('HistoryPanel'),
                open: get('HistoryLink'),
                preset: get('HistoryPreset'),
                frequency: get('HistoryFrequency'),
                version: get('HistoryVersion'),
                refresh: get('HistoryRefresh'),
                page: get('HistoryPage'),
                status: get('HistoryStatus'),
                hint: get('HistoryChartHint'),
                summary: get('HistorySummary'),
                results: get('HistoryResults'),
            };
            this.views = Object.fromEntries(Object.keys(VIEWS).map(key => [key, get('HistoryView' + key[0].toUpperCase() + key.slice(1))]));
            if (Object.values(this.el).some(value => !value) || Object.values(this.views).some(value => !value)) throw new Error('历史面板控件不完整');
            this.state = this.readState();
            this.detail = null;
            this.runs = [];
            this.total = 0;
            this.token = 0;
            this.busy = false;
            this.restoring = false;
            this.pendingScroll = null;
            this.el.hint.textContent = '名单为所选历史版本，图表为最新完整行情，不按版本日期截断。';
            this.options(this.el.frequency, [{value: '', label: '全部周期'}, ...Object.entries(PERIODS).map(([value, label]) => ({value, label}))], this.state.frequency);
            this.bind();
            const requested = new URLSearchParams(window.location.search).get('screener_mode');
            const stored = this.read('screener:mode');
            this.activate(requested === 'history' || (!requested && stored === 'history') ? 'history' : 'realtime', false);
        }

        read(key) {
            try { return this.storage.getItem(key); } catch (_) { return null; }
        }

        readState() {
            let stored = {};
            try { stored = JSON.parse(this.read('screener:history-state') || '{}') || {}; } catch (_) {}
            const values = {...DEFAULTS, ...stored};
            const query = new URLSearchParams(window.location.search);
            Object.entries(PARAMS).forEach(([key, parameter]) => { if (query.has(parameter)) values[key] = query.get(parameter); });
            const scroll = Number(values.scrollTop);
            return {
                presetId: number(values.presetId),
                frequency: Object.keys(PERIODS).includes(values.frequency) ? values.frequency : '',
                runId: number(values.runId),
                view: Object.keys(VIEWS).includes(values.view) ? values.view : 'results',
                offset: 0,
                scrollTop: Number.isFinite(scroll) ? Math.max(0, Math.round(scroll)) : 0,
            };
        }

        store(updateURL = true) {
            try {
                this.storage.setItem('screener:history-state', JSON.stringify(this.state));
                this.storage.setItem('screener:mode', this.mode);
            } catch (_) {}
            if (!updateURL) return;
            const query = new URLSearchParams(window.location.search);
            query.set('screener_mode', this.mode);
            Object.entries(PARAMS).forEach(([key, parameter]) => {
                if (this.mode === 'history') query.set(parameter, String(this.state[key]));
                else query.delete(parameter);
            });
            window.history.replaceState(null, '', window.location.pathname + '?' + query.toString());
        }

        activate(mode, persist = true) {
            this.mode = mode;
            this.el.panel.dataset.mode = mode;
            const historical = mode === 'history';
            this.el.realtimePanel.hidden = historical;
            this.el.historyPanel.hidden = !historical;
            for (const [tab, selected] of [[this.el.realtimeTab, !historical], [this.el.historyTab, historical]]) {
                tab.setAttribute('aria-selected', String(selected));
                tab.setAttribute('tabindex', selected ? '0' : '-1');
            }
            this.store(persist);
            return historical ? this.refresh() : Promise.resolve();
        }

        bind() {
            this.el.realtimeTab.addEventListener('click', () => this.activate('realtime'));
            this.el.historyTab.addEventListener('click', () => this.activate('history'));
            this.el.open.addEventListener('click', () => {
                const selected = number(this.getPresetId());
                if (selected) Object.assign(this.state, {presetId: selected, frequency: '', runId: 0, offset: 0, view: 'results', scrollTop: 0});
                return this.activate('history');
            });
            for (const tab of [this.el.realtimeTab, this.el.historyTab]) tab.addEventListener('keydown', event => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                const mode = event.key === 'Home' ? 'realtime' : event.key === 'End' ? 'history' : this.mode === 'history' ? 'realtime' : 'history';
                (mode === 'history' ? this.el.historyTab : this.el.realtimeTab).focus();
                return this.activate(mode);
            });
            for (const key of ['preset', 'frequency']) this.el[key].addEventListener('change', () => {
                Object.assign(this.state, {presetId: number(this.el.preset.value), frequency: this.el.frequency.value, runId: 0, offset: 0, view: 'results', scrollTop: 0});
                return this.refresh();
            });
            this.el.version.addEventListener('change', () => {
                Object.assign(this.state, {runId: number(this.el.version.value), scrollTop: 0});
                return this.refresh({detailOnly: true});
            });
            this.el.refresh.addEventListener('click', () => this.refresh());
            for (const [view, button] of Object.entries(this.views)) button.addEventListener('click', () => {
                this.state.view = view; this.state.scrollTop = 0;
                this.renderResults(); this.store(); this.setBusy(false);
            });
            this.el.results.addEventListener('scroll', () => {
                if (this.busy || this.restoring || this.mode !== 'history') return;
                this.state.scrollTop = this.el.results.scrollTop;
                this.store(false);
            });
            document.getElementById('screenerExpand').addEventListener('click', () => this.restoreScroll());
        }

        options(select, values, selected) {
            select.textContent = '';
            values.forEach(item => {
                const option = document.createElement('option');
                option.value = String(item.value); option.textContent = item.label;
                select.appendChild(option);
            });
            select.value = String(selected);
        }

        status(message, error = false) {
            this.el.status.textContent = message;
            this.el.status.dataset.error = String(error);
        }

        setBusy(busy) {
            this.busy = busy;
            for (const element of [this.el.preset, this.el.frequency, this.el.refresh]) element.disabled = busy;
            this.el.version.disabled = busy || (!this.runs.length && !this.detail);
            for (const [key, button] of Object.entries(this.views)) {
                button.disabled = busy || !this.detail || (key !== 'results' && !this.detail.comparison_available);
                button.textContent = VIEWS[key] + (this.detail ? ' ' + (key === 'results' ? this.detail.count : this.detail.comparison_available ? this.detail[key].length : '—') : '');
                button.setAttribute('aria-pressed', String(key === this.state.view));
            }
        }

        async refresh({detailOnly = false} = {}) {
            const token = ++this.token;
            let expiredVersion = false;
            this.state.offset = 0;
            this.detail = null;
            this.restoring = true;
            this.el.results.textContent = '';
            this.el.summary.textContent = '';
            this.status('历史结果加载中...');
            this.setBusy(true);
            try {
                if (!detailOnly) {
                    const metadata = await this.request('/api/v1/test_api/stock_screener/presets', {cache: 'no-store'});
                    if (token !== this.token) return;
                    if (this.state.presetId && !metadata.presets.some(item => item.id === this.state.presetId)) Object.assign(this.state, {presetId: 0, runId: 0, offset: 0, scrollTop: 0});
                    this.options(this.el.preset, [{value: 0, label: '全部方案'}, ...metadata.presets.map(item => ({value: item.id, label: item.name}))], this.state.presetId);
                    this.el.frequency.value = this.state.frequency;
                    const listURL = '/api/v1/test_api/stock_screener/runs?' + new URLSearchParams({preset_id: this.state.presetId, frequency: this.state.frequency, limit: HISTORY_LIMIT, offset: 0});
                    const listing = await this.request(listURL, {cache: 'no-store'});
                    if (token !== this.token) return;
                    this.runs = listing.runs.slice(0, HISTORY_LIMIT); this.total = listing.total;
                    this.options(this.el.version, this.runs.length ? this.runs.map(item => ({value: item.id, label: this.versionLabel(item)})) : [{value: 0, label: '暂无已保存版本'}], this.state.runId);
                    this.el.page.textContent = '仅显示最新 ' + HISTORY_LIMIT + ' 个版本 · 当前 ' + this.runs.length + ' 个（共 ' + this.total + ' 个）';
                }
                if (!this.runs.some(run => run.id === this.state.runId)) {
                    expiredVersion = Boolean(this.state.runId);
                    this.state.runId = this.runs[0]?.id || 0;
                    if (expiredVersion) Object.assign(this.state, {view: 'results', scrollTop: 0});
                }
                if (!this.state.runId) {
                    this.status('暂无已保存版本，完整数据更新后自动留档。'); this.store(); return;
                }
                const detail = await this.request('/api/v1/test_api/stock_screener/runs/' + this.state.runId, {cache: 'no-store'});
                if (token !== this.token) return;
                if ((this.state.presetId && detail.preset_id !== this.state.presetId) || (this.state.frequency && detail.frequency !== this.state.frequency)) throw new Error('所选版本不属于当前方案或周期，请重新选择');
                if (detail.id !== this.state.runId) throw new Error('返回的版本与当前选择不一致，请刷新重试');
                this.detail = detail;
                if (!detail.comparison_available) this.state.view = 'results';
                this.el.version.value = String(detail.id);
                this.el.version.title = this.versionLabel(detail);
                this.el.summary.textContent = detail.preset_name + ' · ' + detail.version_date + ' · ' + (PERIODS[detail.frequency] || detail.frequency) + ' · ' + detail.count + ' 个。' + (detail.comparison_available ? '对比上次保存：' + detail.previous_version : '首次版本，无对比基准。');
                this.renderResults(); this.store();
                this.status((expiredVersion ? '仅显示最新 ' + HISTORY_LIMIT + ' 个版本，已切换到最新版本。' : '') + '历史名单已加载；点击标的在当前工作台查看最新 K 线和指标。');
            } catch (error) {
                if (token !== this.token) return;
                this.detail = null; this.el.results.textContent = ''; this.el.summary.textContent = '';
                this.status('历史结果加载失败：' + error.message, true);
            } finally {
                if (token === this.token) this.setBusy(false);
            }
        }

        versionLabel(item) {
            return item.version_date + ' · ' + item.preset_name + ' · ' + (PERIODS[item.frequency] || item.frequency) + ' · ' + item.count + ' 个';
        }

        resultURL(item) {
            const query = new URLSearchParams({symbol: item.code, market: item.market, asset_class: item.asset_class, frequency: this.detail.frequency, screener_mode: 'history'});
            Object.entries(PARAMS).forEach(([key, parameter]) => query.set(parameter, String(this.state[key])));
            return '/api/v1/test_api/lightweight_charts_demo?' + query.toString();
        }

        renderResults() {
            if (!this.detail) return;
            this.restoring = true;
            this.el.results.textContent = '';
            const rows = this.detail[this.state.view] || [];
            const chart = this.getChartContext();
            if (!rows.length) {
                const message = document.createElement('div'); message.className = 'screener-empty';
                message.textContent = this.state.view === 'results' ? '本期没有命中标的；图表保留当前股票。' : '该分类没有标的；图表保留当前股票。';
                this.el.results.appendChild(message);
            }
            rows.forEach((item, index) => {
                const row = document.createElement('a');
                const selected = item.code === chart.symbol && item.market === chart.market && item.asset_class === chart.asset_class;
                row.className = 'screener-result' + (selected ? ' active' : '');
                row.href = this.resultURL(item); row.title = item.code + ' · ' + item.display_name + '；打开最新完整行情';
                const sequence = document.createElement('span'); sequence.className = 'screener-result-index'; sequence.textContent = String(index + 1);
                const name = document.createElement('span'); name.className = 'screener-result-name'; name.textContent = item.display_name;
                const code = document.createElement('span'); code.className = 'screener-result-meta'; code.textContent = item.code;
                row.append(sequence, name, code);
                row.addEventListener('click', event => {
                    if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                    event.preventDefault();
                    this.state.scrollTop = this.el.results.scrollTop;
                    this.store();
                    if (!selected || chart.frequency !== this.detail.frequency) window.location.assign(this.resultURL(item));
                });
                this.el.results.appendChild(row);
            });
            this.pendingScroll = this.state.scrollTop;
            this.restoreScroll();
        }

        restoreScroll() {
            if (this.pendingScroll === null || this.mode !== 'history' || this.el.historyPanel.hidden) return;
            if (document.getElementById('appShell')?.classList.contains('screener-collapsed')) return;
            const target = this.pendingScroll; this.pendingScroll = null;
            requestAnimationFrame(() => requestAnimationFrame(() => {
                this.el.results.scrollTop = target; this.restoring = false;
            }));
        }
    }
    window.ScreenerHistory = ScreenerHistory;
})();
