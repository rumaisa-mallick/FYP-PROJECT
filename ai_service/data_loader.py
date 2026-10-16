import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "synthetic_data" / "output" / "json"

# Statuses that mean the task is finished (compared in lowercase)
DONE_STATUSES = {"done", "completed"}


def _load(name: str) -> list[dict]:
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _skill_names() -> dict[int, str]:
    return {s["skill_id"]: s["name"] for s in _load("skills")}


def load_employees(exclude_task_id: int | None = None) -> list[dict]:
    """
    Active employees with their skill names and open_task_hours.
    open_task_hours counts unfinished tasks, and ignores the task being
    assigned so its own hours do not count against the employee.
    """
    names = _skill_names()

    emp_skills: dict[int, list[str]] = {}
    for link in _load("employee_skills"):
        emp_skills.setdefault(link["employee_id"], []).append(
            names.get(link["skill_id"], "")
        )

    tasks = _load("tasks")
    result = []
    for e in _load("employees"):
        if not e.get("is_active", 1):
            continue
        emp_id = e["employee_id"]
        open_hours = sum(
            (t["estimated_hours"] or 0)
            for t in tasks
            if t["assignee_id"] == emp_id
            and str(t["status"]).lower() not in DONE_STATUSES
            and t["task_id"] != exclude_task_id
        )
        result.append({
            "id": emp_id,
            "name": e["full_name"],
            "skills": emp_skills.get(emp_id, []),
            "weekly_capacity_hours": e["weekly_capacity_hours"] or 0,
            "open_task_hours": open_hours,
        })
    return result


def get_task(task_id: int) -> dict | None:
    """
    Returns the task with an extra key 'required_skill_name',
    because tasks store only the skill ID.
    """
    names = _skill_names()
    for t in _load("tasks"):
        if t["task_id"] == task_id:
            return {
                **t,
                "required_skill_name": names.get(t["required_skill_id"], ""),
            }
    return None