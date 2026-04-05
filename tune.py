#!/usr/bin/env python3
"""
Hyperparameter tuning for chess_montecarlo via Optuna.
Multi-Objective Optimization: Independent Game MSE & Tournament Winner MSE.
Includes Decisive Outcome Weighting to combat the "Lazy Draw" problem.
"""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
import optuna

# ── Constants ─────────────────────────────────────────────────────────────────

STUDY_NAME = "chess_montecarlo"
DB_NAME = "tuning_2024.db"

# Trial accuracy — raise to 100k+ for final verification overnight
EVAL_RUNS = 10_000

# Scoring logic:
FUTURE_DECAY_WEIGHT = 0.35  # Decays weight for predicting games further into the future
WINNER_EVAL_CUTOFF = 1.0  # Evaluate winner MSE for all rounds (set <1.0 to stop early when standings crystallize)
DECISIVE_GAME_WEIGHT = (
    2.5  # Multiplier for penalizing misses on decisive games (Wins/Losses)
)

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


def get_actual_winners(games: list[dict]) -> list[str]:
    """Calculates the actual tournament winner(s) based on total points."""
    scores = {}
    for g in games:
        scores[g["white"]] = scores.get(g["white"], 0.0) + g["result"]
        scores[g["black"]] = scores.get(g["black"], 0.0) + (1.0 - g["result"])

    if not scores:
        return []
    max_score = max(scores.values())
    return [p for p, s in scores.items() if s == max_score]


# ── Output Parsing ────────────────────────────────────────────────────────────

_ROUND_HEADER = re.compile(r"--- ROUND (\d+)")
_PROBS_LINE = re.compile(
    r"1-0:\s*([\d.]+)%\s*\|\s*1/2-1/2:\s*([\d.]+)%\s*\|\s*0-1:\s*([\d.]+)%"
)
_WIN_PROB_LINE = re.compile(r"^\s*([\d.]+)%\s*-\s*(.+)$")


def parse_engine_output(output: str, sim_round: int) -> tuple[dict, dict]:
    """Returns predictions for future rounds AND the overall tournament winner."""
    preds_by_round = {}
    winner_preds = {}
    current_round = None
    in_winners = False
    pending_pair = None

    for line in output.splitlines():
        if "=== Tournament Win Probabilities" in line:
            in_winners = True
            current_round = None
            continue

        if in_winners:
            if m := _WIN_PROB_LINE.search(line):
                prob = float(m.group(1)) / 100.0
                player = m.group(2).strip()
                winner_preds[player] = prob
            continue

        if m := _ROUND_HEADER.search(line):
            r = int(m.group(1))
            if r >= sim_round:
                current_round = r
                if current_round not in preds_by_round:
                    preds_by_round[current_round] = {}
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
            preds_by_round[current_round][pending_pair] = (pw, pd, pb)
            pending_pair = None

    return preds_by_round, winner_preds


# ── Evaluation Engine ─────────────────────────────────────────────────────────


