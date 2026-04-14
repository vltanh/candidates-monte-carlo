#!/usr/bin/env python3
"""
Generate a self-contained HTML visualisation for a chess Candidates tournament.

Examples
--------
# 2026 (ongoing) with full model info:
python tools/viz/generate_html.py \\
    --tournament data/candidates2026.jsonc \\
    --rounds    results/candidates2026/rounds/ \\
    --hparams   configs/best_hparams_22_24.jsonc \\
    --db        db/tuning_22_24.db \\
    --output    vltanh.github.io/assets/chess/candidates2026.html

# 2024 (historical), predictions only:
python tools/viz/generate_html.py \\
    --tournament data/candidates2024.jsonc \\
    --rounds    results/candidates2024/rounds/ \\
    --output    vltanh.github.io/assets/chess/candidates2024.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── palette ───────────────────────────────────────────────────────────────────

PLAYER_COLORS = [
    "#40c4ff",  # vivid azure
    "#ffb300",  # golden amber
    "#00e676",  # vivid emerald
    "#ff4081",  # hot pink
    "#b388ff",  # vivid violet
    "#ea80fc",  # bright fuchsia
    "#18ffff",  # electric cyan
    "#c6ff00",  # acid lime
    "#ff6e40",  # deep orange
    "#76ff03",  # neon green
]

# ── hparam metadata ───────────────────────────────────────────────────────────

HPARAM_GROUPS: dict[str, list[str]] = {
    "Simulation": ["runs", "map_iters", "map_tolerance"],
    "MAP priors": ["prior_weight_known", "prior_weight_sim"],
    "Rating model": ["initial_white_adv", "velocity_time_decay", "lookahead_factor"],
    "Cross-TC blending": ["rapid_form_weight", "blitz_form_weight", "color_bleed"],
    "Draw model": ["classical_nu", "rapid_nu", "blitz_nu"],
    "Aggression": [
        "agg_prior_weight",
        "default_aggression_w",
        "default_aggression_b",
        "standings_aggression",
    ],
}

HPARAM_DESC: dict[str, str] = {
    "runs": "Monte Carlo simulations per run",
    "map_iters": "MAP solver max iterations",
    "map_tolerance": "MAP solver convergence tolerance",
    "prior_weight_known": "Prior weight for known-opponent ratings",
    "prior_weight_sim": "Prior weight for simulated ratings",
    "initial_white_adv": "White-piece advantage (Elo)",
    "velocity_time_decay": "Rating velocity time-decay factor",
    "lookahead_factor": "Forward-looking rating horizon",
    "rapid_form_weight": "Rapid rating blend weight",
    "blitz_form_weight": "Blitz rating blend weight",
    "color_bleed": "White↔Black rating cross-pollination",
    "classical_nu": "Classical draw model parameter ν",
    "rapid_nu": "Rapid draw model parameter ν",
    "blitz_nu": "Blitz draw model parameter ν",
    "agg_prior_weight": "Aggression prior weight",
    "default_aggression_w": "Default White aggression baseline",
    "default_aggression_b": "Default Black aggression baseline",
    "standings_aggression": "Standings-driven aggression factor",
}

# ── JSONC helpers ─────────────────────────────────────────────────────────────


def _extract_meta_comments(text: str) -> dict[str, str]:
    """Pull '// Key: Value' header comments (before any JSON body)."""
    meta: dict[str, str] = {}
    for m in re.finditer(r"//\s*([A-Za-z][\w\s#]*):\s*(.+)", text):
        key = m.group(1).strip().lower().replace(" ", "_").replace("#", "")
        meta[key] = m.group(2).strip()
    return meta


def strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def load_jsonc(path: Path) -> tuple[dict, dict[str, str]]:
    """Returns (parsed_dict, metadata_from_comments)."""
    raw = path.read_text(encoding="utf-8")
    meta = _extract_meta_comments(raw)
    return json.loads(strip_jsonc(raw)), meta


# ── player helpers ────────────────────────────────────────────────────────────


def _fallback_short(full: str) -> str:
    """Last-resort short name when no alias is available."""
    if "," in full:
        return full.split(",")[0].strip()
    return full.split()[0]


def load_aliases(path: Path) -> dict[str, str]:
    """Load name→alias mapping from a players.jsonc file."""
    try:
        data = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
        return {p["name"]: p["alias"] for p in data if "alias" in p}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Warning: could not load players file {path}: {e}", file=sys.stderr)
        return {}


def build_players(t_data: dict, aliases: dict[str, str]) -> list[dict]:
    raw = sorted(t_data["players"], key=lambda p: p.get("rating", 0), reverse=True)
    return [
        {
            "key": p["name"],
            "short": aliases.get(p["name"]) or _fallback_short(p["name"]),
            "color": PLAYER_COLORS[i % len(PLAYER_COLORS)],
            "fide_id": p.get("fide_id"),
            "rating": p.get("rating"),
            "rapid_rating": p.get("rapid_rating"),
            "blitz_rating": p.get("blitz_rating"),
            "history": p.get("history", []),
            "games_played": p.get("games_played", []),
            "rapid_history": p.get("rapid_history", []),
            "rapid_games_played": p.get("rapid_games_played", []),
            "blitz_history": p.get("blitz_history", []),
            "blitz_games_played": p.get("blitz_games_played", []),
        }
        for i, p in enumerate(raw)
    ]


# ── schedule helpers ──────────────────────────────────────────────────────────


def cumulative_scores(t_data: dict) -> dict[str, list[float]]:
    """Index 0 = before R1, index k = after Rk."""
    id2name = {p["fide_id"]: p["name"] for p in t_data["players"]}
    sched = t_data["schedule"]
    max_r = max((g.get("round", 1) for g in sched), default=0)

    scores: dict[str, float] = {n: 0.0 for n in id2name.values()}
    cum: dict[str, list[float]] = {n: [0.0] for n in id2name.values()}

    for r in range(1, max_r + 1):
        for g in (g for g in sched if g.get("round") == r):
            res = g.get("result")
            if not res:
                continue
            w, b = id2name[g["white"]], id2name[g["black"]]
            if res == "1-0":
                scores[w] += 1.0
            elif res == "0-1":
                scores[b] += 1.0
            elif res == "1/2-1/2":
                scores[w] += 0.5
                scores[b] += 0.5
        for n in scores:
            cum[n].append(scores[n])

    return cum


def schedule_by_round(t_data: dict) -> dict[int, list[dict]]:
    id2name = {p["fide_id"]: p["name"] for p in t_data["players"]}
    idx: dict[int, list[dict]] = {}
    for g in t_data["schedule"]:
        r = g.get("round", 1)
        idx.setdefault(r, []).append(
            {
                "white": id2name[g["white"]],
                "black": id2name[g["black"]],
                "result": g.get("result"),
            }
        )
    return idx


# ── round data ────────────────────────────────────────────────────────────────


def load_rounds(rounds_dir: Path) -> list[tuple[int, dict]]:
    files = sorted(
        rounds_dir.glob("round*.json"),
        key=lambda p: int(re.search(r"\d+", p.stem).group()),  # type: ignore[arg-type]
    )
    if not files:
        sys.exit(f"No round JSON files found in {rounds_dir}")
    return [
        (int(re.search(r"\d+", f.stem).group()), json.loads(f.read_text()))  # type: ignore[arg-type]
        for f in files
    ]


def build_rounds(
    rounds: list[tuple[int, dict]],
    cum: dict[str, list[float]],
    sched_idx: dict[int, list[dict]],
    cached_rounds: dict[int, dict] | None = None,
) -> list[dict]:
    players = list(cum.keys())
    total_r = max(sched_idx.keys())

    result = []
    for rn, data in rounds:
        # Scores entering this round = after round (rn-1)
        prev = rn - 1
        actual: dict[str, float] = {}
        for name, lst in cum.items():
            actual[name] = lst[prev] if prev < len(lst) else lst[-1]

        # Upcoming games
        round_probs = data.get("game_probs", {}).get(str(rn), {})
        upcoming = []
        for g in sched_idx.get(rn, []):
            key = f"{g['white']}|{g['black']}"
            upcoming.append(
                {
                    "white": g["white"],
                    "black": g["black"],
                    "probs": round_probs.get(key, [1 / 3, 1 / 3, 1 / 3]),
                    "result": g["result"],
                }
            )

        # Compute elimination status (or reuse cache)
        if cached_rounds and rn in cached_rounds:
            cached = cached_rounds[rn]
            eliminated = cached["eliminated"]
            win_paths = cached["win_paths"]
            sole_win = cached.get("sole_win_paths", {})
            round_label = "Before R1" if rn == 1 else f"After R{rn - 1}"
            print(f"  [{round_label}] using cached elimination data")
        else:
            last_played = rn - 1
            rem_games = []
            for r in range(last_played + 1, total_r + 1):
                for g in sched_idx.get(r, []):
                    rem_games.append((g["white"], g["black"]))
            round_label = "Before R1" if rn == 1 else f"After R{rn - 1}"
            eliminated, win_paths, sole_win = compute_eliminated(
                players, actual, rem_games, label=round_label
            )

        result.append(
            {
                "label": round_label,
                "round_num": rn,
                "winner_probs": data.get("winner_probs", {}),
                "expected_points": data.get("expected_points", {}),
                "rank_matrix": data.get("rank_matrix", {}),
                "actual_scores": actual,
                "upcoming_games": upcoming,
                "eliminated": eliminated,
                "win_paths": win_paths,
                "sole_win_paths": sole_win,
            }
        )
    return result


# ── all-rounds game predictions ──────────────────────────────────────────────


def build_all_games(
    rounds: list[tuple[int, dict]],
    sched_idx: dict[int, list[dict]],
) -> list[dict]:
    """For each tournament round: use that round's own JSON if available,
    otherwise fall back to the latest JSON (for future rounds)."""
    round_map = {rn: d for rn, d in rounds}
    _, latest_data = rounds[-1]
    result = []
    for rn in sorted(sched_idx.keys()):
        src = round_map.get(rn, latest_data)
        rp = src.get("game_probs", {}).get(str(rn), {})
        result.append(
            {
                "round_num": rn,
                "games": [
                    {
                        "white": g["white"],
                        "black": g["black"],
                        "probs": rp.get(
                            f"{g['white']}|{g['black']}", [1 / 3, 1 / 3, 1 / 3]
                        ),
                        "result": g["result"],
                    }
                    for g in sched_idx.get(rn, [])
                ],
            }
        )
    return result


# ── Pareto ────────────────────────────────────────────────────────────────────


def load_pareto(db_path: Path, study_name: str, max_scatter: int = 600) -> dict | None:
    try:
        import optuna
        from optuna.trial import TrialState
        import numpy as np

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        study = optuna.load_study(
            study_name=study_name,
            storage=f"sqlite:///{db_path.resolve()}",
        )
        all_c = [t for t in study.trials if t.state == TrialState.COMPLETE]
        pareto = study.best_trials
        p_nums = {t.number for t in pareto}

        non_p = [t for t in all_c if t.number not in p_nums]
        step = max(1, len(non_p) // max_scatter)

        vals = np.array([t.values for t in pareto])
        mins = vals.min(axis=0)
        ranges = np.where(mins == 0, 1.0, mins)
        norm = (vals - mins) / ranges
        best = pareto[int(np.sqrt((norm**2).sum(axis=1)).argmin())]

        # Normalize all points by Pareto-front minimum (1.0 = optimal)
        x_min, y_min = float(mins[0]), float(mins[1])

        all_pts = [
            {
                "x": t.values[0] / x_min,
                "y": t.values[1] / y_min,
                "rx": t.values[0],
                "ry": t.values[1],
                "n": t.number,
                "p": False,
            }
            for t in non_p[::step]
        ] + [
            {
                "x": t.values[0] / x_min,
                "y": t.values[1] / y_min,
                "rx": t.values[0],
                "ry": t.values[1],
                "n": t.number,
                "p": True,
            }
            for t in pareto
        ]

        p_sorted = sorted(pareto, key=lambda t: t.values[0])
        return {
            "all_points": all_pts,
            "pareto_line": [
                {
                    "x": t.values[0] / x_min,
                    "y": t.values[1] / y_min,
                    "n": t.number,
                    "rx": t.values[0],
                    "ry": t.values[1],
                }
                for t in p_sorted
            ],
            "best": {
                "x": best.values[0] / x_min,
                "y": best.values[1] / y_min,
                "n": best.number,
                "rx": best.values[0],
                "ry": best.values[1],
            },
            "norm_min": {"x": x_min, "y": y_min},
            "total_trials": len(all_c),
            "pareto_count": len(pareto),
        }
    except Exception as e:
        print(f"Warning: Pareto load failed — {e}", file=sys.stderr)
        return None


# ── hparams ───────────────────────────────────────────────────────────────────


def build_hparams(hp: dict, meta: dict[str, str]) -> dict:
    groups = {}
    for grp, keys in HPARAM_GROUPS.items():
        entries = [
            {"key": k, "value": hp[k], "desc": HPARAM_DESC.get(k, "")}
            for k in keys
            if k in hp
        ]
        if entries:
            groups[grp] = entries

    # Add score metadata from comments if available
    score_meta = {}
    for k in ("trial", "rank", "game_brier", "rank_rps"):
        if k in meta:
            score_meta[k] = meta[k]

    return {"groups": groups, "meta": score_meta}


# ── elimination (3-tier: point check → sampling → DFS) ───────────────────────


def compute_eliminated(
    players: list[str],
    scores: dict[str, float],
    remaining_games: list[tuple[str, str]],
    max_samples: int = 1_000_000,
    label: str = "",
) -> tuple[dict[str, bool], dict[str, dict[str, int]]]:
    """Return (eliminated, win_paths).

    eliminated: {player_name: True/False} — True means eliminated.
    win_paths:  {player_name: {game_key: outcome_idx}} — one winning path per player.

    Three-tier approach:
      Phase 1 – simple point check (can definitively eliminate)
      Phase 2 – uniform random sampling (can definitively prove alive)
      Phase 3 – exhaustive DFS (can definitively prove both)
    """
    import random
    import time

    n = len(remaining_games)
    print(f"  [{label}] {n} remaining games")

    # Phase 1: simple point check
    leader = max(scores.values())
    games_left: dict[str, int] = {p: 0 for p in players}
    for w, b in remaining_games:
        games_left[w] += 1
        games_left[b] += 1

    can_win: dict[str, bool | None] = {}
    uncertain: list[str] = []
    for p in players:
        if scores[p] + games_left[p] < leader:
            can_win[p] = False
        else:
            can_win[p] = None
            uncertain.append(p)

    phase1_elim = [p for p in players if can_win[p] is False]
    print(
        f"    Phase 1 (points): {len(phase1_elim)} eliminated"
        + (f" — {', '.join(phase1_elim)}" if phase1_elim else "")
        + f", {len(uncertain)} uncertain"
    )

    if not uncertain:
        return {p: True for p in players}, {}, {}

    # Phase 1b: per-game floor — for each remaining game, the max of the two
    # players' post-game scores is at least min over {W,D,L} of max(w+dw, b+db).
    guaranteed_top = leader
    for w, b in remaining_games:
        sw, sb = scores[w], scores[b]
        g = min(max(sw + 1, sb), max(sw + 0.5, sb + 0.5), max(sw, sb + 1))
        if g > guaranteed_top:
            guaranteed_top = g

    if guaranteed_top > leader:
        newly_elim = []
        for p in list(uncertain):
            if scores[p] + games_left[p] < guaranteed_top:
                can_win[p] = False
                uncertain.remove(p)
                newly_elim.append(p)
        print(
            f"    Phase 1b (per-game): guaranteed top ≥ {guaranteed_top}"
            + (
                f", {len(newly_elim)} eliminated — {', '.join(newly_elim)}"
                if newly_elim
                else ", 0 eliminated"
            )
        )

        if not uncertain:
            eliminated = {p: can_win[p] is not True for p in players}
            total_elim = sum(1 for v in eliminated.values() if v)
            print(
                f"    Result: {total_elim} eliminated, {len(players)-total_elim} alive"
            )
            return eliminated, {}, {}

    deltas = [(1.0, 0.0), (0.5, 0.5), (0.0, 1.0)]
    win_paths: dict[str, dict[str, int]] = {}  # player -> {game_key: outcome_idx}
    sole_win_path: dict[str, bool] = {}  # tracks if stored path is a sole win

    def check_winners(sc: dict[str, float]) -> list[str]:
        mx = max(sc.values())
        return [p for p in players if sc[p] == mx]

    def _needs_path(winners: list[str]) -> bool:
        """Check if any winner still needs a (better) path stored."""
        for k in winners:
            if k not in win_paths or (len(winners) == 1 and not sole_win_path.get(k)):
                return True
        return False

    def _store_path(winners: list[str], choices_map: dict[str, int]) -> None:
        """Store path for each winner, preferring sole-win paths over tied."""
        is_sole = len(winners) == 1
        for k in winners:
            if can_win[k] is not True:
                can_win[k] = True
            # Overwrite if: no path yet, or upgrading from tied to sole
            if k not in win_paths or (is_sole and not sole_win_path.get(k)):
                win_paths[k] = choices_map
                sole_win_path[k] = is_sole

    # Phase 2: uniform random sampling
    t0 = time.time()
    sc = dict(scores)
    samples_used = 0
    for samples_used in range(1, max_samples + 1):
        choices = []
        for w, b in remaining_games:
            ci = random.randrange(3)
            dw, db = deltas[ci]
            sc[w] += dw
            sc[b] += db
            choices.append(ci)
        winners = check_winners(sc)
        if _needs_path(winners):
            _store_path(winners, {
                f"{w}|{b}": ci
                for (w, b), ci in zip(remaining_games, choices)
            })
        for p in players:
            sc[p] = scores[p]
        if all(can_win[k] is True for k in uncertain):
            break
    t1 = time.time()

    phase2_alive = [p for p in uncertain if can_win[p] is True]
    phase2_still = [p for p in uncertain if can_win[p] is not True]
    print(
        f"    Phase 2 (sampling): {samples_used:,} samples, {t1-t0:.3f}s → "
        f"{len(phase2_alive)} proven alive"
        + (
            f", {len(phase2_still)} still uncertain — {', '.join(phase2_still)}"
            if phase2_still
            else ", all resolved"
        )
    )

    # Phase 3: exhaustive DFS for still-uncertain players
    still_uncertain = [k for k in uncertain if can_win[k] is not True]
    if still_uncertain:
        t2 = time.time()
        dfs_leaves = 0
        dfs_path: list[int] = [0] * n  # scratch buffer for current path

        def dfs(idx: int) -> None:
            nonlocal dfs_leaves
            if idx == n:
                dfs_leaves += 1
                winners = check_winners(sc)
                if _needs_path(winners):
                    _store_path(winners, {
                        f"{remaining_games[i][0]}|{remaining_games[i][1]}": dfs_path[i]
                        for i in range(n)
                    })
                return
            if (all(can_win[k] is True for k in still_uncertain)
                    and all(sole_win_path.get(k) for k in still_uncertain)):
                return
            w, b = remaining_games[idx]
            for di, (dw, db) in enumerate(deltas):
                dfs_path[idx] = di
                sc[w] += dw
                sc[b] += db
                dfs(idx + 1)
                sc[w] -= dw
                sc[b] -= db

        for p in players:
            sc[p] = scores[p]
        dfs(0)
        t3 = time.time()

        phase3_alive = [p for p in still_uncertain if can_win[p] is True]
        phase3_elim = [p for p in still_uncertain if can_win[p] is not True]
        print(
            f"    Phase 3 (DFS): {dfs_leaves:,} leaves, {t3-t2:.3f}s → "
            f"{len(phase3_alive)} proven alive, {len(phase3_elim)} eliminated"
            + (f" — {', '.join(phase3_elim)}" if phase3_elim else "")
        )

    eliminated = {p: can_win[p] is not True for p in players}
    total_elim = [p for p in players if eliminated[p]]
    print(
        f"    Result: {len(total_elim)} eliminated, {len(players)-len(total_elim)} alive"
    )
    return eliminated, win_paths, sole_win_path


# ── cached data extraction from existing HTML ────────────────────────────────


def extract_cached_rounds(html_path: Path) -> dict[int, dict] | None:
    """Extract per-round eliminated/win_paths from an existing HTML output.

    Returns {round_num: {"eliminated": {...}, "win_paths": {...}}} or None.
    """
    if not html_path.exists():
        return None
    try:
        text = html_path.read_text(encoding="utf-8")
        prefix = "const DATA = "
        idx = text.find(prefix)
        if idx < 0:
            return None
        start = idx + len(prefix)
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(text, start)
        cache: dict[int, dict] = {}
        for rd in data.get("rounds", []):
            rn = rd.get("round_num")
            if rn is not None and "eliminated" in rd:
                cache[rn] = {
                    "eliminated": rd["eliminated"],
                    "win_paths": rd.get("win_paths", {}),
                    "sole_win_paths": rd.get("sole_win_paths", {}),
                }
        return cache if cache else None
    except Exception as e:
        print(f"Warning: could not extract cached data from {html_path}: {e}",
              file=sys.stderr)
        return None


# ── main data assembly ────────────────────────────────────────────────────────


def assemble(
    t_path: Path,
    t_data: dict,
    rounds: list[tuple[int, dict]],
    hp: dict | None,
    hp_meta: dict[str, str],
    pareto: dict | None,
    aliases: dict[str, str] | None = None,
    cached_rounds: dict[int, dict] | None = None,
) -> dict:
    players = build_players(t_data, aliases or {})
    cum = cumulative_scores(t_data)
    sched_idx = schedule_by_round(t_data)
    rds = build_rounds(rounds, cum, sched_idx, cached_rounds)

    # Tournament metadata: prefer explicit fields, fall back to filename inference
    name = t_data.get("name", "FIDE Candidates")
    year = t_data.get("year")
    if year is None:
        if m := re.search(r"\d{4}", t_path.stem):
            year = int(m.group())
    section = t_data.get("section")
    if section is None:
        section = "Women" if "women" in t_path.stem.lower() else "Open"

    total_r = max((g.get("round", 0) for g in t_data["schedule"]), default=14)
    tiebreak_labels = {
        "fide2026": "FIDE 2026",
        "fide2024": "FIDE 2024",
        "shared": "Shared title",
    }

    return {
        "meta": {
            "name": name,
            "section": section,
            "year": year,
            "gpr": t_data.get("gpr", 4),
            "tiebreak": tiebreak_labels.get(
                t_data.get("tiebreak", ""), t_data.get("tiebreak", "")
            ),
            "total_rounds": total_r,
        },
        "players": players,
        "rounds": rds,
        "all_games": build_all_games(rounds, sched_idx),
        "hparams": build_hparams(hp, hp_meta) if hp else None,
        "pareto": pareto,
        "tournament_players": [
            {
                "name": p["name"],
                "fide_id": p.get("fide_id"),
                "rating": p.get("rating"),
                "rapid_rating": p.get("rapid_rating"),
                "blitz_rating": p.get("blitz_rating"),
                "history": p.get("history", []),
                "games_played": p.get("games_played", []),
                "rapid_history": p.get("rapid_history", []),
                "rapid_games_played": p.get("rapid_games_played", []),
                "blitz_history": p.get("blitz_history", []),
                "blitz_games_played": p.get("blitz_games_played", []),
            }
            for p in sorted(
                t_data["players"], key=lambda x: x.get("rating", 0), reverse=True
            )
        ],
    }


# ── HTML template ─────────────────────────────────────────────────────────────


def html_template() -> str:
    template_path = Path(__file__).parent / "template.html"
    return template_path.read_text(encoding="utf-8")


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate a self-contained HTML visualisation for a Candidates tournament.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--tournament",
        "-t",
        required=True,
        type=Path,
        help="Tournament JSONC file (e.g. data/candidates2026.jsonc)",
    )
    ap.add_argument(
        "--rounds",
        "-r",
        required=True,
        type=Path,
        help="Directory of roundN.json files",
    )
    ap.add_argument(
        "--hparams",
        "-p",
        default=None,
        type=Path,
        help="Hyperparameters JSONC file (optional)",
    )
    ap.add_argument(
        "--db",
        "-d",
        default=None,
        type=Path,
        help="Optuna SQLite database for Pareto front (optional)",
    )
    ap.add_argument(
        "--study",
        "-s",
        default="chess_montecarlo",
        help="Optuna study name (default: chess_montecarlo)",
    )
    ap.add_argument(
        "--output", "-o", required=True, type=Path, help="Output HTML file path"
    )
    ap.add_argument(
        "--players-file",
        default="data/players.jsonc",
        type=Path,
        help="Player name/alias mapping (default: data/players.jsonc)",
    )
    ap.add_argument(
        "--update",
        action="store_true",
        help="Reuse cached elimination/DFS data from existing output HTML for old rounds",
    )

    args = ap.parse_args()

    if not args.tournament.exists():
        sys.exit(f"Tournament file not found: {args.tournament}")
    if not args.rounds.is_dir():
        sys.exit(f"Rounds directory not found: {args.rounds}")

    print(f"Loading tournament: {args.tournament}")
    t_data, _ = load_jsonc(args.tournament)

    print(f"Loading rounds from: {args.rounds}")
    rounds = load_rounds(args.rounds)
    print(f"  Found {len(rounds)} round(s): {[n for n,_ in rounds]}")

    hp, hp_meta = None, {}
    if args.hparams:
        if not args.hparams.exists():
            print(f"Warning: hparams file not found: {args.hparams}", file=sys.stderr)
        else:
            print(f"Loading hparams: {args.hparams}")
            hp, hp_meta = load_jsonc(args.hparams)

    pareto = None
    if args.db:
        if not args.db.exists():
            print(f"Warning: DB not found: {args.db}", file=sys.stderr)
        else:
            print(f"Loading Pareto data from: {args.db}")
            pareto = load_pareto(args.db, args.study)
            if pareto:
                print(
                    f"  {pareto['total_trials']} trials, {pareto['pareto_count']} Pareto-optimal"
                )

    aliases = load_aliases(args.players_file)
    if aliases:
        print(f"Loaded {len(aliases)} player aliases from: {args.players_file}")

    cached_rounds = None
    if args.update:
        print(f"Update mode: checking for cached data in {args.output}")
        cached_rounds = extract_cached_rounds(args.output)
        if cached_rounds:
            print(f"  Found cached data for rounds: {sorted(cached_rounds.keys())}")
        else:
            print("  No cached data found, will compute everything")

    data = assemble(
        args.tournament, t_data, rounds, hp, hp_meta, pareto, aliases, cached_rounds
    )

    template = html_template()
    marker = "/*__INJECT_DATA__*/"
    data_js = f"const DATA = {json.dumps(data, separators=(',', ':'))};"
    html = template.replace(marker, data_js, 1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Written → {args.output}  ({args.output.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
