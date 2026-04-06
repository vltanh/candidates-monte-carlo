#!/usr/bin/env python3
"""
Hyperparameter tuning for chess_montecarlo via Optuna.
Multi-Objective Optimization: Independent Game MSE & Tournament Winner MSE.
Includes Decisive Outcome Weighting to combat the "Lazy Draw" problem.

Usage:
    python tune.py configs/hyperparameters.json data/candidates2024.json
    python tune.py configs/hyperparameters.json data/candidates2022.json data/candidates2024.json
    python tune.py configs/hyperparameters.json data/candidates2024.json --trials 500
    python tune.py configs/hyperparameters.json data/candidates2024.json --db db/tuning_2024.db
"""

import argparse
from pathlib import Path
import optuna

from utils import (
    evaluate,
    get_actual_winners,
    known_games,
    load_jsonc,
)

# ── Constants ─────────────────────────────────────────────────────────────────

STUDY_NAME = "chess_montecarlo"
DB_NAME = "tuning_2024.db"

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

# ── Optuna Objective ──────────────────────────────────────────────────────────


def objective(
    trial: optuna.Trial,
    tournaments: list[tuple[Path, list[dict], list[str]]],
    hyper_base: dict,
    binary_path: Path,
) -> tuple[float, float]:
    """Hyperparameter search space with strict physicality constraints.
    Scores are averaged across all supplied tournaments."""

    # 1. MAP Priors Constraint: prior_weight_known <= prior_weight_sim
    # Lower prior weight = less inertia = more aggressive updates.
    # We want known data to update more aggressively, so pk must be <= ps.
    ps = trial.suggest_float("prior_weight_sim", 2.0, 10.0, log=True)
    pk_ratio = trial.suggest_float("prior_weight_known_ratio", 0.1, 0.9)
    pk = ps * pk_ratio

    map_priors = {
        "prior_weight_known": pk,
        "prior_weight_sim": ps,
    }

    velocity = {
        "initial_white_adv": trial.suggest_float("initial_white_adv", 0.0, 100.0),
        "velocity_time_decay": trial.suggest_float("velocity_time_decay", 0.3, 1.0),
        "lookahead_factor": trial.suggest_float("lookahead_factor", -1.0, 5.0),
    }

    blending = {
        "rapid_form_weight": trial.suggest_float("rapid_form_weight", -0.5, 2.0),
        "blitz_form_weight": trial.suggest_float("blitz_form_weight", -0.5, 2.0),
        "color_bleed": trial.suggest_float("color_bleed", 0.0, 0.5),
    }

    # 2. Draw Chance Constraint: classical_nu >= rapid_nu >= blitz_nu
    # Higher Nu means a wider draw band (higher draw chance).
    nc = trial.suggest_float("classical_nu", 1.0, 10.0, log=True)
    nr_ratio = trial.suggest_float("rapid_nu_ratio", 0.1, 0.9)
    nr = nc * nr_ratio
    nb_ratio = trial.suggest_float("blitz_nu_ratio", 0.1, 0.9)
    nb = nr * nb_ratio

    draw = {
        "classical_nu": nc,
        "rapid_nu": nr,
        "blitz_nu": nb,
    }

    # 3. Aggression Constraint: default_aggression_w >= default_aggression_b
    aw = trial.suggest_float("default_aggression_w", 0.2, 0.8)
    ab_ratio = trial.suggest_float("default_aggression_b_ratio", 0.1, 0.9)
    ab = aw * ab_ratio

    aggression = {
        "agg_prior_weight": trial.suggest_float(
            "agg_prior_weight", 0.5, 100.0, log=True
        ),
        "default_aggression_w": aw,
        "default_aggression_b": ab,
        "standings_aggression": trial.suggest_float("standings_aggression", 0.0, 0.5),
    }

    params = {**map_priors, **velocity, **blending, **draw, **aggression}

    # Save the derived physical parameters to the trial so the callback can print them
    for key, value in params.items():
        trial.set_user_attr(key, value)

    game_scores, winner_scores = [], []
    for tourney_path, games, actual_winners in tournaments:
        g, w = evaluate(
            params,
            games,
            binary_path,
            tourney_path,
            actual_winners,
            hyper_base=hyper_base,
        )
        if g == float("inf") or w == float("inf"):
            return float("inf"), float("inf")
        game_scores.append(g)
        winner_scores.append(w)

    return sum(game_scores) / len(game_scores), sum(winner_scores) / len(winner_scores)


# ── Callbacks ─────────────────────────────────────────────────────────────────


