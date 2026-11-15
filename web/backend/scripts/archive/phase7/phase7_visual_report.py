"""Phase 7 可视化验收报告生成器。

为每个案例生成 old/new 两张并排图，并附线段表和违规列表。
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from CLPainter.web.backend.app.toolbox.datacube import load_data_cache_pickle  # noqa: E402

logger = logging.getLogger(__name__)
STATIC_JS = BACKEND_DIR / "app" / "static" / "js" / "lightweight-charts.standalone.production.js"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 7 可视化验收报告")
    parser.add_argument("--old-dump-dir", type=Path, required=True)
    parser.add_argument("--new-dump-dir", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--old-audit", type=Path)
    parser.add_argument("--new-audit", type=Path)
    return parser.parse_args()


def load_cases(path: Path) -> list[dict]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def load_audit(path: Path | None) -> dict[str, dict]:
    if path is None or not path.exists():
        return {}
    result = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            result[item["path"]] = item
    return result


def _xd_rows(cache) -> list[dict]:
    rows = []
    for segment in cache.xian_duan_list or []:
        rows.append(
            {
                "key": (
                    str(segment.start_time),
                    str(segment.end_time),
                    "up" if segment.is_up() else "down",
                    type(segment).__name__,
                    int(segment.start_bi_idx),
                    int(segment.end_bi_idx),
                ),
                "start": str(segment.start_time.date()),
                "end": str(segment.end_time.date()),
                "direction": "up" if segment.is_up() else "down",
                "type": type(segment).__name__,
                "start_bi": int(segment.start_bi_idx),
                "end_bi": int(segment.end_bi_idx),
            }
        )
    return rows


def _bi_segments(cache) -> list[dict]:
    rows = []
    for bi in cache.bi_list or []:
        rows.append(
            {
                "key": (
                    str(bi.start_time),
                    str(bi.end_time),
                    bi.bi_type.value,
                    round(float(bi.start_price), 8),
                    round(float(bi.end_price), 8),
                    int(bi.start_idx),
                    int(bi.end_idx),
                    type(bi).__name__,
                ),
                "start_time": str(bi.start_time.date()),
                "start_price": float(bi.start_price),
                "end_time": str(bi.end_time.date()),
                "end_price": float(bi.end_price),
            }
        )
    return rows


def _xd_segments(cache) -> list[dict]:
    rows = []
    for segment in cache.xian_duan_list or []:
        rows.append(
            {
                "key": (
                    str(segment.start_time),
                    str(segment.end_time),
                    "up" if segment.is_up() else "down",
                    type(segment).__name__,
                    int(segment.start_bi_idx),
                    int(segment.end_bi_idx),
                ),
                "start_time": str(segment.start_time.date()),
                "start_price": float(segment.start_price),
                "end_time": str(segment.end_time.date()),
                "end_price": float(segment.end_price),
            }
        )
    return rows


def _precision(asset_class: str) -> int:
    return 2 if asset_class == "asset_class=stock" else 3


def _json_for_script(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _earliest_change_time(old_rows: list[dict], new_rows: list[dict]) -> str:
    old_keys = {row["key"] for row in old_rows}
    new_keys = {row["key"] for row in new_rows}
    changed_times = [
        row["start"] for row in old_rows if row["key"] not in new_keys
    ] + [
        row["start"] for row in new_rows if row["key"] not in old_keys
    ]
    if changed_times:
        return min(changed_times)
    return new_rows[0]["start"] if new_rows else ""


def _segment_table(old_rows: list[dict], new_rows: list[dict]) -> str:
    old_keys = {row["key"] for row in old_rows}
    max_len = max(len(old_rows), len(new_rows))
    lines = [
        "<table class='segments'>",
        "<thead><tr><th>#</th><th>Old</th><th>New</th><th>Changed</th></tr></thead><tbody>",
    ]
    for index in range(max_len):
        old = old_rows[index] if index < len(old_rows) else None
        new = new_rows[index] if index < len(new_rows) else None
        old_text = (
            f"{old['start']} → {old['end']} {old['direction']} {old['type']} "
            f"[{old['start_bi']},{old['end_bi']}]"
            if old
            else "-"
        )
        new_text = (
            f"{new['start']} → {new['end']} {new['direction']} {new['type']} "
            f"[{new['start_bi']},{new['end_bi']}]"
            if new
            else "-"
        )
        changed = new is not None and new["key"] not in old_keys
        cls = " class='changed'" if changed else ""
        lines.append(
            f"<tr{cls}><td>{index}</td><td>{old_text}</td><td>{new_text}</td>"
            f"<td>{'yes' if changed else ''}</td></tr>"
        )
    lines.append("</tbody></table>")
    return "\n".join(lines)


def _violation_list(label: str, audit: dict | None) -> str:
    if not audit:
        return f"<p><b>{label}</b>: 无审计数据</p>"
    bi = [item["code"] for item in audit.get("bi_violations", [])]
    xd = [item["code"] for item in audit.get("xd_violations", [])]
    return (
        f"<p><b>{label} bi</b>: {', '.join(bi) if bi else '无'}</p>"
        f"<p><b>{label} xd</b>: {', '.join(xd) if xd else '无'}</p>"
    )


CASE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<script src="lightweight-charts.standalone.production.js"></script>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 16px; color: #222; }
h1 { font-size: 20px; }
h2 { font-size: 16px; margin: 8px 0; }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chart { width: 100%; height: 520px; border: 1px solid #ddd; }
table.segments { border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 12px; }
table.segments th, table.segments td { border: 1px solid #ddd; padding: 4px 6px; text-align: left; vertical-align: top; }
table.segments tr.changed { background: #fff3cd; }
.meta { color: #666; font-size: 13px; }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<p class="meta">path: __PATH__ | status: __STATUS__</p>
<p class="legend">
  <span style="color:#2962ff">笔</span> ·
  <span style="color:#ff0000">Old 线段</span> ·
  <span style="color:#00a000">New 线段</span> ·
  <span style="color:#ff9800;font-weight:bold">变化线段</span> ·
  <span style="color:#9c27b0;font-weight:bold">变化笔</span>
</p>
<div class="charts">
  <div><h2>Old</h2><div id="old" class="chart"></div></div>
  <div><h2>New</h2><div id="new" class="chart"></div></div>
</div>
__OLD_VIOLATIONS__
__NEW_VIOLATIONS__
__SEGMENT_TABLE__
<script>
const oldPayload = __OLD_PAYLOAD__;
const newPayload = __NEW_PAYLOAD__;
const oldChangedBi = __OLD_CHANGED_BI__;
const newChangedBi = __NEW_CHANGED_BI__;
const oldChangedXd = __OLD_CHANGED_XD__;
const newChangedXd = __NEW_CHANGED_XD__;
const focusTime = __FOCUS_TIME__;
function addChangedSegments(chart, segments, color) {
  (segments || []).forEach(seg => {
    const series = chart.addLineSeries({
      color: color,
      lineWidth: 3,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    series.setData([
      { time: seg.start_time, value: seg.start_price },
      { time: seg.end_time, value: seg.end_price },
    ]);
  });
}
function drawChart(id, payload, xdColor, changedBi, changedXd) {
  const container = document.getElementById(id);
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 520,
    layout: { background: { color: '#ffffff' }, textColor: '#333' },
    grid: { vertLines: { color: '#eeeeee' }, horzLines: { color: '#eeeeee' } },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { visible: true },
  });
  const candle = chart.addCandlestickSeries({
    upColor: '#ef5350', downColor: '#26a69a', borderVisible: false,
    wickUpColor: '#ef5350', wickDownColor: '#26a69a',
  });
  candle.setData(payload.candle_data || []);
  const bi = chart.addLineSeries({ color: 'rgba(41,98,255,0.8)', lineWidth: 1 });
  bi.setData((payload.bi_data || []).slice().sort((a,b) => new Date(a.time) - new Date(b.time)));
  const xd = chart.addLineSeries({ color: xdColor, lineWidth: 2 });
  xd.setData((payload.xd_data || []).slice().sort((a,b) => new Date(a.time) - new Date(b.time)));
  addChangedSegments(chart, changedBi, '#9c27b0');
  addChangedSegments(chart, changedXd, '#ff9800');
  const candleData = payload.candle_data || [];
  const focusIndex = focusTime
    ? candleData.findIndex(item => String(item.time) === String(focusTime))
    : -1;
  if (focusIndex >= 0) {
    chart.timeScale().setVisibleLogicalRange({
      from: Math.max(0, focusIndex - 40),
      to: focusIndex + 160,
    });
  } else {
    chart.timeScale().fitContent();
  }
  return chart;
}
drawChart('old', oldPayload, 'rgba(255,0,0,0.75)', oldChangedBi, oldChangedXd);
drawChart('new', newPayload, 'rgba(0,160,0,0.85)', newChangedBi, newChangedXd);
</script>
</body>
</html>"""


