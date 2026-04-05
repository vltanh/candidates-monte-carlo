#!/usr/bin/env python3
"""
Hyperparameter tuning for chess_montecarlo via Optuna.
Optimizes log loss through progressive N-Step Ahead scoring with Exponential Time Decay.
"""

import argparse
import copy
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
import optuna

# ── Constants ─────────────────────────────────────────────────────────────────

STUDY_NAME = "chess_montecarlo"

# Trial accuracy — raise to 100k+ for final verification overnight
EVAL_RUNS = 10_000

# Scoring logic: Weight multiplier for predicting games N rounds into the future.
FUTURE_DECAY_WEIGHT = 0.35

# Strict printing order to match hyperparameters.json
PARAM_ORDER = [
    "prior_weight_known",
    "prior_weight_sim",
    "initial_white_adv",
    "velocity_time_decay",
    "lookahead_factor",
    "rapid_form_weight",
    "blitz_form_weight",
    "color_bleed",
    "classical_nu",
    "rapid_nu",
    "blitz_nu",
    "agg_prior_weight",
    "default_aggression_w",
    "default_aggression_b",
    "standings_aggression",
]

# ── Data Utilities ────────────────────────────────────────────────────────────


def load_jsonc(path: Path) -> dict:
    """Strip // comments then parse as JSON."""
    text = re.sub(r"//[^\n]*", "", path.read_text())
    return json.loads(text)


def known_games(data: dict) -> list[dict]:
    """Extracts ground-truth results from the tournament schedule."""
    players = {p["fide_id"]: p["name"] for p in data["players"]}
    gpr = len(data["players"]) // 2
    games = []
    for i, g in enumerate(data["schedule"]):
        if "result" not in g:
            continue
        res = g["result"]
        score = 1.0 if res == "1-0" else (0.5 if res == "1/2-1/2" else 0.0)
        games.append(
            {
                "white": players[g["white"]],
                "black": players[g["black"]],
                "result": score,
                "round": i // gpr + 1,
            }
        )
    return games


# ── Output Parsing ────────────────────────────────────────────────────────────

_ROUND_HEADER = re.compile(r"--- ROUND (\d+)")
_PROBS_LINE = re.compile(
    r"1-0:\s*([\d.]+)%\s*\|\s*1/2-1/2:\s*([\d.]+)%\s*\|\s*0-1:\s*([\d.]+)%"
)


def parse_all_future_preds(output: str, sim_round: int) -> dict:
    """Returns { round_int: { (white, black): (pw, pd, pb) } } for all future rounds."""
    preds = {}
    current_round = None
    pending_pair = None

    for line in output.splitlines():
        if m := _ROUND_HEADER.search(line):
            r = int(m.group(1))
            if r >= sim_round:
                current_round = r
                if current_round not in preds:
                    preds[current_round] = {}
            else:
                current_round = None
            continue

        if not current_round:
            continue

        if " vs " in line and not line.startswith(" "):
            parts = line.strip().split(" vs ", 1)
            pending_pair = (parts[0].strip(), parts[1].strip())
        elif (m := _PROBS_LINE.search(line)) and pending_pair:
            pw, pd, pb = [float(x) / 100 for x in m.groups()]
            preds[current_round][pending_pair] = (pw, pd, pb)
            pending_pair = None

    return preds


# ── Evaluation Engine ─────────────────────────────────────────────────────────