def evaluate(
    params: dict,
    games: list[dict],
    hyper_base: dict,
    trial: optuna.Trial,
    binary_path: Path,
    tourney_path: Path,
    actual_winners: list[str],
) -> tuple[float, float]:
    """Independent Weighted Game Brier Score and Winner Brier Score.
    Simulation points are weighted by round number: predicting correctly when
    you are closer to the end of the tournament matters more."""
    rounds = sorted(set(g["round"] for g in games))

    cumulative_game_mse = 0.0
    cumulative_winner_mse = 0.0

    total_game_weight = 0.0
    total_winner_weight = 0.0

    # Stop evaluating winner MSE once standings crystallize
    winner_cutoff_idx = max(1, int(len(rounds) * WINNER_EVAL_CUTOFF))

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
            return float("inf"), float("inf")
        finally:
            tmp.unlink(missing_ok=True)

        if proc.returncode != 0:
            print(f"\n[C++ ERROR - Return Code {proc.returncode}]")
            print(
                proc.stderr.strip() if proc.stderr else "(No stderr output. Segfault?)"
            )
            return float("inf"), float("inf")

        preds_by_round, winner_preds = parse_engine_output(proc.stdout, r)

        if not preds_by_round or not winner_preds:
            print(
                f"\n[PARSER ERROR] Could not read probabilities from C++ output for round {r}."
            )
            return float("inf"), float("inf")

        # ------------------------------------------------------------------
        # 1. Game Predictions (Micro-State MSE)
        # ------------------------------------------------------------------
        run_game_loss = 0.0
        run_game_weight = 0.0

        for g in [g for g in games if g["round"] >= r]:
            g_round = g["round"]
            key = (g["white"], g["black"])

            if g_round in preds_by_round and key in preds_by_round[g_round]:
                pw, pd, pb = preds_by_round[g_round][key]
                actual_score = g["result"]

                # Define one-hot actuals: (White Win, Draw, Black Win)
                actual_w = 1.0 if actual_score == 1.0 else 0.0
                actual_d = 1.0 if actual_score == 0.5 else 0.0
                actual_b = 1.0 if actual_score == 0.0 else 0.0

                # Multi-Class Brier Score (Sum of squared errors across all 3 classes)
                # Brier score ranges from 0.0 (perfect) to 2.0 (completely wrong)
                brier_loss = (
                    (pw - actual_w) ** 2 + (pd - actual_d) ** 2 + (pb - actual_b) ** 2
                )

                # You can still optionally apply your decisive multiplier
                distance = g_round - r
                time_weight = FUTURE_DECAY_WEIGHT**distance
                outcome_weight = DECISIVE_GAME_WEIGHT if actual_score != 0.5 else 1.0

                weight = time_weight * outcome_weight

                run_game_loss += (
                    brier_loss / 2.0
                ) * weight  # Div by 2 normalizes max loss to 1.0
                run_game_weight += weight

        # Zero-prediction edge case safely caught
        if run_game_weight == 0:
            print(f"\n[SCORING ERROR] No valid games scored in round {r}.")
            return float("inf"), float("inf")

        run_game_mse = run_game_loss / run_game_weight
        cumulative_game_mse += run_game_mse * r
        total_game_weight += r

        # ------------------------------------------------------------------
        # 2. Tournament Winner Prediction (Macro-State MSE)
        # ------------------------------------------------------------------
        if i < winner_cutoff_idx:
            run_winner_mse = 0.0
            for player, prob in winner_preds.items():
                actual_prob = (
                    (1.0 / len(actual_winners)) if player in actual_winners else 0.0
                )
                run_winner_mse += (prob - actual_prob) ** 2

            run_winner_mse = run_winner_mse / 2.0  # Normalize max penalty to ~1.0

            cumulative_winner_mse += run_winner_mse * r
            total_winner_weight += r

    final_game_mse = (
        cumulative_game_mse / total_game_weight
        if total_game_weight > 0
        else float("inf")
    )
    final_winner_mse = (
        cumulative_winner_mse / total_winner_weight
        if total_winner_weight > 0
        else float("inf")
    )

    return final_game_mse, final_winner_mse


# ── Optuna Objective ──────────────────────────────────────────────────────────


