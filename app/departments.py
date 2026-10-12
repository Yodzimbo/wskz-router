"""The five recipients from the task: the only place where their addresses are defined."""

from enum import StrEnum


class Department(StrEnum):
    """E-mail address of the department that handles the message."""

    HUMAN_RESOURCES = "human-resources@example.com"
    HELP_DESK = "help-desk@example.com"
    IT = "it@example.com"
    KADRY = "kadry@example.com"
    OTHER = "other@example.com"


# Shown to the model in the agent instructions; wording measured in the M2 spike (ADR-002).
DEPARTMENT_SCOPES: dict[Department, str] = {
    Department.KADRY: "formalities - leave requests, employment contracts, payroll, certificates.",
    Department.HUMAN_RESOURCES: (
        "recruitment, career development, training, relations in the team."
    ),
    Department.HELP_DESK: "help for a user with their computer, hardware, account or password.",
    Department.IT: "systems, servers, access rights, deployments, software.",
    Department.OTHER: "anything that fits none of the above, or when you are not sure.",
}

FALLBACK_DEPARTMENT = Department.OTHER
