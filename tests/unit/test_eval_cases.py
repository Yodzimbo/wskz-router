"""The evaluation set (eval/cases.jsonl) is well-formed and unseen by the prompt and the spike."""

import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from app.agent.router_agent import INSTRUCTIONS
from app.departments import DEPARTMENT_SCOPES, Department

ROOT = Path(__file__).resolve().parents[2]
CASES_FILE = ROOT / "eval" / "cases.jsonl"
KINDS = {"clear", "boundary", "injection", "other"}
# The two examples from docs/zadanie.md are allowed in every set.
TASK_EXAMPLES = {"Nie działa mi komputer", "Chciałbym zgłosić urlop na jutro"}
SPIKE_CASES = "eval/spike_cases.jsonl"
SPIKE_REFS = ("spike/model-selection", "origin/spike/model-selection")


def load_cases() -> list[dict[str, Any]]:
    lines = CASES_FILE.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def spike_messages() -> set[str] | None:
    """Messages from the M2 model spike (branch only), or None when the branch is not fetched."""
    for ref in SPIKE_REFS:
        result = subprocess.run(
            ["git", "show", f"{ref}:{SPIKE_CASES}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return {json.loads(line)["message"] for line in result.stdout.splitlines() if line}
    return None


def test_eval_cases_are_valid_json_with_required_fields() -> None:
    cases = load_cases()

    assert all({"id", "message", "expected", "kind"} <= case.keys() for case in cases)
    assert all(case["message"].strip() for case in cases)
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["kind"] for case in cases} <= KINDS


def test_eval_cases_use_department_addresses() -> None:
    addresses = {d.value for d in Department}

    assert all(case["expected"] in addresses for case in load_cases())


def test_eval_cases_cover_every_department_and_kind() -> None:
    cases = load_cases()
    clear = Counter(case["expected"] for case in cases if case["kind"] == "clear")

    assert {case["expected"] for case in cases} == {d.value for d in Department}
    assert {case["kind"] for case in cases} == KINDS
    assert all(clear[d.value] >= 2 for d in Department if d is not Department.OTHER)


def test_eval_cases_not_in_instructions() -> None:
    scopes = " ".join(DEPARTMENT_SCOPES.values())

    for case in load_cases():
        assert case["message"] not in INSTRUCTIONS
        assert case["message"] not in scopes


def test_eval_cases_differ_from_model_spike() -> None:
    # The department wording was chosen on the spike cases, so reusing them would flatter the score.
    spike = spike_messages()
    if spike is None:
        pytest.skip(f"branch with {SPIKE_CASES} not available")

    overlap = {case["message"] for case in load_cases()} & spike
    assert overlap <= TASK_EXAMPLES
