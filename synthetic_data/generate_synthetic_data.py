"""
Projexa MVP - Synthetic Enterprise Data Generator
=================================================

Generates a realistic, internally-consistent enterprise dataset for the Projexa
MVP demo:

    * 6 departments, 50 employees, ~35 skills, employee_skills join rows
    * 10 projects, 300 tasks, ~180 task dependencies (acyclic)

Output is written BOTH as JSON and CSV, one file per table, so it can be:

    * imported directly by the demo/dashboard, or
    * loaded into MySQL by Mariyum's Node.js seed script.

The output matches synthetic_data/schema.sql (see that file for column types).

Design notes
------------
* Deterministic: a single SEED makes the STRUCTURE reproducible. Dates are
  anchored to ``date.today()`` so the demo always looks "current" (overdue /
  in-flight tasks stay realistic). Pin CONFIG["as_of"] to freeze dates exactly.
* Risk + workload signals are baked in on purpose so the FastAPI modules
  (/ai/assign, /ai/risk) and the dashboard have something meaningful to show:
    - over-allocated employees (more in-flight hours than capacity)
    - overdue tasks, blocked tasks, unassigned tasks
    - dependency edges, and tasks started before their predecessor finished
    - projects with Amber/Red health

Run:
    python generate_synthetic_data.py
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

from faker import Faker

# =============================================================================
# Configuration
# =============================================================================

CONFIG = {
    "seed": 42,
    "n_employees": 50,
    "n_projects": 10,
    "n_tasks": 300,
    # Directory that receives output/json and output/csv
    "output_dir": Path(__file__).resolve().parent / "output",
    # Anchor date for all "recent" activity. Set to a fixed date for reproducible
    # runs; defaults to today so the demo data always looks current.
    "as_of": date.today(),
}

# -----------------------------------------------------------------------------
# Static reference data
# -----------------------------------------------------------------------------

# Department name -> (cost_center, location). Counts must sum to n_employees.
DEPARTMENTS = [
    ("Engineering",        "CC-1001", "London"),
    ("Platform & DevOps",  "CC-1002", "Manchester"),
    ("Data & AI",          "CC-1003", "London"),
    ("Quality Assurance",  "CC-1004", "Leeds"),
    ("Product Management", "CC-1005", "London"),
    ("Design",             "CC-1006", "Bristol"),
]

DEPARTMENT_COUNTS = {
    "Engineering":        15,
    "Platform & DevOps":   8,
    "Data & AI":           9,
    "Quality Assurance":   6,
    "Product Management":  6,
    "Design":              6,
}

# Skills whose category is listed here are preferred within each department.
DEPARTMENT_SKILL_CATEGORIES = {
    "Engineering":        ["Backend", "Frontend", "Data"],
    "Platform & DevOps":  ["DevOps", "Cloud", "Backend"],
    "Data & AI":          ["Data/ML", "Data", "Backend"],
    "Quality Assurance":  ["QA", "Backend", "DevOps"],
    "Product Management": ["Soft", "Data", "Frontend"],
    "Design":             ["Design", "Frontend", "Soft"],
}

# (skill name, category)
SKILLS = [
    ("Python",              "Backend"),
    ("Node.js",             "Backend"),
    ("Java",                "Backend"),
    ("C#/.NET",             "Backend"),
    ("Go",                  "Backend"),
    ("REST API Design",     "Backend"),
    ("SQL",                 "Data"),
    ("JavaScript",          "Frontend"),
    ("TypeScript",          "Frontend"),
    ("React",               "Frontend"),
    ("HTML/CSS",            "Frontend"),
    ("Accessibility",       "Frontend"),
    ("Docker",              "DevOps"),
    ("Kubernetes",          "DevOps"),
    ("CI/CD",               "DevOps"),
    ("Terraform",           "DevOps"),
    ("Linux",               "DevOps"),
    ("AWS",                 "Cloud"),
    ("Azure",               "Cloud"),
    ("Machine Learning",    "Data/ML"),
    ("NLP",                 "Data/ML"),
    ("Pandas",              "Data/ML"),
    ("Data Engineering",    "Data/ML"),
    ("Automated Testing",   "QA"),
    ("Selenium",            "QA"),
    ("Performance Testing", "QA"),
    ("Test Planning",       "QA"),
    ("UX Research",         "Design"),
    ("UI Design",           "Design"),
    ("Figma",               "Design"),
    ("Prototyping",         "Design"),
    ("Communication",       "Soft"),
    ("Leadership",          "Soft"),
    ("Agile/Scrum",         "Soft"),
]

ROLE_TITLES = {
    "Engineering":        {"Junior": "Junior Software Engineer", "Mid": "Software Engineer",
                           "Senior": "Senior Software Engineer", "Lead": "Engineering Lead"},
    "Platform & DevOps":  {"Junior": "Junior DevOps Engineer", "Mid": "DevOps Engineer",
                           "Senior": "Senior DevOps Engineer", "Lead": "Platform Lead"},
    "Data & AI":          {"Junior": "Junior Data Scientist", "Mid": "Data Scientist",
                           "Senior": "Senior Data Scientist", "Lead": "Head of Data & AI"},
    "Quality Assurance":  {"Junior": "Junior QA Engineer", "Mid": "QA Engineer",
                           "Senior": "Senior QA Engineer", "Lead": "QA Lead"},
    "Product Management": {"Junior": "Associate Product Manager", "Mid": "Product Manager",
                           "Senior": "Senior Product Manager", "Lead": "Head of Product"},
    "Design":             {"Junior": "Junior Designer", "Mid": "Product Designer",
                           "Senior": "Senior Product Designer", "Lead": "Design Lead"},
}

SENIORITY_LEVELS = ["Junior", "Mid", "Senior", "Lead"]
SENIORITY_WEIGHTS = [0.26, 0.40, 0.24, 0.10]
PROFICIENCY_BY_SENIORITY = {
    "Junior": [1, 2, 3],
    "Mid":    [2, 3, 4],
    "Senior": [3, 4, 5],
    "Lead":   [4, 5, 5],
}

PROJECT_NAMES = [
    "Atlas Migration Platform", "Beacon Customer Portal", "Cobalt Billing Engine",
    "Delta Analytics Suite", "Everest Mobile App", "Falcon Identity Service",
    "Granite Data Warehouse", "Helix Integration Hub", "Iris Notification Service",
    "Jupiter Reporting Dashboard", "Keystone API Gateway", "Lumen Design System",
    "Meridian Onboarding", "Nimbus Cloud Provisioning", "Orion Search Service",
]

PROJECT_STATUSES       = ["Planned", "Active", "On Hold", "Completed"]
PROJECT_STATUS_WEIGHTS = [0.10, 0.60, 0.12, 0.18]
PROJECT_PRIORITIES     = ["Low", "Medium", "High", "Critical"]
PROJECT_PRIORITY_WEIGHTS = [0.15, 0.40, 0.32, 0.13]
PROJECT_HEALTHS        = ["Green", "Amber", "Red"]
PROJECT_HEALTH_WEIGHTS = [0.50, 0.32, 0.18]
# Departments that tend to own the most work.
PROJECT_DEPT_WEIGHTS = {
    "Engineering": 0.30, "Platform & DevOps": 0.16, "Data & AI": 0.18,
    "Quality Assurance": 0.06, "Product Management": 0.14, "Design": 0.16,
}

TASK_STATUSES       = ["Backlog", "To Do", "In Progress", "In Review", "Done", "Blocked"]
TASK_STATUS_WEIGHTS = [0.18, 0.14, 0.24, 0.09, 0.27, 0.08]
TASK_PRIORITIES     = ["Low", "Medium", "High", "Critical"]
TASK_PRIORITY_WEIGHTS = [0.22, 0.42, 0.28, 0.08]

TASK_VERBS = [
    "Implement", "Refactor", "Design", "Instrument", "Harden", "Optimise",
    "Document", "Migrate", "Integrate", "Test",
]
TASK_NOUNS = [
    "service", "module", "pipeline", "endpoint", "dashboard", "workflow",
    "integration", "scheduler", "data model", "UI component",
]

# Column order, kept identical for JSON objects and CSV headers.
TABLE_COLUMNS = {
    "departments":       ["department_id", "name", "cost_center", "location"],
    "skills":            ["skill_id", "name", "category"],
    "employees":         ["employee_id", "full_name", "email", "title", "seniority",
                          "department_id", "manager_id", "employment_type",
                          "weekly_capacity_hours", "hire_date", "is_active"],
    "employee_skills":   ["employee_id", "skill_id", "proficiency", "years_experience"],
    "projects":          ["project_id", "code", "name", "department_id", "manager_id",
                          "client", "status", "priority", "health", "start_date",
                          "target_end_date", "budget_usd"],
    "tasks":             ["task_id", "project_id", "title", "description",
                          "required_skill_id", "assignee_id", "status", "priority",
                          "complexity", "estimated_hours", "actual_hours",
                          "start_date", "due_date", "completed_date", "created_at"],
    "task_dependencies": ["predecessor_task_id", "successor_task_id",
                          "dependency_type", "lag_days"],
}


# =============================================================================
# Helpers
# =============================================================================

def weighted_sample(items, weights, k, rng):
    """Sample k unique items without replacement, proportional to weights."""
    pool = list(zip(items, weights))
    chosen = []
    for _ in range(min(k, len(pool))):
        total = sum(w for _, w in pool)
        r = rng.random() * total
        acc = 0.0
        for i, (item, w) in enumerate(pool):
            acc += w
            if r <= acc:
                chosen.append(item)
                pool.pop(i)
                break
    return chosen


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".")


def make_email(name: str, used: set) -> str:
    base = slugify(name) or "employee"
    email = f"{base}@projexa.com"
    n = 2
    while email in used:
        email = f"{base}{n}@projexa.com"
        n += 1
    used.add(email)
    return email


# =============================================================================
# Step 1 - Departments
# =============================================================================

def build_departments():
    departments = []
    name_to_id = {}
    for i, (name, cc, loc) in enumerate(DEPARTMENTS, start=1):
        departments.append({"department_id": i, "name": name,
                            "cost_center": cc, "location": loc})
        name_to_id[name] = i
    return departments, name_to_id


# =============================================================================
# Step 2 - Skills
# =============================================================================

def build_skills():
    skills = []
    for i, (name, category) in enumerate(SKILLS, start=1):
        skills.append({"skill_id": i, "name": name, "category": category})
    return skills


# =============================================================================
# Step 3 - Employees (org hierarchy)
# =============================================================================

def build_employees(rng, fake, name_to_id, as_of):
    employees = []
    used_emails = set()
    emp_id = 0

    for dept_name, count in DEPARTMENT_COUNTS.items():
        for _ in range(count):
            emp_id += 1
            seniority = rng.choices(SENIORITY_LEVELS, weights=SENIORITY_WEIGHTS)[0]

            # Occasionally give someone a seniority bump so depts have a Lead.
            full_name = fake.name()
            employment_type = rng.choices(
                ["Full-time", "Part-time", "Contract"], weights=[0.88, 0.07, 0.05]
            )[0]
            capacity = {"Full-time": 40.0, "Part-time": 20.0, "Contract": 40.0}[employment_type]

            employees.append({
                "employee_id": emp_id,
                "full_name": full_name,
                "email": make_email(full_name, used_emails),
                "title": ROLE_TITLES[dept_name][seniority],
                "seniority": seniority,
                "department_id": name_to_id[dept_name],
                "manager_id": None,  # assigned below
                "employment_type": employment_type,
                "weekly_capacity_hours": capacity,
                "hire_date": fake.date_between(
                    start_date=date(2015, 1, 1),
                    end_date=as_of - timedelta(days=30),
                ).isoformat(),
                "is_active": 1 if rng.random() < 0.93 else 0,
                "_department_name": dept_name,  # temp, stripped on output
            })

    # --- assign managers: one per department, plus a director -----------------
    by_dept = defaultdict(list)
    for e in employees:
        by_dept[e["_department_name"]].append(e)

    seniority_rank = {"Lead": 0, "Senior": 1, "Mid": 2, "Junior": 3}
    dept_manager_id = {}
    for dept_name, emps in by_dept.items():
        mgr = sorted(emps, key=lambda e: (seniority_rank[e["seniority"]], e["employee_id"]))[0]
        dept_manager_id[dept_name] = mgr["employee_id"]

    director_id = dept_manager_id["Engineering"]

    for e in employees:
        dept_name = e["_department_name"]
        if e["employee_id"] == dept_manager_id[dept_name]:
            # Department manager reports to the director (director reports to none).
            e["manager_id"] = None if e["employee_id"] == director_id else director_id
        else:
            e["manager_id"] = dept_manager_id[dept_name]

    return employees, dept_manager_id, director_id


# =============================================================================
# Step 4 - Employee skills
# =============================================================================

def build_employee_skills(rng, employees, skills):
    rows = []
    for e in employees:
        cats = DEPARTMENT_SKILL_CATEGORIES[e["_department_name"]]
        weights = [3.0 if s["category"] in cats else 0.5 for s in skills]
        k = rng.randint(3, 8)
        chosen = weighted_sample(skills, weights, k, rng)
        prof_options = PROFICIENCY_BY_SENIORITY[e["seniority"]]
        for s in chosen:
            proficiency = rng.choice(prof_options)
            years = round(proficiency * rng.uniform(0.6, 1.7), 1)
            rows.append({
                "employee_id": e["employee_id"],
                "skill_id": s["skill_id"],
                "proficiency": proficiency,
                "years_experience": min(years, 15.0),
            })
    return rows


# =============================================================================
# Step 5 - Projects
# =============================================================================

def build_projects(rng, fake, name_to_id, dept_manager_id, as_of, n_projects):
    projects = []
    dept_names = list(DEPARTMENT_COUNTS.keys())
    dept_weights = [PROJECT_DEPT_WEIGHTS[d] for d in dept_names]
    chosen_names = rng.sample(PROJECT_NAMES, n_projects)

    for i in range(1, n_projects + 1):
        dept_name = rng.choices(dept_names, weights=dept_weights)[0]
        status = rng.choices(PROJECT_STATUSES, weights=PROJECT_STATUS_WEIGHTS)[0]
        priority = rng.choices(PROJECT_PRIORITIES, weights=PROJECT_PRIORITY_WEIGHTS)[0]

        if status == "Completed":
            start = fake.date_between(start_date=as_of - timedelta(days=540),
                                      end_date=as_of - timedelta(days=260))
            duration = rng.randint(90, 200)
            health = "Green"
        elif status == "Planned":
            start = fake.date_between(start_date=as_of - timedelta(days=15),
                                      end_date=as_of + timedelta(days=45))
            duration = rng.randint(90, 240)
            health = rng.choices(["Green", "Amber"], weights=[0.8, 0.2])[0]
        else:  # Active / On Hold
            start = fake.date_between(start_date=as_of - timedelta(days=300),
                                      end_date=as_of - timedelta(days=30))
            duration = rng.randint(120, 300)
            health = rng.choices(PROJECT_HEALTHS, weights=PROJECT_HEALTH_WEIGHTS)[0]

        projects.append({
            "project_id": i,
            "code": f"PRJ-{i:03d}",
            "name": chosen_names[i - 1],
            "department_id": name_to_id[dept_name],
            "manager_id": dept_manager_id[dept_name],
            "client": fake.company(),
            "status": status,
            "priority": priority,
            "health": health,
            "start_date": start.isoformat(),
            "target_end_date": (start + timedelta(days=duration)).isoformat(),
            "budget_usd": float(rng.randrange(50_000, 800_001, 5_000)),
            "_department_name": dept_name,  # temp
            "_start": start,                # temp (date object)
            "_duration": duration,          # temp
        })
    return projects


# =============================================================================
# Step 6 - Tasks
# =============================================================================

def build_tasks(rng, fake, projects, skills, employees, emp_skills, as_of, n_tasks):
    # Index: skill_id -> list of (employee, proficiency) that possess it, active only.
    emp_by_id = {e["employee_id"]: e for e in employees}
    skill_index = defaultdict(list)
    for row in emp_skills:
        emp = emp_by_id[row["employee_id"]]
        if emp["is_active"]:
            skill_index[row["skill_id"]].append((emp, row["proficiency"]))

    skills_by_name = {s["name"]: s for s in skills}
    skills_by_cat = defaultdict(list)
    for s in skills:
        skills_by_cat[s["category"]].append(s)

    proj_weights = [rng.uniform(0.6, 1.4) for _ in projects]
    tasks = []

    for tid in range(1, n_tasks + 1):
        project = rng.choices(projects, weights=proj_weights)[0]
        dept_name = project["_department_name"]

        # Choose a plausible required skill for this project's department.
        cats = DEPARTMENT_SKILL_CATEGORIES[dept_name]
        candidate_skills = [s for s in skills if s["category"] in cats] or skills
        skill = rng.choice(candidate_skills)

        complexity = rng.randint(1, 5)
        est = round(complexity * rng.uniform(3, 9), 1)
        priority = rng.choices(TASK_PRIORITIES, weights=TASK_PRIORITY_WEIGHTS)[0]

        if project["status"] == "Completed":
            status = rng.choices(["Done", "In Review", "Blocked"], weights=[0.85, 0.10, 0.05])[0]
        elif project["status"] == "Planned":
            status = rng.choices(["Backlog", "To Do"], weights=[0.7, 0.3])[0]
        else:
            status = rng.choices(TASK_STATUSES, weights=TASK_STATUS_WEIGHTS)[0]

        # --- Schedule the task -------------------------------------------------
        # Completed work sits in the past; open work sits mostly in the near
        # future, with a deliberate slice overdue so /ai/risk has real signals.
        work_days = max(1, int(est / 6))
        proj_start = project["_start"]
        planned_end = proj_start + timedelta(days=project["_duration"])
        completed_date = None
        actual_hours = None

        if status == "Done":
            latest_due = min(as_of, planned_end) if project["status"] == "Completed" else as_of
            earliest_due = proj_start + timedelta(days=work_days)
            if latest_due <= earliest_due:
                due = latest_due
            else:
                due = earliest_due + timedelta(days=rng.randint(0, (latest_due - earliest_due).days))
            start = max(proj_start, due - timedelta(days=work_days + rng.randint(0, 8)))
            done = min(due + timedelta(days=rng.randint(-2, 7)), as_of)
            done = max(done, start)
            completed_date = done.isoformat()
            actual_hours = round(est * rng.uniform(0.7, 1.4), 1)
        elif project["status"] == "Completed":
            # Leftovers in a finished project: stale and overdue.
            due = as_of - timedelta(days=rng.randint(1, 30))
            start = max(proj_start, due - timedelta(days=work_days + rng.randint(0, 8)))
        else:
            if rng.random() < 0.18:                       # genuinely overdue
                due = as_of - timedelta(days=rng.randint(1, 21))
            else:                                         # upcoming work
                due = as_of + timedelta(days=rng.randint(2, 60))
            start = max(proj_start, due - timedelta(days=work_days + rng.randint(0, 10)))

        # Assignee: prefer same-department people who hold the required skill.
        assignee_id = None
        if rng.random() >= 0.08:  # ~8% deliberately left unassigned
            candidates = skill_index.get(skill["skill_id"], [])
            same_dept = [c for c in candidates if c[0]["department_id"] == project["department_id"]]
            pool = same_dept if (same_dept and rng.random() < 0.8) else candidates
            if pool:
                # Weight by proficiency^3 -> concentrates load on a few experts,
                # which produces realistic (demonstrable) over-allocation.
                emp = rng.choices([c[0] for c in pool],
                                  weights=[c[1] ** 3 for c in pool])[0]
                assignee_id = emp["employee_id"]

        tasks.append({
            "task_id": tid,
            "project_id": project["project_id"],
            "title": f"{rng.choice(TASK_VERBS)} {rng.choice(TASK_NOUNS)} ({skill['name']})",
            "description": fake.sentence(nb_words=12),
            "required_skill_id": skill["skill_id"],
            "assignee_id": assignee_id,
            "status": status,
            "priority": priority,
            "complexity": complexity,
            "estimated_hours": est,
            "actual_hours": actual_hours,
            "start_date": start.isoformat(),
            "due_date": due.isoformat(),
            "completed_date": completed_date,
            "created_at": datetime.combine(start, time(rng.randint(8, 18), 0)).isoformat(sep=" "),
            "_due": due,        # temp
            "_start": start,    # temp
        })
    return tasks


# =============================================================================
# Step 7 - Task dependencies (acyclic: edges only go "forward" in start order)
# =============================================================================

def build_dependencies(rng, tasks):
    by_project = defaultdict(list)
    for t in tasks:
        by_project[t["project_id"]].append(t)

    deps = []
    seen = set()
    dep_types = ["Finish-to-Start", "Start-to-Start", "Finish-to-Finish"]
    type_weights = [0.85, 0.10, 0.05]

    for _, ts in by_project.items():
        ordered = sorted(ts, key=lambda t: (t["_start"], t["task_id"]))
        for idx, successor in enumerate(ordered):
            if idx == 0:
                continue
            if rng.random() < 0.60:
                window = ordered[max(0, idx - 4):idx]
                pred = rng.choice(window)
                key = (pred["task_id"], successor["task_id"])
                if key not in seen:
                    seen.add(key)
                    deps.append({
                        "predecessor_task_id": pred["task_id"],
                        "successor_task_id": successor["task_id"],
                        "dependency_type": rng.choices(dep_types, weights=type_weights)[0],
                        "lag_days": rng.randint(0, 5),
                    })
    return deps


# =============================================================================
# Step 8 - Risk / workload summary (mirrors what FastAPI /ai/risk will compute)
# =============================================================================

def summarise(tasks, deps, projects, employees, as_of, window_days=28):
    done = {"Done"}
    overdue   = [t for t in tasks if t["status"] not in done and t["_due"] < as_of]
    blocked   = [t for t in tasks if t["status"] == "Blocked"]
    unassigned = [t for t in tasks if t["assignee_id"] is None and t["status"] not in done]

    # Overallocation: in-flight estimated hours due within the window vs capacity.
    window_end = as_of + timedelta(days=window_days)
    load = defaultdict(float)
    for t in tasks:
        if t["assignee_id"] is None or t["status"] in done:
            continue
        if t["_start"] <= window_end and t["_due"] >= as_of:
            load[t["assignee_id"]] += t["estimated_hours"]
    cap = {e["employee_id"]: e["weekly_capacity_hours"] for e in employees}
    overallocated = []
    for emp_id, hrs in load.items():
        capacity = cap[emp_id] * (window_days / 7.0)
        if capacity and hrs > capacity:
            overallocated.append((emp_id, round(hrs, 1), round(capacity, 1)))

    # Dependency risk: a not-Done task that has already started while a
    # predecessor is still not Done.
    task_by_id = {t["task_id"]: t for t in tasks}
    started = [t for t in tasks if t["_start"] <= as_of and t["status"] not in done]
    started_ids = {t["task_id"] for t in started}
    dep_risk = [d for d in deps
                if d["successor_task_id"] in started_ids
                and task_by_id[d["predecessor_task_id"]]["status"] not in done]

    return {
        "as_of": as_of.isoformat(),
        "counts": {
            "departments": len(DEPARTMENTS),
            "skills": len(SKILLS),
            "employees": len(employees),
            "projects": len(projects),
            "tasks": len(tasks),
            "task_dependencies": len(deps),
        },
        "risk_signals": {
            "overdue_tasks": len(overdue),
            "blocked_tasks": len(blocked),
            "unassigned_tasks": len(unassigned),
            "overallocated_employees": len(overallocated),
            "dependency_order_violations": len(dep_risk),
            "red_projects": sum(1 for p in projects if p["health"] == "Red"),
            "amber_projects": sum(1 for p in projects if p["health"] == "Amber"),
        },
    }


# =============================================================================
# Step 9 - Output
# =============================================================================

def strip_temps(rows):
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]


def write_outputs(tables, meta, out_dir):
    json_dir = out_dir / "json"
    csv_dir = out_dir / "csv"
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    combined = {}
    for name, rows in tables.items():
        cols = TABLE_COLUMNS[name]
        ordered = [{c: r.get(c) for c in cols} for r in rows]
        combined[name] = ordered

        with open(json_dir / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)

        with open(csv_dir / f"{name}.csv", "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(ordered)

    with open(out_dir / "enterprise_data.json", "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    with open(json_dir / "_meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return json_dir, csv_dir


# =============================================================================
# Entry point
# =============================================================================

def main():
    cfg = CONFIG
    rng = random.Random(cfg["seed"])
    fake = Faker()
    Faker.seed(cfg["seed"])
    as_of = cfg["as_of"]

    print(f"Generating synthetic enterprise data (seed={cfg['seed']}, as_of={as_of})")

    departments, name_to_id = build_departments()
    skills = build_skills()
    employees, dept_manager_id, director_id = build_employees(rng, fake, name_to_id, as_of)
    emp_skills = build_employee_skills(rng, employees, skills)
    projects = build_projects(rng, fake, name_to_id, dept_manager_id, as_of, cfg["n_projects"])
    tasks = build_tasks(rng, fake, projects, skills, employees, emp_skills, as_of, cfg["n_tasks"])
    deps = build_dependencies(rng, tasks)

    meta = summarise(tasks, deps, projects, employees, as_of)

    tables = {
        "departments": departments,
        "skills": skills,
        "employees": strip_temps(employees),
        "employee_skills": emp_skills,
        "projects": strip_temps(projects),
        "tasks": strip_temps(tasks),
        "task_dependencies": deps,
    }

    json_dir, csv_dir = write_outputs(tables, meta, cfg["output_dir"])

    # ---- console report ------------------------------------------------------
    print("\n" + "=" * 60)
    print("Row counts")
    print("-" * 60)
    for name, rows in tables.items():
        print(f"  {name:<20} {len(rows):>6}")
    print("-" * 60)
    print("Risk signals (dashboards + /ai/risk)")
    for k, v in meta["risk_signals"].items():
        print(f"  {k:<32} {v:>5}")
    print("-" * 60)
    print(f"JSON  -> {json_dir}")
    print(f"CSV   -> {csv_dir}")
    print(f"Combined -> {cfg['output_dir'] / 'enterprise_data.json'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
