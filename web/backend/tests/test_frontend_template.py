from __future__ import annotations

"""前端模板的静态回归检查。

这些断言锁定已经交付的交互，防止后续改动悄悄弄坏开关、布局和测量。
不启动浏览器，也不依赖行情数据。
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "templates"
    / "lightweight_charts_demo.html"
)


def _read_template() -> str:
    data = TEMPLATE.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise AssertionError("前端模板不能带 UTF-8 BOM")
    text = data.decode("utf-8")
    if "\ufffd" in text:
        raise AssertionError("前端模板含有替换字符，中文可能已损坏")
    return text


def _strip_jinja(source: str) -> str:
    """去掉模板标记，保留可被 node --check 解析的脚本。"""
    output = []
    index = 0
    length = len(source)
    while index < length:
        if source.startswith("{{", index):
            index += 2
            depth = 0
            while index < length:
                char = source[index]
                if char == "{":
                    depth += 1
                elif char == "}":
                    if depth == 0 and source.startswith("}}", index):
                        break
                    depth = max(0, depth - 1)
                index += 1
            output.append("null")
            if source.startswith("}}", index):
                index += 2
            continue
        if source.startswith("{%", index) or source.startswith("{#", index):
            closer = "%}" if source.startswith("{%", index) else "#}"
            end = source.find(closer, index + 2)
            if end < 0:
                raise AssertionError("模板标记没有闭合")
            index = end + 2
            continue
        output.append(source[index])
        index += 1
    return "".join(output)


def _inline_scripts(html: str) -> list[str]:
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
    if len(scripts) < 2:
        raise AssertionError("前端模板应保留初始化脚本和图表脚本")
    return scripts


def _z_index(html: str, selector: str) -> int | None:
    css = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    found = None
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [item.strip() for item in match.group(1).split(",")]
        if selector not in selectors:
            continue
        value = re.search(r"z-index:\s*(\d+)", match.group(2))
        if value:
            found = int(value.group(1))
    return found


class FrontendTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read_template()
        cls.scripts = "\n".join(_inline_scripts(cls.html))

    def test_inline_scripts_parse(self):
        node = shutil.which("node")
        if node is None:
            self.fail("未找到 node，无法检查前端脚本语法")
        for number, script in enumerate(_inline_scripts(self.html), start=1):
            completed = subprocess.run(
                [node, "--check", "-"],
                input=_strip_jinja(script),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"第 {number} 段脚本语法错误:\n{completed.stderr}",
            )

    def test_saved_switches_are_shared_across_frequencies(self):
        self.assertIn("lsGetBool('gaps:visible', false)", self.scripts)
        self.assertIn("prefix: 'layer:'", self.scripts)
        self.assertIn("prefix: 'ma:'", self.scripts)
        self.assertNotIn("currentFrequency", self.scripts[self.scripts.find("function setupIndicatorGroup"):])
        self.assertIn("cfg.prefix === 'ma:' && visible) ensureMaSeries(item, true)", self.scripts)
        self.assertIn("if (showGapsToggle.checked) applyGapVisibility()", self.scripts)

    def test_dropdowns_stay_above_chart(self):
        self.assertGreater(_z_index(self.html, ".workspace-header"), _z_index(self.html, ".chart-toolbar"))
        self.assertGreater(_z_index(self.html, ".chart-toolbar"), _z_index(self.html, ".tool-toolbar"))
        self.assertGreater(_z_index(self.html, ".tool-toolbar"), _z_index(self.html, ".workspace-scroll"))

    def test_watchlist_layout_and_interactions(self):
        panel = self.html.find('id="watchlistPanel"')
        workspace = self.html.find('class="workspace"')
        self.assertGreater(panel, 0)
        self.assertGreater(workspace, panel)
        for marker in (
            'id="watchlistResizer"',
            "reorderWatchlistItem",
            "/items/order",
            "item.change_pct",
            "searchInput.addEventListener('focus', showSearchResults)",
            "searchInput.addEventListener('click', showSearchResults)",
            "search:history",
            "const SEARCH_HISTORY_LIMIT = 20;",
            "rememberSearchResult",
        ):
            self.assertIn(marker, self.html)

    def test_screener_frequency_options_follow_calendar_order(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify screener frequency ordering")
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const start = html.indexOf('    const renderScreenerField = ');
const end = html.indexOf('    const renderScreenerFilters = ', start);
assert(start >= 0 && end > start, 'Screener renderer must exist');
const document = {
    createElement(tagName) {
        return {
            tagName, dataset: {}, children: [],
            appendChild(child) { this.children.push(child); },
            append(...children) { this.children.push(...children); },
        };
    },
};
const render = new Function('document', html.slice(start, end) + '\nreturn renderScreenerField;')(document);
const options = Object.freeze([
    {value: '1day', label: '日K'},
    {value: '1month', label: '月K'},
    {value: '1quarter', label: '季K'},
    {value: '1week', label: '周K'},
    {value: '1year', label: '年K'},
]);
const rendered = item => render(item, 'dimension').children
    .find(node => node.tagName === 'select').children
    .map(node => [node.value, node.textContent]);
assert.deepEqual(rendered({field: 'frequency', options}), [
    ['', '不限'], ['1day', '日K'], ['1week', '周K'],
    ['1month', '月K'], ['1quarter', '季K'], ['1year', '年K'],
]);
assert.deepEqual(rendered({field: 'frequency', options: [options[4], options[1]]}), [
    ['', '不限'], ['1month', '月K'], ['1year', '年K'],
]);
assert.deepEqual(rendered({field: 'frequency', options: [
    {value: '1min', label: '1分'}, ...options, {value: '5min', label: '5分'},
]}).map(option => option[0]), [
    '', '1day', '1week', '1month', '1quarter', '1year', '1min', '5min',
]);
assert.deepEqual(rendered({field: 'scope', options}), [
    ['', '不限'], ...options.map(option => [option.value, option.label]),
]);
assert.deepEqual(rendered({field: 'frequency'}), [['', '不限']]);
"""
        completed = subprocess.run(
            [node, "-", str(TEMPLATE)],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_screener_preset_actions_are_bold_and_creation_is_collapsed(self):
        style = re.search(r"\.screener-preset-actions button\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(style)
        weight = re.search(r"font-weight:\s*(\d+)", style.group(1))
        self.assertIsNotNone(weight)
        self.assertGreaterEqual(int(weight.group(1)), 600)
        self.assertIn("color: #333", style.group(1))
        self.assertRegex(self.html, r'<div[^>]*id="screenerPresetCreatePanel"[^>]*\bhidden')
        self.assertRegex(self.html, r'id="screenerPresetNew"[^>]*aria-expanded="false"')
        self.assertIn(".screener-preset-create[hidden]", self.html)
        self.assertNotIn('id="screenerHistoryPrev"', self.html)
        self.assertNotIn('id="screenerHistoryNext"', self.html)

    def test_saved_screener_presets_behavior(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify saved screener presets")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_screener_presets.js"), str(TEMPLATE)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_indicator_switch_only_commits_latest_build(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify indicator concurrency")
        script = Path(__file__).resolve().parent / "repros" / "frontend_contracts.js"
        completed = subprocess.run(
            [node, str(script), "--template", str(TEMPLATE), "--group", "indicator_concurrency", "--check"],
            text=True, capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
        results = json.loads(completed.stdout)["results"]
        expected = {
            "indicator_latest_wins",
            "indicator_keeps_visible_while_loading",
            "indicator_failed_latest_keeps_visible",
            "indicator_stale_success_waits_for_latest",
            "indicator_stale_failure_has_no_side_effects",
            "indicator_failed_latest_blocks_older_success",
            "indicator_repeated_selection_single_commit",
            "indicator_panels_independent",
            "indicator_shared_module_survives_switch",
            "indicator_stale_macd_cannot_mutate_volume",
            "indicator_rapid_latest_first",
            "indicator_rapid_latest_last",
            "control_all_indicators_build",
        }
        self.assertEqual(len(results), len(expected))
        self.assertEqual({result["id"] for result in results}, expected)
        self.assertTrue(all(result["status"] == "passed" for result in results), completed.stdout)

    def test_chart_modules_retry_after_failure(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify module retries")
        script = Path(__file__).resolve().parent / "repros" / "frontend_contracts.js"
        completed = subprocess.run(
            [node, str(script), "--template", str(TEMPLATE), "--group", "module_retry_lifecycle", "--check"],
            text=True, capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
        results = json.loads(completed.stdout)["results"]
        expected = {
            "module_retry", "gap_retry", "control_shared_request",
            "retry_http_failure", "retry_outer_json_failure", "retry_embedded_json_failure",
            "retry_invalid_response", "retry_sync_fetch_throw", "retry_shared_failure_recovery",
            "retry_old_failure_keeps_newer_cache", "retry_gap_toggle_recovers",
            "retry_gap_result_respects_switch", "retry_ma_toggle_recovers",
            "retry_ma_result_respects_switch", "retry_indicators_recover",
            "control_empty_success_cached", "control_failed_module_isolated",
            "control_gap_failure_keeps_replacement",
        }
        self.assertEqual(len(results), len(expected))
        self.assertEqual({result["id"] for result in results}, expected)
        self.assertTrue(all(result["status"] == "passed" for result in results), completed.stdout)

    def test_indicator_switch_preserves_visible_window(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify viewport preservation")
        script = Path(__file__).resolve().parent / "repros" / "frontend_contracts.js"
        completed = subprocess.run(
            [node, str(script), "--template", str(TEMPLATE), "--group", "viewport_preservation", "--check"],
            text=True, capture_output=True, check=False, timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
        results = json.loads(completed.stdout)["results"]
        expected = {
            "indicator_preserves_range", "range_main_is_authority",
            "range_pan_while_loading_main", "range_pan_while_loading_sub",
            "range_early_main_pan_preserved", "range_early_sub_pan_syncs",
            "range_load_failure_keeps_window", "range_render_failure_restores_window",
            "range_restore_error_releases_sync", "range_ignores_delayed_stale_event",
            "range_snapshot_preserves_exact_values", "range_no_window_does_not_force_fit",
            "range_initial_default_runs_once", "range_main_resize_keeps_window",
            "range_preserves_existing_sync_guard", "range_layout_notification_keeps_window",
            "control_range_user_sync_still_works",
        }
        self.assertEqual(len(results), len(expected))
        self.assertEqual({result["id"] for result in results}, expected)
        self.assertTrue(all(result["status"] == "passed" for result in results), completed.stdout)
        for layout in ("layoutRangeBox", "layoutMeasure", "layoutRect", "layoutFib", "layoutTrend"):
            self.assertIn("chartContainer.addEventListener('chartlayoutchange', () => " + layout + "());", self.scripts)

    def _check_four_fix_group(self, group, count):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to verify frontend failure recovery")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_four_fixes.js"), str(TEMPLATE), group],
            text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
        results = json.loads(completed.stdout)["results"]
        self.assertEqual(len(results), count)
        self.assertTrue(all(item["category"] == group and item["status"] == "passed" for item in results), completed.stdout)

    def test_workspace_multiple_tabs_do_not_erase_each_other(self):
        self._check_four_fix_group("workspace", 8)

    def test_indicator_failure_is_visible_and_cancel_is_panel_local(self):
        self._check_four_fix_group("indicator", 4)

    def test_request_timeouts_and_manual_cancel_release_the_ui(self):
        self._check_four_fix_group("requests", 9)

    def test_storage_degradation_is_visible_and_truthful(self):
        self._check_four_fix_group("storage", 4)

    def test_storage_faults_only_degrade_persistence(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify storage resilience")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_storage_behavior.js"), str(TEMPLATE)],
            text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)
        results = json.loads(completed.stdout)["results"]
        expected = {
            "storage_denied_defaults", "storage_quota_latest_string", "storage_quota_false_zero_empty",
            "storage_delete_tombstone", "storage_read_uses_last_known", "storage_getter_denied",
            "storage_native_absent", "control_storage_available", "control_external_updates_visible",
            "storage_failed_key_isolated", "storage_explicit_write_recovers",
            "storage_history_shared_fallback", "storage_search_navigation_survives",
            "storage_ui_boot_available", "storage_ui_boot_denied", "storage_ui_boot_quota",
            "storage_ui_boot_delete", "storage_ui_boot_getter",
        }
        self.assertEqual(len(results), len(expected))
        self.assertEqual({result["id"] for result in results}, expected)
        self.assertTrue(all(result["status"] == "passed" for result in results), completed.stdout)
        start = self.scripts.index("    // localStorage 持久化辅助")
        end = self.scripts.index("    const searchInput =", start)
        unsafe = r"\blocalStorage\.(?:getItem|setItem|removeItem)\s*\("
        self.assertNotRegex(self.scripts[:start] + self.scripts[end:], unsafe)
        history = (TEMPLATE.parent.parent / "static/js/screener-history.js").read_text(encoding="utf-8")
        self.assertNotRegex(history, unsafe)

    def test_screener_cache_freshness_behavior(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify screener cache freshness")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_screener_freshness.js"), str(TEMPLATE)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_workspace_module_boundary(self):
        self.assertTrue('{% include "_chart_workspace.js" %}' in self.html, "Main template must compose the workspace module")
        self.assertFalse("function createChartWorkspace(" in self.scripts, "The implementation must live only in the module")
        module = TEMPLATE.with_name("_chart_workspace.js")
        self.assertTrue(module.is_file(), "The extracted workspace module must ship with the template")
        data = module.read_bytes()
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertIn("function createChartWorkspace(", data.decode("utf-8"))
        self.assertNotIn("{%", data.decode("utf-8"))
        self.assertNotIn("{{", data.decode("utf-8"))
        node = shutil.which("node")
        self.assertIsNotNone(node)
        completed = subprocess.run([node, "--check", str(module)], text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_chart_workspace_round_trip(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify chart workspace restoration")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_chart_workspace.js"), str(TEMPLATE)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_keyboard_accessibility_behavior(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify keyboard accessibility")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_keyboard_behavior.js"), str(TEMPLATE)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_candle_access_performance_contract(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify candle-access behavior and work budgets")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_candle_performance.js"), str(TEMPLATE)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_history_workspace_behavior(self):
        node = shutil.which("node")
        if node is None:
            self.fail("Node.js is required to verify the history workspace")
        completed = subprocess.run(
            [node, str(Path(__file__).resolve().parent / "frontend_history_workspace.js"), str(TEMPLATE)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + "\n" + completed.stderr)

    def test_screener_results_are_numbered_and_keep_scroll(self):
        self.assertIn(".screener-result-index", self.html)
        self.assertIn("sequence.textContent = String(index + 1)", self.scripts)
        self.assertIn("const SCREENER_SCROLL_KEY = 'screener:results-scroll';", self.scripts)
        self.assertIn(
            "lsSetString(SCREENER_SCROLL_KEY, String(screenerResults.scrollTop))",
            self.scripts,
        )
        self.assertIn("screenerResults.scrollTop = target", self.scripts)
        self.assertIn("renderScreenerResults(screenerState.results, {restoreScroll: true})", self.scripts)

    def test_screener_reset_restores_defaults_and_clears_results(self):
        self.assertIn('id="screenerReset"', self.html)
        self.assertIn("const screenerReset = document.getElementById('screenerReset');", self.scripts)
        self.assertIn("screenerReset.addEventListener('click', resetScreener);", self.scripts)
        self.assertIn("saveScreenerState({filters: {}, results: null})", self.scripts)
        self.assertIn("const value = SCREENER_DEFAULTS[select.dataset.field];", self.scripts)
        self.assertIn("empty.textContent = '选择条件后点击确认';", self.scripts)
        self.assertIn("screenerReset.disabled = true;", self.scripts)

    def test_screener_marks_last_clicked_result(self):
        self.assertIn(".screener-result-latest", self.html)
        self.assertIn("const SCREENER_LAST_CLICKED_KEY = 'screener:last-clicked';", self.scripts)
        self.assertIn("const isLatest = Boolean(lastClickedCode) && item.code === lastClickedCode;", self.scripts)
        self.assertIn("lsSetString(SCREENER_LAST_CLICKED_KEY, item.code);", self.scripts)
        self.assertIn("latestTag.textContent = '最近';", self.scripts)
        self.assertIn("lsRemove(SCREENER_LAST_CLICKED_KEY);", self.scripts)

    def test_single_time_axis_and_range_stats(self):
        subchart = self.scripts[self.scripts.find("function createSubChart"):self.scripts.find("function buildSubSeries")]
        self.assertIn("visible: false, timeVisible: true", subchart)
        for marker in ("区间统计", "阳柱面积", "阴柱面积", "rangeDrag"):
            self.assertIn(marker, self.scripts)

    def test_gap_ma_and_layer_switches_work_across_frequencies(self):
        node = shutil.which("node")
        if node is None:
            self.fail("未找到 node，无法确认缺口、均线和图层开关")
        script = Path(__file__).resolve().parent / "frontend_switch_behavior.js"
        completed = subprocess.run(
            [node, str(script), str(TEMPLATE)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + "\n" + completed.stderr,
        )

    def test_distance_measure_contract(self):
        self.assertIn('id="toolDistance"', self.html)
        self.assertIn('id="toolRectangle"', self.html)
        self.assertIn("const color = '#7c4dff'", self.scripts)
        self.assertIn("shape.setAttribute('stroke', '#00838f')", self.scripts)
        self.assertIn("rectState.boxes.push", self.scripts)
        self.assertIn('id="toolTrend"', self.html)
        self.assertIn("line.setAttribute('stroke', '#111')", self.scripts)
        self.assertIn("trendState.lines.push", self.scripts)
        self.assertIn("trendState.lines.pop()", self.scripts)
        self.assertIn("undoLatestShape()", self.scripts)
        self.assertIn("shapeOrder.push('rect')", self.scripts)
        self.assertIn("shapeOrder.push('trend')", self.scripts)
        self.assertIn('id="toolFib"', self.html)
        self.assertIn("shapeOrder.push('fib')", self.scripts)
        self.assertIn("61.8%", self.scripts)
        self.assertIn("80.9%", self.scripts)
        self.assertIn("119.1%", self.scripts)
        self.assertIn("161.8%", self.scripts)
        self.assertIn("200.0%", self.scripts)
        self.assertIn("rectState.boxes.pop()", self.scripts)
        self.assertIn("measureState.enabled || measureState.start || measureState.end", self.scripts)
        self.assertIn("clearMeasure()", self.scripts)
        self.assertIn("周期 ${periods}", self.scripts)
        self.assertIn("涨跌 ${signedText", self.scripts)
        self.assertIn("幅度 ${signedText", self.scripts)

    def test_classification_component_shows_all_labels_without_controls(self):
        component = (TEMPLATE.parent / "_instrument_classification.html").read_text(encoding="utf-8")
        for marker in (
            'id="instrumentClassification"', 'id="classificationConceptTags"',
            'aria-label="当前标的全部概念标签"', 'role="list"',
            'classification-concept-heading', '概念数据缺失', '无有效概念',
        ):
            self.assertIn(marker, component)
        for removed in ("<details", "<summary", "展开全部", "收起", "classification-preview", "[:5]"):
            self.assertNotIn(removed, component)
        self.assertNotIn("| safe", component)
        self.assertNotIn("<script", component)

    def test_classification_labels_flow_with_the_existing_workspace_scroll(self):
        css = (TEMPLATE.parent.parent / "static/css/instrument-classification.css").read_text(encoding="utf-8")
        scroll = self.html.index('<div class="workspace-scroll">')
        component = self.html.index('{% include "_instrument_classification.html" %}')
        chart = self.html.index('<div id="chart">')
        self.assertLess(scroll, component)
        self.assertLess(component, chart)
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn("overflow-wrap: anywhere", css)
        self.assertNotIn("position: absolute", css)
        self.assertNotIn("max-height:", css)
        self.assertNotIn("overflow: auto", css)
        self.assertIn("max-width: 600px", css)


if __name__ == "__main__":
    unittest.main()
