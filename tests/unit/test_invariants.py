"""Structural contracts checked on the source tree, so they hold without local hooks."""

import ast
import re
from pathlib import Path

from app.departments import Department

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
SMTP_MODULES = {"smtplib", "aiosmtplib"}
SMTP_CALLS = {"send_message", "sendmail"}


def smtp_usages(root: Path) -> list[str]:
    """Files under root (relative paths) that import an SMTP library or call an SMTP send."""
    found = []
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules = {(node.module or "").split(".")[0]}
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                modules = {node.func.attr} & SMTP_CALLS
            else:
                continue
            if modules & (SMTP_MODULES | SMTP_CALLS):
                found.append(path.relative_to(root).as_posix())
    return found


def send_mail_importers(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and any(a.name == "send_mail" for a in node.names)
    }


def test_smtp_is_used_only_in_app_mail() -> None:
    assert smtp_usages(APP)
    assert all(path.startswith("mail/") for path in smtp_usages(APP))


def test_smtp_scan_detects_smtp_outside_app_mail(tmp_path: Path) -> None:
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "leak.py").write_text("import smtplib\n")
    (tmp_path / "api" / "call.py").write_text("def f(smtp):\n    smtp.sendmail('a', 'b', 'c')\n")

    assert smtp_usages(tmp_path) == ["api/call.py", "api/leak.py"]


def test_send_mail_is_imported_only_by_the_tool() -> None:
    assert send_mail_importers(APP) == {"agent/tools.py"}


def test_readme_lists_exactly_the_department_addresses() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Department table rows: | `address@example.com` | scope |
    table = set(re.findall(r"^\| `([\w.-]+@example\.com)` \|", readme, flags=re.MULTILINE))

    assert table == {d.value for d in Department}
