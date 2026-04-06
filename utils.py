"""
Shared utilities for chess Monte Carlo simulation scoring.
Used by both tune.py (Optuna) and evaluate.py (standalone).
"""

import json
import re
import subprocess
import tempfile
from math import isnan
from pathlib import Path

# ── Scoring constants ──────────────────────────────────────────────────────────

# Trial accuracy — raise to 100k+ for final verification overnight
EVAL_RUNS = 10_000

FUTURE_DECAY_WEIGHT = 0.35  # Decays weight for predicting games further into the future
WINNER_EVAL_CUTOFF = 1.0  # Evaluate winner MSE for all rounds
DECISIVE_GAME_WEIGHT = 2.5  # Multiplier for penalizing misses on decisive games

# ── Data Utilities ─────────────────────────────────────────────────────────────


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


# ── Output Parsing ─────────────────────────────────────────────────────────────

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


# ── Evaluation Engine ──────────────────────────────────────────────────────────


def evaluate(
    params: dict,
    games: list[dict],
    binary_path: Path,
    tourney_path: Path,
    actual_winners: list[str] | None,
    eval_runs: int = EVAL_RUNS,
    hyper_base: dict | None = None,
    verbose: bool = False,
) -> tuple[float, float]:
    """Weighted Game Brier Score and Winner Brier Score.

    Args:
        params:         Hyperparameters to evaluate.
        games:          Ground-truth game list from known_games().
        binary_path:    Path to the compiled C++ engine.
        tourney_path:   Path to the tournament JSON file.
        actual_winners: List of actual winner name(s), or None for an ongoing
                        tournament (winner MSE is skipped; float('nan') returned).
        eval_runs:      Simulation runs per round.
        hyper_base:     Base config dict merged under params (used by tune.py
                        to supply map_iters / map_tolerance etc.).
        verbose:        Print per-round scores to stdout.
    """
    rounds = sorted(set(g["round"] for g in games))

    cumulative_game_mse = 0.0
    cumulative_winner_mse = 0.0
    total_game_weight = 0.0
    total_winner_weight = 0.0

    winner_cutoff_idx = max(1, int(len(rounds) * WINNER_EVAL_CUTOFF))

    for i, r in enumerate(rounds):
        config = {**(hyper_base or {}), **params, "runs": eval_runs}

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
        # 1. Game Predictions (Micro-State Brier Score)
        # ------------------------------------------------------------------
        run_game_loss = 0.0
        run_game_weight = 0.0

        for g in [g for g in games if g["round"] >= r]:
            g_round = g["round"]
            key = (g["white"], g["black"])

            if g_round in preds_by_round and key in preds_by_round[g_round]:
                pw, pd, pb = preds_by_round[g_round][key]
                actual_score = g["result"]

                # One-hot actuals: (White Win, Draw, Black Win)
                actual_w = 1.0 if actual_score == 1.0 else 0.0
                actual_d = 1.0 if actual_score == 0.5 else 0.0
                actual_b = 1.0 if actual_score == 0.0 else 0.0

                # Multi-class Brier Score — ranges 0.0 (perfect) to 2.0 (completely wrong)
                brier_loss = (
                    (pw - actual_w) ** 2 + (pd - actual_d) ** 2 + (pb - actual_b) ** 2
                )

                distance = g_round - r
                time_weight = FUTURE_DECAY_WEIGHT**distance
                outcome_weight = DECISIVE_GAME_WEIGHT if actual_score != 0.5 else 1.0
                weight = time_weight * outcome_weight

                run_game_loss += (
                    brier_loss / 2.0
                ) * weight  # div by 2 normalizes max to 1.0
                run_game_weight += weight

        if run_game_weight == 0:
            print(f"\n[SCORING ERROR] No valid games scored in round {r}.")
            return float("inf"), float("inf")

        run_game_mse = run_game_loss / run_game_weight
        cumulative_game_mse += run_game_mse * r
        total_game_weight += r

        # ------------------------------------------------------------------
        # 2. Tournament Winner Prediction (Macro-State Brier Score)
        # ------------------------------------------------------------------
        run_winner_mse = float("nan")
        if actual_winners and i < winner_cutoff_idx:
            run_winner_mse = 0.0
            all_players = set(winner_preds.keys()) | set(actual_winners)
            for player in all_players:
                prob = winner_preds.get(player, 0.0)
                actual_prob = (
                    (1.0 / len(actual_winners)) if player in actual_winners else 0.0
                )
                run_winner_mse += (prob - actual_prob) ** 2

            run_winner_mse /= 2.0  # Normalize max penalty to ~1.0

            cumulative_winner_mse += run_winner_mse * r
            total_winner_weight += r

        if verbose:
            winner_str = f"{run_winner_mse:.6f}" if not isnan(run_winner_mse) else "N/A"
            print(
                f"  Round {r:>2}: game_brier={run_game_mse:.6f}  winner_brier={winner_str}"
            )

    final_game_mse = (
        cumulative_game_mse / total_game_weight
        if total_game_weight > 0
        else float("inf")
    )
    final_winner_mse = (
        cumulative_winner_mse / total_winner_weight
        if total_winner_weight > 0
        else float("nan")
    )

    return final_game_mse, final_winner_mse
