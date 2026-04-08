#!/usr/bin/env python3
"""
Visualize the Pareto front from a multi-objective Optuna study.

Usage:
  python tools/tuning/pareto_front.py db/tuning_22_24.db
  python tools/tuning/pareto_front.py db/tuning_22_24.db --save results/pareto/front.png
  python tools/tuning/pareto_front.py db/tuning_22_24.db --method knee
  python tools/tuning/pareto_front.py db/tuning_22_24.db --method weighted --weights 0.7 0.3
  python tools/tuning/pareto_front.py db/tuning_22_24.db --method auc
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

OBJECTIVE_LABELS = ("Weighted Game Brier", "Rank RPS")


def load_study(db_path: Path, study_name: str) -> optuna.Study:
    url = f"sqlite:///{db_path.resolve()}"
    return optuna.load_study(study_name=study_name, storage=url)


def _normalize(pareto_trials: list[optuna.trial.FrozenTrial]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Returns (vals, mins, ranges) for scale-invariant normalization.

    Normalizes as (val - min) / min (fractional excess above best), so objectives
    with very different absolute ranges are compared proportionally rather than
    being collapsed to the same [0, 1] interval.
    """
    vals = np.array([t.values for t in pareto_trials])
    mins = vals.min(axis=0)
    ranges = np.where(mins == 0, 1.0, mins)
    return vals, mins, ranges


def find_best_utopia(pareto_trials: list[optuna.trial.FrozenTrial]) -> optuna.trial.FrozenTrial:
    """Closest point to the utopia corner (0, 0) on the normalized front."""
    vals, mins, ranges = _normalize(pareto_trials)
    norm = (vals - mins) / ranges
    dists = np.sqrt((norm ** 2).sum(axis=1))
    return pareto_trials[int(dists.argmin())]


def find_best_knee(pareto_trials: list[optuna.trial.FrozenTrial]) -> optuna.trial.FrozenTrial:
    """Maximum perpendicular distance from the line connecting the two Pareto endpoints — point of maximum curvature."""
    vals, mins, ranges = _normalize(pareto_trials)
    norm = (vals - mins) / ranges

    # Sort by first objective to define the front endpoints
    order = np.argsort(norm[:, 0])
    norm_sorted = norm[order]

    a = norm_sorted[0]
    b = norm_sorted[-1]
    ab = b - a
    ab_len = np.linalg.norm(ab)
    if ab_len == 0:
        return pareto_trials[0]

    # Perpendicular distance from each point to line a→b
    dists = np.abs(np.cross(ab, a - norm_sorted)) / ab_len
    knee_idx = order[int(dists.argmax())]
    return pareto_trials[knee_idx]


def find_best_weighted(
    pareto_trials: list[optuna.trial.FrozenTrial], weights: list[float]
) -> optuna.trial.FrozenTrial:
    """Minimizer of a weighted sum on the normalized front."""
    w = np.array(weights) / sum(weights)  # normalize so they sum to 1
    vals, mins, ranges = _normalize(pareto_trials)
    norm = (vals - mins) / ranges
    scores = norm @ w
    return pareto_trials[int(scores.argmin())]


def find_best_auc(pareto_trials: list[optuna.trial.FrozenTrial]) -> optuna.trial.FrozenTrial:
    """Area median: point whose cumulative area under the normalized Pareto curve is closest to 50% of the total."""
    pts = sorted(pareto_trials, key=lambda t: t.values[0])
    if len(pts) < 2:
        return pts[0]

    vals, mins, ranges = _normalize(pts)
    norm = (vals - mins) / ranges

    x, y = norm[:, 0], norm[:, 1]
    aucs = np.cumsum((y[1:] + y[:-1]) / 2.0 * np.diff(x))
    half = aucs[-1] / 2.0
    idx = int(np.argmin(np.abs(aucs - half))) + 1
    return pts[min(idx, len(pts) - 1)]


def select_best(
    pareto_trials: list[optuna.trial.FrozenTrial],
    method: str,
    weights: list[float] | None,
) -> tuple[optuna.trial.FrozenTrial, str]:
    """Returns (best_trial, method_label)."""
    if method == "knee":
        return find_best_knee(pareto_trials), "Knee point"
    elif method == "weighted":
        w = weights or [0.5, 0.5]
        label = f"Weighted sum ({w[0]:.2g} × Game Brier + {w[1]:.2g} × Rank RPS)"
        return find_best_weighted(pareto_trials, w), label
    elif method == "auc":
        return find_best_auc(pareto_trials), "Area under Pareto curve (AUC)"
    else:  # utopia (default)
        return find_best_utopia(pareto_trials), "Utopia distance"


def print_pareto_table(
    pareto_trials: list[optuna.trial.FrozenTrial],
    method: str,
    weights: list[float] | None,
) -> None:
    if not pareto_trials:
        return

    # Display order: always utopia distance (independent of selection method)
    _, mins, ranges = _normalize(pareto_trials)
    sorted_trials = sorted(
        pareto_trials,
        key=lambda t: float(np.sqrt((((np.array(t.values) - mins) / ranges) ** 2).sum())),
    )

    col_w = max(len(k) for k in PARAM_ORDER) + 2

    print(f"\n{'=' * 80}")
    print(f"  PARETO FRONT — {len(sorted_trials)} trial(s)")
    print(f"{'=' * 80}")

    for rank, trial in enumerate(sorted_trials):
        game_brier, rank_rps = trial.values
        print(
            f"\n  #{rank + 1}  Trial {trial.number:<5}"
            f"  Game Brier: {game_brier:.6f}   Rank RPS: {rank_rps:.6f}"
        )
        print(f"  {'-' * 56}")
        for key in PARAM_ORDER:
            val = trial.user_attrs.get(key, trial.params.get(key))
            if val is not None:
                print(f"    {key:<{col_w}}: {val:.6f}")

    best, method_label = select_best(pareto_trials, method, weights)
    print(
        f"\n  Suggested best [{method_label}] → Trial {best.number}"
        f"  (Game Brier: {best.values[0]:.6f}, Rank RPS: {best.values[1]:.6f})"
    )
    print(f"\n{'=' * 80}\n")