def champion_callback(study, frozen_trial):
    """Prints the current Pareto front updates."""
    try:
        pareto_front = study.best_trials
        if any(t.number == frozen_trial.number for t in pareto_front):
            print(f"\n🏆 [NEW PARETO OPTIMAL] Trial {frozen_trial.number}", flush=True)
            print(f"  ├─ Weighted Game Brier: {frozen_trial.values[0]:.6f}")
            print(
                f"  └─ Winner Brier:        {frozen_trial.values[1]:.6f}\n", flush=True
            )
            print("  Parameters:", flush=True)
            for k in PARAM_ORDER:
                # Retrieve the projected physical parameter, fallback to direct param
                val = frozen_trial.user_attrs.get(k, frozen_trial.params.get(k))
                if val is not None:
                    print(f"    {k:<22}: {val:.4f}", flush=True)
            print("-" * 60, flush=True)
    except ValueError:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Tune the Monte Carlo chess engine.")
    parser.add_argument(
        "hyperparameters", type=Path, help="Path to your base hyperparameters.json"
    )
    parser.add_argument(
        "tournaments", type=Path, nargs="+", help="Path(s) to tournament JSON files"
    )

    parser.add_argument(
        "--binary",
        type=Path,
        default=Path("./bin/chess_montecarlo"),
        help="Path to the C++ executable",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(f"./db/{DB_NAME}"),
        help="Path to save the Optuna SQLite database.",
    )
    parser.add_argument(
        "--trials", type=int, default=200, help="Number of Optuna trials to run"
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
    for tp in args.tournaments:
        if not tp.exists():
            raise FileNotFoundError(f"Tournament file not found at {tp}.")

    args.db.parent.mkdir(parents=True, exist_ok=True)

    hyper_base = load_jsonc(args.hyperparameters)
    all_tournaments = []
    for tp in args.tournaments:
        games = known_games(load_jsonc(tp))
        winners = get_actual_winners(games)
        all_tournaments.append((tp, games, winners))
        print(
            f"[{tp.name}] {len(games)} games across "
            f"{len(set(g['round'] for g in games))} rounds — "
            f"winner(s): {', '.join(winners)}"
        )
    print(f"Database path: {args.db.resolve()}")
    print(f"Starting Multi-Objective optimization (Target: {args.trials} trials)...")
    print("-" * 60)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    db_url = f"sqlite:///{args.db.resolve()}"

    study = optuna.create_study(
        study_name=STUDY_NAME,
        directions=["minimize", "minimize"],
        storage=db_url,
        load_if_exists=True,
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    if not study.trials:
        ps = hyper_base.get("prior_weight_sim", 1.0)
        pk = hyper_base.get("prior_weight_known", 1.0)
        nc = hyper_base.get("classical_nu", 2.1)
        nr = hyper_base.get("rapid_nu", 3.9)
        nb = hyper_base.get("blitz_nu", 1.6)
        aw = hyper_base.get("default_aggression_w", 0.60)
        ab = hyper_base.get("default_aggression_b", 0.50)
        baseline = {
            "prior_weight_sim": ps,
            "prior_weight_known_ratio": pk / ps,
            "initial_white_adv": hyper_base.get("initial_white_adv", 32.0),
            "velocity_time_decay": hyper_base.get("velocity_time_decay", 0.70),
            "lookahead_factor": hyper_base.get("lookahead_factor", 0.60),
            "rapid_form_weight": hyper_base.get("rapid_form_weight", 0.40),
            "blitz_form_weight": hyper_base.get("blitz_form_weight", 0.15),
            "color_bleed": hyper_base.get("color_bleed", 0.05),
            "classical_nu": nc,
            "rapid_nu_ratio": nr / nc,
            "blitz_nu_ratio": nb / nr,
            "agg_prior_weight": hyper_base.get("agg_prior_weight", 15.5),
            "default_aggression_w": aw,
            "default_aggression_b_ratio": ab / aw,
            "standings_aggression": hyper_base.get("standings_aggression", 0.15),
        }
        study.enqueue_trial(baseline)

    study.optimize(
        lambda t: objective(t, all_tournaments, hyper_base, args.binary),
        n_trials=args.trials,
        n_jobs=1,
        show_progress_bar=True,
        callbacks=[champion_callback],
    )

    print("\n" + "=" * 80)
    print("OPTIMIZATION COMPLETE - PARETO FRONT")
    print(
        "These are the best trials offering unique trade-offs between Game vs Winner MSE."
    )
    print("-" * 80)
    for trial in study.best_trials:
        print(
            f"Trial {trial.number:<4} | Weighted Game Brier: {trial.values[0]:.6f} | Winner Brier: {trial.values[1]:.6f}"
        )
    print("=" * 80)


if __name__ == "__main__":
    main()
