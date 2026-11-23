    function requestJson(url, options = {}) {
        const {signal: externalSignal, timeoutMs = 30000, ...requestOptions} = options;
        const controller = new AbortController();
        let timedOut = false, timer;
        const failure = () => {
            const write = String(url).includes('/stock_screener/presets') && ['POST', 'PUT', 'DELETE'].includes(requestOptions.method);
            const message = timedOut ? write ? '请求超时，服务端可能已处理，请先刷新方案列表核对后再重试' : '请求超时，请重试' : '已取消请求';
            const error = new Error(message);
            error.name = timedOut ? 'TimeoutError' : 'AbortError';
            return error;
        };
        if (externalSignal?.aborted) return Promise.reject(failure());
        let rejectAbort;
        const cancelled = new Promise((_resolve, reject) => { rejectAbort = () => reject(failure()); });
        controller.signal.addEventListener('abort', rejectAbort, {once: true});
        const forwardAbort = () => controller.abort();
        externalSignal?.addEventListener('abort', forwardAbort, {once: true});
        timer = setTimeout(() => { timedOut = true; controller.abort(); }, Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 30000);
        const work = Promise.resolve().then(async () => {
            if (controller.signal.aborted) throw failure();
            const response = await fetch(url, {headers: {'Content-Type': 'application/json'}, ...requestOptions, signal: controller.signal});
            if (!response.ok) {
                let detail = '请求失败: ' + response.status;
                try {
                    const value = (await response.json()).detail;
                    if (typeof value === 'string') detail = value;
                    else if (Array.isArray(value)) detail = value.map(item => item.msg).filter(Boolean).join('；') || detail;
                } catch (_) {}
                throw new Error(detail);
            }
            return response.status === 204 ? null : await response.json();
        });
        // The race also releases UI state when a transport ignores abort or its body stalls.
        return Promise.race([work, cancelled]).finally(() => {
            clearTimeout(timer);
            controller.signal.removeEventListener('abort', rejectAbort);
            externalSignal?.removeEventListener('abort', forwardAbort);
        });
    }