def evaluate(
    params: dict,
    games: list[dict],
    hyper_base: dict,
    trial: optuna.Trial,
    binary_path: Path,
    tourney_path: Path,
) -> float:
    """Progressive N-Step Ahead Log Loss with Exponential Time Decay."""
    rounds = sorted(set(g["round"] for g in games))
    total_weighted_loss = 0.0
    total_weight = 0.0

    for i, r in enumerate(rounds):
        config = {**hyper_base, **params, "runs": EVAL_RUNS}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
            json.dump(config, fh)
            tmp = Path(fh.name)

        try:
            proc = subprocess.run(
                [str(binary_path), str(tmp), str(tourney_path), str(r)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print(f"\n[TIMEOUT] C++ engine took longer than 120 seconds on round {r}.")
            tmp.unlink(missing_ok=True)
            return float("inf")
        finally:
            tmp.unlink(missing_ok=True)

        if proc.returncode != 0:
            print(f"\n[C++ ERROR - Return Code {proc.returncode}]")
            print(
                proc.stderr.strip() if proc.stderr else "(No stderr output. Segfault?)"
            )
            return float("inf")

        preds_by_round = parse_all_future_preds(proc.stdout, r)
        if not preds_by_round:
            print(
                f"\n[PARSER ERROR] Could not read probabilities from C++ output for round {r}."
            )
            return float("inf")

        round_step_loss = 0.0
        round_step_weight = 0.0

        for g in [g for g in games if g["round"] >= r]:
            g_round = g["round"]
            key = (g["white"], g["black"])

            if g_round in preds_by_round and key in preds_by_round[g_round]:
                pw, pd, pb = preds_by_round[g_round][key]
                p = pw if g["result"] == 1.0 else (pd if g["result"] == 0.5 else pb)

                loss = -math.log(max(p, 1e-9))
                distance = g_round - r
                weight = FUTURE_DECAY_WEIGHT**distance

                round_step_loss += loss * weight
                round_step_weight += weight

        if round_step_weight > 0:
            total_weighted_loss += round_step_loss
            total_weight += round_step_weight

            current_avg = total_weighted_loss / total_weight
            trial.report(current_avg, i)
            if trial.should_prune():
                raise optuna.exceptions.TrialPruned()

    return total_weighted_loss / total_weight if total_weight else float("inf")


# ── Optuna Objective ──────────────────────────────────────────────────────────


def objective(
    trial: optuna.Trial,
    games: list[dict],
    hyper_base: dict,
    binary_path: Path,
    tourney_path: Path,
) -> float:
    """Hyperparameter search space."""

    map_priors = {
        "prior_weight_known": trial.suggest_float(
            "prior_weight_known", 1.0, 5.0, step=0.1
        ),
        "prior_weight_sim": trial.suggest_float("prior_weight_sim", 1.0, 5.0, step=0.1),
    }

    velocity = {
        "initial_white_adv": trial.suggest_float(
            "initial_white_adv", 25.0, 65.0, step=1.0
        ),
        "velocity_time_decay": trial.suggest_float(
            "velocity_time_decay", 0.70, 1.0, step=0.05
        ),
        "lookahead_factor": trial.suggest_float(
            "lookahead_factor", 0.10, 1.5, step=0.05
        ),
    }

    blending = {
        "rapid_form_weight": trial.suggest_float(
            "rapid_form_weight", 0.05, 0.80, step=0.05
        ),
        "blitz_form_weight": trial.suggest_float(
            "blitz_form_weight", 0.05, 0.80, step=0.05
        ),
        "color_bleed": trial.suggest_float("color_bleed", 0.05, 0.30, step=0.05),
    }

    draw = {
        "classical_nu": trial.suggest_float("classical_nu", 2.0, 6.0, step=0.1),
        "rapid_nu": trial.suggest_float("rapid_nu", 1.5, 5.0, step=0.1),
        "blitz_nu": trial.suggest_float("blitz_nu", 0.5, 4.0, step=0.1),
    }

    aggression = {
        "agg_prior_weight": trial.suggest_float(
            "agg_prior_weight", 2.0, 20.0, step=0.5
        ),
        "default_aggression_w": trial.suggest_float(
            "default_aggression_w", 0.30, 0.85, step=0.05
        ),
        "default_aggression_b": trial.suggest_float(
            "default_aggression_b", 0.10, 0.50, step=0.05
        ),
        "standings_aggression": trial.suggest_float(
            "standings_aggression", 0.05, 0.40, step=0.05
        ),
    }

    params = {**map_priors, **velocity, **blending, **draw, **aggression}
    return evaluate(params, games, hyper_base, trial, binary_path, tourney_path)


# ── Callbacks ─────────────────────────────────────────────────────────────────


def champion_callback(study, frozen_trial):
    """Prints readout in precise JSON order whenever a new best trial is found."""
    try:
        winner = study.best_trial
        if winner.number == frozen_trial.number:
            print(
                f"\n🏆 [NEW BEST] Trial {winner.number} | Weighted Log Loss: {winner.value:.6f}",
                flush=True,
            )
            print("  Parameters:", flush=True)
            for k in PARAM_ORDER:
                if k in winner.params:
                    print(f"    {k:<22}: {winner.params[k]:.4f}", flush=True)
            print("-" * 60, flush=True)
    except ValueError:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Tune the Monte Carlo chess engine.")
    # Positional Arguments
    parser.add_argument(
        "hyperparameters", type=Path, help="Path to your base hyperparameters.json"
    )
    parser.add_argument("tournament", type=Path, help="Path to your tournament.json")

    # Optional Arguments
    parser.add_argument(
        "--binary",
        type=Path,
        default=Path("./bin/chess_montecarlo"),
        help="Path to the C++ executable",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("./db/optuna.db"),
        help="Path to save the Optuna SQLite database.",
    )
    parser.add_argument(
        "--trials", type=int, default=200, help="Number of Optuna trials to run"
    )
    parser.add_argument(
        "--resume", action="store_true", help="Continue an existing study from the db"
    )

    args = parser.parse_args()

    if not args.binary.exists():
        raise FileNotFoundError(
            f"Binary not found at {args.binary}. Please compile the C++ engine first."
        )
    if not args.hyperparameters.exists():
        raise FileNotFoundError(
            f"Hyperparameters file not found at {args.hyperparameters}."
        )
    if not args.tournament.exists():
        raise FileNotFoundError(f"Tournament file not found at {args.tournament}.")

    # Ensure the database directory exists
    args.db.parent.mkdir(parents=True, exist_ok=True)

    hyper_base = load_jsonc(args.hyperparameters)
    games = known_games(load_jsonc(args.tournament))

    print(
        f"Loaded {len(games)} known games across {len(set(g['round'] for g in games))} rounds."
    )
    print(f"Database path: {args.db.resolve()}")
    print(f"Starting optimization (Target: {args.trials} trials)...")
    print("-" * 60)

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # SQLite string requires absolute path to be perfectly safe
    db_url = f"sqlite:///{args.db.resolve()}"

    study = optuna.create_study(
        study_name=STUDY_NAME,
        direction="minimize",
        storage=db_url,
        load_if_exists=args.resume or True,
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
    )

    if not study.trials:
        baseline = {
            "prior_weight_known": hyper_base.get("prior_weight_known", 3.0),
            "prior_weight_sim": hyper_base.get("prior_weight_sim", 2.0),
            "initial_white_adv": hyper_base.get("initial_white_adv", 45.0),
            "velocity_time_decay": hyper_base.get("velocity_time_decay", 0.90),
            "lookahead_factor": hyper_base.get("lookahead_factor", 0.35),
            "rapid_form_weight": hyper_base.get("rapid_form_weight", 0.45),
            "blitz_form_weight": hyper_base.get("blitz_form_weight", 0.50),
            "color_bleed": hyper_base.get("color_bleed", 0.05),
            "classical_nu": hyper_base.get("classical_nu", 3.9),
            "rapid_nu": hyper_base.get("rapid_nu", 3.5),
            "blitz_nu": hyper_base.get("blitz_nu", 2.0),
            "agg_prior_weight": hyper_base.get("agg_prior_weight", 9.5),
            "default_aggression_w": hyper_base.get("default_aggression_w", 0.65),
            "default_aggression_b": hyper_base.get("default_aggression_b", 0.30),
            "standings_aggression": hyper_base.get("standings_aggression", 0.15),
        }
        study.enqueue_trial(baseline)

    study.optimize(
        lambda t: objective(t, games, hyper_base, args.binary, args.tournament),
        n_trials=args.trials,
        n_jobs=1,
        show_progress_bar=True,
        callbacks=[champion_callback],
    )

    print("\n" + "=" * 60)
    print(f"OPTIMIZATION COMPLETE")
    print(f"Best Weighted Log Loss: {study.best_value:.6f}")
    print("-" * 60)
    print(f"{'Parameter':<25} | {'Best Value':<10}")
    print("-" * 40)
    for k in PARAM_ORDER:
        if k in study.best_params:
            print(f"{k:<25} | {study.best_params[k]:<10.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
