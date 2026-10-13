# Projexa (FYP)

Final Year Project repository. It contains two separate parts:

| Part | Folder | Purpose |
| --- | --- | --- |
| **MVP data** | [`synthetic_data/`](synthetic_data/) | Synthetic enterprise dataset (departments, employees, skills, projects, tasks, dependencies) that backs the Projexa MVP demo. Generated with Faker, output as JSON + CSV, matches `synthetic_data/schema.sql`. |
| **Research component** | [`generate_observations.py`](generate_observations.py), `data/` | Builds an NFR observation dataset from the PROMISE-relabeled-NICE corpus for an LLM evaluation (separate from the MVP). |

## Quick start

### Synthetic enterprise data (MVP)

```bash
cd synthetic_data
python -m pip install -r requirements.txt
python generate_synthetic_data.py
python validate_output.py
```

See [`synthetic_data/README.md`](synthetic_data/README.md) for the schema, table
relationships and how to seed MySQL.

### NFR observation dataset (research)

```bash
python generate_observations.py
```

Reads `data/PROMISE-relabeled-NICE_row1.csv` and writes `data/observations.json`
(~107 MB, not committed - see `.gitignore`; regenerate locally).

## Notes

- `data/PROMISE-relabeled-NICE_row1.csv` is derived from the NICE/PROMISE dataset
  (Rejithkumar & Anish, ICSE'25; CC-BY-4.0).
- The observation dataset is an evaluation artifact, not an MVP feature.
