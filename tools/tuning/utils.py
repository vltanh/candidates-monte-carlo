"""
Shared utilities for chess Monte Carlo simulation scoring.
Used by both tools/tuning/tune.py (Optuna) and tools/tuning/evaluate.py (standalone).
"""

import json
import re
import subprocess
import tempfile
from math import isnan
from pathlib import Path

# ── Scoring constants ──────────────────────────────────────────────────────────

EVAL_RUNS = 10_000

FUTURE_DECAY_WEIGHT = 0.80  # Decays weight for predicting games further into the future
MACRO_DECAY_WEIGHT = 0.95  # Gentle decay to favor early-tournament Rank RPS accuracy
WINNER_EVAL_CUTOFF = 1.0  # Evaluate winner MSE for all rounds
DECISIVE_GAME_WEIGHT = 1.0  # Weights draws and decisive games equally

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
                "round": g.get("round", i // gpr + 1),
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


def parse_engine_output(output: str, sim_round: int) -> dict:
    """Parses pure JSON output directly from the engine."""
    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        print(f"\n[PARSER ERROR] Invalid JSON: {e}\nOutput:\n{output[:500]}...")
        return {}


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
) -> tuple[float, float, float, float]:
    """Returns: (game_mse, winner_mse, exp_pts_mse, rps)"""
    rounds = sorted(set(g["round"] for g in games))

    all_players = set()
    for g in games:
        all_players.add(g["white"])
        all_players.add(g["black"])

    cumulative_game_loss = 0.0
    cumulative_game_weight = 0.0
    cumulative_winner_mse, cumulative_pts_mse, cumulative_rps = 0.0, 0.0, 0.0
    total_macro_weight = 0.0
    winner_cutoff_idx = max(1, int(len(rounds) * WINNER_EVAL_CUTOFF))

    for i, r in enumerate(rounds):
        config = {**(hyper_base or {}), **params, "runs": eval_runs}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonc", delete=False) as fh:
            json.dump(config, fh)
            tmp = Path(fh.name)

        try:
            proc = subprocess.run(
                [str(binary_path), str(tmp), str(tourney_path), str(r)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        finally:
            tmp.unlink(missing_ok=True)

        engine_data = parse_engine_output(proc.stdout, r)
        if not engine_data:
            return float("inf"), float("inf"), float("inf"), float("inf")

        # ------------------------------------------------------------------
        # 1. Game Brier Loss (Time Decay & Decisive Weighted)
        # ------------------------------------------------------------------
        for g in [g for g in games if g["round"] >= r]:
            g_round = str(g["round"])
            pair_key = f"{g['white']}|{g['black']}"

            if (
                g_round in engine_data.get("game_probs", {})
                and pair_key in engine_data["game_probs"][g_round]
            ):
                pw, pd, pb = engine_data["game_probs"][g_round][pair_key]
                actual = g["result"]
                act_w = 1.0 if actual == 1.0 else 0.0
                act_d = 1.0 if actual == 0.5 else 0.0
                act_b = 1.0 if actual == 0.0 else 0.0

                brier_loss = (
                    (pw - act_w) ** 2 + (pd - act_d) ** 2 + (pb - act_b) ** 2
                ) / 2.0

                time_weight = FUTURE_DECAY_WEIGHT ** (int(g_round) - r)
                outcome_weight = DECISIVE_GAME_WEIGHT if actual != 0.5 else 1.0
                weight = time_weight * outcome_weight

                cumulative_game_loss += brier_loss * weight
                cumulative_game_weight += weight

        # ------------------------------------------------------------------
        # 2. Macro State Losses (Expected Points, RPS, Winner) - Gently Decayed
        # ------------------------------------------------------------------
        run_winner_mse, run_pts_mse, run_rps = float("nan"), float("nan"), float("nan")
        if actual_winners and i < winner_cutoff_idx:
            final_scores = {p: 0.0 for p in all_players}
            for g in games:
                final_scores[g["white"]] += g["result"]
                final_scores[g["black"]] += 1.0 - g["result"]

            score_groups = {}
            for p, s in final_scores.items():
                score_groups.setdefault(s, []).append(p)

            N_players = len(all_players)
            actual_rank_probs = {p: [0.0] * N_players for p in all_players}
            curr_rank = 0
            for s in sorted(score_groups.keys(), reverse=True):
                group = score_groups[s]
                k = len(group)
                for p in group:
                    for j in range(curr_rank, curr_rank + k):
                        actual_rank_probs[p][j] = 1.0 / k
                curr_rank += k

            run_winner_mse, run_pts_mse, run_rps = 0.0, 0.0, 0.0
            for p in all_players:
                # Winner
                pred_win = engine_data["winner_probs"].get(p, 0.0)
                act_win = (1.0 / len(actual_winners)) if p in actual_winners else 0.0
                run_winner_mse += (pred_win - act_win) ** 2

                # Expected Points
                pred_pts = engine_data["expected_points"].get(p, 0.0)
                run_pts_mse += (pred_pts - final_scores[p]) ** 2

                # Rank Probability Score (RPS)
                pred_ranks = engine_data["rank_matrix"].get(p, [0.0] * N_players)
                cum_pred, cum_act, p_rps = 0.0, 0.0, 0.0
                for j in range(N_players):
                    cum_pred += pred_ranks[j]
                    cum_act += actual_rank_probs[p][j]
                    p_rps += (cum_pred - cum_act) ** 2
                run_rps += p_rps / (N_players - 1)

            run_winner_mse /= 2.0
            run_pts_mse /= N_players
            run_rps /= N_players

            # Gentle decay based on the round number
            macro_weight = MACRO_DECAY_WEIGHT ** (r - 1)
            cumulative_winner_mse += run_winner_mse * macro_weight
            cumulative_pts_mse += run_pts_mse * macro_weight
            cumulative_rps += run_rps * macro_weight
            total_macro_weight += macro_weight

        if verbose:
            game_str = (
                f"{cumulative_game_loss/cumulative_game_weight:.6f}"
                if cumulative_game_weight > 0
                else "N/A"
            )
            w_str = f"{run_winner_mse:.6f}" if not isnan(run_winner_mse) else "N/A"
            pts_str = f"{run_pts_mse:.6f}" if not isnan(run_pts_mse) else "N/A"
            rps_str = f"{run_rps:.6f}" if not isnan(run_rps) else "N/A"
            print(
                f"  Round {r:>2}: g_brier={game_str} | win_brier={w_str} | pts_mse={pts_str} | rps={rps_str}"
            )

    final_g = (
        cumulative_game_loss / cumulative_game_weight
        if cumulative_game_weight > 0
        else float("inf")
    )
    final_w = (
        cumulative_winner_mse / total_macro_weight
        if total_macro_weight > 0
        else float("nan")
    )
    final_p = (
        cumulative_pts_mse / total_macro_weight
        if total_macro_weight > 0
        else float("nan")
    )
    final_r = (
        cumulative_rps / total_macro_weight if total_macro_weight > 0 else float("nan")
    )

    return final_g, final_w, final_p, final_r
