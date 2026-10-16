from datetime import date

from fastapi import FastAPI, HTTPException

from data_loader import get_task, load_employees

app = FastAPI(title="Projexa AI Service")

WEIGHTS = {"skill": 0.5, "capacity": 0.3, "deadline": 0.2}
AS_OF = date(2026, 10, 14)  # same date as _meta.json, keeps results reproducible


def score_employee(task: dict, emp: dict) -> dict:
    reasons = []
    task_hours = task["estimated_hours"] or 0

    # 1. Skill match
    skills = [s.lower() for s in emp["skills"]]
    has_skill = task["required_skill_name"].lower() in skills
    skill_score = 1.0 if has_skill else 0.0
    reasons.append("has required skill" if has_skill else "missing required skill")

    # 2. Free capacity
    cap = emp["weekly_capacity_hours"]
    free = max(0.0, cap - emp["open_task_hours"])
    capacity_score = free / cap if cap > 0 else 0.0
    reasons.append(f"{free:.0f}h free of {cap:.0f}h weekly capacity")

    # 3. Deadline fit (if the task has no due date, deadline is not a factor)
    if task["due_date"]:
        deadline = date.fromisoformat(task["due_date"])
        weeks_left = max(0, (deadline - AS_OF).days) / 7
        available = max(0.0, weeks_left * cap - emp["open_task_hours"])
        deadline_score = min(1.0, available / task_hours) if task_hours > 0 else 1.0
    else:
        deadline_score = 1.0
    reasons.append(
        "enough time before deadline" if deadline_score >= 1.0
        else "tight on time before deadline"
    )

    total = (
        WEIGHTS["skill"] * skill_score
        + WEIGHTS["capacity"] * capacity_score
        + WEIGHTS["deadline"] * deadline_score
    )
    return {
        "employee_id": emp["id"],
        "name": emp["name"],
        "score": round(total, 3),
        "reasons": reasons,
    }


@app.get("/ai/assign/{task_id}")
def assign(task_id: int):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    employees = load_employees(exclude_task_id=task_id)
    scored = [score_employee(task, emp) for emp in employees]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"task_id": task_id, "suggestions": scored[:3]}