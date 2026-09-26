"""One canvas, same sections every run. Values come from the result. No commentary."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pr_route_workout.facts import make_facts
from pr_route_workout.policies import POLICIES, policy_clauses
from pr_route_workout.run import Result

# OpenCode Zen list price for jev-1.13. Output tokens are not billed.
LIST_INPUT_USD_PER_MILLION = 0.042

_TEMPLATE = """import {{ BarChart, H1, H2, Link, Row, Stack, Stat, Table, Text }} from "cursor/canvas";

type QuestionRow = {{
  id: string;
  kind: string;
  speculative: boolean;
  value: string;
  confidence: string;
  noul: number | null;
  score: number | null;
}};

type Run = {{
  repo: string;
  number: number;
  url: string;
  title: string;
  model: string;
  disposition: string;
  policyId: string;
  listPriceCents: string;
  billedCents: string;
  tokens: string;
  facts: string[][];
  questions: QuestionRow[];
  clauses: string[][];
  clauseHeld: boolean[];
  policies: string[][];
  threads: string[][];
  task: string | null;
  skills: string[][];
  noulChartHeight: number;
  scoreChartHeight: number;
}};

const RUN: Run = {payload};

function dispositionTone(disposition: string): "success" | "danger" | "warning" | "info" {{
  if (disposition === "needs_author" || disposition === "blocked") return "danger";
  if (disposition === "ready_for_hitl") return "warning";
  if (disposition === "agent_ready" || disposition === "waiting_for_checks") return "info";
  return "success";
}}

function primitiveTone(question: QuestionRow): "warning" | undefined {{
  if (question.noul !== null && question.noul >= 0.6) return "warning";
  if (question.score !== null && question.score >= 1.5) return "warning";
  return undefined;
}}

function threadTone(row: string[]): "danger" | "warning" | "success" | "info" | undefined {{
  const verdict = row[3];
  if (verdict === "unaddressed" || verdict === "open" || verdict === "disputed") return "danger";
  if (verdict === "acknowledged") return "warning";
  if (verdict === "addressed") return "success";
  if (verdict.endsWith("unscored")) return "info";
  return undefined;
}}

