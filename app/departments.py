"""The five recipients from the task: the only place where their addresses are defined."""

from enum import StrEnum


class Department(StrEnum):
    """E-mail address of the department that handles the message."""

    HUMAN_RESOURCES = "human-resources@example.com"
    HELP_DESK = "help-desk@example.com"
    IT = "it@example.com"
    KADRY = "kadry@example.com"
    OTHER = "other@example.com"


# Shown to the model in the agent instructions; wording tuned on the M5 eval (eval/results/).
DEPARTMENT_SCOPES: dict[Department, str] = {
    Department.KADRY: "formalities - leave requests, employment contracts, payroll, certificates.",
    Department.HUMAN_RESOURCES: (
        "recruitment, career development, training, relations in the team."
    ),
    Department.HELP_DESK: (
        "first-line help for one employee: their computer, laptop or peripherals, logging in, "
        "password, e-mail, software on their own device."
    ),
    Department.IT: (
        "company systems and infrastructure: servers, networks, databases, deployments, "
        "access rights, licences and company-wide software."
    ),
    Department.OTHER: (
        "anything that fits none of the above (e.g. office, building or facilities matters), "
        "or when you are not sure."
    ),
}

FALLBACK_DEPARTMENT = Department.OTHER
