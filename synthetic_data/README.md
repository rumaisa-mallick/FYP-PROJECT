# Synthetic Enterprise Data (Projexa MVP)

Generates a realistic, internally-consistent enterprise dataset for the Projexa
demo: **6 departments, 50 employees, 34 skills, 10 projects, 300 tasks,
~170 task dependencies**. Output is written as **JSON and CSV**, one file per
table, matching `schema.sql`.

This is the critical-path dataset: FastAPI `/ai/assign` and `/ai/risk`, the
Node.js seed script, and the React dashboard all read from it.

> Note: this is **not** the NFR observation dataset. That one lives in
> `../data/` (`observations.json`) and is a separate research/evaluation
> component.

## Files

| File | Purpose |
| --- | --- |
| `schema.sql` | Proposed normalized MySQL schema (InnoDB, utf8mb4). Review before freezing. |
| `generate_synthetic_data.py` | The generator (Faker + stdlib). Writes JSON + CSV. |
| `validate_output.py` | Checks referential integrity + that dependencies are acyclic. |
| `requirements.txt` | Python dependency (`Faker`). |
| `output/json/*.json` | One JSON array per table, plus `_meta.json`. |
| `output/csv/*.csv` | One CSV per table (same columns/order). |
| `output/enterprise_data.json` | All tables in a single object (handy for the demo). |

## Run

```bash
python -m pip install -r requirements.txt
python generate_synthetic_data.py
python validate_output.py      # exit code 0 == all good
```

## Tables

`departments`, `skills`, `employees`, `employee_skills`, `projects`, `tasks`,
`task_dependencies`.

Key relationships:

- `employees.department_id  -> departments`
- `employees.manager_id     -> employees` (self-referencing; one manager per
  department plus a director)
- `employee_skills            -> employees + skills` (many-to-many, with
  `proficiency` 1..5 and `years_experience`)
- `projects.department_id   -> departments`, `projects.manager_id -> employees`
- `tasks.project_id         -> projects`
- `tasks.assignee_id        -> employees` (NULL = unassigned)
- `tasks.required_skill_id  -> skills` (NULL = none)
- `task_dependencies         -> tasks` (directed, **acyclic** by construction)

## Risk signals baked in (for `/ai/risk` and the dashboard)

The generator deliberately produces:

- ~10-15% **overdue** tasks, some **blocked** and **unassigned**
- a few **over-allocated** employees (more open hours than capacity; part-timers
  tip over fastest)
- **dependency edges** where a task started before its predecessor finished
  ("dependency order violations")
- projects with **Amber/Red** health

These are summarised in `output/json/_meta.json` and printed by the generator.

## How the Node.js seed script should consume it

Either parse `output/json/<table>.json` per table, or use the single
`output/enterprise_data.json`. Insert in dependency order:

```
departments -> skills -> employees -> employee_skills
                      -> projects -> tasks -> task_dependencies
```

Because `employees.manager_id` and `tasks.assignee_id` are self/soft references,
insert `employees` (and `tasks`) with those columns NULL, then run an `UPDATE`
pass — or disable FK checks for the seed and re-enable them after, then verify.

## Tunable knobs (`CONFIG` in `generate_synthetic_data.py`)

| Knob | Meaning |
| --- | --- |
| `seed` | RNG seed. Same seed => same *structure* (reproducible). |
| `n_employees` / `n_projects` / `n_tasks` | Volumes (must keep `DEPARTMENT_COUNTS` summing to `n_employees`). |
| `as_of` | Anchor date. Defaults to `date.today()` so the demo stays current; pin it to freeze dates exactly. |

Intentional skews (edit the constants near the top of the file): department
sizes, seniority mix, project status/priority/health weights, task status
weights, and how strongly assignments concentrate on experts
(`proficiency ** 3`).
