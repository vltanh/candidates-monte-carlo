#!/usr/bin/env python3
"""
Evaluate a fixed set of hyperparameters against one or more tournaments.
Reports the same Weighted Game Brier Score and Winner Brier Score used during tuning.

Usage:
    python evaluate.py configs/best_hparams_22_24.json data/candidates2022.json
    python evaluate.py configs/best_hparams_22_24.json data/candidates2022.json data/candidates2024.json
    python evaluate.py configs/best_hparams_22_24.json data/candidates2024.json --runs 100000
"""

import argparse
from math import isnan
from pathlib import Path

from utils import (
    EVAL_RUNS,
    evaluate,
    get_actual_winners,
    known_games,
    load_jsonc,
)


def main():
    parser = argparse.ArgumentParser(
        description="Score a fixed hyperparameter set against tournament data."
    )
    parser.add_argument(
        "hyperparameters", type=Path, help="Path to hyperparameters JSON"
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
        "--runs",
        type=int,
        default=EVAL_RUNS,
        help=f"Simulation runs per round (default: {EVAL_RUNS})",
    )

    args = parser.parse_args()

    if not args.binary.exists():
        raise FileNotFoundError(f"Binary not found at {args.binary}.")
    if not args.hyperparameters.exists():
        raise FileNotFoundError(
            f"Hyperparameters file not found at {args.hyperparameters}."
        )
    for tp in args.tournaments:
        if not tp.exists():
            raise FileNotFoundError(f"Tournament file not found at {tp}.")

    params = load_jsonc(args.hyperparameters)
    # Strip simulation-only keys that evaluate() controls
    for key in ("runs", "map_iters", "map_tolerance"):
        params.pop(key, None)

    print(f"Hyperparameters: {args.hyperparameters}")
    print(f"Simulation runs: {args.runs}")
    print("-" * 60)

    total_game_scores, total_winner_scores = [], []

    for tp in args.tournaments:
        data = load_jsonc(tp)
        is_ongoing = any("result" not in g for g in data["schedule"])
        games = known_games(data)
        winners = None if is_ongoing else get_actual_winners(games)

        rounds_played = len(set(g["round"] for g in games))
        status = "ongoing" if is_ongoing else f"winner(s): {', '.join(winners)}"
        print(f"\n[{tp.name}] {len(games)} games, {rounds_played} rounds — {status}")

        g_score, w_score = evaluate(
            params,
            games,
            args.binary,
            tp,
            winners,
            eval_runs=args.runs,
            verbose=True,
        )
        total_game_scores.append(g_score)
        total_winner_scores.append(w_score)

        winner_str = f"{w_score:.6f}" if not isnan(w_score) else "N/A"
        print(f"  -> Weighted Game Brier: {g_score:.6f}  |  Winner Brier: {winner_str}")

    if len(args.tournaments) > 1:
        avg_g = sum(total_game_scores) / len(total_game_scores)
        finite_winner_scores = [s for s in total_winner_scores if not isnan(s)]
        avg_w = (
            sum(finite_winner_scores) / len(finite_winner_scores)
            if finite_winner_scores
            else float("nan")
        )
        print("\n" + "=" * 60)
        print(f"AVERAGE across {len(args.tournaments)} tournaments")
        print(f"  Weighted Game Brier: {avg_g:.6f}")
        winner_avg_str = f"{avg_w:.6f}" if not isnan(avg_w) else "N/A"
        print(f"  Winner Brier:        {winner_avg_str}")
        print("=" * 60)


if __name__ == "__main__":
    main()
