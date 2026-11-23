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
        const suffix = JSON.stringify(identity);
        const journalPrefix = 'chart:workspace-drawings:v1:' + suffix + ':';
        const legacyKey = 'chart:workspace-legacy:v1:' + suffix;
        let actor;
        try { actor = globalThis.crypto?.randomUUID?.(); } catch (_) {}
        actor = actor || Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
        const journalKey = journalPrefix + actor;
        const changes = new Map();
        let measureChange = null, clock = 0, nextId = 0, rootReadFailed = false;
        const validId = id => Number.isSafeInteger(id) && id > 0 && id <= 1e9
            || typeof id === 'string' && /^[A-Za-z0-9_-]+:\d+$/.test(id) && id.length < 160;
        const cleanShape = item => {
            const pair = cleanPair(item);
            return pair && validId(item.id) && kinds.has(item.kind) ? {id: item.id, kind: item.kind, ...pair} : null;
        };
        const sameIdentity = value => value && JSON.stringify(value.identity) === suffix;
        const read = name => { try { return JSON.parse(storage.getItem(name) || 'null'); } catch (_) { return null; } };
        const readHead = () => {
            rootReadFailed = false;
            let value;
            try {
                value = JSON.parse(storage.getItem(key) || 'null');
                rootReadFailed = Boolean(storage.status?.().readBlocked);
            } catch (_) { rootReadFailed = true; }
            return sameIdentity(value) && (value.schema === 1 || value.schema === 2) ? value : {};
        };
        let head = readHead();
        const backup = read(legacyKey);
        const original = sameIdentity(backup) ? backup : head.schema === 2 ? head.legacy : head;
        const legacyIds = new Set();
        const legacyShapes = (Array.isArray(original?.shapes) ? original.shapes : []).map(cleanShape).filter(shape => {
            if (!shape || legacyIds.has(shape.id)) return false;
            legacyIds.add(shape.id); return true;
        });
        const legacy = {shapes: legacyShapes, measure: cleanPair(original?.measure)};
        const ordinal = (a, b) => String(a) < String(b) ? -1 : String(a) > String(b) ? 1 : 0;
        const compare = (a, b) => a.clock - b.clock || ordinal(a.actor, b.actor);
        const stamp = value => value && Number.isSafeInteger(value.clock) && value.clock >= 0 && typeof value.actor === 'string' && value.actor.length < 160;
        const merge = () => {
            const latest = readHead(), records = new Map();
            clock = Math.max(clock, legacy.shapes.length);
            let measure = {clock: 0, actor: '', value: legacy.measure};
            legacy.shapes.forEach((shape, index) => records.set(shape.id, {shape, clock: 0, actor: '', born: {clock: index, actor: ''}, deleted: false}));
            const keys = typeof storage.keys === 'function' ? storage.keys(journalPrefix) : [journalKey];
            if (typeof storage.keys !== 'function' && latest.schema === 2 && Array.isArray(latest.shapes)) {
                latest.shapes.map(cleanShape).filter(Boolean).forEach((shape, index) => records.set(shape.id, {shape, clock: 0, actor: '', born: {clock: index, actor: ''}, deleted: false}));
                measure.value = cleanPair(latest.measure);
            }
            for (const name of keys) {
                const value = read(name);
                if (!sameIdentity(value) || value.schema !== 1 || typeof value.actor !== 'string' || value.actor.length > 128
                    || name !== journalPrefix + value.actor || !Array.isArray(value.changes)) continue;
                for (const change of value.changes) {
                    const shape = cleanShape(change?.shape);
                    if (!shape || !stamp(change) || !stamp(change.born) || change.actor !== value.actor || typeof change.deleted !== 'boolean') continue;
                    clock = Math.max(clock, change.clock);
                    const previous = records.get(shape.id);
                    if (!previous || compare(change, previous) > 0) records.set(shape.id, {...change, shape});
                }
                const next = value.measure;
                if (stamp(next) && next.actor === value.actor && (next.value === null || cleanPair(next.value))) {
                    clock = Math.max(clock, next.clock);
                    if (compare(next, measure) > 0) measure = {...next, value: cleanPair(next.value)};
                }
            }
            const shapes = [...records.values()].filter(item => !item.deleted).sort((a, b) => compare(a.born, b.born) || ordinal(a.shape.id, b.shape.id)).map(item => item.shape);
            return {head: latest, records, shapes, measure: measure.value};
        };
        const first = merge();
        const from = cleanAnchor(head.viewport?.from), to = cleanAnchor(head.viewport?.to);
        const state = {schema: 2, identity, viewport: from && to ? {from, to} : null, shapes: first.shapes, measure: first.measure};
        const tick = () => { clock = Math.max(clock, Date.now()) + 1; return clock; };
        const decodePoint = point => point && indices.has(point.time) ? {index: indices.get(point.time), price: point.price} : null;
        const decodePair = item => {
            const start = decodePoint(item?.start), end = decodePoint(item?.end);
            return start && end ? {start, end} : null;
        };
        const hidden = new Set(state.shapes.filter(item => !decodePair(item)).map(item => item.id));
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
        const write = viewportChanged => {
            let persistent = true;
            const put = (name, value) => {
                try { if (storage.setItem(name, JSON.stringify(value)) === false) persistent = false; }
                catch (_) { persistent = false; }
            };
            // Each page owns its change journal; another page can never overwrite it.
            if (!viewportChanged && (changes.size || measureChange)) put(journalKey, {schema: 1, identity, actor, changes: [...changes.values()], measure: measureChange});
            const merged = merge();
            if (rootReadFailed) return false;
            if ((legacy.shapes.length || legacy.measure) && !sameIdentity(read(legacyKey))) put(legacyKey, {identity, ...legacy});
            const viewport = viewportChanged ? state.viewport : merged.head.viewport || state.viewport;
            // The head is a convenience snapshot; journals remain the authoritative drawings.
            put(key, {schema: 2, identity, legacy, viewport, shapes: merged.shapes, measure: merged.measure});
            return persistent;
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
                return write(true);
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
                    if (!old.has(id) || old.get(id).kind !== kind || active.has(id)) id = actor + ':' + (++nextId);
                    item.workspaceId = id;
                    const record = {id, kind, ...pair};
                    active.set(id, record); sequence.push(record);
                }
                const retained = state.shapes.flatMap(item => active.has(item.id) ? [active.get(item.id)] : hidden.has(item.id) ? [item] : []);
                const nextShapes = retained.concat(sequence.filter(item => !old.has(item.id)));
                const merged = merge(), next = new Map(nextShapes.map(item => [item.id, item]));
                const change = (shape, deleted) => {
                    const previous = merged.records.get(shape.id);
                    const version = tick();
                    changes.set(shape.id, {shape, deleted, clock: version, actor, born: previous?.born || {clock: version, actor}});
                };
                for (const shape of nextShapes) if (JSON.stringify(shape) !== JSON.stringify(old.get(shape.id))) change(shape, false);
                for (const shape of state.shapes) if (!next.has(shape.id)) change(shape, true);
                const measure = measureChanged || !missingMeasure ? encodePair(snapshot.measure) : state.measure;
                if (JSON.stringify(measure) !== JSON.stringify(state.measure)) measureChange = {value: measure, clock: tick(), actor};
                state.shapes = nextShapes; state.measure = measure;
                return write(false);
            },
        };
    }