import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from math import comb


# =============================================================================
# Configuration
# =============================================================================

CONFIG = {
    # Path to the PROMISE-relabeled-NICE CSV file
    "csv_path": "data/PROMISE-relabeled-NICE_row1.csv",

    # Output path for the generated observation dataset
    "output_path": "data/observations.json",

    # Base random seed; all observation seeds are derived from this value
    "global_seed": 2026,

    # Subset ratio interval [r_min, r_max], step fixed at 0.1
    "r_min": 0.2,
    "r_max": 0.9,

    # Number of seeds (distinct subsets) generated per (target, r) pair
    "K": 3,
}

# Canonical NFR category names
NFR_CATEGORY_COLUMNS = [
    "Availability (A)",
    "Fault Tolerance (FT)",
    "Legal (L)",
    "Look & Feel (LF)",
    "Maintainability (MN)",
    "Operability (O)",
    "Performance (PE)",
    "Portability (PO)",
    "Scalability (SC)",
    "Security (SE)",
    "Usability (US)",
]


# =============================================================================
# Step 1 — Load and parse the CSV
# =============================================================================

def load_csv(csv_path: str) -> list[dict]:
    """
    Read the PROMISE CSV and return a list of requirement records.
    """
    records = []
    project_counters = defaultdict(int)

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = int(row["ProjectID"])
            project_counters[pid] += 1
            local_idx = project_counters[pid]

            # Strip surrounding single quotes that some entries carry
            text = row["RequirementText"].strip("'").strip()

            nfr_labels = [
                col for col in NFR_CATEGORY_COLUMNS
                if row.get(col, "0").strip() == "1"
            ]

            records.append({
                "project_id": pid,
                "req_id":     f"P{pid}_R{local_idx:02d}",
                "text":       text,
                "is_quality": int(row["IsQuality"]),
                "nfr_labels": nfr_labels,
            })

    print(f"Loaded {len(records)} requirements from {csv_path}")
    return records


# =============================================================================
# Step 2 — Build per-project pools
# =============================================================================

def build_project_pools(records: list[dict]) -> dict:
    """
    Partition requirements by project. Returns a dict keyed by project_id with
    all_reqs, nfr_reqs, N (total count) and Q (NFR count).
    """
    by_project = defaultdict(list)
    for rec in records:
        by_project[rec["project_id"]].append(rec)

    pools = {}
    for pid, reqs in by_project.items():
        all_reqs = [{"req_id": r["req_id"], "text": r["text"]} for r in reqs]
        nfr_reqs = [
            {"req_id": r["req_id"], "text": r["text"]}
            for r in reqs if r["is_quality"] == 1
        ]
        pools[pid] = {
            "all_reqs": all_reqs,
            "nfr_reqs": nfr_reqs,
            "N": len(all_reqs),
            "Q": len(nfr_reqs),
        }
        print(f"  Project {pid}: N={len(all_reqs)}, Q={len(nfr_reqs)} NFR")

    return pools


# =============================================================================
# Step 3 — Compute the list of r values
# =============================================================================

def get_r_values(r_min: float, r_max: float, step: float = 0.1) -> list[float]:
    """
    Return evenly spaced ratio values from r_min to r_max (inclusive).

    Example: get_r_values(0.3, 0.6) -> [0.3, 0.4, 0.5, 0.6]
    """
    n_steps = round((r_max - r_min) / step)
    return [round(r_min + i * step, 10) for i in range(n_steps + 1)]


# =============================================================================
# Step 4 — Sample a subset for one observation
# =============================================================================

def sample_subset(
    all_reqs:    list[dict],
    target:      dict,
    operation:   str,
    subset_size: int,
    seed_obs:    int,
) -> list[dict]:
    """
    Draw a reproducible subset for one observation.

    ADD:    target absent, subset_size items sampled from background.
    REMOVE: target forced in as first element, subset_size - 1 background items.
    """
    background_pool = [r for r in all_reqs if r["req_id"] != target["req_id"]]
    rng = random.Random(seed_obs)

    if operation == "add":
        subset = rng.sample(background_pool, subset_size)
    else:  # "remove"
        background_sample = rng.sample(background_pool, subset_size - 1)
        subset = [target] + background_sample

    return subset


# =============================================================================
# Step 5 — Main generation loop
# =============================================================================

