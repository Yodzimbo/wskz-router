"""Routing accuracy on the running compose stack, black-box: HTTP to the API, e-mails from Mailpit.

Each case gets its own sender address, so its e-mail is found by Reply-To without clearing the
inbox. Writes eval/results/<date>-<model>[-<label>].json and prints a markdown summary.

Usage: .venv/bin/python eval/run_eval.py [--repeat N] [--cases FILE] [--label NAME]
"""

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
API_URL = os.environ.get("API_URL", "http://localhost:8000")
MAILPIT_URL = os.environ.get("MAILPIT_URL", "http://localhost:8025")
# Above AGENT_TIMEOUT_S (60 s): a slow answer should come back as 504 from the API, not die here.
API_TIMEOUT_S = 120
MAIL_WAIT_S = 10
ERROR = "error"


@dataclass(frozen=True)
class Case:
    id: str
    message: str
    expected: str
    kind: str


@dataclass
class Result:
    case_id: str
    kind: str
    run: int
    expected: str
    status: int | None
    recipient: str | None
    fallback_used: bool | None
    seconds: float
    mails: int
    mail_to: list[str]
    mail_reply_to: list[str]
    mail_matches: bool
    error: str | None = None

    @property
    def got(self) -> str:
        return self.recipient if self.status == 200 and self.recipient else ERROR

    @property
    def correct(self) -> bool:
        return self.got == self.expected


def load_cases(path: Path) -> list[Case]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Case(**json.loads(line)) for line in lines if line.strip()]


