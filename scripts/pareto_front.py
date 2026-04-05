#!/usr/bin/env python3
"""
Visualize the Pareto front from a multi-objective Optuna study.

Usage:
  python scripts/pareto_front.py [db_path] [study_name]
  python scripts/pareto_front.py db/tuning_2024.db chess_montecarlo
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

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

OBJECTIVE_LABELS = ("Weighted Game Brier", "Winner Brier")


def load_study(db_path: Path, study_name: str) -> optuna.Study:
    url = f"sqlite:///{db_path.resolve()}"
    return optuna.load_study(study_name=study_name, storage=url)


def print_pareto_table(pareto_trials: list[optuna.trial.FrozenTrial]) -> None:
    # Sort by average of both objectives as a convenient ordering
    pareto_trials = sorted(pareto_trials, key=lambda t: sum(t.values))

    col_w = max(len(k) for k in PARAM_ORDER) + 2

    print(f"\n{'=' * 80}")
    print(f"  PARETO FRONT — {len(pareto_trials)} trial(s)")
    print(f"{'=' * 80}")

    for rank, trial in enumerate(pareto_trials):
        game_brier, winner_brier = trial.values
        print(f"\n  #{rank + 1}  Trial {trial.number:<5}"
              f"  Game Brier: {game_brier:.6f}   Winner Brier: {winner_brier:.6f}")
        print(f"  {'-' * 56}")
        for key in PARAM_ORDER:
            if key in trial.params:
                print(f"    {key:<{col_w}}: {trial.params[key]:.6f}")

    print(f"\n{'=' * 80}\n")


def plot_pareto(
    study: optuna.Study,
    pareto_trials: list[optuna.trial.FrozenTrial],
    out_path: Path | None,
) -> None:
    all_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    pareto_numbers = {t.number for t in pareto_trials}

    all_x = [t.values[0] for t in all_trials]
    all_y = [t.values[1] for t in all_trials]
    all_nums = [t.number for t in all_trials]

    pareto_sorted = sorted(pareto_trials, key=lambda t: t.values[0])
    p_x = [t.values[0] for t in pareto_sorted]
    p_y = [t.values[1] for t in pareto_sorted]
    p_nums = [t.number for t in pareto_sorted]

    fig, ax = plt.subplots(figsize=(9, 6))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#161b22")

    # All non-Pareto trials, coloured by trial number (age)
    non_pareto = [(x, y, n) for x, y, n in zip(all_x, all_y, all_nums) if n not in pareto_numbers]
    if non_pareto:
        nx, ny, nn = zip(*non_pareto)
        scatter = ax.scatter(nx, ny, c=nn, cmap="Blues", alpha=0.35, s=18,
                             linewidths=0, vmin=0, vmax=max(all_nums))
        cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
        cbar.set_label("Trial number", color="#8b949e", fontsize=9)
        cbar.ax.yaxis.set_tick_params(color="#8b949e")
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#8b949e")

    # Pareto front staircase line
    ax.step(p_x, p_y, where="post", color="#58a6ff", linewidth=1.2,
            linestyle="--", alpha=0.6, zorder=3)

    # Pareto points — gradient from blue (good game) to gold (good winner)
    colors = cm.plasma(np.linspace(0.2, 0.85, len(pareto_sorted)))
    ax.scatter(p_x, p_y, c=colors, s=90, zorder=4, linewidths=0.8,
               edgecolors="#ffffff40")

    # Label Pareto points with trial numbers
    for x, y, n in zip(p_x, p_y, p_nums):
        ax.annotate(str(n), (x, y), textcoords="offset points", xytext=(5, 4),
                    fontsize=7, color="#c9d1d9", alpha=0.85)

    ax.set_xlabel(OBJECTIVE_LABELS[0], color="#c9d1d9", fontsize=11)
    ax.set_ylabel(OBJECTIVE_LABELS[1], color="#c9d1d9", fontsize=11)
    ax.set_title(
        f"Pareto Front · {len(pareto_trials)} optimal / {len(all_trials)} total trials",
        color="#f0f6fc", fontsize=13, pad=12,
    )
    ax.tick_params(colors="#8b949e")
    for spine in ax.spines.values():
        spine.set_edgecolor("#30363d")

    # "ideal" corner annotation
    x_min, y_min = min(all_x), min(all_y)
    ax.annotate("← better", xy=(x_min, y_min), xytext=(x_min + (max(all_x) - x_min) * 0.04,
                y_min - (max(all_y) - y_min) * 0.06),
                color="#3fb950", fontsize=8, alpha=0.7)

    plt.tight_layout()

    if out_path:
        fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        print(f"Plot saved to {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize Optuna Pareto front.")
    parser.add_argument("db", nargs="?", default="db/tuning_2024.db",
                        type=Path, help="Path to Optuna SQLite database")
    parser.add_argument("study", nargs="?", default="chess_montecarlo",
                        help="Study name")
    parser.add_argument("--save", type=Path, default=None, metavar="FILE",
                        help="Save plot to file instead of showing it")
    args = parser.parse_args()

    if not args.db.exists():
        sys.exit(f"Database not found: {args.db}")

    study = load_study(args.db, args.study)
    pareto = study.best_trials

    all_complete = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    print(f"Study : {args.study}")
    print(f"Trials: {len(all_complete)} complete, {len(pareto)} Pareto-optimal")

    print_pareto_table(pareto)
    plot_pareto(study, pareto, args.save)


if __name__ == "__main__":
    main()
