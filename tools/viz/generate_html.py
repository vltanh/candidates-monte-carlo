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

        # Compute elimination status
        last_played = rn - 1
        rem_games = []
        for r in range(last_played + 1, total_r + 1):
            for g in sched_idx.get(r, []):
                rem_games.append((g["white"], g["black"]))
        round_label = "Before R1" if rn == 1 else f"After R{rn - 1}"
        eliminated = compute_eliminated(players, actual, rem_games, label=round_label)

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
) -> dict[str, bool]:
    """Return {player_name: True/False} — True means eliminated.

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
    print(f"    Phase 1 (points): {len(phase1_elim)} eliminated"
          + (f" — {', '.join(phase1_elim)}" if phase1_elim else "")
          + f", {len(uncertain)} uncertain")

    if not uncertain:
        return {p: True for p in players}

    deltas = [(1.0, 0.0), (0.5, 0.5), (0.0, 1.0)]

    def check_winners(sc: dict[str, float]) -> list[str]:
        mx = max(sc.values())
        return [p for p in players if sc[p] == mx]

    # Phase 2: uniform random sampling
    t0 = time.time()
    sc = dict(scores)
    samples_used = 0
    for samples_used in range(1, max_samples + 1):
        for w, b in remaining_games:
            dw, db = random.choice(deltas)
            sc[w] += dw
            sc[b] += db
        for k in check_winners(sc):
            can_win[k] = True
        for p in players:
            sc[p] = scores[p]
        if all(can_win[k] is True for k in uncertain):
            break
    t1 = time.time()

    phase2_alive = [p for p in uncertain if can_win[p] is True]
    phase2_still = [p for p in uncertain if can_win[p] is not True]
    print(f"    Phase 2 (sampling): {samples_used:,} samples, {t1-t0:.3f}s → "
          f"{len(phase2_alive)} proven alive"
          + (f", {len(phase2_still)} still uncertain — {', '.join(phase2_still)}"
             if phase2_still else ", all resolved"))

    # Phase 3: exhaustive DFS for still-uncertain players
    still_uncertain = [k for k in uncertain if can_win[k] is not True]
    if still_uncertain:
        t2 = time.time()
        dfs_leaves = 0

        def dfs(idx: int) -> None:
            nonlocal dfs_leaves
            if idx == n:
                dfs_leaves += 1
                for k in check_winners(sc):
                    if can_win[k] is not True:
                        can_win[k] = True
                return
            if all(can_win[k] is True for k in still_uncertain):
                return
            w, b = remaining_games[idx]
            for dw, db in deltas:
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
        print(f"    Phase 3 (DFS): {dfs_leaves:,} leaves, {t3-t2:.3f}s → "
              f"{len(phase3_alive)} proven alive, {len(phase3_elim)} eliminated"
              + (f" — {', '.join(phase3_elim)}" if phase3_elim else ""))

    result = {p: can_win[p] is not True for p in players}
    total_elim = [p for p in players if result[p]]
    print(f"    Result: {len(total_elim)} eliminated, {len(players)-len(total_elim)} alive")
    return result


# ── main data assembly ────────────────────────────────────────────────────────


def assemble(
    t_path: Path,
    t_data: dict,
    rounds: list[tuple[int, dict]],
    hp: dict | None,
    hp_meta: dict[str, str],
    pareto: dict | None,
    aliases: dict[str, str] | None = None,
) -> dict:
    players = build_players(t_data, aliases or {})
    cum = cumulative_scores(t_data)
    sched_idx = schedule_by_round(t_data)
    rds = build_rounds(rounds, cum, sched_idx)

    year = None
    if m := re.search(r"\d{4}", t_path.stem):
        year = int(m.group())

    total_r = max((g.get("round", 0) for g in t_data["schedule"]), default=14)
    tiebreak_labels = {
        "fide2026": "FIDE 2026",
        "fide2024": "FIDE 2024",
        "shared": "Shared title",
    }

    return {
        "meta": {
            "name": "FIDE Candidates",
            "section": "Women" if "women" in t_path.stem.lower() else "Open",
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
            }
            for p in sorted(
                t_data["players"], key=lambda x: x.get("rating", 0), reverse=True
            )
        ],
    }


# ── HTML template ─────────────────────────────────────────────────────────────


def html_template() -> str:
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title id="pageTitle">Chess Candidates — Monte Carlo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT@0,9..144,300..900,30..100;1,9..144,300..900,30..100&family=Figtree:ital,wght@0,300..900;1,300..900&family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root{
  --ink:#0b1120;
  --ink-2:#121a36;
  --ink-3:#1a2448;
  --paper:#f4f6fb;
  --paper-2:#c0cceb;
  --paper-3:#8494be;
  --paper-4:#4e5f8a;
  --rule:#263764;
  --rule-2:#354d80;
  --azure:#78b4ff;
  --azure-2:#a0ccff;
  --azure-3:#5090ff;
  --cobalt:#3a66cc;
  --signal:#ff6b7a;
}

html{scroll-behavior:smooth}

body{
  background:var(--ink);
  color:var(--paper);
  font-family:'Figtree',system-ui,-apple-system,sans-serif;
  font-feature-settings:"ss01","kern","liga","cv11";
  font-size:18px;
  line-height:1.55;
  -webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility;
  min-height:100vh;
  background-image:
    radial-gradient(ellipse 80% 60% at 20% 10%, rgba(58,102,204,.08) 0%, transparent 60%),
    radial-gradient(ellipse 60% 50% at 80% 85%, rgba(120,180,255,.05) 0%, transparent 55%);
  background-attachment:fixed;
}
a{color:var(--azure);text-decoration-thickness:1px;text-underline-offset:3px}
a:hover{color:var(--paper)}

.page{max-width:1180px;margin:0 auto;padding:3rem 1.5rem 5rem;position:relative}

/* ═══════════════ MASTHEAD ═══════════════ */
.hdr{position:relative;text-align:center;margin-bottom:3rem;padding:0}
.hdr .top-rule{
  display:flex;align-items:center;justify-content:space-between;gap:1rem;
  padding:.55rem 0;
  border-top:1px solid var(--paper-3);
  border-bottom:1px solid var(--paper-4);
  font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:.66rem;letter-spacing:.22em;
  color:var(--paper-2);text-transform:uppercase;
}
.hdr .top-rule .ornament{
  font-family:'Fraunces',serif;font-size:1.15rem;letter-spacing:.4em;
  color:var(--azure);
}
.hdr h1{
  font-family:'Fraunces',serif;
  font-optical-sizing:auto;
  font-variation-settings:"opsz" 144,"SOFT" 30;
  font-weight:900;
  font-size:clamp(2.8rem,6.8vw,4.8rem);
  line-height:.92;
  letter-spacing:-.028em;
  color:var(--paper);
  margin:1.5rem auto .5rem;
  max-width:14ch;
}
.hdr h1 em{
  font-style:italic;
  font-variation-settings:"opsz" 144,"SOFT" 100;
  font-weight:300;
  color:var(--azure);
}
.hdr h1 .hdr-sec{
  font-weight:300;
  font-style:normal;
  font-variation-settings:"opsz" 144,"SOFT" 100;
  color:var(--paper-3);
  font-size:.55em;
  letter-spacing:.08em;
  text-transform:uppercase;
  vertical-align:.12em;
}
.hdr .sub{
  font-family:'Fraunces',serif;font-style:italic;font-weight:400;
  font-variation-settings:"opsz" 14;
  font-size:1.05rem;
  color:var(--paper-2);
  margin-bottom:1.1rem;
}
.hdr .badges{display:flex;flex-wrap:wrap;justify-content:center;gap:.5rem;margin-bottom:1.1rem}
.badge{
  font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:.66rem;letter-spacing:.11em;text-transform:uppercase;
  color:var(--paper-2);
  background:rgba(120,180,255,.02);
  border:1px solid var(--rule-2);
  padding:.4rem .8rem;
  border-radius:3px;
  transition:border-color .2s;
}
.badge:hover{border-color:var(--paper-3)}
.badge.live{color:var(--azure);border-color:var(--azure)}
.badge.live::before{
  content:'';display:inline-block;
  width:6px;height:6px;border-radius:50%;
  background:var(--azure);margin-right:.5rem;vertical-align:1px;
  box-shadow:0 0 0 0 var(--azure);
  animation:pulse 2s cubic-bezier(.4,0,.6,1) infinite;
}
@keyframes pulse{
  0%{box-shadow:0 0 0 0 rgba(106,166,255,.6)}
  70%{box-shadow:0 0 0 9px rgba(106,166,255,0)}
  100%{box-shadow:0 0 0 0 rgba(106,166,255,0)}
}
.gh-link{
  display:inline-flex;align-items:center;gap:.55rem;
  padding:.55rem 1.3rem;
  font-family:'JetBrains Mono',monospace;font-size:.75rem;
  letter-spacing:.1em;text-transform:uppercase;text-decoration:none;
  color:var(--paper);
  background:var(--cobalt);
  border:1px solid var(--cobalt);
  transition:all .25s;
  border-radius:3px;
}
.gh-link:hover{
  color:var(--paper);background:var(--azure-3);border-color:var(--azure-3);
  transform:translateY(-1px);
  box-shadow:0 3px 12px rgba(58,102,204,.25);
}
.gh-link:active{transform:translateY(0);transition:transform .08s}

/* dot-leader hairline beneath masthead */
.hdr::after{
  content:'';display:block;margin-top:1.5rem;height:1px;
  background:linear-gradient(90deg,transparent,var(--rule-2) 20%,var(--azure-3) 50%,var(--rule-2) 80%,transparent);
  opacity:.6;
}

/* ═══════════════ SECTIONS ═══════════════ */
section{margin-bottom:3.25rem}

.card{
  background:var(--ink-2);
  border:1px solid var(--rule);
  padding:1.5rem 1.6rem;
  position:relative;
  transition:border-color .25s,box-shadow .25s;
}
.card:hover{
  border-color:var(--rule-2);
  box-shadow:0 4px 24px rgba(58,102,204,.06),0 1px 4px rgba(0,0,0,.15);
}
.card::before,.card::after{
  content:'';position:absolute;width:14px;height:14px;pointer-events:none;
  transition:width .25s,height .25s;
}
.card::before{top:-1px;left:-1px;border-top:1px solid var(--azure-3);border-left:1px solid var(--azure-3)}
.card::after{bottom:-1px;right:-1px;border-bottom:1px solid var(--azure-3);border-right:1px solid var(--azure-3)}
.card:hover::before,.card:hover::after{width:20px;height:20px}
.card+.show-more-btn,.card+button{margin-top:1.25rem}

.note{
  font-family:'Figtree',sans-serif;font-weight:400;
  font-size:.88rem;color:var(--paper-3);
  margin-top:1rem;line-height:1.55;
}

/* ═══════════════ TABS ═══════════════ */
.tabs-wrap{
  margin-bottom:2.75rem;
  border-top:1px solid var(--rule);
  border-bottom:1px solid var(--rule);
  padding:.85rem 0;
  position:relative;
}
.tabs{display:flex;gap:0;flex-wrap:wrap;justify-content:center}
.tab{
  padding:.55rem .85rem;
  border:none;background:transparent;
  font-family:'JetBrains Mono',monospace;
  font-size:.7rem;font-weight:500;
  letter-spacing:.11em;text-transform:uppercase;
  color:var(--paper-3);
  cursor:pointer;
  position:relative;
  transition:color .18s,background .18s;
}
.tab:hover:not(:disabled){color:var(--paper);background:rgba(120,180,255,.04)}
.tab.active{color:var(--azure)}
.tab.active::after{
  content:'';position:absolute;left:50%;bottom:0;
  width:28px;height:2px;background:var(--azure);
  transform:translateX(-50%);
  animation:tab-in .25s ease-out both;
}
@keyframes tab-in{from{width:0;opacity:0}to{width:28px;opacity:1}}
.tab:disabled{color:var(--paper-4);cursor:not-allowed;opacity:.5}
.tab:disabled::after{content:'';display:none}

/* ═══════════════ CHARTS ═══════════════ */
.chart-wrap{position:relative}
.chart-wrap.tall{height:400px}
.chart-wrap.med{height:290px}

.two-col{display:grid;grid-template-columns:1.05fr .95fr;gap:1.1rem}
@media(max-width:780px){
  .two-col{grid-template-columns:1fr}
  .games-grid{grid-template-columns:1fr!important}
  .hm-table{font-size:.72rem}
  .hm-table th,.hm-table td{padding:.25rem .15rem}
  .card{padding:1rem 1.1rem;overflow-x:auto}
  .page{padding:2rem 1rem 3rem}
  /* standings table */
  table{font-size:.82rem}
  thead th{font-size:.55rem;padding:.4rem .3rem;letter-spacing:.08em}
  tbody td{padding:.55rem .3rem}
  .rank-num{font-size:.85rem;width:1.5rem}
  .rank-num.gold{font-size:1rem}
  .pcell{font-size:.82rem;gap:.35rem}
  .dot{width:7px;height:7px}
  .bar-inline{min-width:40px}
  .winpct{font-size:.72rem}
  .score{font-size:.88rem}
  /* game cards */
  .gcard{padding:.75rem .85rem .7rem}
  .gcard .players{font-size:.85rem;gap:.3rem;margin-bottom:.6rem}
  .prob-bars{height:28px}
  .pb{font-size:.65rem}
  .prob-foot{font-size:.52rem}
  .piece{font-size:.75rem}
  .result-badge{font-size:.58rem;padding:.2rem .5rem}
  /* tabs */
  .tabs{gap:0;justify-content:flex-start;overflow-x:auto;flex-wrap:nowrap;-webkit-overflow-scrolling:touch}
  .tab{padding:.45rem .55rem;font-size:.6rem;flex-shrink:0}
  /* header */
  .hdr h1{font-size:clamp(2rem,5.5vw,3.5rem)}
  .hdr .sub{font-size:.88rem}
  .badges{gap:.35rem}
  .badge{font-size:.58rem;padding:.3rem .55rem}
  .gh-link{font-size:.65rem;padding:.45rem .9rem}
  /* heatmap */
  .hm-table{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
  /* title race detail */
  #titleRaceDetail{font-size:.78rem}
  /* scenario explorer */
  #seSvgWrap{overflow-x:auto}
  /* sections */
  summary{font-size:1.2rem;gap:.6rem}
  summary .num{font-size:.58rem;padding:.2rem .4rem}
  .note{font-size:.78rem}
  /* hp */
  .hp-key{min-width:auto;font-size:.82rem}
  .hp-val{font-size:.88rem}
  .hp-desc{font-size:.78rem}
  .hp-row{gap:.4rem}
  /* pareto meta */
  .pareto-meta{gap:.5rem}
  .pmeta-item{padding:.4rem .7rem}
  .pmeta-item .pv{font-size:1rem}
  /* hide Elo column on mobile */
  .hide-mobile{display:none}
}
@media(max-width:420px){
  .page{padding:1.5rem .65rem 2.5rem}
  .card{padding:.75rem .8rem}
  .hdr h1{font-size:clamp(1.6rem,5vw,2.5rem)}
  .hdr .sub{font-size:.78rem}
  .hdr .top-rule{font-size:.55rem;gap:.5rem}
  table{font-size:.75rem}
  thead th{font-size:.5rem;padding:.3rem .2rem}
  tbody td{padding:.45rem .2rem}
  .pcell{font-size:.75rem}
  .score{font-size:.8rem}
  .bar-inline{min-width:30px;height:10px}
  .winpct{font-size:.65rem}
  .gcard .round-label{font-size:.52rem}
  .gcard .players{font-size:.78rem}
  .pb{font-size:.58rem}
  .prob-foot{font-size:.48rem}
  summary{font-size:1rem}
  .badge{font-size:.52rem;padding:.25rem .4rem}
  .tab{padding:.35rem .4rem;font-size:.52rem}
}

/* ═══════════════ STANDINGS TABLE ═══════════════ */
table{width:100%;border-collapse:collapse;font-size:.93rem}
thead th{
  text-align:left;
  font-family:'JetBrains Mono',monospace;font-weight:500;
  font-size:.62rem;text-transform:uppercase;letter-spacing:.15em;
  color:var(--paper-3);
  padding:.5rem .55rem;
  border-bottom:1px solid var(--rule-2);
}
tbody tr{border-bottom:1px solid var(--rule);transition:background .2s,box-shadow .2s}
tbody tr:last-child{border-bottom:none}
tbody td{padding:.75rem .55rem;vertical-align:middle}
tbody tr:hover{background:rgba(106,166,255,.045);box-shadow:inset 3px 0 0 var(--azure-3)}
tbody tr:nth-child(even){background:rgba(120,180,255,.012)}
.rank-num{
  font-family:'Figtree',sans-serif;
  color:var(--paper-3);font-size:1rem;font-weight:500;
  font-feature-settings:"tnum","lnum";
  width:2.2rem;
}
.rank-num.gold{
  color:var(--azure);font-weight:700;font-size:1.25rem;
}
.dot{
  display:inline-block;width:9px;height:9px;
  flex-shrink:0;
  transform:rotate(45deg);
}
.pcell{
  display:flex;align-items:center;gap:.55rem;
  padding-left:3px;
  font-family:'Figtree',sans-serif;font-weight:500;
  font-size:.95rem;
  color:var(--paper);
}
.score{
  font-family:'JetBrains Mono',monospace;
  font-weight:600;font-size:1.05rem;color:var(--paper);
  font-feature-settings:"tnum","lnum";
}
.winpct{
  font-family:'JetBrains Mono',monospace;
  font-feature-settings:"tnum";
  color:var(--paper-2);font-size:.85rem;font-weight:500;
}
.winpct.hi{color:var(--azure);font-weight:700}
.bar-mini{display:none}
.bar-inline{flex:1;height:14px;background:var(--rule);overflow:hidden;min-width:80px;border-radius:2px}
.bar-inline .bar-fill{height:100%;transition:width .5s cubic-bezier(.22,.61,.36,1);border-radius:2px}
.bar-fill{height:100%}

/* ═══════════════ PLAYER TOGGLES ═══════════════ */
.player-toggles{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1.25rem}
.ptoggle{
  display:inline-flex;align-items:center;gap:.45rem;
  padding:.32rem .75rem;
  border:1px solid;border-radius:3px;
  background:transparent;cursor:pointer;
  font-family:'JetBrains Mono',monospace;
  font-size:.7rem;font-weight:500;
  letter-spacing:.06em;text-transform:uppercase;
  user-select:none;
  transition:all .15s;
}
.ptoggle:hover{background:rgba(106,166,255,.05)}
.ptoggle.off{opacity:.22;text-decoration:line-through}

/* ═══════════════ GAME CARDS ═══════════════ */
.games-grid{display:grid;gap:.9rem}
.gcard{
  background:var(--ink-2);
  border:1px solid var(--rule);
  padding:1rem 1.15rem 1.05rem;
  position:relative;
  transition:border-color .25s,background .25s,box-shadow .25s,transform .2s;
}
.gcard:hover{
  border-color:var(--rule-2);background:var(--ink-3);
  box-shadow:0 2px 12px rgba(0,0,0,.2);
  transform:translateY(-1px);
}
.gcard .round-label{
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;font-weight:500;
  color:var(--paper-3);
  text-transform:uppercase;letter-spacing:.16em;
  margin-bottom:.55rem;
}
.gcard .players{
  font-family:'Figtree',sans-serif;font-weight:600;
  font-size:.98rem;
  display:flex;align-items:center;gap:.45rem;
  padding-left:3px;
  margin-bottom:.85rem;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  color:var(--paper);
}
.gcard .players .sep{
  color:var(--paper-3);font-size:.72rem;
  font-weight:400;text-transform:uppercase;letter-spacing:.1em;
  margin:0 .15rem;
}
.piece{font-size:.88rem;flex-shrink:0;color:var(--paper-2)}
.prob-bars{
  height:34px;display:flex;gap:1px;
  border:1px solid var(--rule);
  border-radius:4px;
  overflow:hidden;
}
.pb{
  display:flex;align-items:center;justify-content:center;
  font-family:'JetBrains Mono',monospace;
  font-size:.74rem;font-weight:700;
  font-feature-settings:"tnum";
  gap:.2rem;letter-spacing:.02em;
}
.pb.white-win{color:var(--paper)}
.pb.draw{color:var(--paper-2);background:rgba(168,184,216,.08)!important}
.pb.black-win{color:var(--paper)}
.pb .ps{font-size:.62rem;opacity:.75}
.prob-foot{
  display:flex;justify-content:space-between;
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;color:var(--paper-3);
  margin-top:.45rem;letter-spacing:.08em;text-transform:uppercase;
}
.result-badge{
  display:inline-block;margin-top:.7rem;
  padding:.3rem .8rem;
  font-family:'JetBrains Mono',monospace;
  font-size:.64rem;font-weight:700;
  letter-spacing:.12em;text-transform:uppercase;
  border:1px solid #ffee58;
  color:#ffee58;
  background:rgba(255,238,88,.10);
  border-radius:3px;
  animation:badge-in .4s ease-out both;
}
@keyframes badge-in{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:none}}
.result-badge.draw{color:var(--paper);border-color:var(--paper-2);background:rgba(168,184,216,.08)}

/* ═══════════════ SHOW-MORE / PANELS ═══════════════ */
.show-more-btn{
  display:block;margin:0 auto;
  padding:.5rem 1.25rem;
  border:1px solid var(--rule-2);background:transparent;
  color:var(--paper-2);
  font-family:'JetBrains Mono',monospace;
  font-size:.66rem;font-weight:500;
  letter-spacing:.14em;text-transform:uppercase;
  cursor:pointer;transition:all .22s;
  border-radius:3px;
}
.show-more-btn:hover{
  color:var(--azure);border-color:var(--azure);
  background:rgba(106,166,255,.06);
  box-shadow:0 0 12px rgba(106,166,255,.08);
}
.show-more-btn:active{transform:scale(.97);transition:transform .08s}
.all-games-panel{margin-top:1.5rem}
.games-section-lbl{
  font-family:'JetBrains Mono',monospace;
  font-size:.66rem;font-weight:500;
  color:var(--paper-3);text-transform:uppercase;letter-spacing:.16em;
  margin:1.75rem 0 .75rem;
  display:flex;align-items:center;gap:.85rem;
}
.games-section-lbl::after{content:'';flex:1;height:1px;background:var(--rule)}
.round-group{margin-bottom:1.4rem}
.round-group-lbl{
  font-family:'Figtree',sans-serif;font-weight:600;
  font-size:.85rem;color:var(--paper-2);
  text-transform:uppercase;letter-spacing:.1em;
  margin-bottom:.6rem;padding-bottom:.3rem;
  border-bottom:1px solid var(--rule);
}

/* ═══════════════ HEATMAP ═══════════════ */
.hm-table{width:100%;border-collapse:collapse;font-size:.82rem}
.hm-table th{
  text-align:center;
  font-family:'JetBrains Mono',monospace;
  font-size:.6rem;font-weight:500;
  color:var(--paper-3);text-transform:uppercase;letter-spacing:.12em;
  padding:.4rem .35rem;
  border-bottom:1px solid var(--rule-2);
}
.hm-table th:first-child{text-align:left}
.hm-table td{text-align:center;padding:.35rem .3rem;border-bottom:1px solid var(--rule)}
.hm-table td:first-child{text-align:left}
.hm-cell{
  display:inline-block;width:100%;padding:.25rem .25rem;
  font-family:'JetBrains Mono',monospace;
  font-feature-settings:"tnum";
  font-weight:600;font-size:.74rem;letter-spacing:.02em;
  border-radius:2px;
  transition:transform .15s,box-shadow .15s;
}
.hm-cell:hover{transform:scale(1.08);box-shadow:0 0 8px rgba(106,166,255,.15)}

/* ═══════════════ PARETO ═══════════════ */
.pareto-meta{display:flex;gap:.8rem;flex-wrap:wrap;margin-bottom:1.3rem}
.pmeta-item{
  background:transparent;
  border:1px solid var(--rule-2);
  padding:.55rem 1rem;
  position:relative;
  transition:border-color .2s,background .2s;
  border-radius:3px;
}
.pmeta-item:hover{border-color:var(--azure-3);background:rgba(106,166,255,.03)}
.pmeta-item .pk{
  font-family:'JetBrains Mono',monospace;
  font-size:.58rem;font-weight:500;
  color:var(--paper-3);text-transform:uppercase;letter-spacing:.14em;
  margin-bottom:.15rem;
}
.pmeta-item .pv{
  font-family:'Figtree',sans-serif;
  font-size:1.25rem;font-weight:700;
  color:var(--azure);
  font-feature-settings:"tnum","lnum";
}

/* ═══════════════ HPARAMS ═══════════════ */
.hp-groups{display:grid;grid-template-columns:1fr;gap:.9rem}
.hp-group{
  background:var(--ink-2);
  border:1px solid var(--rule);
  padding:1.4rem 1.6rem;
  transition:border-color .25s;
}
.hp-group:hover{border-color:var(--rule-2)}
.hp-group h4{
  font-family:'JetBrains Mono',monospace;
  font-weight:500;font-size:.78rem;
  text-transform:uppercase;letter-spacing:.16em;
  color:var(--azure);
  margin-bottom:1.1rem;
  padding-bottom:.65rem;
  border-bottom:1px solid var(--rule);
}
.hp-row{
  display:flex;align-items:baseline;gap:.75rem;flex-wrap:wrap;
  padding:.7rem 0;
  border-bottom:1px dotted var(--rule);
}
.hp-row:last-child{border-bottom:none}
.hp-key{
  font-family:'JetBrains Mono',monospace;
  font-size:.95rem;font-weight:500;color:var(--paper);
  min-width:16rem;flex:0 0 auto;
}
.hp-val{
  font-family:'JetBrains Mono',monospace;
  font-size:1rem;font-weight:700;
  color:var(--azure);
  margin-left:auto;white-space:nowrap;
  font-feature-settings:"tnum";
}
.hp-desc{
  font-family:'Figtree',sans-serif;font-weight:400;
  font-size:.88rem;color:var(--paper-3);
  display:block;margin-top:.3rem;flex-basis:100%;
  line-height:1.45;
}
.hp-score-row{display:flex;gap:.8rem;flex-wrap:wrap;margin-bottom:1.5rem}
.hp-score{
  background:transparent;
  border:1px solid var(--rule-2);
  padding:.65rem 1.15rem;
  border-radius:3px;
  transition:border-color .2s;
}
.hp-score:hover{border-color:var(--azure-3)}
.hp-score .sk{
  font-family:'JetBrains Mono',monospace;
  font-size:.7rem;font-weight:500;
  color:var(--paper-3);
  text-transform:uppercase;letter-spacing:.14em;
  margin-bottom:.15rem;
}
.hp-score .sv{
  font-family:'Figtree',sans-serif;
  font-size:1.35rem;font-weight:700;
  color:var(--azure);
  font-feature-settings:"tnum","lnum";
}

/* ═══════════════ SORTABLE HEADERS ═══════════════ */
th[data-sort]{cursor:pointer;user-select:none;position:relative;white-space:nowrap}
th[data-sort]:hover{color:var(--azure)}
th[data-sort]::after{
  content:'⇅';margin-left:.35rem;font-size:.65rem;opacity:.35;
  font-family:'JetBrains Mono',monospace;
}
th[data-sort].asc::after{content:'↑';opacity:.85;color:var(--azure)}
th[data-sort].desc::after{content:'↓';opacity:.85;color:var(--azure)}

/* ═══════════════ DETAILS (COLLAPSIBLE) ═══════════════ */
details{margin-bottom:3.25rem}
summary{
  cursor:pointer;
  background:transparent;
  font-family:'Fraunces',serif;
  font-variation-settings:"opsz" 48,"SOFT" 30;
  font-weight:500;
  font-size:1.5rem;
  letter-spacing:-.012em;
  color:var(--paper);
  list-style:none;user-select:none;
  display:flex;align-items:baseline;gap:.9rem;
  padding-bottom:.6rem;
  border-bottom:1px solid var(--rule);
  transition:color .2s,border-color .2s;
}
summary:hover{color:var(--azure);border-bottom-color:var(--azure-3)}
summary::-webkit-details-marker{display:none}
summary::after{
  content:'▾';
  margin-left:auto;
  font-family:'JetBrains Mono',monospace;
  font-size:.8rem;
  color:var(--paper-3);
  transition:transform .25s;
  position:relative;top:-.15em;
}
details[open] summary::after{transform:rotate(180deg)}
summary .num{
  font-family:'JetBrains Mono',monospace;
  font-size:.66rem;font-weight:500;
  color:var(--azure);letter-spacing:.2em;text-transform:uppercase;
  padding:.25rem .5rem;border:1px solid var(--azure-3);
  font-variation-settings:initial;
  position:relative;top:-.25em;
  display:inline-block;min-width:1.8em;text-align:center;
}
.sec-sub{font-style:italic;color:var(--azure-2);font-weight:400}
.details-body{padding:1.1rem 0 0;animation:details-reveal .35s ease-out both}
@keyframes details-reveal{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
.details-body section:last-child{margin-bottom:0}

/* ═══════════════ REVEAL ═══════════════ */
@keyframes fade-in{
  from{opacity:0;transform:translateY(10px)}
  to{opacity:1;transform:none}
}
.hdr .top-rule{animation:fade-in .9s .05s both}
.hdr h1{animation:fade-in 1.1s .2s both}
.hdr .sub{animation:fade-in 1.1s .35s both}
.hdr .badges{animation:fade-in 1.1s .5s both}
.hdr .gh-link{animation:fade-in 1.1s .6s both}
.tabs-wrap{animation:fade-in 1.1s .7s both}
details{animation:fade-in .8s both}
details:nth-of-type(1){animation-delay:.8s}
details:nth-of-type(2){animation-delay:.95s}
details:nth-of-type(3){animation-delay:1.1s}
details:nth-of-type(4){animation-delay:1.25s}
details:nth-of-type(5){animation-delay:1.4s}
details:nth-of-type(n+6){animation-delay:1.6s}
.appendix-divider{animation:fade-in .8s 1.5s both}

/* scenario tree transitions */
@keyframes se-fwd{
  from{opacity:0;transform:translateX(60px)}
  to{opacity:1;transform:none}
}
@keyframes se-bwd{
  from{opacity:0;transform:translateX(-60px)}
  to{opacity:1;transform:none}
}
@keyframes se-fade{
  from{opacity:0;transform:scale(0.97)}
  to{opacity:1;transform:none}
}
#seSvgWrap{scroll-behavior:smooth}
#seSvgWrap>svg{will-change:transform,opacity}
#seFootnote{transition:opacity .3s,transform .3s}
#seRandomMenu{
  backdrop-filter:blur(8px);
  box-shadow:0 4px 16px rgba(0,0,0,.35);
}

/* subtle grain overlay for atmosphere */
body::before{
  content:'';position:fixed;inset:0;z-index:9999;pointer-events:none;
  opacity:.03;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size:180px;
}

/* focus visible for accessibility */
:focus-visible{
  outline:2px solid var(--azure-3);
  outline-offset:2px;
}
button:focus-visible{
  outline:2px solid var(--azure-3);
  outline-offset:2px;
}

/* selection */
::selection{background:rgba(106,166,255,.35);color:var(--paper)}

/* scrollbar */
html{scrollbar-color:var(--rule-2) var(--ink)}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-track{background:var(--ink)}
::-webkit-scrollbar-thumb{background:var(--rule-2);border:2px solid var(--ink);border-radius:4px}
::-webkit-scrollbar-thumb:hover{background:var(--azure-3)}

/* ═══════════════ APPENDIX DIVIDER ═══════════════ */
.appendix-divider{
  margin:3rem 0 1.5rem;
  display:flex;align-items:center;gap:1rem;
}
.appendix-divider::before,.appendix-divider::after{
  content:'';flex:1;height:1px;
  background:linear-gradient(90deg,transparent,var(--rule) 30%,var(--rule) 70%,transparent);
}
.appendix-label{
  font-family:'JetBrains Mono',monospace;
  font-size:.7rem;letter-spacing:.25em;text-transform:uppercase;
  color:var(--paper-3);white-space:nowrap;
}

/* ═══════════════ BACK TO TOP (floating) ═══════════════ */
.back-to-top{
  position:fixed;bottom:1.5rem;right:1.5rem;z-index:90;
  width:40px;height:40px;
  display:flex;align-items:center;justify-content:center;
  padding:0;
  font-family:'JetBrains Mono',monospace;
  font-size:1rem;line-height:1;
  color:var(--paper-3);
  background:rgba(18,26,54,.65);
  backdrop-filter:blur(8px);
  border:1px solid var(--rule-2);
  border-radius:50%;
  cursor:pointer;
  opacity:0;pointer-events:none;
  transition:opacity .3s,color .2s,border-color .2s,transform .2s,box-shadow .2s;
}
.back-to-top.visible{opacity:1;pointer-events:auto}
.back-to-top:hover{
  color:var(--azure);border-color:var(--azure-3);
  transform:translateY(-2px);
  box-shadow:0 2px 12px rgba(106,166,255,.15);
  background:rgba(18,26,54,.85);
}
</style>
</head>
<body>
<div class="page">

<!-- header / masthead -->
<header class="hdr">
  <div class="top-rule">
    <span id="hdr-vol">VOL. —</span>
    <span class="ornament">♜ &nbsp;·&nbsp; ♞ &nbsp;·&nbsp; ♝</span>
    <span>MONTE CARLO EDITION</span>
  </div>
  <h1 id="hdr-title">FIDE <em>Candidates</em></h1>
  <div class="sub" id="hdr-sub">A broadsheet of simulated futures — one million tournaments, recomputed at every round.</div>
  <div class="badges" id="hdr-badges"></div>
  <a class="gh-link" href="https://github.com/vltanh/candidates-monte-carlo" target="_blank" rel="noopener">
    <svg height="13" width="13" viewBox="0 0 16 16" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
               0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
               -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
               .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
               -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27
               .68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12
               .51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48
               0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
    </svg>
    vltanh/candidates-monte-carlo
  </a>
</header>

<!-- round tabs -->
<div class="tabs-wrap"><div class="tabs" id="tabs"></div></div>

<!-- I: timeline -->
<details open>
  <summary><span class="num">I</span> Win Probability <em class="sec-sub">Timeline</em></summary>
  <div class="details-body">
    <div class="card">
      <div class="player-toggles" id="playerToggles"></div>
      <div class="chart-wrap tall"><canvas id="cTimeline"></canvas></div>
      <p class="note">Click a tab above to see predictions entering that round. The dashed rule marks the selected round. Click a player chip to show or hide them.</p>
    </div>
  </div>
</details>

<!-- II: standings -->
<details open id="roundPanel">
  <summary id="roundTitle"><span class="num">II</span> Standings</summary>
  <div class="details-body">
    <div class="card"><table id="tStandings"><thead><tr>
      <th data-sort="rank">#</th><th data-sort="player">Player</th><th data-sort="elo" class="hide-mobile">Elo</th><th data-sort="score">Score</th><th data-sort="winpct">Win %</th>
    </tr></thead><tbody id="tbStandings"></tbody></table></div>
    <div style="display:none"><canvas id="cWinPct"></canvas></div>
    <div class="card" id="titleRaceCard" style="margin-top:1.1rem;display:none">
      <div style="font-family:'JetBrains Mono',monospace;font-size:.66rem;font-weight:500;color:var(--paper-3);text-transform:uppercase;letter-spacing:.16em;margin-bottom:.85rem" id="titleRaceLabel">Title Race</div>
      <div class="chart-wrap med"><canvas id="cTitleRace"></canvas></div>
      <div id="titleRaceDetail" style="margin-top:1rem"></div>
      <p class="note" id="titleRaceNote"></p>
      <div style="display:flex;justify-content:center;margin-top:1rem">
        <button class="show-more-btn" id="showScenariosBtn" onclick="toggleScenarios()">▾ Scenario explorer</button>
      </div>
      <div id="scenarioContainer" style="display:none;margin-top:1.5rem"></div>
    </div>
  </div>
</details>

<!-- III: games -->
<details open>
  <summary id="gamesTitle"><span class="num">III</span> Game Predictions <em class="sec-sub">Round</em></summary>
  <div class="details-body">
    <div class="all-games-panel" id="pastGamesPanel" style="display:none"></div>
    <div style="display:flex;justify-content:center;margin-bottom:1rem">
      <button class="show-more-btn" id="showPastBtn" onclick="toggleSection('past')">▴ Past rounds</button>
    </div>
    <div class="games-grid" id="gamesGrid"></div>
    <div style="display:flex;justify-content:center;margin-top:1rem">
      <button class="show-more-btn" id="showFutureBtn" onclick="toggleSection('future')">▾ Future rounds</button>
    </div>
    <div class="all-games-panel" id="futureGamesPanel" style="display:none"></div>
  </div>
</details>

<!-- IV: rank distribution -->
<details>
  <summary id="rankTitle"><span class="num">IV</span> Rank Distribution</summary>
  <div class="details-body">
    <div class="card">
      <table class="hm-table" id="hmTable"></table>
      <p class="note">Probability of finishing in each rank position. Hover a cell for the exact value.</p>
    </div>
  </div>
</details>

<!-- V: expected score -->
<details>
  <summary><span class="num">V</span> Expected Final Score <em class="sec-sub">Timeline</em></summary>
  <div class="details-body">
    <div class="card">
      <div class="chart-wrap tall"><canvas id="cExpScore"></canvas></div>
      <p class="note">Expected total points (out of <span id="totalRounds">14</span>), computed via simulation at each checkpoint.</p>
    </div>
  </div>
</details>

<!-- appendix divider -->
<div class="appendix-divider">
  <span class="appendix-label">Appendices</span>
</div>

<!-- appendix: tournament info -->
<details class="appendix-section">
  <summary><span class="num appendix-num"></span> Tournament Information</summary>
  <div class="details-body">
    <div class="card">
      <div id="tournMeta" style="margin-bottom:.9rem;font-size:.85rem;color:var(--paper-3)"></div>
      <table id="tPlayers">
        <thead><tr><th data-sort="name">Player</th><th data-sort="fide_id">FIDE ID</th><th data-sort="rating">Classical</th><th data-sort="rapid">Rapid</th><th data-sort="blitz">Blitz</th></tr></thead>
        <tbody id="tbPlayers"></tbody>
      </table>
    </div>
  </div>
</details>

<!-- pareto -->
<details id="paretoSection" class="appendix-section" style="display:none">
  <summary><span class="num appendix-num"></span> Pareto Front</summary>
  <div class="details-body">
    <div id="paretoMeta" class="pareto-meta"></div>
    <div class="card">
      <div class="chart-wrap" style="height:600px"><canvas id="cPareto"></canvas></div>
      <p class="note">Multi-objective optimisation over 2022 + 2024 Candidates data.
        ★ marks the best trial by utopia distance. Highlighted points are Pareto-optimal.</p>
    </div>
    <button class="show-more-btn" id="showParetoTableBtn" onclick="toggleParetoTable()">▾ Pareto front points</button>
    <div id="paretoTablePanel" style="display:none;margin-top:.7rem">
      <div class="card">
        <table id="tPareto">
          <thead><tr><th data-sort="idx">#</th><th data-sort="trial">Trial</th><th data-sort="brier">Game Brier</th><th data-sort="rps">Rank RPS</th></tr></thead>
          <tbody id="tbPareto"></tbody>
        </table>
      </div>
    </div>
  </div>
</details>

<!-- hyperparameters -->
<details id="hparamsSection" class="appendix-section" style="display:none">
  <summary><span class="num appendix-num"></span> Best Hyperparameters</summary>
  <div class="details-body">
    <div id="hpScores" class="hp-score-row"></div>
    <div class="hp-groups" id="hpGroups"></div>
  </div>
</details>


</div><!-- /page -->
<button class="back-to-top" id="backToTop" onclick="window.scrollTo({top:0,behavior:'smooth'})" title="Back to top">↑</button>
<script>
// ═══════════════════════════════════════════════
// DATA (injected by generate_html.py)
// ═══════════════════════════════════════════════
/*__INJECT_DATA__*/

// ═══════════════════════════════════════════════
// GLOBALS
// ═══════════════════════════════════════════════
let currentIdx = DATA.rounds.length - 1;
let winPctChart, timelineChart, expScoreChart, paretoChart, titleRaceChart;
let hiddenPlayers = new Set();
let sortedPlayers = [];   // dataset order used by timeline + expScore charts
let pastVisible = false;
let futureVisible = false;

let standingsSort = {col:'score', dir:-1};
let heatmapSort   = {col:'cascade', dir:-1};
let playersSort   = {col:'rating', dir:-1};
let paretoSort    = {col:'brier', dir:1};

// quick lookup
const P_MAP = Object.fromEntries(DATA.players.map(p => [p.key, p]));

// Integer → Roman numeral (for masthead volume)
function toRoman(num){
  if (!num || num < 1) return '—';
  const map = [[1000,'M'],[900,'CM'],[500,'D'],[400,'CD'],[100,'C'],[90,'XC'],
               [50,'L'],[40,'XL'],[10,'X'],[9,'IX'],[5,'V'],[4,'IV'],[1,'I']];
  let r = '';
  for (const [v,s] of map){ while (num >= v){ r += s; num -= v; } }
  return r;
}

// ═══════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════
function pct(v, d=1){ return (v*100).toFixed(d)+'%'; }
function fmt(v){
  if (typeof v !== 'number') return v;
  if (!isFinite(v)) return String(v);
  if (Number.isInteger(v)) return v.toLocaleString('en-US');
  const abs = Math.abs(v);
  // Very small non-zero values → scientific
  if (abs > 0 && abs < 1e-3) return v.toExponential(2);
  // Otherwise up to 6 significant digits, trim trailing zeros
  let s = v.toPrecision(6);
  if (s.indexOf('.') !== -1 && s.indexOf('e') === -1){
    s = s.replace(/0+$/, '').replace(/\.$/, '');
  }
  return s;
}

function hexAlpha(hex, a){ return hex+Math.round(a*255).toString(16).padStart(2,'0'); }

function toggleSort(state, col){
  if (state.col === col) state.dir *= -1;
  else { state.col = col; state.dir = -1; }
}

function markSortHeaders(table, state){
  table.querySelectorAll('th[data-sort]').forEach(th => {
    th.classList.remove('asc','desc');
    if (String(th.dataset.sort) === String(state.col)){
      th.classList.add(state.dir > 0 ? 'asc' : 'desc');
    }
  });
}

function heatBg(v, playerKey){
  const hex = (P_MAP[playerKey]?.color ?? '#88a').replace('#','');
  const r=parseInt(hex.slice(0,2),16), g=parseInt(hex.slice(2,4),16), b=parseInt(hex.slice(4,6),16);
  const alpha = Math.min(.5, v*2.2+0.03);
  return `rgba(${r},${g},${b},${alpha})`;
}

function trialColor(n, maxN){
  const t = n / maxN;
  // deep cobalt → soft azure gradient for the trial cloud
  return `rgba(${Math.round(46+t*60)},${Math.round(82+t*100)},${Math.round(176+t*55)},0.32)`;
}

function paretoColor(idx, total){
  const t = total<=1 ? 0 : idx/(total-1);
  return `rgb(${Math.round(67+t*178)},${Math.round(97+t*129)},${Math.round(238+t*(122-238))})`;
}

// ═══════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════
Chart.defaults.color = '#c0cceb';
Chart.defaults.borderColor = '#263764';
Chart.defaults.font.family = "'JetBrains Mono', ui-monospace, monospace";
Chart.defaults.font.size = 13;

function numberAppendices(){
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let i = 0;
  document.querySelectorAll('.appendix-section').forEach(sec => {
    if (sec.style.display === 'none') return;
    sec.querySelector('.appendix-num').textContent = letters[i++];
  });
}

document.addEventListener('DOMContentLoaded', () => {
  // Header / masthead — name on top, year · section below (big)
  const sec = DATA.meta.section || '';
  const fullTitle = DATA.meta.name + (sec ? ' \u2014 ' + sec : '');
  document.getElementById('pageTitle').textContent = fullTitle + ' \u2014 Monte Carlo';

  const titleEl = document.getElementById('hdr-title');
  let line2 = '';
  if (DATA.meta.year) line2 += `<em>${DATA.meta.year}</em>`;
  if (sec){
    if (line2) line2 += ' <span class="hdr-sec">\u00b7</span> ';
    line2 += `<span class="hdr-sec">${sec}</span>`;
  }
  titleEl.innerHTML = DATA.meta.name + (line2 ? '<br>' + line2 : '');

  // Volume line: roman numeral year
  const volEl = document.getElementById('hdr-vol');
  if (volEl) volEl.textContent = `VOL. ${toRoman(DATA.meta.year)}`;

  const badges = document.getElementById('hdr-badges');
  const latest = DATA.rounds[DATA.rounds.length-1];
  const latestNum = latest.round_num;
  const totalR = DATA.meta.total_rounds;
  const allPlayed = latest.upcoming_games?.every(g => g.result !== null) ?? false;
  const isFinished = latestNum > totalR || (latestNum === totalR && allPlayed);
  const statusBadge = isFinished
    ? `<span class="badge">Final</span>`
    : `<span class="badge live">Round ${latestNum} · Live</span>`;
  badges.innerHTML = `
    ${statusBadge}
    <span class="badge">${totalR} Rounds · ${DATA.meta.gpr}/Round</span>
    <span class="badge">Tiebreak · ${DATA.meta.tiebreak}</span>`;
  document.getElementById('totalRounds').textContent = totalR;

  buildTabs();
  initTimeline();
  initExpScore();
  initWinPct();
  initTitleRace();
  buildPlayerToggles();
  buildTournamentPlayers();

  // Wire up sortable headers — standings
  document.querySelectorAll('#tStandings thead th[data-sort]').forEach(th => {
    th.onclick = () => { toggleSort(standingsSort, th.dataset.sort); updateStandings(DATA.rounds[currentIdx]); };
  });
  // Wire up sortable headers — tournament players
  document.querySelectorAll('#tPlayers thead th[data-sort]').forEach(th => {
    th.onclick = () => { toggleSort(playersSort, th.dataset.sort); renderTournamentPlayers(); };
  });

  if (DATA.pareto) buildPareto();
  if (DATA.hparams) buildHparams();
  numberAppendices();

  setRound(currentIdx, false);

  // Floating back-to-top visibility
  const btt = document.getElementById('backToTop');
  window.addEventListener('scroll', function(){
    btt.classList.toggle('visible', window.scrollY > 400);
  }, {passive:true});
});

// ═══════════════════════════════════════════════
// TABS
// ═══════════════════════════════════════════════
function chooseCols(n){
  // Pick 3 or 4 columns — whichever leaves the last row most filled (highest fill fraction).
  // Tie-break: prefer 4 (wider grid looks better).
  let best = 4, bestFill = -1;
  for (const cols of [3, 4]){
    const rem = n % cols;
    const lastRow = rem === 0 ? cols : rem;   // if perfectly divisible, last row is full
    const fill = lastRow / cols;
    if (fill > bestFill){ bestFill = fill; best = cols; }
  }
  return best;
}

function buildTabs(){
  const wrap = document.getElementById('tabs');
  const available = DATA.rounds.length;
  const total = DATA.meta.total_rounds;
  for (let i = 0; i <= total; i++){
    const btn = document.createElement('button');
    if (i < available){
      btn.className = 'tab';
      btn.textContent = DATA.rounds[i].label;
      btn.onclick = (idx => () => setRound(idx))(i);
    } else {
      const label = i === 0 ? 'Before R1' : `After R${i}`;
      btn.className = 'tab';
      btn.textContent = label;
      btn.disabled = true;
      btn.title = 'Round not yet played';
    }
    wrap.appendChild(btn);
  }
}

// ═══════════════════════════════════════════════
// PLAYER TOGGLES
// ═══════════════════════════════════════════════
function buildPlayerToggles(){
  const wrap = document.getElementById('playerToggles');
  DATA.players.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'ptoggle';
    btn.dataset.key = p.key;
    btn.style.borderColor = p.color;
    btn.style.color = p.color;
    btn.innerHTML = `<span style="width:8px;height:8px;border-radius:50%;background:${p.color};flex-shrink:0"></span>${p.short}`;
    btn.onclick = () => togglePlayer(p.key);
    wrap.appendChild(btn);
  });
}

function togglePlayer(key){
  if (hiddenPlayers.has(key)) hiddenPlayers.delete(key);
  else hiddenPlayers.add(key);

  // update chip appearance
  document.querySelectorAll('.ptoggle').forEach(btn => {
    btn.classList.toggle('off', hiddenPlayers.has(btn.dataset.key));
  });

  updateChartVisibility();
  updateStandings(DATA.rounds[currentIdx]);
  updateHeatmap(DATA.rounds[currentIdx]);
}

function updateChartVisibility(){
  [timelineChart, expScoreChart].forEach(chart => {
    if (!chart) return;
    sortedPlayers.forEach((p, i) => {
      const vis = !hiddenPlayers.has(p.key);
      chart.setDatasetVisibility(i, vis);
    });
    chart.update();
  });
}

// ═══════════════════════════════════════════════
// SET ROUND
// ═══════════════════════════════════════════════
function setRound(idx, animate=true){
  currentIdx = idx;
  // update tabs
  document.querySelectorAll('.tab').forEach((el,i) => el.classList.toggle('active', i===idx));

  const round = DATA.rounds[idx];

  // update annotation on timeline charts
  [timelineChart, expScoreChart].forEach(c => {
    if (!c) return;
    c.options.plugins.annotation.annotations.vline.xMin = idx;
    c.options.plugins.annotation.annotations.vline.xMax = idx;
    c.update(animate ? undefined : 'none');
  });

  updateStandings(round);
  updateTitleRace(round);
  updateGames(round);
  updateHeatmap(round);

  document.getElementById('roundTitle').innerHTML =
    `<span class="num">II</span> Standings <em class="sec-sub">After Round ${round.round_num - 1}</em>`;
  document.getElementById('gamesTitle').innerHTML =
    `<span class="num">III</span> Game Predictions <em class="sec-sub">Round ${round.round_num}</em>`;
  document.getElementById('rankTitle').innerHTML =
    `<span class="num">IV</span> Rank Distribution <em class="sec-sub">After Round ${round.round_num - 1}</em>`;
}

// ═══════════════════════════════════════════════
// STANDINGS
// ═══════════════════════════════════════════════
function updateStandings(round){
  // Compute true standings rank (score desc, tiebreak by winpct)
  const byRank = [...DATA.players].sort((a,b) => {
    const sa = round.actual_scores[a.key]??0, sb = round.actual_scores[b.key]??0;
    if (sb!==sa) return sb-sa;
    return (round.winner_probs[b.key]??0)-(round.winner_probs[a.key]??0);
  });
  const rankMap = {};
  byRank.forEach((p,i) => rankMap[p.key] = i+1);

  // Sort for display based on user-chosen column
  const valFn = (p) => {
    switch(standingsSort.col){
      case 'rank':   return rankMap[p.key];
      case 'player': return p.short.toLowerCase();
      case 'elo':    return p.rating ?? 0;
      case 'score':  return round.actual_scores[p.key] ?? 0;
      case 'winpct': return round.winner_probs[p.key] ?? 0;
      default:       return rankMap[p.key];
    }
  };
  const sorted = [...DATA.players].sort((a,b) => {
    const va = valFn(a), vb = valFn(b);
    if (typeof va === 'string') return standingsSort.dir * va.localeCompare(vb);
    const d = standingsSort.dir * (va - vb);
    if (d !== 0) return d;
    // tiebreak by win probability descending
    return (round.winner_probs[b.key]??0) - (round.winner_probs[a.key]??0);
  });

  const tbl = document.getElementById('tStandings');
  markSortHeaders(tbl, standingsSort);

  const tb = document.getElementById('tbStandings');
  tb.innerHTML = '';
  sorted.forEach(p => {
    const rank  = rankMap[p.key];
    const score = round.actual_scores[p.key]??0;
    const wp    = round.winner_probs[p.key]??0;
    const hidden = hiddenPlayers.has(p.key);
    const tr = document.createElement('tr');
    tr.style.opacity = hidden ? '0.35' : '';
    tr.innerHTML = `
      <td class="rank-num ${rank===1?'gold':''}">${rank}</td>
      <td><div class="pcell"><span class="dot" style="background:${p.color}"></span>${p.short}</div></td>
      <td class="hide-mobile" style="color:var(--paper-3);font-size:.83rem">${p.rating??'—'}</td>
      <td class="score">${score}</td>
      <td>
        <div style="display:flex;align-items:center;gap:.6rem">
          <div class="bar-inline"><div class="bar-fill" style="width:${Math.min(100,wp*100)}%;background:${p.color}"></div></div>
          <span class="winpct ${wp>.15?'hi':''}" title="${pct(wp,2)}">${pct(wp)}</span>
        </div>
      </td>`;
    tb.appendChild(tr);
  });

  // bar chart — only visible players
  const visibleSorted = sorted.filter(p => !hiddenPlayers.has(p.key));
  winPctChart.data.labels = visibleSorted.map(p => p.short);
  winPctChart.data.datasets[0].data = visibleSorted.map(p => +(((round.winner_probs[p.key]??0)*100).toFixed(2)));
  winPctChart.data.datasets[0].backgroundColor = visibleSorted.map(p => hexAlpha(p.color, 0.7));
  winPctChart.data.datasets[0].borderColor      = visibleSorted.map(p => p.color);
  winPctChart.update();
}

// ═══════════════════════════════════════════════
// GAME CARD BUILDER (shared)
// ═══════════════════════════════════════════════
function makeGameCard(g, roundNum){
  const [ww,dd,bw] = g.probs;
  const wp = Math.round(ww*100), dp = Math.round(dd*100), bp = Math.round(bw*100);
  const wc = P_MAP[g.white]?.color ?? '#888';
  const bc = P_MAP[g.black]?.color ?? '#888';
  const wn = P_MAP[g.white]?.short ?? g.white;
  const bn = P_MAP[g.black]?.short ?? g.black;

  // Gold inset shadow on the bar matching the actual result
  const wShadow = g.result==='1-0'   ? 'box-shadow:inset 0 0 0 3px #ffee58;' : '';
  const dShadow = g.result==='1/2-1/2'? 'box-shadow:inset 0 0 0 3px #ffee58;' : '';
  const bShadow = g.result==='0-1'   ? 'box-shadow:inset 0 0 0 3px #ffee58;' : '';

  let resultBadge = '';
  if (g.result==='1-0')
    resultBadge = `<div style="text-align:left"><span class="result-badge white-win">✓ ${wn} won</span></div>`;
  else if (g.result==='0-1')
    resultBadge = `<div style="text-align:right"><span class="result-badge black-win">✓ ${bn} won</span></div>`;
  else if (g.result==='1/2-1/2')
    resultBadge = `<div style="text-align:center"><span class="result-badge draw">½–½ Draw</span></div>`;

  const card = document.createElement('div');
  card.className = 'gcard';
  card.innerHTML = `
    <div class="round-label">Round ${roundNum}</div>
    <div class="players">
      <span class="dot" style="background:${wc}"></span>${wn}
      <span class="sep">vs</span>
      <span class="dot" style="background:${bc}"></span>${bn}
    </div>
    <div class="prob-bars">
      <div class="pb white-win" style="flex:${ww};background:${hexAlpha(wc,0.8)};${wShadow}" title="${(ww*100).toFixed(2)}%">${wp}%</div>
      <div class="pb draw" style="flex:${dd};${dShadow}" title="${(dd*100).toFixed(2)}%">${dp}%</div>
      <div class="pb black-win" style="flex:${bw};background:${hexAlpha(bc,0.65)};${bShadow}" title="${(bw*100).toFixed(2)}%">${bp}%</div>
    </div>
    <div class="prob-foot">
      <span>${wn} <span style="color:#6a7ca3">(W)</span></span>
      <span>Draw</span>
      <span>${bn} <span style="color:#6a7ca3">(B)</span></span>
    </div>
    ${resultBadge}`;
  return card;
}

// ═══════════════════════════════════════════════
// GAMES
// ═══════════════════════════════════════════════
function updateGames(round){
  const grid = document.getElementById('gamesGrid');
  grid.innerHTML = '';
  if (!round.upcoming_games?.length){
    grid.innerHTML = '<p style="color:#6a7ca3;font-size:.88rem">No game data for this round.</p>';
    return;
  }
  grid.style.gridTemplateColumns = `repeat(${chooseCols(round.upcoming_games.length)}, 1fr)`;
  round.upcoming_games.forEach(g => grid.appendChild(makeGameCard(g, round.round_num)));
  if (pastVisible)   buildPanel('past');
  if (futureVisible) buildPanel('future');
}

// ═══════════════════════════════════════════════
// SHOW PAST / FUTURE ROUNDS
// ═══════════════════════════════════════════════
function toggleSection(which){
  const isPast = which === 'past';
  if (isPast) pastVisible = !pastVisible; else futureVisible = !futureVisible;
  const visible = isPast ? pastVisible : futureVisible;
  const panelId = isPast ? 'pastGamesPanel' : 'futureGamesPanel';
  const btnId   = isPast ? 'showPastBtn'    : 'showFutureBtn';
  const panel   = document.getElementById(panelId);
  const btn     = document.getElementById(btnId);
  if (visible){
    buildPanel(which);
    panel.style.display = '';
    btn.textContent = isPast ? '▾ Hide past' : '▴ Hide future';
  } else {
    panel.style.display = 'none';
    btn.textContent = isPast ? '▴ Past rounds' : '▾ Future rounds';
  }
}

function buildPanel(which){
  const isPast  = which === 'past';
  const panel   = document.getElementById(isPast ? 'pastGamesPanel' : 'futureGamesPanel');
  panel.innerHTML = '';
  const curRound = DATA.rounds[currentIdx].round_num;
  const rounds = isPast
    ? DATA.all_games.filter(ag => ag.round_num < curRound)
    : DATA.all_games.filter(ag => ag.round_num > curRound);

  rounds.forEach(ag => {
    const completed = ag.games.every(g => g.result !== null);
    const grp  = document.createElement('div');
    grp.className = 'round-group';
    const glbl = document.createElement('div');
    glbl.className = 'round-group-lbl';
    glbl.textContent = `Round ${ag.round_num} — ${completed ? 'Completed' : 'Upcoming'}`;
    grp.appendChild(glbl);
    const grid = document.createElement('div');
    grid.className = 'games-grid';
    grid.style.gridTemplateColumns = `repeat(${chooseCols(ag.games.length)}, 1fr)`;
    ag.games.forEach(g => grid.appendChild(makeGameCard(g, ag.round_num)));
    grp.appendChild(grid);
    panel.appendChild(grp);
  });
}

// ═══════════════════════════════════════════════
// RANK HEATMAP
// ═══════════════════════════════════════════════
function updateHeatmap(round){
  const tbl = document.getElementById('hmTable');
  tbl.innerHTML = '';
  const n = DATA.players.length;

  const thead = document.createElement('thead');
  const hrow = document.createElement('tr');
  const thP = document.createElement('th');
  thP.textContent = 'Player';
  thP.dataset.sort = 'player';
  thP.onclick = () => { toggleSort(heatmapSort,'player'); updateHeatmap(DATA.rounds[currentIdx]); };
  hrow.appendChild(thP);
  for (let i=0;i<n;i++){
    const th = document.createElement('th');
    th.textContent = `${i+1}${['st','nd','rd'][i]??'th'}`;
    th.dataset.sort = String(i);
    th.onclick = ((idx) => () => { toggleSort(heatmapSort,idx); updateHeatmap(DATA.rounds[currentIdx]); })(i);
    hrow.appendChild(th);
  }
  thead.appendChild(hrow);
  tbl.appendChild(thead);
  markSortHeaders(tbl, heatmapSort);

  const sorted = [...DATA.players]
    .filter(p => !hiddenPlayers.has(p.key))
    .sort((a,b) => {
      if (heatmapSort.col === 'player'){
        return heatmapSort.dir * a.short.toLowerCase().localeCompare(b.short.toLowerCase());
      }
      if (heatmapSort.col === 'cascade'){
        const rmA = round.rank_matrix[a.key] ?? [];
        const rmB = round.rank_matrix[b.key] ?? [];
        for (let i=0;i<n;i++){
          const d = (rmA[i]??0) - (rmB[i]??0);
          if (d !== 0) return heatmapSort.dir * d;
        }
        return 0;
      }
      const rmA = round.rank_matrix[a.key] ?? [];
      const rmB = round.rank_matrix[b.key] ?? [];
      return heatmapSort.dir * ((rmB[heatmapSort.col]??0) - (rmA[heatmapSort.col]??0));
    });

  const tbody = document.createElement('tbody');
  sorted.forEach(p => {
    const rm = round.rank_matrix[p.key] ?? Array(n).fill(0);
    const tr = document.createElement('tr');
    const cells = rm.map((v,ri) => {
      const bg = heatBg(v, p.key);
      return `<td><span class="hm-cell" style="background:${bg}" title="${pct(v,2)}">${pct(v,0)}</span></td>`;
    }).join('');
    tr.innerHTML = `<td><div class="pcell"><span class="dot" style="background:${p.color}"></span>${p.short}</div></td>${cells}`;
    tbody.appendChild(tr);
  });
  tbl.appendChild(tbody);
}

// ═══════════════════════════════════════════════
// TIMELINE CHART
// ═══════════════════════════════════════════════
function initTimeline(){
  const labels = DATA.rounds.map(r => r.label);
  sortedPlayers = [...DATA.players].sort((a,b) =>
    (DATA.rounds[DATA.rounds.length-1].winner_probs[b.key]??0) -
    (DATA.rounds[DATA.rounds.length-1].winner_probs[a.key]??0));
  const sortedP = sortedPlayers;

  timelineChart = new Chart(document.getElementById('cTimeline').getContext('2d'), {
    type:'line',
    data:{
      labels,
      datasets: sortedP.map(p => ({
        label: p.short,
        data: DATA.rounds.map(r => +((r.winner_probs[p.key]??0)*100).toFixed(2)),
        borderColor: p.color,
        backgroundColor: p.color+'14',
        tension:.35, fill:false,
        // future points fade out
        pointRadius:       ctx => ctx.dataIndex > currentIdx ? 2.5 : 4,
        pointHoverRadius:  6,
        pointBackgroundColor: ctx => ctx.dataIndex > currentIdx ? hexAlpha(p.color, 0.18) : p.color,
        pointBorderColor:     ctx => ctx.dataIndex > currentIdx ? hexAlpha(p.color, 0.18) : p.color,
        // future line segments become dashed + transparent
        segment:{
          borderColor: ctx => ctx.p1DataIndex > currentIdx ? hexAlpha(p.color, 0.18) : p.color,
          borderDash:  ctx => ctx.p1DataIndex > currentIdx ? [6,4] : undefined,
          borderWidth: ctx => ctx.p1DataIndex > currentIdx ? 1.5 : 2.5,
        },
      }))
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      scales:{
        x:{grid:{color:'rgba(120,180,255,.1)'},ticks:{font:{size:11}}},
        y:{grid:{color:'rgba(120,180,255,.1)'},ticks:{callback:v=>v+'%',font:{size:11}},
           title:{display:true,text:'Win Probability (%)',color:'#6a7ca3'}}
      },
      plugins:{
        legend:{position:'bottom',labels:{boxWidth:12,padding:13,font:{size:12}}},
        tooltip:{itemSort:(a,b)=>b.parsed.y-a.parsed.y,callbacks:{label:ctx=>` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`}},
        annotation:{annotations:{vline:{type:'line',xMin:currentIdx,xMax:currentIdx,
          borderColor:'#ffee58cc',borderWidth:2,borderDash:[6,4]}}}
      }
    }
  });
}

// ═══════════════════════════════════════════════
// EXP SCORE CHART
// ═══════════════════════════════════════════════
function initExpScore(){
  const labels = DATA.rounds.map(r => r.label);
  const sortedP = [...DATA.players].sort((a,b) =>
    (DATA.rounds[DATA.rounds.length-1].winner_probs[b.key]??0) -
    (DATA.rounds[DATA.rounds.length-1].winner_probs[a.key]??0));

  expScoreChart = new Chart(document.getElementById('cExpScore').getContext('2d'), {
    type:'line',
    data:{
      labels,
      datasets: sortedP.map(p => ({
        label: p.short,
        data: DATA.rounds.map(r => +((r.expected_points[p.key]??0).toFixed(2))),
        borderColor: p.color,
        backgroundColor: p.color+'14',
        tension:.35, fill:false,
        pointRadius:       ctx => ctx.dataIndex > currentIdx ? 2.5 : 4,
        pointHoverRadius:  6,
        pointBackgroundColor: ctx => ctx.dataIndex > currentIdx ? hexAlpha(p.color, 0.18) : p.color,
        pointBorderColor:     ctx => ctx.dataIndex > currentIdx ? hexAlpha(p.color, 0.18) : p.color,
        segment:{
          borderColor: ctx => ctx.p1DataIndex > currentIdx ? hexAlpha(p.color, 0.18) : p.color,
          borderDash:  ctx => ctx.p1DataIndex > currentIdx ? [6,4] : undefined,
          borderWidth: ctx => ctx.p1DataIndex > currentIdx ? 1.5 : 2.5,
        },
      }))
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      scales:{
        x:{grid:{color:'rgba(120,180,255,.1)'},ticks:{font:{size:11}}},
        y:{grid:{color:'rgba(120,180,255,.1)'},
           ticks:{stepSize:1,font:{size:11}},
           title:{display:true,text:`Expected Final Score (out of ${DATA.meta.total_rounds})`,color:'#6a7ca3'}}
      },
      plugins:{
        legend:{position:'bottom',labels:{boxWidth:12,padding:13,font:{size:12}}},
        tooltip:{itemSort:(a,b)=>b.parsed.y-a.parsed.y,callbacks:{label:ctx=>` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)} pts`}},
        annotation:{annotations:{vline:{type:'line',xMin:currentIdx,xMax:currentIdx,
          borderColor:'#ffee58cc',borderWidth:2,borderDash:[6,4]}}}
      }
    }
  });
}

// ═══════════════════════════════════════════════
// WIN % BAR CHART
// ═══════════════════════════════════════════════
function initWinPct(){
  winPctChart = new Chart(document.getElementById('cWinPct').getContext('2d'), {
    type:'bar',
    data:{labels:[],datasets:[{label:'Win Probability',data:[],
      backgroundColor:[],borderColor:[],borderWidth:1,borderRadius:4}]},
    options:{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{label:ctx=>` ${ctx.parsed.x.toFixed(1)}%`}}},
      scales:{
        x:{grid:{color:'rgba(120,180,255,.1)'},ticks:{callback:v=>v+'%',font:{size:11}},max:100},
        y:{grid:{display:false},ticks:{font:{size:12}}}
      }
    }
  });
}

// ═══════════════════════════════════════════════
// TITLE RACE
// ═══════════════════════════════════════════════
let titleRaceData = [];

function initTitleRace(){
  titleRaceChart = new Chart(document.getElementById('cTitleRace').getContext('2d'), {
    type:'bar',
    data:{labels:[], datasets:[
      {label:'Current', data:[], backgroundColor:[], borderColor:[], borderWidth:1},
      {label:'Remaining', data:[], backgroundColor:[], borderColor:[], borderWidth:1}
    ]},
    options:{
      indexAxis:'y',
      responsive:true, maintainAspectRatio:false,
      scales:{
        x:{stacked:true, grid:{color:'rgba(120,180,255,.1)'},
           ticks:{font:{size:11}, stepSize:1},
           title:{display:true, text:'Points', color:'#6a7ca3'}, min:0},
        y:{stacked:true, grid:{display:false}, ticks:{font:{size:12}}}
      },
      plugins:{
        legend:{display:false},
        tooltip:{callbacks:{
          label: ctx => {
            const d = titleRaceData[ctx.dataIndex];
            if (!d) return '';
            if (ctx.datasetIndex===0) return ` Current: ${d.score} pts \u00b7 Win: ${pct(d.wp)}`;
            return ` Max: ${d.score+d.maxAdd} pts (+${d.maxAdd} remaining)`;
          }
        }},
        annotation:{annotations:{}}
      }
    }
  });
}

function updateTitleRace(round){
  const totalR = DATA.meta.total_rounds;
  const lastPlayed = round.round_num - 1;
  const remaining = totalR - lastPlayed;
  const card = document.getElementById('titleRaceCard');

  if (remaining <= 0){ card.style.display = 'none'; return; }
  card.style.display = '';

  const elim = round.eliminated || {};

  const sorted = [...DATA.players].sort((a,b) => {
    const sa = round.actual_scores[a.key]??0, sb = round.actual_scores[b.key]??0;
    if (sb !== sa) return sb - sa;
    return (round.winner_probs[b.key]??0) - (round.winner_probs[a.key]??0);
  });

  const leaderScore = round.actual_scores[sorted[0].key] ?? 0;

  titleRaceData = sorted.map(p => {
    const score = round.actual_scores[p.key] ?? 0;
    const wp = round.winner_probs[p.key] ?? 0;
    return {
      key:p.key, short:p.short, color:p.color,
      score, maxAdd:remaining, wp,
      eliminated: elim[p.key]
    };
  });

  const ds0 = titleRaceChart.data.datasets[0];
  const ds1 = titleRaceChart.data.datasets[1];
  titleRaceChart.data.labels = titleRaceData.map(d => d.short);
  ds0.data = titleRaceData.map(d => d.score);
  ds0.backgroundColor = titleRaceData.map(d => d.eliminated ? hexAlpha(d.color,0.2) : hexAlpha(d.color,0.8));
  ds0.borderColor     = titleRaceData.map(d => d.eliminated ? hexAlpha(d.color,0.25) : d.color);
  ds1.data = titleRaceData.map(d => d.maxAdd);
  ds1.backgroundColor = titleRaceData.map(d => d.eliminated ? 'rgba(255,255,255,0.02)' : hexAlpha(d.color,0.15));
  ds1.borderColor     = titleRaceData.map(d => d.eliminated ? 'rgba(255,255,255,0.04)' : hexAlpha(d.color,0.25));

  titleRaceChart.options.plugins.annotation.annotations = {
    leaderLine:{
      type:'line', xMin:leaderScore, xMax:leaderScore,
      borderColor:'#ffee58cc', borderWidth:2, borderDash:[6,4],
      label:{
        display:true,
        content:`Leader: ${leaderScore} pts`,
        position:'start', color:'#ffee58',
        font:{size:10, family:"'JetBrains Mono', monospace"},
        backgroundColor:'rgba(11,17,32,0.75)', padding:4
      }
    }
  };
  titleRaceChart.options.scales.x.max = totalR + 0.5;
  titleRaceChart.update();

  // Contender detail: remaining games for alive players
  const detail = document.getElementById('titleRaceDetail');
  const contenders = titleRaceData.filter(d => !d.eliminated);
  const elimCount = titleRaceData.length - contenders.length;

  if (contenders.length > 0 && contenders.length < titleRaceData.length && remaining > 0){
    const lines = contenders.map(d => {
      const games = [];
      DATA.all_games.forEach(ag => {
        if (ag.round_num <= lastPlayed) return;
        ag.games.forEach(g => {
          let opp = null, clr = '';
          if (g.white === d.key){ opp = g.black; clr = 'W'; }
          else if (g.black === d.key){ opp = g.white; clr = 'B'; }
          if (opp){
            const os = P_MAP[opp]?.short ?? opp;
            const isRival = contenders.some(c => c.key === opp);
            const tag = isRival
              ? `<strong style="color:${P_MAP[opp]?.color??'var(--paper)'}">${os}</strong>`
              : os;
            games.push(`R${ag.round_num} vs ${tag} (${clr})`);
          }
        });
      });
      return `<div style="margin-bottom:.4rem">`+
        `<span style="color:${d.color};font-weight:600">${d.short}</span>`+
        `<span style="color:var(--paper-3);margin:0 .4rem">\u00b7</span>`+
        `<span style="font-family:'JetBrains Mono',monospace;font-size:.82rem">${d.score} pts</span>`+
        `<span style="color:var(--paper-3);margin:0 .4rem">\u00b7</span>`+
        `<span class="winpct ${d.wp>.15?'hi':''}">${pct(d.wp)}</span>`+
        `<span style="color:var(--paper-3);margin:0 .4rem">\u2192</span>`+
        `<span style="color:var(--paper-2);font-size:.82rem">${games.join(' \u00b7 ')}</span>`+
        `</div>`;
    });
    detail.innerHTML =
      `<div style="font-family:'JetBrains Mono',monospace;font-size:.62rem;color:var(--paper-3);text-transform:uppercase;letter-spacing:.14em;margin-bottom:.55rem">Contenders\u2019 Remaining Games</div>`+
      lines.join('');
  } else {
    detail.innerHTML = '';
  }

  document.getElementById('titleRaceNote').textContent =
    `${remaining} round${remaining!==1?'s':''} remaining. `+
    `${contenders.length} player${contenders.length!==1?'s':''} mathematically alive`+
    (elimCount > 0 ? `, ${elimCount} eliminated` : '')+
    `. Dashed line = leader\u2019s current score \u2014 eliminated players cannot finish first in any remaining-game scenario.`;

  // Show/hide scenario button
  const sBtn = document.getElementById('showScenariosBtn');
  if (remaining > 0){
    sBtn.style.display = '';
    if (scenariosVisible) initScenarioExplorer();
  } else {
    sBtn.style.display = 'none';
    document.getElementById('scenarioContainer').style.display = 'none';
    scenariosVisible = false;
  }

  document.getElementById('titleRaceLabel').textContent =
    `Title Race \u2014 ${remaining} Round${remaining!==1?'s':''} Remaining`;
}

// ═══════════════════════════════════════════════
// SCENARIO TREE (interactive, navigable SVG tree)
// ═══════════════════════════════════════════════
let scenariosVisible = false;
let _seTree = null;
let _sePath = [];
let _seGames = [];
let _seContenders = [];
let _seRandomTarget = null;  // null = any, or player key
let _seOrphaned = [];  // steps lost after breadcrumb edit: [{round,ws,bs,k,actual}]
const SE_NS = 'http://www.w3.org/2000/svg';

function toggleScenarios(){
  scenariosVisible = !scenariosVisible;
  document.getElementById('scenarioContainer').style.display = scenariosVisible ? '' : 'none';
  document.getElementById('showScenariosBtn').textContent = scenariosVisible ? '\u25b4 Hide scenario explorer' : '\u25be Scenario explorer';
  if (scenariosVisible) initScenarioExplorer();
}

function _seResultToOutcome(r){
  // Map result string to outcome index: 0=W, 1=D, 2=L (from white's perspective)
  if (r === '1-0') return 0;
  if (r === '1/2-1/2') return 1;
  if (r === '0-1') return 2;
  return null;
}

function initScenarioExplorer(){
  const container = document.getElementById('scenarioContainer');
  const round = DATA.rounds[currentIdx];
  const totalR = DATA.meta.total_rounds;
  const lastPlayed = round.round_num - 1;
  const remaining = totalR - lastPlayed;

  if (remaining <= 0){
    container.innerHTML = '<p style="color:#6a7ca3;font-size:.88rem">Tournament complete.</p>';
    return;
  }

  // Determine contenders via DFS: players who can still finish first
  const elim = round.eliminated || {};
  const scores = {};
  DATA.players.forEach(p => { scores[p.key] = round.actual_scores[p.key] ?? 0; });

  _seContenders = DATA.players
    .filter(p => !elim[p.key])
    .sort((a,b) => scores[b.key] - scores[a.key]);

  if (_seContenders.length <= 1){
    container.innerHTML = '<p style="color:#6a7ca3;font-size:.88rem">Tournament already decided.</p>';
    return;
  }

  // Collect games — include played games with their actual result
  const cKeys = new Set(_seContenders.map(p => p.key));
  _seGames = [];
  DATA.all_games.forEach(ag => {
    if (ag.round_num <= lastPlayed) return;
    ag.games.forEach(g => {
      if (cKeys.has(g.white) || cKeys.has(g.black)){
        _seGames.push({
          round: ag.round_num,
          white: g.white, black: g.black,
          ws: P_MAP[g.white]?.short ?? g.white,
          bs: P_MAP[g.black]?.short ?? g.black,
          wc: P_MAP[g.white]?.color ?? '#8494be',
          bc: P_MAP[g.black]?.color ?? '#8494be',
          probs: g.probs,
          actual: _seResultToOutcome(g.result)  // null if unplayed, 0/1/2 if played
        });
      }
    });
  });
  _seGames.sort((a,b) => a.round - b.round);

  const initScores = {};
  DATA.players.forEach(p => { initScores[p.key] = round.actual_scores[p.key] ?? 0; });

  _seTree = _seMakeNode(initScores, _seGames.map((_,i) => i));
  _sePath = [];

  container.innerHTML =
    '<div style="position:relative;height:36px;margin-bottom:1rem">' +
      '<button class="show-more-btn" onclick="_seNav(-1)" style="font-size:.75rem;white-space:nowrap;position:absolute;left:0;top:0">\u21ba Reset</button>' +
      '<button class="show-more-btn" onclick="_seFollowTruth()" style="font-size:.75rem;white-space:nowrap;position:absolute;left:50%;top:0;transform:translateX(-50%)">\u2713 Follow Truth</button>' +
      '<div style="position:absolute;right:0;top:0;display:inline-flex">' +
        '<button id="seRandomBtn" class="show-more-btn" onclick="_seRandom()" style="font-size:.75rem;border-radius:4px 0 0 4px;border-right:1px solid rgba(120,180,255,.15);white-space:nowrap">\u27f3 Random: Any</button>' +
        '<button class="show-more-btn" onclick="_seToggleRandomMenu()" style="font-size:.75rem;border-radius:0 4px 4px 0;padding:0 6px">\u25be</button>' +
        '<div id="seRandomMenu" style="display:none;position:absolute;top:100%;right:0;margin-top:4px;background:rgba(15,22,40,0.97);border:1px solid rgba(120,180,255,.2);border-radius:4px;z-index:10;min-width:140px;padding:4px 0">' +
          '<div onclick="_seSetRandomTarget(null)" style="padding:5px 12px;cursor:pointer;font-family:\'JetBrains Mono\',monospace;font-size:.72rem;color:#78b4ff;white-space:nowrap" '+
            'onmouseenter="this.style.background=\'rgba(120,180,255,.1)\'" onmouseleave="this.style.background=\'none\'">' +
            'Any</div>' +
          _seContenders.map(function(p){
            return '<div onclick="_seSetRandomTarget(\''+p.key+'\')" style="padding:5px 12px;cursor:pointer;font-family:\'JetBrains Mono\',monospace;font-size:.72rem;color:'+p.color+';white-space:nowrap" '+
              'onmouseenter="this.style.background=\'rgba(120,180,255,.1)\'" onmouseleave="this.style.background=\'none\'">' +
              p.short+'</div>';
          }).join('') +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div id="seCrumb" style="margin-bottom:.75rem"></div>' +
    '<div id="seSvgWrap" style="overflow-x:hidden"></div>' +
    '<div id="seFootnote" style="display:none;margin-top:.5rem;padding:6px 10px;font-size:.7rem;font-family:\'JetBrains Mono\',monospace;color:#ffb74d;background:rgba(255,183,77,.08);border:1px solid rgba(255,183,77,.2);border-radius:4px"></div>';

  _seRenderAll();
}

/* ── node factory with elimination pruning ── */
function _seMakeNode(scores, pendingGIs){
  const node = {scores: {...scores}};
  const sorted = [..._seContenders].sort((a,b) => scores[b.key] - scores[a.key]);
  const leaderScore = scores[sorted[0].key];
  const alive = [];
  sorted.forEach(p => {
    const gl = pendingGIs.filter(gi => {
      const g = _seGames[gi]; return g.white === p.key || g.black === p.key;
    }).length;
    if (scores[p.key] + gl >= leaderScore) alive.push(p.key);
  });
  node.alive = new Set(alive);
  // Remove games not involving any alive contender
  node.pending = pendingGIs.filter(gi => {
    const g = _seGames[gi]; return node.alive.has(g.white) || node.alive.has(g.black);
  });
  // Leaf: no pending games OR only 1 player alive (clinched)
  if (node.pending.length === 0 || alive.length <= 1){
    node.leaf = true;
    if (alive.length === 1){
      // Clinched: one player can't be caught
      node.tied = [sorted.find(p => p.key === alive[0])];
      node.winner = node.tied[0];
    } else {
      const top = scores[sorted[0].key];
      node.tied = sorted.filter(p => scores[p.key] === top);
      node.winner = node.tied.length === 1 ? node.tied[0] : null;
    }
  }
  return node;
}

/* ── lazy child generation: branches for current round only ── */
function _seGenChildren(node){
  if (node.leaf || node.ch) return;
  const curRound = Math.min(...node.pending.map(gi => _seGames[gi].round));
  const curGIs = node.pending.filter(gi => _seGames[gi].round === curRound);
  node.ch = [];
  curGIs.forEach(gi => {
    const g = _seGames[gi];
    [{k:'W',wp:1,bp:0,p:g.probs[0]},{k:'D',wp:.5,bp:.5,p:g.probs[1]},{k:'L',wp:0,bp:1,p:g.probs[2]}]
      .forEach(({k,wp,bp,p}) => {
        const ns = {...node.scores}; ns[g.white] += wp; ns[g.black] += bp;
        node.ch.push({k, p, gi, child: _seMakeNode(ns, node.pending.filter(i => i !== gi))});
      });
  });
}

/* ── navigation ── */
let _seNavDir = 'fade';  // 'forward','backward','fade'
let _seDfsWarning = '';  // non-empty when DFS fallback was used
function _seGetFocused(){
  let n = _seTree;
  for (const i of _sePath){ _seGenChildren(n); if (n.ch && n.ch[i]) n = n.ch[i].child; else break; }
  return n;
}
function _seBuildPastChain(){
  const chain = [];
  let n = _seTree;
  for (let i = 0; i < _sePath.length; i++){
    _seGenChildren(n);
    const e = n.ch[_sePath[i]];
    chain.push({node:n, edge:e, game:_seGames[e.gi]});
    n = e.child;
  }
  return chain;
}
function _seNav(d){ _seNavDir = 'backward'; _seDfsWarning = ''; _seOrphaned = []; _sePath = d < 0 ? [] : _sePath.slice(0,d); _seRenderAll(); }
function _seClick(ci){ _seNavDir = 'forward'; _seDfsWarning = ''; _seOrphaned = []; _sePath.push(ci); _seRenderAll(); }
function _seFollowTruth(){
  _seNavDir = 'forward';
  _seDfsWarning = '';
  _seOrphaned = [];
  let n = _seGetFocused();
  let added = 0;
  while (!n.leaf){
    _seGenChildren(n);
    if (!n.ch || !n.ch.length) break;
    const gi0 = n.ch[0].gi;
    const g = _seGames[gi0];
    if (g.actual === null) break;  // no actual result from here
    const targetK = ['W','D','L'][g.actual];
    let found = false;
    for (let i = 0; i < n.ch.length; i++){
      if (n.ch[i].gi === gi0 && n.ch[i].k === targetK){
        _sePath.push(i);
        n = n.ch[i].child;
        added++;
        found = true;
        break;
      }
    }
    if (!found) break;
  }
  if (added === 0){
    // No actual results to follow from here
    return;
  }
  _seRenderAll();
}
function _seSetRandomTarget(key){
  _seRandomTarget = key;
  const btn = document.getElementById('seRandomBtn');
  if (btn){
    if (key){
      const p = _seContenders.find(function(c){return c.key===key;});
      btn.innerHTML = '\u27f3 Random: <span style="color:'+p.color+';font-weight:700">'+p.short+'</span>';
    } else {
      btn.textContent = '\u27f3 Random: Any';
    }
  }
  _seToggleRandomMenu();
}
function _seRandom(){
  const targetKey = _seRandomTarget;
  _seNavDir = 'forward';
  _sePath = [];
  _seDfsWarning = '';
  _seOrphaned = [];
  let n = _seTree;
  const MAX_TRIES = 1000;
  if (targetKey){
    for (let t = 0; t < MAX_TRIES; t++){
      const path = []; let nd = _seTree;
      while (!nd.leaf){
        _seGenChildren(nd);
        if (!nd.ch || !nd.ch.length) break;
        const gi0 = nd.ch[0].gi;
        const outs = []; nd.ch.forEach((c,i) => { if (c.gi === gi0) outs.push({c,i}); });
        const r = Math.random(); let cum = 0, ch = outs[outs.length-1];
        for (const o of outs){ cum += o.c.p; if (r < cum){ ch = o; break; } }
        path.push(ch.i); nd = ch.c.child;
      }
      if (nd.winner && nd.winner.key === targetKey){ _sePath = path; _seRenderAll(); return; }
      if (nd.tied && nd.tied.some(function(p){return p.key===targetKey;})){ _sePath = path; _seRenderAll(); return; }
    }
    // Uniform random fallback (1/3 each outcome)
    const pName = _seContenders.find(function(p){return p.key===targetKey;})?.short||targetKey;
    for (let t = 0; t < MAX_TRIES; t++){
      const path = []; let nd = _seTree;
      while (!nd.leaf){
        _seGenChildren(nd);
        if (!nd.ch || !nd.ch.length) break;
        const gi0 = nd.ch[0].gi;
        const outs = []; nd.ch.forEach((c,i) => { if (c.gi === gi0) outs.push({c,i}); });
        const ch = outs[Math.floor(Math.random() * outs.length)];
        path.push(ch.i); nd = ch.c.child;
      }
      if (nd.winner && nd.winner.key === targetKey){
        _seDfsWarning = 'Win probability for '+pName+' is very low. No path found in '+MAX_TRIES.toLocaleString()+' weighted samples; found via uniform random sampling after '+(t+1).toLocaleString()+' tries.';
        _sePath = path; _seRenderAll(); return;
      }
      if (nd.tied && nd.tied.some(function(p){return p.key===targetKey;})){
        _seDfsWarning = 'Win probability for '+pName+' is very low. No path found in '+MAX_TRIES.toLocaleString()+' weighted samples; found via uniform random sampling after '+(t+1).toLocaleString()+' tries.';
        _sePath = path; _seRenderAll(); return;
      }
    }
    // Deterministic DFS fallback
    function dfsFindWin(nd){
      if (nd.leaf){
        if (nd.winner && nd.winner.key === targetKey) return [];
        if (nd.tied && nd.tied.some(function(p){return p.key===targetKey;})) return [];
        return null;
      }
      _seGenChildren(nd);
      if (!nd.ch || !nd.ch.length) return null;
      const gi0 = nd.ch[0].gi;
      const outs = []; nd.ch.forEach(function(c,i){ if (c.gi === gi0) outs.push({c:c,i:i}); });
      for (let j = 0; j < outs.length; j++){
        const sub = dfsFindWin(outs[j].c.child);
        if (sub !== null) return [outs[j].i].concat(sub);
      }
      return null;
    }
    const dfsPath = dfsFindWin(_seTree);
    if (dfsPath){
      _seDfsWarning = 'Win probability for '+pName+' is extremely low. No path found in '+MAX_TRIES.toLocaleString()+' weighted + '+MAX_TRIES.toLocaleString()+' uniform samples; resolved via deterministic search.';
      _sePath = dfsPath; _seRenderAll(); return;
    }
    alert('No possible winning path exists for '+pName+' (searched '+MAX_TRIES.toLocaleString()+' weighted + '+MAX_TRIES.toLocaleString()+' uniform samples + full DFS).');
    return;
  }
  while (!n.leaf){
    _seGenChildren(n);
    if (!n.ch || !n.ch.length) break;
    const gi0 = n.ch[0].gi;
    const outs = []; n.ch.forEach((c,i) => { if (c.gi === gi0) outs.push({c,i}); });
    const r = Math.random(); let cum = 0, ch = outs[outs.length-1];
    for (const o of outs){ cum += o.c.p; if (r < cum){ ch = o; break; } }
    _sePath.push(ch.i); n = ch.c.child;
  }
  _seRenderAll();
}
function _seToggleRandomMenu(){
  const menu = document.getElementById('seRandomMenu');
  if (menu) menu.style.display = menu.style.display === 'none' ? '' : 'none';
}

/* ── breadcrumb inline editing ── */
let _seCrumbPopover = null;  // active popover element
function _seDismissPopover(){
  if (_seCrumbPopover){ _seCrumbPopover.remove(); _seCrumbPopover = null; }
}
function _seEditCrumb(depth, evt){
  evt.stopPropagation();
  _seDismissPopover();
  // Walk to the parent node at this depth
  let n = _seTree;
  for (let i = 0; i < depth; i++){
    _seGenChildren(n);
    n = n.ch[_sePath[i]].child;
  }
  _seGenChildren(n);
  const curEdge = n.ch[_sePath[depth]];
  const gi = curEdge.gi;
  const g = _seGames[gi];
  // Collect all outcomes for this game
  const outcomes = [];
  for (let i = 0; i < n.ch.length; i++){
    if (n.ch[i].gi === gi) outcomes.push({ci:i, k:n.ch[i].k, p:n.ch[i].p});
  }
  const oClr = {W:'#00e676', D:'#8494be', L:'#ff5252'};
  const oLbl = {W:'1\u20130', D:'\u00bd\u2013\u00bd', L:'0\u20131'};
  // Build popover
  const pop = document.createElement('div');
  pop.style.cssText = 'position:absolute;z-index:20;background:rgba(15,22,40,0.97);border:1px solid rgba(120,180,255,.25);border-radius:5px;padding:4px;display:flex;gap:2px;box-shadow:0 4px 16px rgba(0,0,0,.4);backdrop-filter:blur(8px);animation:se-fade .15s ease-out both';
  outcomes.forEach(function(o){
    const isCurrent = o.ci === _sePath[depth];
    const isActual = g.actual !== null && ['W','D','L'][g.actual] === o.k;
    const GOLD = '#ffd54f';
    const btnClr = isActual ? GOLD : oClr[o.k];
    const btnBg = isCurrent ? (isActual ? 'rgba(255,213,79,.15)' : hexAlpha(oClr[o.k],0.15)) : 'transparent';
    const btnBorder = isCurrent ? (isActual ? GOLD+'80' : oClr[o.k]+'80') : (isActual ? GOLD+'50' : oClr[o.k]+'30');
    const btn = document.createElement('button');
    btn.style.cssText = 'border:1px solid '+btnBorder+';background:'+btnBg+';color:'+btnClr+';font-family:"JetBrains Mono",monospace;font-size:.68rem;font-weight:'+((isCurrent||isActual)?'700':'500')+';padding:4px 8px;cursor:pointer;border-radius:3px;white-space:nowrap;transition:background .12s';
    btn.textContent = (isActual?'\u2713 ':'')+oLbl[o.k]+' '+(o.p*100).toFixed(0)+'%';
    var hoverBg = isActual ? 'rgba(255,213,79,.2)' : hexAlpha(oClr[o.k],0.2);
    btn.onmouseenter = function(){ btn.style.background = hoverBg; };
    btn.onmouseleave = function(){ btn.style.background = btnBg; };
    btn.onclick = function(e){
      e.stopPropagation();
      _seDismissPopover();
      if (o.ci === _sePath[depth]) return;  // same outcome, no change
      // Save the intent of remaining path steps (game index + outcome key)
      // Save the intent of remaining path steps (game index + outcome key + display info)
      var remaining = [];
      var rn = n.ch[_sePath[depth]].child;
      for (var ri = depth+1; ri < _sePath.length; ri++){
        _seGenChildren(rn);
        if (!rn.ch || !rn.ch[_sePath[ri]]) break;
        var re = rn.ch[_sePath[ri]];
        var rg = _seGames[re.gi];
        remaining.push({gi:re.gi, k:re.k, round:rg.round, ws:rg.ws, bs:rg.bs, actual:rg.actual});
        rn = re.child;
      }
      // Also include any previously orphaned steps
      remaining = remaining.concat(_seOrphaned);
      // Apply the change
      _sePath[depth] = o.ci;
      _sePath = _sePath.slice(0, depth+1);
      // Replay remaining steps where possible
      _seOrphaned = [];
      var cur = n.ch[o.ci].child;
      var replayed = 0;
      for (var ri2 = 0; ri2 < remaining.length; ri2++){
        if (cur.leaf) break;
        _seGenChildren(cur);
        if (!cur.ch || !cur.ch.length) break;
        var want = remaining[ri2];
        var found = false;
        for (var ci2 = 0; ci2 < cur.ch.length; ci2++){
          if (cur.ch[ci2].gi === want.gi && cur.ch[ci2].k === want.k){
            _sePath.push(ci2);
            cur = cur.ch[ci2].child;
            found = true;
            replayed++;
            break;
          }
        }
        if (!found){
          // This step and all after become orphaned
          _seOrphaned = remaining.slice(ri2);
          break;
        }
      }
      _seNavDir = 'fade';
      _seDfsWarning = '';
      _seRenderAll();
    };
    pop.appendChild(btn);
  });
  // Position relative to the clicked pill
  const target = evt.currentTarget;
  const rect = target.getBoundingClientRect();
  const crumbEl = document.getElementById('seCrumb');
  const crumbRect = crumbEl.getBoundingClientRect();
  pop.style.left = (rect.left - crumbRect.left) + 'px';
  pop.style.top = (rect.bottom - crumbRect.top + 4) + 'px';
  crumbEl.style.position = 'relative';
  crumbEl.appendChild(pop);
  _seCrumbPopover = pop;
  // Dismiss on outside click
  setTimeout(function(){
    document.addEventListener('click', _seDismissPopover, {once:true});
  }, 0);
}

function _seRenderAll(){
  _seRenderCrumb(); _seRenderSvg();
  const fn = document.getElementById('seFootnote');
  if (fn){ if (_seDfsWarning){ fn.textContent = '\u26a0 '+_seDfsWarning; fn.style.display = ''; } else { fn.style.display = 'none'; } }
  _seNavDir = 'fade';
}

/* ── breadcrumb (pill-style with gold for actual results, grouped by round) ── */
function _seRenderCrumb(){
  const el = document.getElementById('seCrumb');
  if (!el) return;
  const oClr = {W:'#00e676', D:'#8494be', L:'#ff5252'};
  const oLbl = {W:'1\u20130', D:'\u00bd\u2013\u00bd', L:'0\u20131'};
  const GOLD = '#ffd54f';

  if (_sePath.length === 0){
    el.innerHTML = '<div style="display:flex;align-items:center;gap:3px;font-family:\'JetBrains Mono\',monospace;font-size:.7rem;line-height:1">' +
      '<span onclick="_seNav(-1)" style="cursor:pointer;padding:4px 8px;border-radius:4px;background:rgba(120,180,255,.1);border:1px solid rgba(120,180,255,.2);color:#78b4ff;font-weight:600;font-size:.65rem;letter-spacing:.05em">START</span></div>';
    return;
  }

  // Collect steps with round info
  const steps = [];
  let n = _seTree;
  for (let i = 0; i < _sePath.length; i++){
    _seGenChildren(n);
    const e = n.ch[_sePath[i]];
    const g = _seGames[e.gi];
    steps.push({depth:i, edge:e, game:g});
    n = e.child;
  }

  // Group by round
  const roundGroups = [];
  steps.forEach(function(s){
    const rn = s.game.round;
    if (roundGroups.length === 0 || roundGroups[roundGroups.length-1].round !== rn){
      roundGroups.push({round:rn, steps:[]});
    }
    roundGroups[roundGroups.length-1].steps.push(s);
  });

  let html = '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:5px;font-family:\'JetBrains Mono\',monospace;font-size:.7rem;line-height:1">';

  // Start pill
  html += '<span onclick="_seNav(-1)" style="cursor:pointer;padding:4px 8px;border-radius:4px;background:rgba(120,180,255,.1);border:1px solid rgba(120,180,255,.2);color:#78b4ff;font-weight:600;font-size:.65rem;letter-spacing:.05em">START</span>';

  roundGroups.forEach(function(rg){
    // Arrow between round groups
    html += '<span style="color:#263764;font-size:.55rem">\u25b8</span>';

    // Round group container
    html += '<div style="display:inline-flex;align-items:center;gap:2px;padding:2px 4px;border-radius:4px;border:1px solid rgba(120,180,255,.1);background:rgba(120,180,255,.03)">';

    // Round label
    html += '<span style="color:#4e5f8a;font-size:.55rem;font-weight:600;letter-spacing:.06em;margin-right:2px">R'+rg.round+'</span>';

    rg.steps.forEach(function(s, si){
      const e = s.edge, g = s.game;
      const rc = oClr[e.k];
      const rl = oLbl[e.k];
      const isActual = g.actual !== null && ['W','D','L'][g.actual] === e.k;
      const bg = isActual ? 'rgba(255,213,79,.12)' : hexAlpha(rc, 0.08);
      const border = isActual ? GOLD+'60' : hexAlpha(rc, 0.25);
      const labelClr = isActual ? GOLD : rc;

      // Result pill — click to edit outcome
      html += '<span onclick="_seEditCrumb('+s.depth+',event)" style="cursor:pointer;display:inline-flex;align-items:center;gap:2px;padding:2px 5px;border-radius:3px;background:'+bg+';border:1px solid '+border+';transition:background .15s" '+
        'onmouseenter="this.style.background=\''+hexAlpha(rc,0.18)+'\'" onmouseleave="this.style.background=\''+bg+'\'">';
      if (isActual) html += '<span style="color:'+GOLD+';font-size:.5rem">\u2713</span>';
      html += '<span style="color:var(--paper-2);font-size:.58rem">'+g.ws+'</span>';
      html += '<span style="color:'+labelClr+';font-weight:700;font-size:.6rem">'+rl+'</span>';
      html += '<span style="color:var(--paper-2);font-size:.58rem">'+g.bs+'</span>';
      html += '</span>';
    });

    html += '</div>';
  });

  // Render orphaned (greyed-out) steps
  if (_seOrphaned.length > 0){
    const orphanLbl = {W:'1\u20130', D:'\u00bd\u2013\u00bd', L:'0\u20131'};
    // Group orphans by round
    const orphanGroups = [];
    _seOrphaned.forEach(function(s){
      if (orphanGroups.length === 0 || orphanGroups[orphanGroups.length-1].round !== s.round){
        orphanGroups.push({round:s.round, steps:[]});
      }
      orphanGroups[orphanGroups.length-1].steps.push(s);
    });

    // Separator
    html += '<span style="color:#263764;font-size:.55rem;margin:0 2px">\u00d7</span>';

    orphanGroups.forEach(function(rg, rgi){
      if (rgi > 0) html += '<span style="color:#1a2448;font-size:.55rem">\u25b8</span>';

      html += '<div style="display:inline-flex;align-items:center;gap:2px;padding:2px 4px;border-radius:4px;border:1px dashed rgba(120,180,255,.08);background:transparent;opacity:.35">';
      html += '<span style="color:#4e5f8a;font-size:.55rem;font-weight:600;letter-spacing:.06em;margin-right:2px">R'+rg.round+'</span>';

      rg.steps.forEach(function(s){
        const k = s.k;
        const rl = orphanLbl[k];
        html += '<span style="display:inline-flex;align-items:center;gap:2px;padding:2px 5px;border-radius:3px;border:1px solid rgba(120,180,255,.08);background:transparent">';
        html += '<span style="color:var(--paper-4);font-size:.58rem">'+s.ws+'</span>';
        html += '<span style="color:var(--paper-4);font-weight:600;font-size:.6rem">'+rl+'</span>';
        html += '<span style="color:var(--paper-4);font-size:.58rem">'+s.bs+'</span>';
        html += '</span>';
      });

      html += '</div>';
    });
  }

  html += '</div>';
  el.innerHTML = html;
}

/* ── SVG rendering (past trail + 2 levels deep + transitions) ── */
function _seRenderSvg(){
  const wrap = document.getElementById('seSvgWrap');
  const focus = _seGetFocused();
  const pastChain = _seBuildPastChain();

  // Animation name based on navigation direction
  const animName = _seNavDir === 'forward' ? 'se-fwd' : _seNavDir === 'backward' ? 'se-bwd' : 'se-fade';

  // Leaf: verdict
  if (focus.leaf){
    const sorted = [..._seContenders].sort((a,b) => focus.scores[b.key] - focus.scores[a.key]);
    let html = '<div style="animation:'+animName+' .3s ease-out both;display:flex;gap:1.5rem;align-items:flex-start">';
    // Last round games panel
    if (pastChain.length > 0){
      const lastRound = pastChain[pastChain.length - 1].game.round;
      const lastRoundSteps = [];
      for (let i = pastChain.length - 1; i >= 0; i--){
        if (pastChain[i].game.round === lastRound) lastRoundSteps.unshift({step:pastChain[i], depth:i});
        else break;
      }
      const oClr = {W:'#00e676', D:'#8494be', L:'#ff5252'};
      const oLbl = {W:'1\u20130', D:'\u00bd\u2013\u00bd', L:'0\u20131'};
      const GOLD = '#ffd54f';
      html += '<div style="flex-shrink:0;min-width:140px">';
      html += '<div style="font-family:\'JetBrains Mono\',monospace;font-size:.6rem;color:#4e5f8a;text-transform:uppercase;letter-spacing:.1em;margin-bottom:.5rem;font-weight:600">Round '+lastRound+'</div>';
      lastRoundSteps.forEach(function(s){
        const g = s.step.game, e = s.step.edge;
        const rc = oClr[e.k];
        const isActual = g.actual !== null && ['W','D','L'][g.actual] === e.k;
        const nodeClr = isActual ? GOLD : rc;
        const bg = isActual ? 'rgba(255,213,79,.08)' : 'rgba(120,180,255,.04)';
        const border = isActual ? GOLD+'50' : 'rgba(120,180,255,.15)';
        html += '<div onclick="_seNav('+s.depth+')" style="cursor:pointer;padding:6px 10px;margin-bottom:4px;border-radius:5px;border:1px solid '+border+';background:'+bg+';transition:background .15s,border-color .15s" '+
          'onmouseenter="this.style.background=\'rgba(120,180,255,.12)\';this.style.borderColor=\'rgba(120,180,255,.3)\'" '+
          'onmouseleave="this.style.background=\''+bg+'\';this.style.borderColor=\''+border+'\'">';
        html += '<div style="font-family:\'JetBrains Mono\',monospace;font-size:.7rem;display:flex;align-items:center;gap:6px">';
        html += '<span style="color:var(--paper-2)">'+g.ws+'</span>';
        html += '<span style="color:'+nodeClr+';font-weight:700">'+oLbl[e.k]+'</span>';
        html += '<span style="color:var(--paper-2)">'+g.bs+'</span>';
        if (isActual) html += '<span style="color:'+GOLD+';font-size:.55rem;margin-left:auto">\u2713</span>';
        html += '</div></div>';
      });
      html += '</div>';
    }
    // Verdict card
    html += '<div style="flex:1;min-width:0">';
    if (focus.winner){
      html += '<div style="text-align:center;padding:1.5rem;background:rgba(0,230,118,.06);border:1px solid rgba(0,230,118,.25);border-radius:8px">' +
        '<div style="font-size:.65rem;color:var(--paper-3);text-transform:uppercase;letter-spacing:.14em;margin-bottom:.4rem">All contender games decided</div>' +
        '<div style="font-size:1.3rem;font-weight:700;color:'+focus.winner.color+'">\u2605 '+focus.winner.short+'</div>' +
        '<div style="font-family:\'JetBrains Mono\',monospace;font-size:.85rem;color:var(--paper-2);margin-top:.3rem">'+focus.scores[focus.winner.key]+' points</div></div>';
    } else {
      html += '<div style="text-align:center;padding:1.5rem;background:rgba(255,238,88,.06);border:1px solid rgba(255,238,88,.25);border-radius:8px">' +
        '<div style="font-size:.65rem;color:var(--paper-3);text-transform:uppercase;letter-spacing:.14em;margin-bottom:.4rem">Tiebreak Required</div>' +
        '<div style="font-size:1.1rem;font-weight:700">'+focus.tied.map(function(p){return '<span style="color:'+p.color+'">'+p.short+'</span>';}).join(' \u00b7 ')+'</div>' +
        '<div style="font-family:\'JetBrains Mono\',monospace;font-size:.85rem;color:var(--paper-2);margin-top:.3rem">Tied at '+focus.scores[focus.tied[0].key]+' points</div></div>';
    }
    const maxScore = Math.max(...sorted.map(function(p){return focus.scores[p.key];}));
    html += '<div style="margin-top:.8rem;display:flex;flex-direction:column;gap:.4rem;font-family:\'JetBrains Mono\',monospace;font-size:.8rem">' + sorted.map(function(p){
      var sc = focus.scores[p.key];
      var barW = maxScore > 0 ? (sc / maxScore * 100) : 0;
      return '<div style="display:flex;align-items:center;gap:.5rem">' +
        '<span style="color:'+p.color+';font-weight:600;width:8em;text-align:right;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+p.short+'</span>' +
        '<div style="flex:1;height:8px;background:var(--rule);border-radius:2px;overflow:hidden">' +
          '<div style="width:'+barW+'%;height:100%;background:'+p.color+';border-radius:2px"></div></div>' +
        '<span style="color:var(--paper-2);width:4.5em;text-align:right;flex-shrink:0">'+sc+' pts</span></div>';
    }).join('') + '</div></div></div>';
    wrap.innerHTML = html;
    return;
  }

  _seGenChildren(focus);
  const ch = focus.ch;
  if (!ch || !ch.length){ wrap.innerHTML = ''; return; }

  // Group level-1 children by game
  const groups = [];
  let lastGi = -1;
  ch.forEach(function(c,ci){
    if (c.gi !== lastGi){ groups.push({gi:c.gi, items:[]}); lastGi = c.gi; }
    groups[groups.length-1].items.push({k:c.k, p:c.p, gi:c.gi, child:c.child, ci:ci});
  });

  // Generate level-2 grandchildren
  const GC_H = 18, GC_VS = 3, GC_GRP_LBL = 14, GC_GRP_VS = 6;
  const VERDICT_H = 30;  // height for leaf verdict nodes in GC column
  let hasAnyGC = false;
  groups.forEach(function(grp){
    grp.items.forEach(function(c){
      c.gcGroups = []; c.gcFanH = 0; c.isLeaf = c.child.leaf;
      if (c.child.leaf){
        // Leaf children get a verdict node in the GC column
        hasAnyGC = true;
        c.gcFanH = VERDICT_H;
      } else {
        _seGenChildren(c.child);
        if (c.child.ch && c.child.ch.length){
          hasAnyGC = true;
          let lg = -1;
          c.child.ch.forEach(function(gc, gci){
            if (gc.gi !== lg){ c.gcGroups.push({gi:gc.gi, items:[]}); lg = gc.gi; }
            c.gcGroups[c.gcGroups.length-1].items.push({k:gc.k, p:gc.p, gi:gc.gi, child:gc.child, gci:gci});
          });
          let h = 0;
          c.gcGroups.forEach(function(gg,i){
            h += GC_GRP_LBL + gg.items.length * GC_H + (gg.items.length - 1) * GC_VS;
            if (i < c.gcGroups.length - 1) h += GC_GRP_VS;
          });
          c.gcFanH = h;
        }
      }
    });
  });

  // Past trail: group by round, show last 2 rounds
  const MAX_PAST_ROUNDS = 2;
  const PAST_W = 145, PAST_ITEM_H = 28, PAST_ITEM_VS = 4, PAST_HS = 35;
  const TRUNC_W = 18;

  // Group past steps by round
  const pastRoundGroups = [];
  pastChain.forEach(function(step, si){
    const rn = step.game.round;
    if (pastRoundGroups.length === 0 || pastRoundGroups[pastRoundGroups.length-1].round !== rn){
      pastRoundGroups.push({round: rn, steps: []});
    }
    pastRoundGroups[pastRoundGroups.length-1].steps.push({step:step, depth:si});
  });
  const visRoundGroups = pastRoundGroups.slice(-MAX_PAST_ROUNDS);
  const hasTrunc = pastRoundGroups.length > MAX_PAST_ROUNDS;
  const pastAreaW = visRoundGroups.length > 0
    ? (hasTrunc ? TRUNC_W + 10 : 0) + visRoundGroups.length * PAST_W + visRoundGroups.length * PAST_HS
    : 0;

  // Layout dimensions — adapt to number of contenders
  const nC = _seContenders.length;
  const FOCUS_LH = 18;
  const FOCUS_W = 170, FOCUS_H = 26 + nC * FOCUS_LH + 6;
  const CH_W = 170;
  const GC_W = 120;
  const CH_LH = Math.min(15, Math.max(10, (60 - 26) / nC));
  const defaultCH_H = Math.max(42, 26 + nC * CH_LH);
  const VS_IN = 6, VS_OUT = 20, GRP_LBL = 18;
  const HS = 70, HS2 = 45, PAD = 30;

  groups.forEach(function(grp){
    grp.items.forEach(function(c){
      c.slotH = Math.max(defaultCH_H, c.gcFanH);
    });
  });

  let totalChildH = 0;
  groups.forEach(function(grp,gi){
    totalChildH += GRP_LBL;
    grp.items.forEach(function(c,i){
      totalChildH += c.slotH;
      if (i < grp.items.length - 1) totalChildH += VS_IN;
    });
    if (gi < groups.length - 1) totalChildH += VS_OUT;
  });

  let maxPastColH = 0;
  visRoundGroups.forEach(function(rg){
    const h = rg.steps.length * PAST_ITEM_H + (rg.steps.length - 1) * PAST_ITEM_VS + 15;
    if (h > maxPastColH) maxPastColH = h;
  });
  const svgH = Math.max(totalChildH, FOCUS_H, maxPastColH) + PAD*2;
  const svgW = PAD + pastAreaW + FOCUS_W + HS + CH_W + (hasAnyGC ? HS2 + GC_W : 0) + PAD;

  const svg = document.createElementNS(SE_NS,'svg');
  svg.setAttribute('viewBox','0 0 '+svgW+' '+svgH);
  svg.setAttribute('width','100%');
  svg.style.maxWidth = svgW+'px';
  svg.style.overflow = 'hidden';
  svg.style.animation = animName+' .3s ease-out both';

  const fx = PAD + pastAreaW, fy = svgH/2;
  const childX = fx + FOCUS_W + HS;
  const gcX = childX + CH_W + HS2;

  // ── Past trail nodes (grouped by round) ──
  if (visRoundGroups.length > 0){
    const eClr2 = {W:'#00e676', D:'#8494be', L:'#ff5252'};
    let px = PAD + (hasTrunc ? TRUNC_W + 10 : 0);

    // Truncation indicator
    if (hasTrunc){
      const dt = document.createElementNS(SE_NS,'text');
      dt.setAttribute('x',PAD+TRUNC_W/2); dt.setAttribute('y',fy+4);
      dt.setAttribute('text-anchor','middle'); dt.setAttribute('fill','#4e5f8a');
      dt.setAttribute('font-family',"'JetBrains Mono',monospace");
      dt.setAttribute('font-size','11'); dt.setAttribute('font-weight','600');
      dt.textContent = '\u00b7\u00b7\u00b7';
      svg.appendChild(dt);
    }

    const GOLD_PAST = '#ffd54f';
    visRoundGroups.forEach(function(rg, rgi){
      const nItems = rg.steps.length;
      const colH = nItems * PAST_ITEM_H + (nItems - 1) * PAST_ITEM_VS;
      const colTop = fy - colH / 2;
      const baseOp = 0.35 + rgi * (0.35 / Math.max(1, visRoundGroups.length - 1));

      // Round label above the column
      const rl2 = document.createElementNS(SE_NS,'text');
      rl2.setAttribute('x',px+PAST_W/2); rl2.setAttribute('y',colTop-5);
      rl2.setAttribute('text-anchor','middle'); rl2.setAttribute('fill','#4e5f8a');
      rl2.setAttribute('font-family',"'JetBrains Mono',monospace");
      rl2.setAttribute('font-size','7.5'); rl2.setAttribute('opacity',baseOp.toFixed(2));
      rl2.textContent = 'Round '+rg.round;
      svg.appendChild(rl2);

      rg.steps.forEach(function(s, si){
        const step = s.step, depth = s.depth;
        const iy = colTop + si * (PAST_ITEM_H + PAST_ITEM_VS);
        const rc = eClr2[step.edge.k];
        const rl = step.edge.k==='W'?'1\u20130':step.edge.k==='D'?'\u00bd\u2013\u00bd':'0\u20131';
        const isActual = step.game.actual !== null && ['W','D','L'][step.game.actual] === step.edge.k;
        const nodeClr = isActual ? GOLD_PAST : rc;

        const rect = document.createElementNS(SE_NS,'rect');
        rect.setAttribute('x',px); rect.setAttribute('y',iy);
        rect.setAttribute('width',PAST_W); rect.setAttribute('height',PAST_ITEM_H);
        rect.setAttribute('fill', isActual ? 'rgba(255,213,79,0.06)' : 'rgba(11,17,32,0.6)');
        rect.setAttribute('stroke', isActual ? GOLD_PAST+'70' : rc+'50');
        rect.setAttribute('stroke-width', isActual ? '1.5' : '1');
        rect.setAttribute('rx','4'); rect.setAttribute('opacity',baseOp.toFixed(2));
        svg.appendChild(rect);

        // Result text
        const rt = document.createElementNS(SE_NS,'text');
        rt.setAttribute('x',px+PAST_W/2); rt.setAttribute('y',iy+PAST_ITEM_H/2+3);
        rt.setAttribute('text-anchor','middle'); rt.setAttribute('fill',nodeClr);
        rt.setAttribute('font-family',"'JetBrains Mono',monospace");
        rt.setAttribute('font-size','7.5'); rt.setAttribute('font-weight','600');
        rt.setAttribute('opacity',baseOp.toFixed(2));
        const pastLabel = (isActual?'\u2713 ':'')+step.game.ws+' '+rl+' '+step.game.bs;
        rt.textContent = pastLabel;
        if (pastLabel.length > 22) rt.setAttribute('textLength', PAST_W - 12);
        rt.setAttribute('lengthAdjust','spacingAndGlyphs');
        svg.appendChild(rt);

        // Click overlay
        const click = document.createElementNS(SE_NS,'rect');
        click.setAttribute('x',px); click.setAttribute('y',iy);
        click.setAttribute('width',PAST_W); click.setAttribute('height',PAST_ITEM_H);
        click.setAttribute('fill','transparent'); click.setAttribute('cursor','pointer');
        const navDepth = depth;
        click.addEventListener('click', function(){ _seNav(navDepth); });
        click.addEventListener('mouseenter', function(){ rect.setAttribute('stroke',rc); rect.setAttribute('opacity','0.9'); });
        click.addEventListener('mouseleave', function(){ rect.setAttribute('stroke',isActual?GOLD_PAST+'70':rc+'50'); rect.setAttribute('opacity',baseOp.toFixed(2)); });
        svg.appendChild(click);
      });

      // Edge from this round column to next column or focus
      const nextX = px + PAST_W;
      const toX = rgi < visRoundGroups.length - 1 ? px + PAST_W + PAST_HS : fx;
      const mx = (nextX + toX) / 2;
      const edge = document.createElementNS(SE_NS,'path');
      edge.setAttribute('d','M'+nextX+','+fy+' C'+mx+','+fy+' '+mx+','+fy+' '+toX+','+fy);
      edge.setAttribute('fill','none');
      edge.setAttribute('stroke','#263764');
      edge.setAttribute('stroke-width','1');
      edge.setAttribute('stroke-dasharray','3,3');
      edge.setAttribute('opacity',(baseOp+0.15).toFixed(2));
      svg.appendChild(edge);

      px += PAST_W + PAST_HS;
    });
  }

  // ── Position level-1 children and level-2 fans ──
  let cy2 = PAD + Math.max(0, svgH - PAD*2 - totalChildH) / 2;
  groups.forEach(function(grp){
    grp._ly = cy2 + GRP_LBL*0.75;
    cy2 += GRP_LBL;
    grp.items.forEach(function(c,i){
      c._x = childX; c._y = cy2 + c.slotH/2;
      if (c.isLeaf){
        // Position verdict node in GC column, centered on child
        c._verdictX = gcX; c._verdictY = c._y;
      } else if (c.gcGroups.length > 0){
        let gy = c._y - c.gcFanH/2;
        c.gcGroups.forEach(function(gg,gi2){
          gg._ly = gy + GC_GRP_LBL*0.75;
          gy += GC_GRP_LBL;
          gg.items.forEach(function(gc,j){
            gc._x = gcX; gc._y = gy + GC_H/2;
            gy += GC_H + (j < gg.items.length-1 ? GC_VS : 0);
          });
          if (gi2 < c.gcGroups.length-1) gy += GC_GRP_VS;
        });
      }
      cy2 += c.slotH + (i < grp.items.length-1 ? VS_IN : 0);
    });
    cy2 += VS_OUT;
  });

  const eClr = {W:'#00e676', D:'#8494be', L:'#ff5252'};

  const GOLD = '#ffd54f';

  // ── Draw level-0 → level-1 edges ──
  groups.forEach(function(grp){
    grp.items.forEach(function(c){
      const gg = _seGames[c.gi];
      const isActual = gg.actual !== null && ['W','D','L'][gg.actual] === c.k;
      const x1 = fx+FOCUS_W, y1 = fy, x2 = c._x, y2 = c._y, mx = (x1+x2)/2;
      const p = document.createElementNS(SE_NS,'path');
      p.setAttribute('d','M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2);
      p.setAttribute('fill','none');
      p.setAttribute('stroke',isActual ? GOLD : eClr[c.k]);
      p.setAttribute('stroke-width',isActual ? '2.5' : Math.max(0.8,c.p*3.5).toFixed(1));
      p.setAttribute('opacity',isActual ? '0.9' : (0.25+c.p*0.65).toFixed(2));
      svg.appendChild(p);
    });
  });

  // ── Draw level-1 → level-2 edges ──
  groups.forEach(function(grp){
    grp.items.forEach(function(c){
      if (c.isLeaf){
        // Edge from leaf child to verdict node
        const x1 = c._x+CH_W, y1 = c._y, x2 = c._verdictX, y2 = c._verdictY, mx = (x1+x2)/2;
        const p = document.createElementNS(SE_NS,'path');
        p.setAttribute('d','M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2);
        p.setAttribute('fill','none');
        p.setAttribute('stroke', c.child.winner ? c.child.winner.color : '#ffee58');
        p.setAttribute('stroke-width','1.5');
        p.setAttribute('opacity','0.7');
        svg.appendChild(p);
      } else if (c.gcGroups.length > 0){
        c.gcGroups.forEach(function(gg){
          gg.items.forEach(function(gc){
            const x1 = c._x+CH_W, y1 = c._y, x2 = gc._x, y2 = gc._y, mx = (x1+x2)/2;
            const p = document.createElementNS(SE_NS,'path');
            p.setAttribute('d','M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2);
            p.setAttribute('fill','none');
            p.setAttribute('stroke',eClr[gc.k]);
            p.setAttribute('stroke-width',Math.max(0.5,gc.p*2.5).toFixed(1));
            p.setAttribute('opacity',(0.15+gc.p*0.45).toFixed(2));
            svg.appendChild(p);
          });
        });
      }
    });
  });

  // ── Focus node (level 0) ──
  (function(){
    const sorted = [..._seContenders].sort((a,b) => focus.scores[b.key] - focus.scores[a.key]);
    const lc = sorted[0].color;
    const rect = document.createElementNS(SE_NS,'rect');
    rect.setAttribute('x',fx); rect.setAttribute('y',fy-FOCUS_H/2);
    rect.setAttribute('width',FOCUS_W); rect.setAttribute('height',FOCUS_H);
    rect.setAttribute('fill','rgba(15,22,40,0.95)');
    rect.setAttribute('stroke',lc); rect.setAttribute('stroke-width','2');
    rect.setAttribute('rx','6');
    svg.appendChild(rect);

    const np = focus.pending.length;
    const hl = document.createElementNS(SE_NS,'text');
    hl.setAttribute('x',fx+FOCUS_W/2); hl.setAttribute('y',fy-FOCUS_H/2+15);
    hl.setAttribute('text-anchor','middle'); hl.setAttribute('fill','#6a7ca3');
    hl.setAttribute('font-family',"'JetBrains Mono',monospace");
    hl.setAttribute('font-size','9');
    hl.textContent = np+' game'+(np!==1?'s':'')+' remaining';
    svg.appendChild(hl);

    const sy = fy - FOCUS_H/2 + 26, lh = FOCUS_LH;
    sorted.forEach(function(p,i){
      const sc = focus.scores[p.key], ty = sy + i*lh;
      const al = focus.alive.has(p.key), ld = p.key === sorted[0].key;
      const bw = (sc / DATA.meta.total_rounds) * (FOCUS_W-8);
      const bar = document.createElementNS(SE_NS,'rect');
      bar.setAttribute('x',fx+4); bar.setAttribute('y',ty);
      bar.setAttribute('width',Math.max(0,bw)); bar.setAttribute('height',lh-4);
      bar.setAttribute('fill',hexAlpha(p.color,al?0.2:0.06)); bar.setAttribute('rx','2');
      svg.appendChild(bar);
      const st = document.createElementNS(SE_NS,'text');
      st.setAttribute('x',fx+FOCUS_W-5); st.setAttribute('y',ty+lh*0.65);
      st.setAttribute('text-anchor','end');
      st.setAttribute('fill',al?p.color:hexAlpha(p.color,0.3));
      st.setAttribute('font-family',"'JetBrains Mono',monospace");
      st.setAttribute('font-size','10'); st.setAttribute('font-weight',ld?'700':'400');
      st.textContent = p.short+' '+sc+(al?'':' \u2717');
      svg.appendChild(st);
    });
  })();

  // ── Level-1 group labels + child nodes ──
  groups.forEach(function(grp){
    const g = _seGames[grp.gi];
    const gl = document.createElementNS(SE_NS,'text');
    gl.setAttribute('x',childX); gl.setAttribute('y',grp._ly);
    gl.setAttribute('fill','#6a7ca3');
    gl.setAttribute('font-family',"'JetBrains Mono',monospace");
    gl.setAttribute('font-size','9');
    gl.textContent = 'R'+g.round+': '+g.ws+' vs '+g.bs;
    svg.appendChild(gl);

    grp.items.forEach(function(c){
      const x = c._x, y = c._y;
      const gg = _seGames[c.gi];
      const rc = eClr[c.k];
      const isActual = gg.actual !== null && ['W','D','L'][gg.actual] === c.k;
      const sorted = [..._seContenders].sort((a,b) => c.child.scores[b.key] - c.child.scores[a.key]);
      const lc = sorted[0].color;

      const grpEl = document.createElementNS(SE_NS,'g');
      const rect = document.createElementNS(SE_NS,'rect');
      rect.setAttribute('x',x); rect.setAttribute('y',y-defaultCH_H/2);
      rect.setAttribute('width',CH_W); rect.setAttribute('height',defaultCH_H);
      rect.setAttribute('fill', isActual ? 'rgba(255,213,79,0.06)' : 'rgba(11,17,32,0.85)');
      rect.setAttribute('stroke', isActual ? GOLD+'80' : rc+'40');
      rect.setAttribute('stroke-width', isActual ? '1.5' : '1');
      rect.setAttribute('rx','4');
      grpEl.appendChild(rect);

      const rl = c.k==='W'?'1\u20130':c.k==='D'?'\u00bd\u2013\u00bd':'0\u20131';
      const rt = document.createElementNS(SE_NS,'text');
      rt.setAttribute('x', isActual ? x+16 : x+6); rt.setAttribute('y',y-defaultCH_H/2+14);
      rt.setAttribute('fill', isActual ? GOLD : rc);
      rt.setAttribute('font-family',"'JetBrains Mono',monospace");
      rt.setAttribute('font-size','10'); rt.setAttribute('font-weight','600');
      rt.textContent = gg.ws+' '+rl+' '+gg.bs;
      grpEl.appendChild(rt);
      // Checkmark for actual result
      if (isActual){
        const chk = document.createElementNS(SE_NS,'text');
        chk.setAttribute('x',x+6); chk.setAttribute('y',y-defaultCH_H/2+14);
        chk.setAttribute('fill',GOLD); chk.setAttribute('font-size','9.5');
        chk.textContent = '\u2713';
        grpEl.appendChild(chk);
      }
      const pt = document.createElementNS(SE_NS,'text');
      pt.setAttribute('x',x+CH_W-6); pt.setAttribute('y',y-defaultCH_H/2+14);
      pt.setAttribute('text-anchor','end'); pt.setAttribute('fill', isActual ? GOLD : rc);
      pt.setAttribute('font-family',"'JetBrains Mono',monospace");
      pt.setAttribute('font-size','9'); pt.setAttribute('opacity','0.7');
      pt.textContent = (c.p*100).toFixed(0)+'%';
      grpEl.appendChild(pt);

      const sy = y - defaultCH_H/2 + 24;
      const lh = CH_LH;
      sorted.forEach(function(p,i){
        const sc = c.child.scores[p.key], ty = sy + i*lh;
        const al = c.child.alive.has(p.key), ld = p.key === sorted[0].key;
        const changed = sc !== focus.scores[p.key];
        const st = document.createElementNS(SE_NS,'text');
        st.setAttribute('x',x+6); st.setAttribute('y',ty+lh*0.8);
        st.setAttribute('fill',al ? (changed ? '#fff' : p.color) : hexAlpha(p.color,0.3));
        st.setAttribute('font-family',"'JetBrains Mono',monospace");
        st.setAttribute('font-size','9.5');
        st.setAttribute('font-weight',(ld||changed)?'700':'400');
        st.textContent = p.short+' '+sc+(al?'':' \u2717');
        grpEl.appendChild(st);
      });

      svg.appendChild(grpEl);

      const click = document.createElementNS(SE_NS,'rect');
      click.setAttribute('x',x); click.setAttribute('y',y-defaultCH_H/2);
      click.setAttribute('width',CH_W); click.setAttribute('height',defaultCH_H);
      click.setAttribute('fill','transparent'); click.setAttribute('cursor','pointer');
      click.addEventListener('click', function(){ _seClick(c.ci); });
      click.addEventListener('mouseenter', function(){ rect.setAttribute('stroke',lc); rect.setAttribute('stroke-width','1.5'); });
      click.addEventListener('mouseleave', function(){ rect.setAttribute('stroke',rc+'40'); rect.setAttribute('stroke-width','1'); });
      svg.appendChild(click);
    });
  });

  // ── Level-2 grandchild pills ──
  groups.forEach(function(grp){
    grp.items.forEach(function(c){
      // Render verdict node for leaf children
      if (c.isLeaf){
        const vx = c._verdictX, vy = c._verdictY;
        const vw = GC_W, vh = VERDICT_H;
        const wn = c.child.winner;
        const vc = wn ? wn.color : '#ffee58';
        const vr = document.createElementNS(SE_NS,'rect');
        vr.setAttribute('x',vx); vr.setAttribute('y',vy-vh/2);
        vr.setAttribute('width',vw); vr.setAttribute('height',vh);
        vr.setAttribute('fill','rgba(11,17,32,0.85)');
        vr.setAttribute('stroke',vc+'60'); vr.setAttribute('stroke-width','1.5');
        vr.setAttribute('rx','4');
        svg.appendChild(vr);
        // Accent bar
        const va = document.createElementNS(SE_NS,'rect');
        va.setAttribute('x',vx); va.setAttribute('y',vy-vh/2);
        va.setAttribute('width','3'); va.setAttribute('height',vh);
        va.setAttribute('fill',vc); va.setAttribute('opacity','0.8');
        va.setAttribute('rx','1.5');
        svg.appendChild(va);
        // Verdict text
        const vt = document.createElementNS(SE_NS,'text');
        vt.setAttribute('x',vx+vw/2); vt.setAttribute('y',vy+4);
        vt.setAttribute('text-anchor','middle'); vt.setAttribute('fill',vc);
        vt.setAttribute('font-family',"'JetBrains Mono',monospace");
        vt.setAttribute('font-size','10'); vt.setAttribute('font-weight','700');
        vt.textContent = wn ? '\u2605 '+wn.short : 'TIE';
        svg.appendChild(vt);
        return;
      }
      if (c.gcGroups.length === 0) return;
      c.gcGroups.forEach(function(gg){
        const g2 = _seGames[gg.gi];
        const gl2 = document.createElementNS(SE_NS,'text');
        gl2.setAttribute('x',gcX); gl2.setAttribute('y',gg._ly);
        gl2.setAttribute('fill','#4e5f8a');
        gl2.setAttribute('font-family',"'JetBrains Mono',monospace");
        gl2.setAttribute('font-size','8');
        gl2.textContent = g2.ws+' v '+g2.bs;
        svg.appendChild(gl2);

        gg.items.forEach(function(gc){
          const gx = gc._x, gy = gc._y;
          const rc2 = eClr[gc.k];
          const gsorted = [..._seContenders].sort((a,b) => gc.child.scores[b.key] - gc.child.scores[a.key]);
          const glc = gsorted[0].color;

          const pill = document.createElementNS(SE_NS,'rect');
          pill.setAttribute('x',gx); pill.setAttribute('y',gy-GC_H/2);
          pill.setAttribute('width',GC_W); pill.setAttribute('height',GC_H);
          pill.setAttribute('fill','rgba(11,17,32,0.7)');
          pill.setAttribute('stroke',rc2+'30'); pill.setAttribute('stroke-width','0.5');
          pill.setAttribute('rx','3');
          svg.appendChild(pill);

          const accent = document.createElementNS(SE_NS,'rect');
          accent.setAttribute('x',gx); accent.setAttribute('y',gy-GC_H/2);
          accent.setAttribute('width','3'); accent.setAttribute('height',GC_H);
          accent.setAttribute('fill',rc2); accent.setAttribute('opacity','0.7');
          accent.setAttribute('rx','1.5');
          svg.appendChild(accent);

          const rl2 = gc.k==='W'?'W':gc.k==='D'?'D':'L';
          const leaderSc = gc.child.scores[gsorted[0].key];
          const leaders = gsorted.filter(function(p){ return gc.child.scores[p.key] === leaderSc; });
          // Build label: truncate names part, always show score suffix
          const pct2 = (gc.p*100).toFixed(0)+'%';
          let lbl, lblDisplay;
          if (gc.child.leaf){
            if (gc.child.winner) lbl = rl2+' '+pct2+' \u2605 '+gc.child.winner.short;
            else lbl = rl2+' '+pct2+' TIE';
            lblDisplay = lbl;
          } else {
            const names = leaders.map(function(p){ return p.short; }).join(', ');
            const suffix = ' '+leaderSc;
            lbl = rl2+' '+pct2+' '+names+suffix;
            // Truncate names if full label is too long (~18 chars at font-size 8.5)
            const maxChars = 18;
            const prefixLen = rl2.length + 1 + pct2.length + 1; // "W 31% "
            const suffixLen = suffix.length;
            const namesBudget = maxChars - prefixLen - suffixLen;
            if (names.length > namesBudget && namesBudget > 2){
              lblDisplay = rl2+' '+pct2+' '+names.slice(0, namesBudget-1)+'\u2026'+suffix;
            } else {
              lblDisplay = lbl;
            }
          }

          const gcGrp = document.createElementNS(SE_NS,'g');
          const gt = document.createElementNS(SE_NS,'text');
          gt.setAttribute('x',gx+7); gt.setAttribute('y',gy+GC_H*0.3);
          gt.setAttribute('fill',gc.child.leaf ? (gc.child.winner ? gc.child.winner.color : '#ffee58') : (leaders.length > 1 ? '#ffee58' : glc));
          gt.setAttribute('font-family',"'JetBrains Mono',monospace");
          gt.setAttribute('font-size','8.5');
          gt.setAttribute('font-weight',gc.child.leaf ? '700' : '400');
          gt.setAttribute('opacity','0.85');
          gt.textContent = lblDisplay;
          gcGrp.appendChild(gt);
          // SVG tooltip via <title> child element
          if (lblDisplay !== lbl){
            const tt = document.createElementNS(SE_NS,'title');
            tt.textContent = lbl;
            gcGrp.appendChild(tt);
          }
          svg.appendChild(gcGrp);
        });
      });
    });
  });

  wrap.innerHTML = '';
  wrap.appendChild(svg);

  // Horizontal scroll to keep focus node visible
  if (_seNavDir === 'forward'){
    wrap.scrollLeft = Math.max(0, fx - 20);
  } else if (_seNavDir === 'backward'){
    wrap.scrollLeft = 0;
  }

  // Scroll the explorer into view so the focus node stays visible
  wrap.scrollIntoView({behavior:'smooth', block:'nearest'});
}

// ═══════════════════════════════════════════════
// PARETO CHART
// ═══════════════════════════════════════════════
function buildPareto(){
  const pd = DATA.pareto;
  document.getElementById('paretoSection').style.display='';

  // meta badges — show raw (unnormalized) values
  const meta = document.getElementById('paretoMeta');
  meta.innerHTML = `
    <div class="pmeta-item"><div class="pk">Total Trials</div><div class="pv">${pd.total_trials.toLocaleString()}</div></div>
    <div class="pmeta-item"><div class="pk">Pareto-Optimal</div><div class="pv">${pd.pareto_count}</div></div>
    <div class="pmeta-item"><div class="pk">Best Trial</div><div class="pv">#${pd.best.n}</div></div>
    <div class="pmeta-item"><div class="pk">Game Brier</div><div class="pv">${pd.best.rx.toFixed(4)}</div></div>
    <div class="pmeta-item"><div class="pk">Rank RPS</div><div class="pv">${pd.best.ry.toFixed(4)}</div></div>`;

  const xMin = pd.norm_min.x, yMin = pd.norm_min.y;
  const maxN = Math.max(...pd.all_points.map(p=>p.n));
  const nonPareto = pd.all_points.filter(p=>!p.p);
  const paretoOnly = pd.all_points.filter(p=>p.p);
  const axisMax = Math.max(...pd.all_points.map(p=>p.x), ...pd.all_points.map(p=>p.y));

  // step line
  const stepLineExt = [];
  for (let i=0; i<pd.pareto_line.length; i++){
    stepLineExt.push({x:pd.pareto_line[i].x, y:pd.pareto_line[i].y});
    if (i<pd.pareto_line.length-1)
      stepLineExt.push({x:pd.pareto_line[i+1].x, y:pd.pareto_line[i].y});
  }

  // Tooltip helper: denormalize for display
  function rawTip(ctx, prefix){
    const rx = (ctx.parsed.x * xMin).toFixed(4);
    const ry = (ctx.parsed.y * yMin).toFixed(4);
    return ` ${prefix}Brier=${rx}, RPS=${ry}`;
  }

  paretoChart = new Chart(document.getElementById('cPareto').getContext('2d'), {
    type:'scatter',
    data:{
      datasets:[
        {
          label:'All trials',
          data: nonPareto.map(p=>({x:p.x,y:p.y})),
          backgroundColor: nonPareto.map(p=>trialColor(p.n,maxN)),
          pointRadius:2.5, pointHoverRadius:4,
          order:3,
        },
        {
          label:'Pareto front line',
          data: stepLineExt,
          type:'line',
          borderColor:'#78b4ff70',
          borderWidth:1.5,
          borderDash:[4,3],
          pointRadius:0,
          tension:0,
          order:2,
          showLine:true,
        },
        {
          label:'Pareto-optimal',
          data: paretoOnly.map(p=>({x:p.x,y:p.y,n:p.n})),
          backgroundColor: '#40c4ffcc',
          borderColor: '#40c4ff',
          borderWidth:1,
          pointRadius:6, pointHoverRadius:8,
          order:1,
        },
        {
          label:`★ Best (Trial ${pd.best.n})`,
          data:[{x:pd.best.x,y:pd.best.y}],
          backgroundColor:'#ffee58',
          borderColor:'#ffee58',
          borderWidth:2,
          pointStyle:'star',
          pointRadius:24, pointHoverRadius:26,
          order:0,
        },
      ]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{position:'bottom',labels:{boxWidth:12,padding:12,font:{size:11},
          filter: item => item.text!=='Pareto front line'}},
        tooltip:{callbacks:{
          label: ctx => {
            if (ctx.datasetIndex===3) return rawTip(ctx, `★ Best #${pd.best.n} — `);
            if (ctx.datasetIndex===2) {
              const pt = paretoOnly[ctx.dataIndex];
              return rawTip(ctx, `Pareto #${pt?.n} — `);
            }
            return rawTip(ctx, '');
          }
        }}
      },
      scales:{
        x:{grid:{color:'rgba(120,180,255,.1)'},
           title:{display:true,text:'Game Brier (normalized, 1.0 = optimal)',color:'#8494be'},
           ticks:{font:{size:11}, callback:v=>v.toFixed(2)},
           min:0.98, max:axisMax},
        y:{grid:{color:'rgba(120,180,255,.1)'},
           title:{display:true,text:'Rank RPS (normalized, 1.0 = optimal)',color:'#8494be'},
           ticks:{font:{size:11}, callback:v=>v.toFixed(2)},
           min:0.98, max:axisMax}
      }
    }
  });

  // Pareto front table
  window._paretoPoints = paretoOnly;
  window._paretoBestN = pd.best.n;
  renderParetoTable();

  // Wire up sortable headers
  document.querySelectorAll('#tPareto thead th[data-sort]').forEach(th => {
    th.onclick = () => { toggleSort(paretoSort, th.dataset.sort); renderParetoTable(); };
  });
}

function renderParetoTable(){
  const pts = window._paretoPoints;
  const bestN = window._paretoBestN;
  const sorted = [...pts].sort((a,b) => {
    let va, vb;
    switch(paretoSort.col){
      case 'idx':   va = a.rx; vb = b.rx; break;
      case 'trial': va = a.n;  vb = b.n;  break;
      case 'brier': va = a.rx; vb = b.rx; break;
      case 'rps':   va = a.ry; vb = b.ry; break;
      default:      va = a.rx; vb = b.rx;
    }
    return paretoSort.dir * (va - vb);
  });
  const tbl = document.getElementById('tPareto');
  document.getElementById('tbPareto').innerHTML = sorted.map((p,i) => {
    const star = p.n === bestN ? ' ★' : '';
    return `<tr${star?' style="color:#ffee58"':''}>` +
      `<td>${i+1}</td><td>#${p.n}${star}</td>` +
      `<td>${p.rx.toFixed(6)}</td><td>${p.ry.toFixed(6)}</td></tr>`;
  }).join('');
  markSortHeaders(tbl, paretoSort);
}

let paretoTableVisible = false;
function toggleParetoTable(){
  paretoTableVisible = !paretoTableVisible;
  document.getElementById('paretoTablePanel').style.display = paretoTableVisible ? '' : 'none';
  document.getElementById('showParetoTableBtn').textContent = paretoTableVisible ? '▴ Pareto front points' : '▾ Pareto front points';
}

// ═══════════════════════════════════════════════
// HPARAMS TABLE
// ═══════════════════════════════════════════════
function buildHparams(){
  const hp = DATA.hparams;
  document.getElementById('hparamsSection').style.display='';

  // score metadata
  const scores = document.getElementById('hpScores');
  if (hp.meta && Object.keys(hp.meta).length){
    const labels = {trial:'Trial',rank:'Pareto Rank',game_brier:'Game Brier',rank_rps:'Rank RPS'};
    scores.innerHTML = Object.entries(hp.meta)
      .filter(([k])=>k in labels)
      .map(([k,v])=>`<div class="hp-score"><div class="sk">${labels[k]??k}</div><div class="sv">${v}</div></div>`)
      .join('');
  }

  const container = document.getElementById('hpGroups');
  Object.entries(hp.groups).forEach(([grpName, entries]) => {
    const div = document.createElement('div');
    div.className = 'hp-group';
    div.innerHTML = `<h4>${grpName}</h4>` + entries.map(e => `
      <div class="hp-row">
        <span class="hp-key">${e.key}</span>
        <span class="hp-val">${fmt(e.value)}</span>
        ${e.desc ? `<span class="hp-desc">${e.desc}</span>` : ''}
      </div>`).join('');
    container.appendChild(div);
  });
}

// ═══════════════════════════════════════════════
// PLAYERS TABLE
// ═══════════════════════════════════════════════
function buildTournamentPlayers(){
  const meta = document.getElementById('tournMeta');
  const tn = DATA.meta.name + (DATA.meta.section ? ' — ' + DATA.meta.section : '') + (DATA.meta.year ? ' ' + DATA.meta.year : '');
  meta.textContent = `${tn} · ${DATA.meta.total_rounds} rounds · ${DATA.meta.gpr} games/round · Tiebreak: ${DATA.meta.tiebreak}`;
  renderTournamentPlayers();
}

function renderTournamentPlayers(){
  const tbl = document.getElementById('tPlayers');
  markSortHeaders(tbl, playersSort);

  const valFn = (p) => {
    switch(playersSort.col){
      case 'name':  return p.name.toLowerCase();
      case 'fide_id': return p.fide_id ?? 0;
      case 'rating': return p.rating ?? 0;
      case 'rapid':  return p.rapid_rating ?? 0;
      case 'blitz':  return p.blitz_rating ?? 0;
      default: return p.rating ?? 0;
    }
  };
  const sorted = [...DATA.tournament_players].sort((a,b) => {
    const va = valFn(a), vb = valFn(b);
    if (typeof va === 'string') return playersSort.dir * va.localeCompare(vb);
    return playersSort.dir * (va - vb);
  });

  const tb = document.getElementById('tbPlayers');
  tb.innerHTML = '';
  sorted.forEach(p => {
    const playerInfo = P_MAP[p.name];
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><div class="pcell">
        ${playerInfo ? `<span class="dot" style="background:${playerInfo.color}"></span>` : ''}
        ${p.name}
      </div></td>
      <td style="color:var(--paper-3);font-size:.83rem">${p.fide_id??'—'}</td>
      <td style="font-weight:600">${p.rating??'—'}</td>
      <td style="color:var(--paper-2)">${p.rapid_rating??'—'}</td>
      <td style="color:var(--paper-2)">${p.blitz_rating??'—'}</td>`;
    tb.appendChild(tr);
  });
}
</script>
</body>
</html>
"""


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

    data = assemble(args.tournament, t_data, rounds, hp, hp_meta, pareto, aliases)

    template = html_template()
    marker = "/*__INJECT_DATA__*/"
    data_js = f"const DATA = {json.dumps(data, separators=(',', ':'))};"
    html = template.replace(marker, data_js, 1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Written → {args.output}  ({args.output.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
