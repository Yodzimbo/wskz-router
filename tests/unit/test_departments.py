from app.departments import DEPARTMENT_SCOPES, FALLBACK_DEPARTMENT, Department


def test_departments_match_task_list() -> None:
    # The five addresses from docs/zadanie.md, spelled out once more on purpose.
    assert {d.value for d in Department} == {
        "human-resources@example.com",
        "help-desk@example.com",
        "it@example.com",
        "kadry@example.com",
        "other@example.com",
    }


def test_every_department_has_a_scope() -> None:
    assert set(DEPARTMENT_SCOPES) == set(Department)
    assert all(scope.strip() for scope in DEPARTMENT_SCOPES.values())


def test_fallback_is_other() -> None:
    assert FALLBACK_DEPARTMENT is Department.OTHER