def objective(
    trial: optuna.Trial,
    games: list[dict],
    hyper_base: dict,
    binary_path: Path,
    tourney_path: Path,
    actual_winners: list[str],
) -> tuple[float, float]:
    """Hyperparameter search space."""

    map_priors = {
        # Anchor strength in MAP update; log scale — effect is multiplicative
        "prior_weight_known": trial.suggest_float("prior_weight_known", 0.01, 20.0, log=True),
        "prior_weight_sim": trial.suggest_float("prior_weight_sim", 0.01, 20.0, log=True),
    }

    velocity = {
        # Direct Elo offset split ±½ onto white/black lambdas; real chess ≈ 35–50
        "initial_white_adv": trial.suggest_float("initial_white_adv", 0.0, 100.0),
        # WLS exponent base pow(decay, age); must be ≤ 1 (decay), = 1 is flat weights
        "velocity_time_decay": trial.suggest_float("velocity_time_decay", 0.3, 1.0),
        # Scales velocity in forward projection; negative = mean reversion
        "lookahead_factor": trial.suggest_float("lookahead_factor", -1.0, 5.0),
    }

    blending = {
        # Blend coefficient pulling classical estimate toward rapid; negative = inverse signal
        "rapid_form_weight": trial.suggest_float("rapid_form_weight", -0.5, 2.0),
        "blitz_form_weight": trial.suggest_float("blitz_form_weight", -0.5, 2.0),
        # Mixes white/black lambdas & aggression; 0 = fully separate, 0.5 = symmetric crossover
        "color_bleed": trial.suggest_float("color_bleed", 0.0, 0.5),
    }

    draw = {
        # Scales draw band: p_draw = ν·√(λW·λB)/denom; log scale — effect is multiplicative
        "classical_nu": trial.suggest_float("classical_nu", 0.1, 10.0, log=True),
        "rapid_nu": trial.suggest_float("rapid_nu", 0.1, 10.0, log=True),
        "blitz_nu": trial.suggest_float("blitz_nu", 0.1, 10.0, log=True),
    }

    aggression = {
        # Laplace smoothing on decisive-game fraction; log scale
        "agg_prior_weight": trial.suggest_float("agg_prior_weight", 0.5, 100.0, log=True),
        # Prior mean for decisive-game fraction; lives in [0, 1] as a probability
        "default_aggression_w": trial.suggest_float("default_aggression_w", 0.0, 1.0),
        "default_aggression_b": trial.suggest_float("default_aggression_b", 0.0, 1.0),
        # Deflates draw band for players behind; max(0.40, 1 − s·deficit) clamps above ~0.5
        "standings_aggression": trial.suggest_float("standings_aggression", 0.0, 0.5),
    }

    params = {**map_priors, **velocity, **blending, **draw, **aggression}
    return evaluate(
        params, games, hyper_base, trial, binary_path, tourney_path, actual_winners
    )


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
                if k in frozen_trial.params:
                    print(f"    {k:<22}: {frozen_trial.params[k]:.4f}", flush=True)
            print("-" * 60, flush=True)
    except ValueError:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Tune the Monte Carlo chess engine.")
    parser.add_argument(
        "hyperparameters", type=Path, help="Path to your base hyperparameters.json"
    )
    parser.add_argument("tournament", type=Path, help="Path to your tournament.json")

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
    if not args.tournament.exists():
        raise FileNotFoundError(f"Tournament file not found at {args.tournament}.")

    args.db.parent.mkdir(parents=True, exist_ok=True)

    hyper_base = load_jsonc(args.hyperparameters)
    games = known_games(load_jsonc(args.tournament))
    actual_winners = get_actual_winners(games)

    print(
        f"Loaded {len(games)} known games across {len(set(g['round'] for g in games))} rounds."
    )
    print(f"Ground Truth Tournament Winner(s): {', '.join(actual_winners)}")
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
        baseline = {
            "prior_weight_known": hyper_base.get("prior_weight_known", 1.0),
            "prior_weight_sim": hyper_base.get("prior_weight_sim", 1.0),
            "initial_white_adv": hyper_base.get("initial_white_adv", 32.0),
            "velocity_time_decay": hyper_base.get("velocity_time_decay", 0.70),
            "lookahead_factor": hyper_base.get("lookahead_factor", 0.60),
            "rapid_form_weight": hyper_base.get("rapid_form_weight", 0.40),
            "blitz_form_weight": hyper_base.get("blitz_form_weight", 0.15),
            "color_bleed": hyper_base.get("color_bleed", 0.05),
            "classical_nu": hyper_base.get("classical_nu", 2.1),
            "rapid_nu": hyper_base.get("rapid_nu", 3.9),
            "blitz_nu": hyper_base.get("blitz_nu", 1.6),
            "agg_prior_weight": hyper_base.get("agg_prior_weight", 15.5),
            "default_aggression_w": hyper_base.get("default_aggression_w", 0.60),
            "default_aggression_b": hyper_base.get("default_aggression_b", 0.50),
            "standings_aggression": hyper_base.get("standings_aggression", 0.15),
        }
        study.enqueue_trial(baseline)

    study.optimize(
        lambda t: objective(
            t, games, hyper_base, args.binary, args.tournament, actual_winners
        ),
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