def generate_observations(records: list[dict], config: dict) -> list[dict]:
    """
    Iterate over all (project, target, r, k, operation) combinations and
    produce one observation dict per combination.

    observation_id format: {req_id}_{operation}_r{r_tag}_k{seed_idx}
    seed_obs = global_seed + nfr_idx * (M * K) + r_idx * K + seed_idx
    """
    global_seed = config["global_seed"]
    r_values    = get_r_values(config["r_min"], config["r_max"])
    K           = config["K"]
    M           = len(r_values)

    pools        = build_project_pools(records)
    observations = []
    skipped      = 0

    for pid in sorted(pools.keys()):
        pool_data = pools[pid]
        all_reqs  = pool_data["all_reqs"]
        nfr_reqs  = pool_data["nfr_reqs"]
        N         = pool_data["N"]

        expected = pool_data["Q"] * 2 * M * K
        print(f"\nProject {pid}: generating up to {expected} observations …")

        for nfr_idx, target in enumerate(nfr_reqs):
            for r_idx, r in enumerate(r_values):

                subset_size = math.floor(r * N)

                if subset_size < 2:
                    print(f"  SKIP {target['req_id']} r={r}: "
                          f"subset_size={subset_size} < 2")
                    skipped += 2 * K
                    continue

                if subset_size - 1 > N - 1:
                    print(f"  SKIP {target['req_id']} r={r}: "
                          f"not enough background requirements")
                    skipped += 2 * K
                    continue

                background_size = N - 1
                max_distinct = min(
                    comb(background_size, subset_size),
                    comb(background_size, subset_size - 1),
                )
                effective_K = min(K, max_distinct)
                if effective_K < K:
                    print(f"  NOTE {target['req_id']} r={r}: "
                          f"K capped at {effective_K} "
                          f"(only {max_distinct} distinct subsets possible)")

                for seed_idx in range(effective_K):
                    seq_idx  = nfr_idx * (M * K) + r_idx * K + seed_idx
                    seed_obs = global_seed + seq_idx
                    r_tag    = str(r).replace(".", "")

                    for operation in ["add", "remove"]:
                        subset = sample_subset(
                            all_reqs    = all_reqs,
                            target      = target,
                            operation   = operation,
                            subset_size = subset_size,
                            seed_obs    = seed_obs,
                        )

                        obs = {
                            "observation_id": (
                                f"{target['req_id']}_{operation}"
                                f"_r{r_tag}_k{seed_idx}"
                            ),
                            "project_id":   pid,
                            "operation":    operation,
                            "subset_ratio": r,
                            "subset_size":  subset_size,
                            "seed_obs":     seed_obs,
                            "subset":       subset,
                            "target": {
                                "req_id": target["req_id"],
                                "text":   target["text"],
                            },
                            "llm_predicted_nfr_ranked": None,
                        }
                        observations.append(obs)

    print(f"\nGeneration complete: {len(observations)} observations "
          f"({skipped} skipped).")
    return observations


# =============================================================================
# Step 6 — Deduplication check
# =============================================================================

def check_duplicates(observations: list[dict]) -> list[dict]:
    """
    Remove duplicate observations. Uniqueness is defined by
    (operation, target req_id, frozenset of subset req_ids).
    """
    seen    = set()
    unique  = []
    n_dupes = 0

    for obs in observations:
        key = (
            obs["operation"],
            obs["target"]["req_id"],
            frozenset(r["req_id"] for r in obs["subset"]),
        )
        if key not in seen:
            seen.add(key)
            unique.append(obs)
        else:
            n_dupes += 1

    if n_dupes:
        print(f"WARNING: {n_dupes} duplicate observations removed.")
    else:
        print("Deduplication check passed — no duplicates found.")

    print(f"Final dataset: {len(unique)} unique observations.")
    return unique


# =============================================================================
# Step 7 — Save output and print statistics
# =============================================================================

def save_observations(observations: list[dict], output_path: str) -> None:
    """
    Serialise the observation list to JSON and print dataset statistics.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(observations, f, ensure_ascii=False, indent=2)

    total     = len(observations)
    add_count = sum(1 for o in observations if o["operation"] == "add")
    rem_count = sum(1 for o in observations if o["operation"] == "remove")
    projects  = sorted(set(o["project_id"] for o in observations))

    per_project = defaultdict(int)
    for o in observations:
        per_project[o["project_id"]] += 1

    print(f"\n{'='*52}")
    print(f"Output : {output_path}")
    print(f"{'─'*52}")
    print(f"Total observations : {total:>6}")
    print(f"  ADD              : {add_count:>6}")
    print(f"  REMOVE           : {rem_count:>6}")
    print(f"{'─'*52}")
    print("Per-project breakdown:")
    for pid in projects:
        print(f"  Project {pid:>3}     : {per_project[pid]:>6}")
    print(f"{'='*52}")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    records      = load_csv(CONFIG["csv_path"])
    observations = generate_observations(records, CONFIG)
    observations = check_duplicates(observations)
    save_observations(observations, CONFIG["output_path"])