export default function PrRoute() {{
  const nouls = RUN.questions.filter((question) => question.noul !== null);
  const scores = RUN.questions.filter((question) => question.score !== null);
  const decisionTone = dispositionTone(RUN.disposition);
  const noulHigh = nouls.map((question) => ((question.noul ?? 0) >= 0.6 ? question.noul ?? 0 : 0));
  const noulLow = nouls.map((question) => ((question.noul ?? 0) >= 0.6 ? 0 : question.noul ?? 0));
  const scoreHigh = scores.map((question) => ((question.score ?? 0) >= 1.5 ? question.score ?? 0 : 0));
  const scoreLow = scores.map((question) => ((question.score ?? 0) >= 1.5 ? 0 : question.score ?? 0));
  return (
    <Stack gap={{24}}>
      <Stack gap={{6}}>
        <H1>
          {{RUN.repo}}#{{RUN.number}}
        </H1>
        <Text>{{RUN.title}}</Text>
        <Text size="small" tone="tertiary">
          {{RUN.model}} · {{RUN.tokens}} · <Link href={{RUN.url}}>pull request</Link>
        </Text>
      </Stack>

      <Row gap={{24}} align="end">
        <Stat value={{RUN.disposition}} label="Disposition" tone={{decisionTone}} />
        <Stat value={{RUN.policyId}} label="Policy" tone={{decisionTone}} />
        <Stat value={{RUN.listPriceCents}} label="List price" />
        <Stat value={{RUN.billedCents}} label="Billed" />
      </Row>

      {{RUN.task ? (
        <Stack gap={{8}}>
          <H2>Agent task</H2>
          <Text>{{RUN.task}}</Text>
          <Table headers={{["Skill", "Noul"]}} rows={{RUN.skills}} />
        </Stack>
      ) : null}}

      <Stack gap={{8}}>
        <H2>Facts</H2>
        <Table headers={{["Fact", "Value"]}} rows={{RUN.facts}} />
      </Stack>

      <Stack gap={{8}}>
        <H2>Primitives</H2>
        <Text size="small" tone="tertiary">
          Warning marks a Noul at or above 0.6, or a score at or above 1.5.
        </Text>
        <Table
          headers={{["Question", "Kind", "Speculative", "Value", "Confidence"]}}
          columnAlign={{["left", "left", "left", "right", "right"]}}
          rows={{RUN.questions.map((question) => [
            question.id,
            question.kind,
            question.speculative ? "yes" : "no",
            question.value,
            question.confidence,
          ])}}
          rowTone={{RUN.questions.map(primitiveTone)}}
          striped
          stickyHeader
        />
      </Stack>

      {{nouls.length > 0 ? (
        <Stack gap={{8}}>
          <H2>Noul</H2>
          <Text size="small" tone="tertiary">
            Category axis: question. Value axis: Noul (0–1). Reference line: 0.6. Bars at or above 0.6 are warning. Source: fan-out answers.
          </Text>
          <BarChart
            horizontal
            stacked
            height={{RUN.noulChartHeight}}
            yMax={{1}}
            showValues
            categories={{nouls.map((question) => question.id)}}
            series={{[
              {{ name: "Noul ≥ 0.6", tone: "warning", data: noulHigh }},
              {{ name: "Noul < 0.6", tone: "neutral", data: noulLow }},
            ]}}
            referenceLines={{[{{ value: 0.6, label: "0.6", tone: "warning" }}]}}
          />
        </Stack>
      ) : null}}

      {{scores.length > 0 ? (
        <Stack gap={{8}}>
          <H2>Score</H2>
          <Text size="small" tone="tertiary">
            Category axis: question. Value axis: score (0–3). Reference line: 1.5. Bars at or above 1.5 are warning. Source: fan-out answers.
          </Text>
          <BarChart
            stacked
            height={{RUN.scoreChartHeight}}
            yMax={{3}}
            showValues
            categories={{scores.map((question) => question.id)}}
            series={{[
              {{ name: "Score ≥ 1.5", tone: "warning", data: scoreHigh }},
              {{ name: "Score < 1.5", tone: "neutral", data: scoreLow }},
            ]}}
            referenceLines={{[{{ value: 1.5, label: "1.5", tone: "warning" }}]}}
          />
        </Stack>
      ) : null}}

      <Stack gap={{8}}>
        <H2>Policies</H2>
        <Table
          headers={{["Policy", "Disposition", "Matched"]}}
          rows={{RUN.policies}}
          rowTone={{RUN.policies.map((row): "success" | "danger" | "warning" | "info" | undefined => {{
            if (row[2] !== "yes") return undefined;
            if (row[0] === RUN.policyId) return decisionTone;
            return "info";
          }})}}
        />
        <Table
          headers={{["Policy", "Clause", "Holds"]}}
          rows={{RUN.clauses}}
          rowTone={{RUN.clauses.map((row, index): "success" | "danger" | "warning" | "info" | "neutral" => {{
            if (!RUN.clauseHeld[index]) return "neutral";
            if (row[0] === RUN.policyId) return decisionTone;
            return "info";
          }})}}
        />
      </Stack>

      {{RUN.threads.length > 0 ? (
        <Stack gap={{8}}>
          <H2>Review threads</H2>
          <Table
            headers={{["Source", "Id", "Path", "Verdict", "Stance", "Addressed", "Replied", "Later commit"]}}
            rows={{RUN.threads}}
            rowTone={{RUN.threads.map(threadTone)}}
            striped
          />
        </Stack>
      ) : null}}
    </Stack>
  );
}}
"""

def list_price_cents(usage: dict[str, Any] | None) -> float | None:
    if not usage:
        return None
    tokens = usage.get("input_tokens")
    if not isinstance(tokens, (int, float)):
        return None
    return float(tokens) * LIST_INPUT_USD_PER_MILLION / 1_000_000 * 100


def canvas_destination() -> Path:
    override = os.environ.get("PR_ROUTE_CANVAS")
    if override:
        return Path(override)
    slug = str(Path.cwd().resolve()).lstrip("/").replace("/", "-")
    return Path.home() / ".cursor" / "projects" / slug / "canvases" / "pr-route.canvas.tsx"


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _question_payload(result: Result) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for question in result.questions:
        answer = None if result.answers is None else result.answers.by_id.get(question.id)
        choice = answer.choice if answer else None
        confidence = answer.confidence if answer else None
        noul = answer.noul if answer else None
        score = answer.score if answer else None
        if question.kind == "choice":
            value = choice or "—"
        elif question.kind == "noul":
            value = _fmt_number(noul)
        elif question.kind == "score":
            value = _fmt_number(score)
        else:
            value = "—"
        rows.append(
            {
                "id": question.id,
                "kind": question.kind,
                "speculative": question.speculative,
                "value": value,
                "confidence": _fmt_number(confidence),
                "noul": noul,
                "score": score,
            }
        )
    return rows


def _payload(result: Result) -> dict[str, Any]:
    pr = result.pull_request
    facts = make_facts(
        author_login=pr.author,
        checks=pr.checks,
        draft=pr.draft,
        jira_keys=result.jira_keys,
        files=pr.files,
    )
    cents = list_price_cents(result.usage)
    billed = 0.0 if result.model and "free" in result.model else cents
    usage = result.usage or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    tokens = "—"
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        tokens = f"{input_tokens} in / {output_tokens} out"
    code = ", ".join(f"{suffix} {count}" for suffix, count in facts.code_suffixes) or "—"
    clauses = policy_clauses(facts, result.answers)
    known = {policy.id for policy in POLICIES}
    policies = [
        [policy.id, policy.disposition.value, "yes" if policy.id in result.decision.matched_policy_ids else "no"]
        for policy in POLICIES
    ]
    for policy_id in result.decision.matched_policy_ids:
        if policy_id not in known:
            policies.append([policy_id, "—", "yes"])
    questions = _question_payload(result)
    noul_count = sum(1 for question in questions if question["noul"] is not None)
    score_count = sum(1 for question in questions if question["score"] is not None)
    return {
        "repo": pr.repo,
        "number": pr.number,
        "url": pr.url,
        "title": pr.title,
        "model": result.model or result.judgments,
        "disposition": result.decision.disposition.value,
        "policyId": result.decision.policy_id or "—",
        "listPriceCents": "—" if cents is None else f"{cents:.3f}¢",
        "billedCents": "—" if billed is None else f"{billed:.3f}¢",
        "tokens": tokens,
        "facts": [
            ["checks", f"{facts.checks.value} ({pr.check_summary})"],
            ["author", pr.author],
            ["draft", str(pr.draft).lower()],
            ["jira", ", ".join(facts.jira_keys) or "—"],
            ["files", str(len(facts.files))],
            ["code", code],
            ["path_domains", ", ".join(facts.path_domains) or "—"],
            ["ui_path", str(facts.ui_path).lower()],
            ["frontend_code_only", str(facts.frontend_code_only).lower()],
            ["touches_frontend_code", str(facts.touches_frontend_code).lower()],
            ["dependency_manifest_only", str(facts.dependency_manifest_only).lower()],
            ["docs_only", str(facts.docs_only).lower()],
        ],
        "questions": questions,
        "clauses": [[policy_id, text, "yes" if held else "no"] for policy_id, text, held in clauses],
        "clauseHeld": [held for _policy_id, _text, held in clauses],
        "policies": policies,
        "threads": [
            [
                row.source,
                str(row.thread_id),
                row.path,
                row.verdict,
                row.stance or "—",
                _fmt_number(row.addressed_noul),
                "yes" if row.replied else "no",
                row.later_commit_sha or "—",
            ]
            for row in result.thread_rows
        ],
        "task": result.review.task,
        "skills": [
            [skill.id, _fmt_number(skill.noul)] for skill in result.review.skills
        ],
        "noulChartHeight": max(180, 26 * max(noul_count, 1)),
        "scoreChartHeight": 220,
    }


def render_canvas(result: Result) -> str:
    payload = json.dumps(_payload(result), ensure_ascii=False, indent=2)
    return _TEMPLATE.format(payload=payload)


def write_canvas(result: Result) -> Path:
    path = canvas_destination()
    path.write_text(render_canvas(result), encoding="utf-8")
    return path