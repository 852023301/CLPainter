function createChartWorkspace(storage, context, candles) {
        const identity = [String(context.market).replace(/^market=/, ''), String(context.assetClass).replace(/^asset_class=/, ''), String(context.symbol), String(context.frequency).replace(/^freq=/, '')];
        const key = 'chart:workspace:v1:' + JSON.stringify(identity);
        const kinds = new Set(['rect', 'trend', 'fib']);
        const finite = value => typeof value === 'number' && Number.isFinite(value);
        const epoch = time => {
            if (finite(time)) return Math.abs(time) <= 8640000000000 ? time : null;
            let year, month, day;
            if (typeof time === 'string') {
                const found = /^(\d{4})-(\d{2})-(\d{2})$/.exec(time);
                if (!found) return null;
                [year, month, day] = found.slice(1).map(Number);
            } else if (time && typeof time === 'object') {
                ({year, month, day} = time);
            } else return null;
            if (![year, month, day].every(Number.isInteger) || year < 1000 || year > 9999) return null;
            const date = new Date(Date.UTC(year, month - 1, day));
            return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day ? date.getTime() / 1000 : null;
        };
        const times = candles.map(candle => epoch(candle.time));
        const indices = new Map();
        times.forEach((time, index) => { if (time !== null) indices.set(time, index); });
        const ordered = [...indices].map(([time, index]) => ({time, index})).sort((a, b) => a.time - b.time);
        const cleanPoint = point => point && finite(point.time) && finite(point.price) && Math.abs(point.price) <= 1e15 ? {time: point.time, price: point.price} : null;
        const cleanPair = item => {
            const start = cleanPoint(item?.start), end = cleanPoint(item?.end);
            return start && end ? {start, end} : null;
        };
        const cleanAnchor = point => point && finite(point.time) && finite(point.offset) && Math.abs(point.offset) <= 1e6 ? {time: point.time, offset: point.offset} : null;
        let raw = null;
        try { raw = JSON.parse(storage.getItem(key) || 'null'); } catch (_) {}
        if (!raw || raw.schema !== 1 || JSON.stringify(raw.identity) !== JSON.stringify(identity)) raw = {};
        const unique = new Set();
        const shapes = [];
        if (Array.isArray(raw.shapes)) raw.shapes.forEach(item => {
            const pair = cleanPair(item);
            if (!pair || !kinds.has(item.kind) || !Number.isSafeInteger(item.id) || item.id < 1 || item.id > 1e9 || unique.has(item.id)) return;
            unique.add(item.id);
            shapes.push({id: item.id, kind: item.kind, ...pair});
        });
        const from = cleanAnchor(raw.viewport?.from), to = cleanAnchor(raw.viewport?.to);
        const state = {schema: 1, identity, viewport: from && to ? {from, to} : null, shapes, measure: cleanPair(raw.measure)};
        let nextId = shapes.reduce((value, item) => Math.max(value, item.id), 0) + 1;
        const decodePoint = point => point && indices.has(point.time) ? {index: indices.get(point.time), price: point.price} : null;
        const decodePair = item => {
            const start = decodePoint(item?.start), end = decodePoint(item?.end);
            return start && end ? {start, end} : null;
        };
        const hidden = new Set(shapes.filter(item => !decodePair(item)).map(item => item.id));
        const missingMeasure = Boolean(state.measure && !decodePair(state.measure));
        const encodePoint = point => point && Number.isInteger(point.index) && point.index >= 0 && point.index < times.length && times[point.index] !== null && finite(point.price) && Math.abs(point.price) <= 1e15 ? {time: times[point.index], price: point.price} : null;
        const encodePair = item => {
            const start = encodePoint(item?.start), end = encodePoint(item?.end);
            return start && end ? {start, end} : null;
        };
        const nearestIndex = time => {
            if (indices.has(time)) return indices.get(time);
            if (!ordered.length) return null;
            let low = 0, high = ordered.length;
            while (low < high) { const middle = Math.floor((low + high) / 2); if (ordered[middle].time < time) low = middle + 1; else high = middle; }
            if (low === 0) return ordered[0].index;
            if (low === ordered.length) return ordered[low - 1].index;
            return time - ordered[low - 1].time <= ordered[low].time - time ? ordered[low - 1].index : ordered[low].index;
        };
        const validRange = range => range && finite(range.from) && finite(range.to) && range.from < range.to && range.to - range.from <= 1e6 && Math.abs(range.from) <= 1e6 && Math.abs(range.to) <= 1e6;
        const decodeViewport = () => {
            if (!state.viewport || !ordered.length) return null;
            const first = ordered[0].time, last = ordered[ordered.length - 1].time;
            if ((state.viewport.from.time < first && state.viewport.to.time < first) || (state.viewport.from.time > last && state.viewport.to.time > last)) return null;
            const a = nearestIndex(state.viewport.from.time), b = nearestIndex(state.viewport.to.time);
            if (a === null || b === null) return null;
            const range = {from: a + state.viewport.from.offset, to: b + state.viewport.to.offset};
            return validRange(range) ? range : null;
        };
        const write = () => {
            try { storage.setItem(key, JSON.stringify(state)); return true; } catch (_) { return false; }
        };
        return {
            key,
            restore() {
                const result = {viewport: decodeViewport(), rectangles: [], trends: [], fibs: [], order: [], measure: decodePair(state.measure)};
                const groups = {rect: result.rectangles, trend: result.trends, fib: result.fibs};
                state.shapes.forEach(item => {
                    const pair = decodePair(item);
                    if (!pair) return;
                    groups[item.kind].push({...pair, workspaceId: item.id});
                    result.order.push(item.kind);
                });
                return result;
            },
            saveViewport(range) {
                if (!validRange(range) || !times.length) return false;
                const anchor = value => {
                    const index = Math.max(0, Math.min(times.length - 1, Math.round(value)));
                    return times[index] === null ? null : {time: times[index], offset: value - index};
                };
                const from = anchor(range.from), to = anchor(range.to);
                if (!from || !to) return false;
                state.viewport = {from, to};
                return write();
            },
            saveDrawings(snapshot, measureChanged = false) {
                const groups = {rect: snapshot.rectangles || [], trend: snapshot.trends || [], fib: snapshot.fibs || []};
                const positions = {rect: 0, trend: 0, fib: 0}, active = new Map(), sequence = [];
                const old = new Map(state.shapes.map(item => [item.id, item]));
                for (const kind of snapshot.order || []) {
                    if (!kinds.has(kind)) continue;
                    const item = groups[kind][positions[kind]++], pair = encodePair(item);
                    if (!pair) continue;
                    let id = item.workspaceId;
                    if (!old.has(id) || old.get(id).kind !== kind || active.has(id)) id = nextId++;
                    item.workspaceId = id;
                    const record = {id, kind, ...pair};
                    active.set(id, record); sequence.push(record);
                }
                const retained = state.shapes.flatMap(item => active.has(item.id) ? [active.get(item.id)] : hidden.has(item.id) ? [item] : []);
                state.shapes = retained.concat(sequence.filter(item => !old.has(item.id)));
                if (measureChanged || !missingMeasure) state.measure = encodePair(snapshot.measure);
                return write();
            },
        };
    }