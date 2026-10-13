"""
Validate the synthetic enterprise dataset for referential integrity and
DAG-correctness. Run after generate_synthetic_data.py:

    python validate_output.py

Exits non-zero if any problem is found.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

JSON_DIR = Path(__file__).resolve().parent / "output" / "json"


def load(name):
    return json.load(open(JSON_DIR / f"{name}.json", encoding="utf-8"))


def main() -> int:
    departments = load("departments")
    skills = load("skills")
    employees = load("employees")
    employee_skills = load("employee_skills")
    projects = load("projects")
    tasks = load("tasks")
    dependencies = load("task_dependencies")

    dep_ids = {d["department_id"] for d in departments}
    skill_ids = {s["skill_id"] for s in skills}
    emp_ids = {e["employee_id"] for e in employees}
    proj_ids = {p["project_id"] for p in projects}
    task_ids = {t["task_id"] for t in tasks}

    problems = []

    def check(cond, msg):
        if not cond:
            problems.append(msg)

    # --- unique keys ---------------------------------------------------------
    for name, rows, key in [
        ("departments", departments, "department_id"),
        ("skills", skills, "skill_id"),
        ("employees", employees, "employee_id"),
        ("projects", projects, "project_id"),
        ("tasks", tasks, "task_id"),
    ]:
        ids = [r[key] for r in rows]
        check(len(ids) == len(set(ids)), f"{name}: duplicate {key}")

    # --- foreign keys --------------------------------------------------------
    for e in employees:
        check(e["department_id"] in dep_ids, f"employee {e['employee_id']}: bad department_id")
        check(e["manager_id"] is None or e["manager_id"] in emp_ids,
              f"employee {e['employee_id']}: bad manager_id")
        check(e["manager_id"] != e["employee_id"], f"employee {e['employee_id']}: self-manager")
    for r in employee_skills:
        check(r["employee_id"] in emp_ids, f"employee_skills: bad employee_id {r['employee_id']}")
        check(r["skill_id"] in skill_ids, f"employee_skills: bad skill_id {r['skill_id']}")
        check(1 <= r["proficiency"] <= 5, "employee_skills: proficiency out of range")
    for p in projects:
        check(p["department_id"] in dep_ids, f"project {p['project_id']}: bad department_id")
        check(p["manager_id"] is None or p["manager_id"] in emp_ids,
              f"project {p['project_id']}: bad manager_id")
    for t in tasks:
        check(t["project_id"] in proj_ids, f"task {t['task_id']}: bad project_id")
        check(t["assignee_id"] is None or t["assignee_id"] in emp_ids,
              f"task {t['task_id']}: bad assignee_id")
        check(t["required_skill_id"] is None or t["required_skill_id"] in skill_ids,
              f"task {t['task_id']}: bad required_skill_id")
        check(1 <= t["complexity"] <= 5, f"task {t['task_id']}: complexity out of range")
        if t["status"] == "Done":
            check(t["completed_date"] is not None, f"task {t['task_id']}: Done without completed_date")
            check(t["actual_hours"] is not None, f"task {t['task_id']}: Done without actual_hours")
        else:
            check(t["completed_date"] is None, f"task {t['task_id']}: not Done but has completed_date")

    # --- dependencies: valid refs, no self-loop ------------------------------
    adj = defaultdict(list)
    for d in dependencies:
        a, b = d["predecessor_task_id"], d["successor_task_id"]
        check(a in task_ids and b in task_ids, f"dependency {a}->{b}: bad task id")
        check(a != b, f"dependency {a}->{b}: self-loop")
        adj[a].append(b)

    # --- dependencies: acyclic (DFS) -----------------------------------------
    WHITE, GREY, BLACK = 0, 1, 2
    color = defaultdict(int)
    cycle = []

    def dfs(node, stack):
        color[node] = GREY
        for nxt in adj.get(node, []):
            if color[nxt] == GREY:
                cycle.append(stack + [node, nxt])
                return True
            if color[nxt] == WHITE and dfs(nxt, stack + [node]):
                return True
        color[node] = BLACK
        return False

    for tid in list(task_ids):
        if color[tid] == WHITE:
            if dfs(tid, []):
                break
    check(not cycle, f"task_dependencies contains a cycle: {cycle[:1]}")

    # --- summary -------------------------------------------------------------
    print(f"Departments ........ {len(departments)}")
    print(f"Skills ............. {len(skills)}")
    print(f"Employees .......... {len(employees)}")
    print(f"Employee skills .... {len(employee_skills)}")
    print(f"Projects ........... {len(projects)}")
    print(f"Tasks .............. {len(tasks)}")
    print(f"Dependencies ....... {len(dependencies)}")
    print()
    if problems:
        print(f"FAILED - {len(problems)} problem(s):")
        for p in problems[:50]:
            print(f"  - {p}")
        return 1
    print("OK - referential integrity intact, dependency graph acyclic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
