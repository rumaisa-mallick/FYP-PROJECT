# Projexa

Projexa is an AI-powered enterprise workflow platform. It brings project management, task coordination, scheduling and progress tracking into one system, so organisations do not have to manage projects across several disconnected tools.

Many organisations run projects across emails, spreadsheets, chat apps and separate project management software. This causes communication gaps, uneven workloads and delays. Projexa aims to solve this with a single platform that uses AI to support workload distribution and risk detection.

## Current status

| Component | Status |
| --- | --- |
| Synthetic enterprise dataset (generator, schema, validation) | Done |
| AI workload distribution (`GET /ai/assign/{task_id}`) | Done |
| Risk detection | Planned |
| Dependency shifting for delayed tasks | Planned |
| Meeting assistant (transcription, requirements, tasks) | Planned |
| Backend (Node.js, Express, MySQL) | Planned |
| Frontend (React) and dashboards | Planned |

## Repository structure

| Path | Description |
| --- | --- |
| `synthetic_data/` | Generator script, MySQL schema, validation script and the generated sample data |
| `ai_service/` | FastAPI service for the AI modules |
| `data/` | Input data for the research component |
| `generate_observations.py` | Builds an NFR observation dataset for LLM evaluation (research, not part of the MVP) |
| `requirements.txt` | Python dependencies |

## Getting started

Requires Python 3.10 or newer.

```bash
git clone https://github.com/rumaisa-mallick/PROJEXA-FYP.git
cd PROJEXA-FYP
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Generate the sample data and validate it:

```bash
cd synthetic_data
python generate_synthetic_data.py
python validate_output.py
cd ..
```

Run the AI service:

```bash
cd ai_service
uvicorn main:app --reload
```

Open <http://127.0.0.1:8000/docs> to try the endpoints.

## AI workload distribution

`GET /ai/assign/{task_id}` returns the top 3 employees for a task. Each employee gets a score between 0 and 1:

```
score = 0.5 * skill + 0.3 * capacity + 0.2 * deadline
```

- **Skill:** 1 if the employee has the task's required skill, otherwise 0.
- **Capacity:** free hours divided by weekly capacity, where free hours are the capacity minus the hours of the employee's unfinished tasks.
- **Deadline:** the share of the task's estimated hours the employee can finish before the due date, capped at 1.

The reference date is fixed at 2026-10-14 (the `as_of` date in `_meta.json`), so results are reproducible.

## Research component

`data/PROMISE-relabeled-NICE_row1.csv` is derived from the NICE/PROMISE dataset (Rejithkumar & Anish, ICSE'25; CC-BY-4.0). `data/observations.json` is about 107 MB and is not committed, because GitHub rejects files over 100 MB. Regenerate it with `python generate_observations.py`.