def build_case_html(case: dict, old_cache, new_cache, old_audit, new_audit) -> str:
    precision = _precision(case["asset_class"])
    old_full = old_cache.build_chart_payload(precision=precision)
    new_full = new_cache.build_chart_payload(precision=precision)
    old_payload = {
        "candle_data": json.loads(old_full["candle_data"]),
        "bi_data": json.loads(old_full["bi_data"]),
        "xd_data": json.loads(old_full["xd_data"]),
    }
    new_payload = {
        "candle_data": json.loads(new_full["candle_data"]),
        "bi_data": json.loads(new_full["bi_data"]),
        "xd_data": json.loads(new_full["xd_data"]),
    }
    old_rows = _xd_rows(old_cache)
    new_rows = _xd_rows(new_cache)
    focus_time = _earliest_change_time(old_rows, new_rows)
    old_bi_segments = _bi_segments(old_cache)
    new_bi_segments = _bi_segments(new_cache)
    old_xd_segments = _xd_segments(old_cache)
    new_xd_segments = _xd_segments(new_cache)
    old_bi_keys = {row["key"] for row in old_bi_segments}
    new_bi_keys = {row["key"] for row in new_bi_segments}
    old_xd_keys = {row["key"] for row in old_xd_segments}
    new_xd_keys = {row["key"] for row in new_xd_segments}
    old_changed_bi = [row for row in old_bi_segments if row["key"] not in new_bi_keys]
    new_changed_bi = [row for row in new_bi_segments if row["key"] not in old_bi_keys]
    old_changed_xd = [row for row in old_xd_segments if row["key"] not in new_xd_keys]
    new_changed_xd = [row for row in new_xd_segments if row["key"] not in old_xd_keys]
    title = f"{case['symbol']} {case['frequency']} {case['asset_class']} [{case['group']}]"
    html = CASE_TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__PATH__", case["path"])
    html = html.replace("__STATUS__", case["status"])
    html = html.replace("__OLD_VIOLATIONS__", _violation_list("Old", old_audit))
    html = html.replace("__NEW_VIOLATIONS__", _violation_list("New", new_audit))
    html = html.replace("__SEGMENT_TABLE__", _segment_table(old_rows, new_rows))
    html = html.replace("__OLD_PAYLOAD__", _json_for_script(old_payload))
    html = html.replace("__NEW_PAYLOAD__", _json_for_script(new_payload))
    html = html.replace("__OLD_CHANGED_BI__", _json_for_script(old_changed_bi))
    html = html.replace("__NEW_CHANGED_BI__", _json_for_script(new_changed_bi))
    html = html.replace("__OLD_CHANGED_XD__", _json_for_script(old_changed_xd))
    html = html.replace("__NEW_CHANGED_XD__", _json_for_script(new_changed_xd))
    html = html.replace("__FOCUS_TIME__", _json_for_script(focus_time))
    return html


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = parse_args()
    cases = load_cases(args.cases)
    old_audit = load_audit(args.old_audit)
    new_audit = load_audit(args.new_audit)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for stale_case in args.output_dir.glob("case_*.html"):
        stale_case.unlink()
    if STATIC_JS.exists():
        shutil.copy(STATIC_JS, args.output_dir / STATIC_JS.name)

    index_items = []
    for index, case in enumerate(cases):
        try:
            old_cache = load_data_cache_pickle(
                case["symbol"],
                case["frequency"],
                case["market"],
                case["asset_class"],
                args.old_dump_dir,
            )
            new_cache = load_data_cache_pickle(
                case["symbol"],
                case["frequency"],
                case["market"],
                case["asset_class"],
                args.new_dump_dir,
            )
            html = build_case_html(
                case,
                old_cache,
                new_cache,
                old_audit.get(case["path"]),
                new_audit.get(case["path"]),
            )
            filename = f"case_{index:04d}.html"
            (args.output_dir / filename).write_text(html, encoding="utf-8")
            index_items.append((case, filename))
        except Exception as error:
            logger.exception("生成失败: %s: %s", case.get("path"), error)

    index_lines = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>",
        "<title>Phase 7 可视化验收</title>",
        "<style>body{font-family:sans-serif;margin:20px}table{border-collapse:collapse;width:100%}",
        "th,td{border:1px solid #ddd;padding:6px;text-align:left}tr:hover{background:#f5f5f5}",
        "a{color:#0969da;text-decoration:none}</style></head><body>",
        "<h1>Phase 7 可视化验收</h1>",
        "<p>Old: " + str(args.old_dump_dir) + "<br>New: " + str(args.new_dump_dir) + "</p>",
        "<table><thead><tr><th>#</th><th>Symbol</th><th>Frequency</th><th>Asset</th><th>Group</th><th>Status</th><th>Link</th></tr></thead><tbody>",
    ]
    for index, (case, filename) in enumerate(index_items):
        index_lines.append(
            f"<tr><td>{index}</td><td>{case['symbol']}</td><td>{case['frequency']}</td>"
            f"<td>{case['asset_class']}</td><td>{case['group']}</td><td>{case['status']}</td>"
            f"<td><a href='{filename}'>查看</a></td></tr>"
        )
    index_lines.append("</tbody></table></body></html>")
    (args.output_dir / "index.html").write_text("\n".join(index_lines), encoding="utf-8")
    logger.info("生成完成: %d 个案例，输出 %s", len(index_items), args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
