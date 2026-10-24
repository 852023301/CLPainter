from __future__ import annotations

"""前端模板的静态回归检查。

这些断言锁定已经交付的交互，防止后续改动悄悄弄坏开关、布局和测量。
不启动浏览器，也不依赖行情数据。
"""

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
        ):
            self.assertIn(marker, self.html)

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
        self.assertIn("const color = '#7c4dff'", self.scripts)
        self.assertIn("measureState.enabled || measureState.start || measureState.end", self.scripts)
        self.assertIn("clearMeasure()", self.scripts)
        self.assertIn("周期 ${periods}", self.scripts)
        self.assertIn("涨跌 ${signedText", self.scripts)
        self.assertIn("幅度 ${signedText", self.scripts)


if __name__ == "__main__":
    unittest.main()
