#!/usr/bin/env python3
"""
Evaluate a fixed set of hyperparameters against one or more tournaments.
Reports the same Weighted Game Brier Score and Winner Brier Score used during tuning.

Usage:
    python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc
    python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc data/candidates2024.jsonc
    python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2024.jsonc --runs 100000
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

    total_g, total_w, total_p, total_r = [], [], [], []

    for tp in args.tournaments:
        data = load_jsonc(tp)
        is_ongoing = any("result" not in g for g in data["schedule"])
        games = known_games(data)
        winners = None if is_ongoing else get_actual_winners(games)

        rounds_played = len(set(g["round"] for g in games))
        status = "ongoing" if is_ongoing else f"winner(s): {', '.join(winners)}"
        print(f"\n[{tp.name}] {len(games)} games, {rounds_played} rounds — {status}")

        g_score, w_score, pts_score, rps_score = evaluate(
            params,
            games,
            args.binary,
            tp,
            winners,
            eval_runs=args.runs,
            verbose=True,
        )
        total_g.append(g_score)
        total_w.append(w_score)
        total_p.append(pts_score)
        total_r.append(rps_score)

        print(f"  -> Weighted Game Brier: {g_score:.6f}")
        if not isnan(w_score):
            print(f"  -> Winner Brier:        {w_score:.6f}")
            print(f"  -> Expected Points MSE: {pts_score:.6f}")
            print(f"  -> Rank RPS:            {rps_score:.6f}")

    if len(args.tournaments) > 1:
        avg_g = sum(total_g) / len(total_g)
        finite_w = [s for s in total_w if not isnan(s)]
        finite_p = [s for s in total_p if not isnan(s)]
        finite_r = [s for s in total_r if not isnan(s)]

        avg_w = sum(finite_w) / len(finite_w) if finite_w else float("nan")
        avg_p = sum(finite_p) / len(finite_p) if finite_p else float("nan")
        avg_r = sum(finite_r) / len(finite_r) if finite_r else float("nan")

        print("\n" + "=" * 60)
        print(f"AVERAGE across {len(args.tournaments)} tournaments")
        print(f"  Weighted Game Brier: {avg_g:.6f}")
        if not isnan(avg_w):
            print(f"  Winner Brier:        {avg_w:.6f}")
            print(f"  Expected Points MSE: {avg_p:.6f}")
            print(f"  Rank RPS:            {avg_r:.6f}")
        print("=" * 60)


if __name__ == "__main__":
    main()