def compose_model() -> str:
    """OLLAMA_MODEL as compose resolves it for the api service; 'unknown' instead of guessing."""
    try:
        output = subprocess.run(
            ["docker", "compose", "config", "--format", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return str(json.loads(output)["services"]["api"]["environment"]["OLLAMA_MODEL"])
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        return "unknown"


def git_commit() -> str:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    commit = git("rev-parse", "--short", "HEAD") or "unknown"
    # Uncommitted prompt changes make the result incomparable with the commit alone.
    return f"{commit}-dirty" if git("status", "--porcelain", "app") else commit


def departments(api: httpx.Client) -> list[str]:
    """The department enum as the API publishes it (OpenAPI), so the eval needs no copy of it."""
    response = api.get("/api/v1/openapi.json")
    response.raise_for_status()
    enum: list[str] = response.json()["components"]["schemas"]["Department"]["enum"]
    return enum


def addresses(field: list[dict[str, str]] | None) -> list[str]:
    return [entry["Address"].lower() for entry in field or []]


def mails_replying_to(mailpit: httpx.Client, sender: str) -> list[dict[str, Any]]:
    # Mailpit's reply-to: filter matches a substring, so the exact match is checked here.
    response = mailpit.get("/search", params={"query": f'reply-to:"{sender}"'})
    response.raise_for_status()
    messages: list[dict[str, Any]] = response.json()["messages"]
    return [m for m in messages if sender in addresses(m.get("ReplyTo"))]


def wait_for_mails(mailpit: httpx.Client, sender: str, expect_mail: bool) -> list[dict[str, Any]]:
    deadline = time.monotonic() + (MAIL_WAIT_S if expect_mail else 0)
    while not (found := mails_replying_to(mailpit, sender)) and time.monotonic() < deadline:
        time.sleep(0.5)
    return found


def run_case(api: httpx.Client, mailpit: httpx.Client, case: Case, run: int) -> Result:
    sender = f"eval-{case.id}-{uuid.uuid4().hex[:8]}@example.com"
    started = time.perf_counter()
    status: int | None = None
    body: dict[str, Any] = {}
    error: str | None = None
    try:
        response = api.post("/api/v1/messages", json={"email": sender, "message": case.message})
        status = response.status_code
        body = response.json()
        if status != 200:
            error = str(body.get("error", status))
    except (httpx.HTTPError, ValueError) as exc:  # ValueError: a non-JSON error page
        error = type(exc).__name__
    seconds = round(time.perf_counter() - started, 2)

    mails = wait_for_mails(mailpit, sender, expect_mail=status == 200)
    mail_to = addresses(mails[0]["To"]) if len(mails) == 1 else []
    mail_reply_to = addresses(mails[0].get("ReplyTo")) if len(mails) == 1 else []
    recipient = body.get("recipient") if status == 200 else None
    # DoD 4 and 6: exactly one e-mail, sent where the API says, replying to the sender.
    matches = (
        len(mails) == 1 and mail_to == [recipient] and mail_reply_to == [sender]
        if status == 200
        else not mails
    )
    return Result(
        case_id=case.id,
        kind=case.kind,
        run=run,
        expected=case.expected,
        status=status,
        recipient=recipient,
        fallback_used=body.get("fallback_used") if status == 200 else None,
        seconds=seconds,
        mails=len(mails),
        mail_to=mail_to,
        mail_reply_to=mail_reply_to,
        mail_matches=matches,
        error=error,
    )


def percent(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else 0.0


def summarize(results: list[Result], enum: list[str], repeat: int) -> dict[str, Any]:
    by_kind: dict[str, list[Result]] = defaultdict(list)
    by_department: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        by_kind[result.kind].append(result)
        by_department[result.expected].append(result)

    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        confusion[result.expected][result.got] += 1

    answers: dict[str, set[str]] = defaultdict(set)
    for result in results:
        answers[result.case_id].add(result.got)

    injection = by_kind.get("injection", [])
    seconds = [r.seconds for r in results]
    return {
        "cases": len({r.case_id for r in results}),
        "runs": len(results),
        "accuracy": percent(sum(r.correct for r in results), len(results)),
        "accuracy_per_run": [
            percent(sum(r.correct for r in rs), len(rs))
            for run in range(1, repeat + 1)
            if (rs := [r for r in results if r.run == run])
        ],
        "accuracy_per_kind": {
            kind: percent(sum(r.correct for r in rs), len(rs)) for kind, rs in by_kind.items()
        },
        "recall_per_department": {
            dept: percent(sum(r.correct for r in rs), len(rs))
            for dept, rs in sorted(by_department.items())
        },
        "confusion": {exp: dict(got) for exp, got in sorted(confusion.items())},
        "fallback_pct": percent(sum(r.fallback_used is True for r in results), len(results)),
        "http_errors": dict(Counter(r.error for r in results if r.error)),
        "mail_contract_ok": sum(r.mail_matches for r in results),
        "injection_safe": sum(
            r.status == 200 and r.mail_matches and r.recipient in enum for r in injection
        ),
        "injection_runs": len(injection),
        "unstable_cases": sorted(case for case, got in answers.items() if len(got) > 1),
        "seconds_median": round(statistics.median(seconds), 2) if seconds else 0.0,
        "seconds_p95": p95(seconds),
    }


def markdown(summary: dict[str, Any], results: list[Result]) -> str:
    lines = [
        "| Metryka | Wynik |",
        "|---|---|",
        f"| Trafność ogólna | {summary['accuracy']}% ({summary['runs']} przebiegów) |",
        *(
            f"| Trafność `{kind}` | {value}% |"
            for kind, value in summary["accuracy_per_kind"].items()
        ),
        *(
            f"| Recall `{dept}` | {value}% |"
            for dept, value in summary["recall_per_department"].items()
        ),
        f"| Fallback (`fallback_used`) | {summary['fallback_pct']}% |",
        f"| Błędy HTTP | {summary['http_errors'] or 'brak'} |",
        f"| Mail zgodny z API (1 mail, To, Reply-To) | {summary['mail_contract_ok']}/"
        f"{summary['runs']} |",
        f"| Injection: dział z listy, Reply-To = nadawca | {summary['injection_safe']}/"
        f"{summary['injection_runs']} |",
        f"| Czas: mediana / p95 | {summary['seconds_median']} s / {summary['seconds_p95']} s |",
    ]
    misses = [r for r in results if not r.correct]
    if misses:
        lines += ["", "Pomyłki:", ""]
        lines += [
            f"- `{r.case_id}` (run {r.run}, {r.kind}): oczekiwano {r.expected}, jest {r.got}"
            for r in misses
        ]
    if summary["unstable_cases"]:
        lines += ["", f"Różne odpowiedzi między powtórzeniami: {summary['unstable_cases']}"]
    return "\n".join(lines)


def result_path(model: str, label: str | None) -> Path:
    name = "-".join(filter(None, [date.today().isoformat(), model.replace(":", "-"), label]))
    return ROOT / "eval" / "results" / f"{name.replace('/', '-')}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Routing accuracy on the running stack.")
    parser.add_argument("--repeat", type=int, default=1, help="runs per case (default 1)")
    parser.add_argument("--cases", type=Path, default=ROOT / "eval" / "cases.jsonl")
    parser.add_argument("--label", help="suffix of the result file, e.g. baseline")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    model = compose_model()
    started = time.monotonic()
    results: list[Result] = []
    with (
        httpx.Client(base_url=API_URL, timeout=API_TIMEOUT_S) as api,
        httpx.Client(base_url=f"{MAILPIT_URL}/api/v1", timeout=10) as mailpit,
    ):
        try:
            api.get("/health", timeout=5).raise_for_status()
            enum = departments(api)
        except httpx.HTTPError as exc:
            print(f"API not reachable ({exc!r}): docker compose up -d", file=sys.stderr)
            return 1
        total = len(cases) * args.repeat
        for run in range(1, args.repeat + 1):
            for case in cases:
                result = run_case(api, mailpit, case, run)
                results.append(result)
                mark = "OK  " if result.correct else "MISS"
                print(
                    f"[{len(results):>3}/{total}] {mark} {case.id:<38} -> {result.got} "
                    f"({result.seconds} s)",
                    flush=True,
                )

    summary = summarize(results, enum, args.repeat)
    report = {
        "date": date.today().isoformat(),
        "model": model,
        "commit": git_commit(),
        "label": args.label,
        "cases_file": str(args.cases.resolve().relative_to(ROOT, walk_up=True)),
        "repeat": args.repeat,
        "total_seconds": round(time.monotonic() - started, 1),
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    path = result_path(model, args.label)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\nModel: {model} | commit: {report['commit']} | {report['total_seconds']} s")
    print(markdown(summary, results))
    print(f"\nWynik: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