def plot_pareto(
    study: optuna.Study,
    pareto_trials: list[optuna.trial.FrozenTrial],
    out_path: Path | None,
    method: str,
    weights: list[float] | None,
) -> None:
    all_trials = [
        t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE
    ]
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
    non_pareto = [
        (x, y, n) for x, y, n in zip(all_x, all_y, all_nums) if n not in pareto_numbers
    ]
    if non_pareto:
        nx, ny, nn = zip(*non_pareto)
        scatter = ax.scatter(
            nx,
            ny,
            c=nn,
            cmap="Blues",
            alpha=0.35,
            s=18,
            linewidths=0,
            vmin=0,
            vmax=max(all_nums),
        )
        cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
        cbar.set_label("Trial number", color="#8b949e", fontsize=9)
        cbar.ax.yaxis.set_tick_params(color="#8b949e")
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color="#8b949e")

    # Pareto front staircase line
    ax.step(
        p_x,
        p_y,
        where="post",
        color="#58a6ff",
        linewidth=1.2,
        linestyle="--",
        alpha=0.6,
        zorder=3,
    )

    # Pareto points — gradient from blue (good game) to gold (good RPS)
    colors = cm.plasma(np.linspace(0.2, 0.85, len(pareto_sorted)))
    ax.scatter(
        p_x, p_y, c=colors, s=90, zorder=4, linewidths=0.8, edgecolors="#ffffff40"
    )

    # Mark the suggested best with a star
    best, method_label = select_best(pareto_trials, method, weights)
    ax.scatter(
        [best.values[0]], [best.values[1]],
        marker="*", s=260, color="#ffd700", zorder=5,
        linewidths=0.8, edgecolors="#ffffff80",
        label=f"Best [{method_label}] — Trial {best.number}",
    )
    ax.legend(loc="upper right", fontsize=9, facecolor="#161b22", labelcolor="#c9d1d9", framealpha=0.7)

    # Label Pareto points with trial numbers
    for x, y, n in zip(p_x, p_y, p_nums):
        ax.annotate(
            str(n),
            (x, y),
            textcoords="offset points",
            xytext=(5, 4),
            fontsize=7,
            color="#c9d1d9",
            alpha=0.85,
        )

    ax.set_xlabel(OBJECTIVE_LABELS[0], color="#c9d1d9", fontsize=11)
    ax.set_ylabel(OBJECTIVE_LABELS[1], color="#c9d1d9", fontsize=11)
    ax.set_title(
        f"Pareto Front · {len(pareto_trials)} optimal / {len(all_trials)} total trials",
        color="#f0f6fc",
        fontsize=13,
        pad=12,
    )
    ax.tick_params(colors="#8b949e")
    for spine in ax.spines.values():
        spine.set_edgecolor("#30363d")

    # "ideal" corner annotation
    x_min, y_min = min(all_x), min(all_y)
    ax.annotate(
        "← better",
        xy=(x_min, y_min),
        xytext=(
            x_min + (max(all_x) - x_min) * 0.04,
            y_min - (max(all_y) - y_min) * 0.06,
        ),
        color="#3fb950",
        fontsize=8,
        alpha=0.7,
    )

    plt.tight_layout()

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor()
        )
        print(f"Plot saved to {out_path}")
    else:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize Optuna Pareto front.")
    parser.add_argument(
        "db",
        nargs="?",
        default="db/tuning_2024.db",
        type=Path,
        help="Path to Optuna SQLite database",
    )
    parser.add_argument(
        "study", nargs="?", default="chess_montecarlo", help="Study name"
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        metavar="FILE",
        help="Save plot to file instead of showing it",
    )
    parser.add_argument(
        "--method",
        choices=["utopia", "knee", "weighted", "auc"],
        default="utopia",
        help=(
            "Method for selecting the suggested best trial: "
            "'utopia' (closest to ideal corner under scale-invariant normalization, default), "
            "'knee' (maximum curvature / elbow point), "
            "'weighted' (weighted sum — use with --weights), "
            "'auc' (area median of the normalized Pareto curve)"
        ),
    )
    parser.add_argument(
        "--weights",
        type=float,
        nargs=2,
        default=None,
        metavar=("W_GAME", "W_RPS"),
        help="Objective weights for --method weighted (e.g. --weights 0.7 0.3). Default: 0.5 0.5",
    )
    args = parser.parse_args()

    if args.method == "weighted" and args.weights is None:
        args.weights = [0.5, 0.5]

    if not args.db.exists():
        sys.exit(f"Database not found: {args.db}")

    study = load_study(args.db, args.study)
    pareto = study.best_trials

    all_complete = [
        t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE
    ]
    print(f"Study : {args.study}")
    print(f"Trials: {len(all_complete)} complete, {len(pareto)} Pareto-optimal")

    print_pareto_table(pareto, args.method, args.weights)
    plot_pareto(study, pareto, args.save, args.method, args.weights)


if __name__ == "__main__":
    main()
