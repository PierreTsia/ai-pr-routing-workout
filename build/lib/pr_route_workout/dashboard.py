"""One static page from the routing JSON, served on a free port."""

from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pr_route_workout.report import to_jsonable
from pr_route_workout.run import Result

_TONE = {
    "needs_author": "bad",
    "blocked": "bad",
    "ready_for_hitl": "warn",
    "agent_ready": "info",
    "waiting_for_checks": "info",
    "ready_for_merge": "ok",
    "unaddressed": "bad",
    "open": "bad",
    "disputed": "bad",
    "acknowledged": "warn",
    "addressed": "ok",
}


def _esc(value: object) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def _num(value: object) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value:.2f}"


def _tone(name: object) -> str:
    return _TONE.get(str(name), "")


def _fact_rows(facts: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key, value in facts.items():
        if key == "code_suffixes" and isinstance(value, list):
            shown = ", ".join(
                f"{item.get('suffix')} {item.get('count')}" for item in value
            )
            rows.append((key, shown or "—"))
        elif key == "files" and isinstance(value, list):
            rows.append((key, "\n".join(value) if value else "—"))
        elif isinstance(value, list):
            rows.append((key, ", ".join(str(item) for item in value) or "—"))
        elif isinstance(value, dict):
            choice = value.get("choice")
            confidence = value.get("confidence")
            rows.append((key, f"{choice} ({_num(confidence)})" if choice else "—"))
        else:
            rows.append((key, str(value)))
    return rows


def _primitive_value(row: dict[str, Any]) -> tuple[str, str]:
    kind = row.get("type")
    if kind == "choice":
        return str(row.get("choice") or "—"), ""
    if kind == "noul":
        value = row.get("noul")
        hot = isinstance(value, (int, float)) and value >= 0.6
        return _num(value), "warn" if hot else ""
    if kind == "score":
        value = row.get("score")
        hot = isinstance(value, (int, float)) and value >= 1.5
        return _num(value), "warn" if hot else ""
    return "—", ""


def _bars(rows: list[dict[str, Any]], field: str, scale: float, mark: float) -> str:
    usable = [row for row in rows if isinstance(row.get(field), (int, float))]
    if not usable:
        return ""
    mark_pct = mark / scale * 100
    title = "Noul" if field == "noul" else "Score"
    lines = [
        f"<h2>{title}</h2>",
        f'<p class="note">Axis 0–{_esc(scale)}. Mark at {_esc(mark)}.</p>',
    ]
    for row in usable:
        value = float(row[field])
        width = min(100.0, value / scale * 100)
        tone = "warn" if value >= mark else ""
        lines.append(
            "<div class='bar-row'>"
            f"<span class='bar-label'>{_esc(row.get('id'))}</span>"
            "<span class='bar-track'>"
            f"<span class='mark' style='left:{mark_pct:.2f}%'></span>"
            f"<span class='bar {tone}' style='width:{width:.2f}%'></span>"
            "</span>"
            f"<span class='bar-value {_esc(tone)}'>{_num(value)}</span>"
            "</div>"
        )
    return "\n".join(lines)


def render_page(payload: dict[str, Any]) -> str:
    pr = payload["pull_request"]
    disposition = payload["disposition"]
    judgments = payload["judgments"]
    pricing = payload["pricing"]
    usage = judgments.get("usage") or {}
    tone = _tone(disposition.get("value"))
    tokens = "—"
    if isinstance(usage.get("input_tokens"), int) and isinstance(usage.get("output_tokens"), int):
        tokens = f"{usage['input_tokens']} in / {usage['output_tokens']} out"
    list_cents = pricing.get("list_cents")
    billed_cents = pricing.get("billed_cents")
    facts = "".join(
        f"<tr><th>{_esc(key)}</th><td>{_esc(value)}</td></tr>"
        for key, value in _fact_rows(payload["facts"])
    )
    primitives = []
    for row in payload["fan_out"]:
        value, hot = _primitive_value(row)
        confidence = row.get("confidence")
        primitives.append(
            "<tr>"
            f"<td>{_esc(row.get('id'))}</td>"
            f"<td>{_esc(row.get('type'))}</td>"
            f"<td>{'yes' if row.get('speculative') else 'no'}</td>"
            f"<td class='num {_esc(hot)}'>{_esc(value)}</td>"
            f"<td class='num'>{_esc(_num(confidence) if confidence is not None else None)}</td>"
            "</tr>"
        )
    unscored = ""
    if judgments.get("source") == "unavailable":
        unscored = "<p class='note'>primitives not scored, no Zen key</p>"
    policies = []
    winning = disposition.get("policy_id")
    for row in payload["policies"]:
        matched = "yes" if row.get("matched") else "no"
        row_tone = _tone(row.get("disposition")) if row.get("matched") and row.get("id") == winning else ""
        policies.append(
            f"<tr class='{_esc(row_tone)}'>"
            f"<td>{_esc(row.get('id'))}</td>"
            f"<td>{_esc(row.get('disposition'))}</td>"
            f"<td>{matched}</td>"
            "</tr>"
        )
    clauses = []
    for row in payload["policy_clauses"]:
        held = "yes" if row.get("holds") else "no"
        row_tone = _tone(disposition.get("value")) if row.get("holds") and row.get("policy") == winning else ""
        clauses.append(
            f"<tr class='{_esc(row_tone)}'>"
            f"<td>{_esc(row.get('policy'))}</td>"
            f"<td>{_esc(row.get('clause'))}</td>"
            f"<td>{held}</td>"
            "</tr>"
        )
    review = payload["ai_review"]
    task = ""
    if review.get("task"):
        skills = "".join(
            f"<tr><td>{_esc(skill.get('id'))}</td><td class='num'>{_esc(_num(skill.get('noul')))}</td></tr>"
            for skill in review.get("skills") or []
        )
        task = (
            "<h2>Agent task</h2>"
            f"<p class='task'>{_esc(review.get('task'))}</p>"
            f"<table><thead><tr><th>Skill</th><th>Noul</th></tr></thead><tbody>{skills}</tbody></table>"
        )
    threads = ""
    if payload["review_threads"]:
        body = []
        for row in payload["review_threads"]:
            body.append(
                f"<tr class='{_esc(_tone(row.get('verdict')))}'>"
                f"<td>{_esc(row.get('source'))}</td>"
                f"<td>{_esc(row.get('verdict'))}</td>"
                f"<td>{_esc(row.get('stance'))}</td>"
                f"<td class='num'>{_esc(_num(row.get('addressed_noul')))}</td>"
                f"<td>{_esc(row.get('later_commit_sha'))}</td>"
                f"<td>{_esc(row.get('path'))}</td>"
                f"<td>{_esc(row.get('excerpt'))}</td>"
                "</tr>"
            )
        threads = (
            "<h2>Review threads</h2>"
            "<table><thead><tr><th>Source</th><th>Verdict</th><th>Stance</th>"
            "<th>Addressed</th><th>Later commit</th><th>Path</th><th>Excerpt</th></tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table>"
        )
    left_out = payload.get("fan_out_truncated") or 0
    truncated = f"<p class='note'>{left_out} review threads left out of the fan-out cap</p>" if left_out else ""
    title = f"{pr.get('repo')}#{pr.get('number')}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; font: 14px/1.45 ui-sans-serif, system-ui, sans-serif; color: #1a1a1a; background: #fff; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 28px 24px 64px; }}
  h1 {{ font-size: 22px; margin: 0; }}
  h2 {{ font-size: 15px; margin: 28px 0 8px; }}
  a {{ color: inherit; }}
  .meta {{ color: #666; font-size: 12px; }}
  .stats {{ display: flex; gap: 16px; margin-top: 20px; }}
  .stat {{ flex: 1; min-width: 0; }}
  .stat b {{ display: block; font-size: 18px; overflow-wrap: anywhere; }}
  .stat span {{ color: #666; font-size: 12px; }}
  .bad {{ color: #b42318; }}
  .warn {{ color: #b54708; }}
  .info {{ color: #175cd3; }}
  .ok {{ color: #067647; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid #e6e6e6; }}
  th {{ font-weight: 600; color: #444; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.bad td:first-child, tr.warn td:first-child, tr.info td:first-child, tr.ok td:first-child {{ font-weight: 600; }}
  .task {{ font-size: 16px; margin: 0 0 8px; }}
  .note {{ color: #666; font-size: 12px; }}
  .bar-row {{ display: grid; grid-template-columns: 220px 1fr 48px; gap: 8px; align-items: center; margin: 4px 0; }}
  .bar-label {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .bar-track {{ position: relative; height: 10px; background: #f2f2f2; }}
  .bar {{ position: relative; display: block; height: 10px; background: #444; }}
  .bar.warn {{ background: #b54708; }}
  .mark {{ position: absolute; top: -3px; width: 1px; height: 16px; background: #b54708; }}
  .bar-value {{ text-align: right; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<main>
  <h1>{_esc(title)}</h1>
  <p>{_esc(pr.get("title"))}</p>
  <p class="meta">{_esc(judgments.get("model") or judgments.get("source"))} · {_esc(tokens)} · <a href="{_esc(pr.get("url"))}">pull request</a></p>
  <div class="stats">
    <div class="stat"><b class="{tone}">{_esc(disposition.get("value"))}</b><span>Disposition</span></div>
    <div class="stat"><b class="{tone}">{_esc(disposition.get("policy_id"))}</b><span>Policy</span></div>
    <div class="stat"><b>{_esc(None if list_cents is None else f"{list_cents:.3f}¢")}</b><span>List price</span></div>
    <div class="stat"><b>{_esc(None if billed_cents is None else f"{billed_cents:.3f}¢")}</b><span>Billed</span></div>
  </div>
  {task}
  <h2>Facts</h2>
  <table><tbody>{facts}</tbody></table>
  <h2>Primitives</h2>
  {unscored}
  <table>
    <thead><tr><th>Question</th><th>Kind</th><th>Speculative</th><th class="num">Value</th><th class="num">Confidence</th></tr></thead>
    <tbody>{''.join(primitives)}</tbody>
  </table>
  {_bars(payload["fan_out"], "noul", 1, 0.6)}
  {_bars(payload["fan_out"], "score", 3, 1.5)}
  <h2>Policies</h2>
  <table>
    <thead><tr><th>Policy</th><th>Disposition</th><th>Matched</th></tr></thead>
    <tbody>{''.join(policies)}</tbody>
  </table>
  <table>
    <thead><tr><th>Policy</th><th>Clause</th><th>Holds</th></tr></thead>
    <tbody>{''.join(clauses)}</tbody>
  </table>
  {threads}
  {truncated}
</main>
</body>
</html>
"""


def render_dashboard(result: Result) -> str:
    return render_page(to_jsonable(result))


class _Handler(BaseHTTPRequestHandler):
    page = b""

    def do_GET(self) -> None:
        body = self.page
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def serve(page: str) -> ThreadingHTTPServer:
    handler = type("PageHandler", (_Handler,), {"page": page.encode("utf-8")})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    return server