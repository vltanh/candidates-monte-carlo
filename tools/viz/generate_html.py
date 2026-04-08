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
    "#f5e27a",  # gold
    "#4fc3f7",  # sky blue
    "#81c784",  # green
    "#ff8a65",  # coral
    "#ce93d8",  # purple
    "#80deea",  # cyan
    "#ffb74d",  # amber
    "#ef9a9a",  # rose
    "#a5d6a7",  # light green
    "#90caf9",  # light blue
]

# ── hparam metadata ───────────────────────────────────────────────────────────

HPARAM_GROUPS: dict[str, list[str]] = {
    "Simulation":        ["runs", "map_iters", "map_tolerance"],
    "MAP priors":        ["prior_weight_known", "prior_weight_sim"],
    "Rating model":      ["initial_white_adv", "velocity_time_decay", "lookahead_factor"],
    "Cross-TC blending": ["rapid_form_weight", "blitz_form_weight", "color_bleed"],
    "Draw model":        ["classical_nu", "rapid_nu", "blitz_nu"],
    "Aggression":        [
        "agg_prior_weight", "default_aggression_w",
        "default_aggression_b", "standings_aggression",
    ],
}

HPARAM_DESC: dict[str, str] = {
    "runs":                "Monte Carlo simulations per run",
    "map_iters":           "MAP solver max iterations",
    "map_tolerance":       "MAP solver convergence tolerance",
    "prior_weight_known":  "Prior weight for known-opponent ratings",
    "prior_weight_sim":    "Prior weight for simulated ratings",
    "initial_white_adv":   "White-piece advantage (Elo)",
    "velocity_time_decay": "Rating velocity time-decay factor",
    "lookahead_factor":    "Forward-looking rating horizon",
    "rapid_form_weight":   "Rapid rating blend weight",
    "blitz_form_weight":   "Blitz rating blend weight",
    "color_bleed":         "White↔Black rating cross-pollination",
    "classical_nu":        "Classical draw model parameter ν",
    "rapid_nu":            "Rapid draw model parameter ν",
    "blitz_nu":            "Blitz draw model parameter ν",
    "agg_prior_weight":    "Aggression prior weight",
    "default_aggression_w":"Default White aggression baseline",
    "default_aggression_b":"Default Black aggression baseline",
    "standings_aggression":"Standings-driven aggression factor",
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
            "key":          p["name"],
            "short":        aliases.get(p["name"]) or _fallback_short(p["name"]),
            "color":        PLAYER_COLORS[i % len(PLAYER_COLORS)],
            "fide_id":      p.get("fide_id"),
            "rating":       p.get("rating"),
            "rapid_rating": p.get("rapid_rating"),
            "blitz_rating": p.get("blitz_rating"),
        }
        for i, p in enumerate(raw)
    ]

# ── schedule helpers ──────────────────────────────────────────────────────────

def cumulative_scores(t_data: dict) -> dict[str, list[float]]:
    """Index 0 = before R1, index k = after Rk."""
    id2name = {p["fide_id"]: p["name"] for p in t_data["players"]}
    sched    = t_data["schedule"]
    max_r    = max((g.get("round", 1) for g in sched), default=0)

    scores: dict[str, float] = {n: 0.0 for n in id2name.values()}
    cum:    dict[str, list[float]] = {n: [0.0] for n in id2name.values()}

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
            {"white": id2name[g["white"]], "black": id2name[g["black"]], "result": g.get("result")}
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
    rounds:    list[tuple[int, dict]],
    cum:       dict[str, list[float]],
    sched_idx: dict[int, list[dict]],
) -> list[dict]:
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
            upcoming.append({
                "white":  g["white"],
                "black":  g["black"],
                "probs":  round_probs.get(key, [1/3, 1/3, 1/3]),
                "result": g["result"],
            })

        result.append({
            "label":           "Before R1" if rn == 1 else f"After R{rn - 1}",
            "round_num":       rn,
            "winner_probs":    data.get("winner_probs",    {}),
            "expected_points": data.get("expected_points", {}),
            "rank_matrix":     data.get("rank_matrix",     {}),
            "actual_scores":   actual,
            "upcoming_games":  upcoming,
        })
    return result

# ── all-rounds game predictions ──────────────────────────────────────────────

def build_all_games(
    rounds:    list[tuple[int, dict]],
    sched_idx: dict[int, list[dict]],
) -> list[dict]:
    """For each tournament round: use that round's own JSON if available,
    otherwise fall back to the latest JSON (for future rounds)."""
    round_map      = {rn: d for rn, d in rounds}
    _, latest_data = rounds[-1]
    result = []
    for rn in sorted(sched_idx.keys()):
        src = round_map.get(rn, latest_data)
        rp  = src.get("game_probs", {}).get(str(rn), {})
        result.append({
            "round_num": rn,
            "games": [
                {
                    "white":  g["white"],
                    "black":  g["black"],
                    "probs":  rp.get(f"{g['white']}|{g['black']}", [1/3, 1/3, 1/3]),
                    "result": g["result"],
                }
                for g in sched_idx.get(rn, [])
            ],
        })
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
        all_c  = [t for t in study.trials if t.state == TrialState.COMPLETE]
        pareto = study.best_trials
        p_nums = {t.number for t in pareto}

        non_p = [t for t in all_c if t.number not in p_nums]
        step  = max(1, len(non_p) // max_scatter)

        all_pts = (
            [{"x": t.values[0], "y": t.values[1], "n": t.number, "p": False} for t in non_p[::step]]
            + [{"x": t.values[0], "y": t.values[1], "n": t.number, "p": True} for t in pareto]
        )

        vals   = np.array([t.values for t in pareto])
        mins   = vals.min(axis=0)
        ranges = np.where(mins == 0, 1.0, mins)
        norm   = (vals - mins) / ranges
        best   = pareto[int(np.sqrt((norm**2).sum(axis=1)).argmin())]

        p_sorted = sorted(pareto, key=lambda t: t.values[0])
        return {
            "all_points":   all_pts,
            "pareto_line":  [{"x": t.values[0], "y": t.values[1], "n": t.number} for t in p_sorted],
            "best":         {"x": best.values[0], "y": best.values[1], "n": best.number},
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
            for k in keys if k in hp
        ]
        if entries:
            groups[grp] = entries

    # Add score metadata from comments if available
    score_meta = {}
    for k in ("trial", "rank", "game_brier", "rank_rps"):
        if k in meta:
            score_meta[k] = meta[k]

    return {"groups": groups, "meta": score_meta}

# ── main data assembly ────────────────────────────────────────────────────────

def assemble(
    t_path:  Path,
    t_data:  dict,
    rounds:  list[tuple[int, dict]],
    hp:      dict | None,
    hp_meta: dict[str, str],
    pareto:  dict | None,
    aliases: dict[str, str] | None = None,
) -> dict:
    players   = build_players(t_data, aliases or {})
    cum       = cumulative_scores(t_data)
    sched_idx = schedule_by_round(t_data)
    rds       = build_rounds(rounds, cum, sched_idx)

    year = None
    if m := re.search(r"\d{4}", t_path.stem):
        year = int(m.group())

    total_r = max((g.get("round", 0) for g in t_data["schedule"]), default=14)
    tiebreak_labels = {
        "fide2026": "FIDE 2026", "fide2024": "FIDE 2024", "shared": "Shared title",
    }

    return {
        "meta": {
            "title":        f"{year} FIDE Candidates" if year else "FIDE Candidates",
            "year":         year,
            "gpr":          t_data.get("gpr", 4),
            "tiebreak":     tiebreak_labels.get(t_data.get("tiebreak", ""), t_data.get("tiebreak", "")),
            "total_rounds": total_r,
        },
        "players":   players,
        "rounds":    rds,
        "all_games": build_all_games(rounds, sched_idx),
        "hparams": build_hparams(hp, hp_meta) if hp else None,
        "pareto":  pareto,
        "tournament_players": [
            {
                "name":         p["name"],
                "fide_id":      p.get("fide_id"),
                "rating":       p.get("rating"),
                "rapid_rating": p.get("rapid_rating"),
                "blitz_rating": p.get("blitz_rating"),
            }
            for p in sorted(t_data["players"], key=lambda x: x.get("rating", 0), reverse=True)
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
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0f1a;color:#dde3ef;font-family:'Segoe UI',system-ui,sans-serif;font-size:15px;line-height:1.5}
a{color:#7ec8e3}
.page{max-width:1120px;margin:0 auto;padding:2rem 1.25rem 4rem}

/* header */
.hdr{text-align:center;margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:1px solid #1e2438}
.hdr h1{font-size:1.9rem;font-weight:700;color:#f5e27a;letter-spacing:-.5px}
.hdr .sub{color:#8a93b2;margin-top:.3rem;font-size:.9rem}
.badge{display:inline-block;background:#1f2640;border:1px solid #3a4260;color:#a0aec0;
  padding:.15rem .65rem;border-radius:999px;font-size:.78rem;margin:.4rem .2rem 0}

/* section */
section{margin-bottom:2.5rem}
section h2{font-size:1rem;font-weight:600;color:#c8d0e7;text-transform:uppercase;
  letter-spacing:.06em;margin-bottom:.9rem;padding-bottom:.35rem;border-bottom:1px solid #1e2438}
.card{background:#131728;border:1px solid #1e2438;border-radius:10px;padding:1.25rem}
.note{font-size:.76rem;color:#4a5278;margin-top:.65rem;font-style:italic}

/* round tabs */
.tabs-wrap{padding-bottom:.5rem;margin-bottom:2rem}
.tabs{display:flex;gap:.4rem;flex-wrap:wrap}
.tab{padding:.35rem .8rem;border-radius:6px;border:1px solid #2a3050;background:#131728;
  color:#8a93b2;font-size:.82rem;cursor:pointer;transition:all .15s;user-select:none}
.tab:hover:not(:disabled){background:#1e2438;color:#c8d0e7}
.tab.active{background:#1e2440;border-color:#4a6eff;color:#f5e27a;font-weight:600}
.tab:disabled{opacity:.32;cursor:not-allowed;border-color:#1a1f35;color:#3a4260}
.tab:disabled::after{content:'🔒';font-size:.65rem;margin-left:.3rem;opacity:.7}

/* charts */
.chart-wrap{position:relative}.chart-wrap.tall{height:380px}.chart-wrap.med{height:270px}

/* two-column grid */
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:680px){.two-col{grid-template-columns:1fr}}

/* standings table */
table{width:100%;border-collapse:collapse;font-size:.87rem}
thead th{text-align:left;color:#6b7494;font-weight:600;font-size:.74rem;text-transform:uppercase;
  letter-spacing:.05em;padding:.4rem .5rem;border-bottom:1px solid #1e2438}
tbody tr{border-bottom:1px solid #191d30}
tbody tr:last-child{border-bottom:none}
tbody td{padding:.5rem .5rem;vertical-align:middle}
tbody tr:hover{background:#191e35}
.rank-num{color:#6b7494;font-size:.8rem;min-width:1.4rem}
.rank-num.gold{color:#f5e27a;font-weight:700}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;flex-shrink:0}
.pcell{display:flex;align-items:center}
.score{font-weight:700;font-size:1rem;color:#e8eaf6}
.winpct{color:#a0aec0;font-size:.82rem}
.winpct.hi{color:#f5e27a;font-weight:600}
.bar-mini{height:5px;border-radius:3px;background:#1e2438;margin-top:3px;overflow:hidden}
.bar-fill{height:100%;border-radius:3px}

/* player toggles */
.player-toggles{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.9rem}
.ptoggle{display:inline-flex;align-items:center;gap:.35rem;padding:.22rem .65rem;
  border-radius:999px;border:1.5px solid;cursor:pointer;font-size:.8rem;
  background:transparent;transition:opacity .15s;user-select:none}
.ptoggle.off{opacity:.28;text-decoration:line-through}

/* game cards */
.games-grid{display:grid;gap:.75rem}
.gcard{background:#131728;border:1px solid #1e2438;border-radius:8px;padding:.9rem 1rem}
.gcard .round-label{font-size:.75rem;color:#6b7494;text-transform:uppercase;letter-spacing:.04em;margin-bottom:.35rem}
.gcard .players{font-weight:600;font-size:.93rem;display:flex;align-items:center;gap:.35rem;margin-bottom:.7rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gcard .players .sep{color:#6b7494;font-weight:400;font-size:.78rem}
.piece{font-size:.82rem;opacity:.85;flex-shrink:0}
.prob-bars{height:28px;border-radius:4px;overflow:hidden;display:flex;gap:2px}
.pb{display:flex;align-items:center;justify-content:center;font-size:.76rem;font-weight:700;gap:.2rem}
.pb.white-win{color:#0d0f1a}.pb.draw{color:#c8d0e7;background:#4a5278!important}.pb.black-win{color:#e8eaf6}
.pb .ps{font-size:.68rem;opacity:.8}
.prob-foot{display:flex;justify-content:space-between;font-size:.72rem;color:#4a5278;margin-top:3px}
.result-badge{display:inline-block;margin-top:.5rem;padding:.12rem .5rem;border-radius:4px;
  font-size:.75rem;font-weight:700;letter-spacing:.03em}
.result-badge.white-win{background:#4fc3f720;color:#4fc3f7;border:1px solid #4fc3f740}
.result-badge.draw{background:#8a93b220;color:#c8d0e7;border:1px solid #8a93b240}
.result-badge.black-win{background:#ce93d820;color:#ce93d8;border:1px solid #ce93d840}

/* show-more / all-games panel */
.show-more-btn{display:block;margin:.75rem auto 0;padding:.3rem 1.1rem;border-radius:6px;
  border:1px solid #2a3050;background:#131728;color:#8a93b2;font-size:.82rem;
  cursor:pointer;transition:all .15s}
.show-more-btn:hover{background:#1e2438;color:#c8d0e7}
.all-games-panel{margin-top:1rem}
.games-section-lbl{font-size:.8rem;font-weight:600;color:#6b7494;text-transform:uppercase;
  letter-spacing:.06em;margin:1.25rem 0 .5rem;display:flex;align-items:center;gap:.6rem}
.games-section-lbl::after{content:'';flex:1;height:1px;background:#1e2438}
.round-group{margin-bottom:1rem}
.round-group-lbl{font-size:.72rem;color:#4a5278;text-transform:uppercase;letter-spacing:.05em;
  margin-bottom:.4rem;padding-bottom:.2rem;border-bottom:1px solid #191d30}

/* rank heatmap */
.hm-table{width:100%;border-collapse:collapse;font-size:.81rem}
.hm-table th{text-align:center;color:#6b7494;font-size:.73rem;font-weight:600;
  padding:.3rem .4rem;border-bottom:1px solid #1e2438}
.hm-table th:first-child{text-align:left}
.hm-table td{text-align:center;padding:.28rem .35rem;border-bottom:1px solid #191d30}
.hm-table td:first-child{text-align:left}
.hm-cell{display:inline-block;width:100%;padding:.18rem .25rem;border-radius:4px;font-weight:600;font-size:.78rem}

/* pareto section */
.pareto-meta{display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:1rem}
.pmeta-item{background:#1a1f35;border:1px solid #2a3050;border-radius:6px;padding:.4rem .8rem}
.pmeta-item .pk{font-size:.72rem;color:#6b7494;text-transform:uppercase;letter-spacing:.04em}
.pmeta-item .pv{font-size:.95rem;font-weight:700;color:#f5e27a}

/* hparams */
.hp-groups{display:grid;grid-template-columns:1fr;gap:.75rem}
.hp-group{background:#131728;border:1px solid #1e2438;border-radius:8px;padding:.9rem 1rem}
.hp-group h4{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:#6b7494;
  font-weight:600;margin-bottom:.6rem}
.hp-row{display:flex;align-items:baseline;gap:.5rem;padding:.2rem 0;border-bottom:1px solid #191d30}
.hp-row:last-child{border-bottom:none}
.hp-key{font-size:.8rem;color:#a0aec0;font-family:monospace;min-width:11rem}
.hp-val{font-size:.83rem;font-weight:600;color:#e8eaf6;margin-left:auto;white-space:nowrap}
.hp-desc{font-size:.72rem;color:#4a5278;display:block;margin-top:.1rem}
.hp-score-row{display:flex;gap:.75rem;flex-wrap:wrap;margin-bottom:1rem}
.hp-score{background:#1a1f35;border:1px solid #2a3050;border-radius:6px;padding:.3rem .7rem}
.hp-score .sk{font-size:.7rem;color:#6b7494;text-transform:uppercase;letter-spacing:.04em}
.hp-score .sv{font-size:.9rem;font-weight:700;color:#80deea}

/* players table */
details{margin-bottom:1.5rem}
summary{cursor:pointer;padding:.5rem .75rem;background:#131728;border:1px solid #1e2438;
  border-radius:8px;color:#c8d0e7;font-size:.9rem;font-weight:600;
  list-style:none;user-select:none;display:flex;align-items:center;gap:.5rem}
summary::before{content:"▶";font-size:.7rem;transition:transform .2s;color:#6b7494}
details[open] summary::before{transform:rotate(90deg)}
.details-body{padding:1rem 0 0}
</style>
</head>
<body>
<div class="page">

<!-- header -->
<div class="hdr">
  <h1 id="hdr-title">FIDE Candidates Tournament</h1>
  <div class="sub" id="hdr-sub">Monte Carlo win probability tracker · 1,000,000 simulations per round</div>
  <div id="hdr-badges"></div>
  <div style="margin-top:.75rem">
    <a href="https://github.com/vltanh/candidates-monte-carlo" target="_blank" rel="noopener"
       style="display:inline-flex;align-items:center;gap:.4rem;color:#8a93b2;font-size:.83rem;
              text-decoration:none;border:1px solid #2a3050;border-radius:6px;
              padding:.25rem .7rem;background:#131728;transition:all .15s"
       onmouseover="this.style.color='#c8d0e7';this.style.borderColor='#4a5278'"
       onmouseout="this.style.color='#8a93b2';this.style.borderColor='#2a3050'">
      <svg height="14" width="14" viewBox="0 0 16 16" fill="currentColor">
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
  </div>
</div>

<!-- round tabs -->
<div class="tabs-wrap"><div class="tabs" id="tabs"></div></div>

<!-- timeline charts -->
<section>
  <h2>Win Probability Timeline</h2>
  <div class="card">
    <div class="player-toggles" id="playerToggles"></div>
    <div class="chart-wrap tall"><canvas id="cTimeline"></canvas></div>
    <p class="note">Click a tab above to see predictions entering that round. Dashed line marks the selected round. Click a player chip to show/hide them.</p>
  </div>
</section>

<!-- round-specific panel -->
<section id="roundPanel">
  <h2 id="roundTitle">Standings &amp; Win Probability</h2>
  <div class="two-col">
    <div class="card"><table id="tStandings"><thead><tr>
      <th>#</th><th>Player</th><th>Elo</th><th>Score</th><th>Win %</th>
    </tr></thead><tbody id="tbStandings"></tbody></table></div>
    <div class="card"><div class="chart-wrap med"><canvas id="cWinPct"></canvas></div></div>
  </div>
</section>

<section>
  <h2 id="gamesTitle">Round Games</h2>
  <div class="games-grid" id="gamesGrid"></div>
  <div style="display:flex;gap:.5rem;justify-content:center;margin-top:.75rem">
    <button class="show-more-btn" id="showPastBtn" onclick="toggleSection('past')">▾ Past rounds</button>
    <button class="show-more-btn" id="showFutureBtn" onclick="toggleSection('future')">▾ Future rounds</button>
  </div>
  <div class="all-games-panel" id="pastGamesPanel" style="display:none"></div>
  <div class="all-games-panel" id="futureGamesPanel" style="display:none"></div>
</section>

<section>
  <h2>Rank Distribution</h2>
  <div class="card">
    <table class="hm-table" id="hmTable"></table>
    <p class="note">Probability of finishing in each rank position. Hover for exact value.</p>
  </div>
</section>

<!-- expected score timeline -->
<section>
  <h2>Expected Final Score Timeline</h2>
  <div class="card">
    <div class="chart-wrap tall"><canvas id="cExpScore"></canvas></div>
    <p class="note">Expected total points (out of <span id="totalRounds">14</span>) via simulation at each checkpoint.</p>
  </div>
</section>

<!-- model section -->
<details id="modelSection" style="display:none">
  <summary>Model Details</summary>
  <div class="details-body">

    <section id="paretoSection" style="display:none">
      <h2>Pareto Front — Hyperparameter Tuning</h2>
      <div id="paretoMeta" class="pareto-meta"></div>
      <div class="card">
        <div class="chart-wrap tall"><canvas id="cPareto"></canvas></div>
        <p class="note">Multi-objective optimisation over 2022 + 2024 Candidates data.
          ★ = best trial (utopia distance). Coloured points = Pareto-optimal.</p>
      </div>
    </section>

    <section id="hparamsSection" style="display:none">
      <h2>Best Hyperparameters</h2>
      <div id="hpScores" class="hp-score-row"></div>
      <div class="hp-groups" id="hpGroups"></div>
    </section>

  </div>
</details>

<!-- tournament info -->
<details>
  <summary>Tournament Information</summary>
  <div class="details-body">
    <div class="card">
      <div id="tournMeta" style="margin-bottom:.9rem;font-size:.85rem;color:#8a93b2"></div>
      <table id="tPlayers">
        <thead><tr><th>Player</th><th>FIDE ID</th><th>Classical</th><th>Rapid</th><th>Blitz</th></tr></thead>
        <tbody id="tbPlayers"></tbody>
      </table>
    </div>
  </div>
</details>

</div><!-- /page -->
<script>
// ═══════════════════════════════════════════════
// DATA (injected by generate_html.py)
// ═══════════════════════════════════════════════
/*__INJECT_DATA__*/

// ═══════════════════════════════════════════════
// GLOBALS
// ═══════════════════════════════════════════════
let currentIdx = DATA.rounds.length - 1;
let winPctChart, timelineChart, expScoreChart, paretoChart;
let hiddenPlayers = new Set();
let sortedPlayers = [];   // dataset order used by timeline + expScore charts
let pastVisible = false;
let futureVisible = false;

// quick lookup
const P_MAP = Object.fromEntries(DATA.players.map(p => [p.key, p]));

// ═══════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════
function pct(v, d=1){ return (v*100).toFixed(d)+'%'; }
function fmt(v, d=3){ return typeof v==='number'?v.toFixed(d):v; }

function hexAlpha(hex, a){ return hex+Math.round(a*255).toString(16).padStart(2,'0'); }

function heatBg(v, playerKey){
  const hex = (P_MAP[playerKey]?.color ?? '#888').replace('#','');
  const r=parseInt(hex.slice(0,2),16), g=parseInt(hex.slice(2,4),16), b=parseInt(hex.slice(4,6),16);
  const alpha = Math.min(1, v*2.5+0.05);
  return `rgba(${r},${g},${b},${alpha})`;
}

function trialColor(n, maxN){
  const t = n / maxN;
  return `rgba(${Math.round(26+t*53)},${Math.round(43+t*152)},${Math.round(94+t*153)},0.35)`;
}

function paretoColor(idx, total){
  const t = total<=1 ? 0 : idx/(total-1);
  return `rgb(${Math.round(67+t*178)},${Math.round(97+t*129)},${Math.round(238+t*(122-238))})`;
}

// ═══════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════
Chart.defaults.color = '#8a93b2';
Chart.defaults.borderColor = '#1e2438';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";

document.addEventListener('DOMContentLoaded', () => {
  // Header
  document.getElementById('pageTitle').textContent = DATA.meta.title + ' — Monte Carlo';
  document.getElementById('hdr-title').textContent = DATA.meta.title;
  const badges = document.getElementById('hdr-badges');
  const latest = DATA.rounds[DATA.rounds.length-1];
  const latestNum = latest.round_num;
  const totalR = DATA.meta.total_rounds;
  badges.innerHTML = `
    <span class="badge">Updated through Round ${latestNum-1} · Round ${latestNum} upcoming</span>
    <span class="badge">${totalR} rounds total · ${DATA.meta.gpr} games/round</span>
    <span class="badge">Tiebreak: ${DATA.meta.tiebreak}</span>`;
  document.getElementById('totalRounds').textContent = totalR;

  buildTabs();
  initTimeline();
  initExpScore();
  initWinPct();
  buildPlayerToggles();
  buildTournamentPlayers();

  if (DATA.pareto) buildPareto();
  if (DATA.hparams) buildHparams();
  if (DATA.pareto || DATA.hparams) document.getElementById('modelSection').style.display='';

  setRound(currentIdx, false);
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
  updateGames(round);
  updateHeatmap(round);

  document.getElementById('roundTitle').textContent =
    `Standings — ${round.label}`;
  document.getElementById('gamesTitle').textContent =
    `Round ${round.round_num} — Game Predictions`;
}

// ═══════════════════════════════════════════════
// STANDINGS
// ═══════════════════════════════════════════════
function updateStandings(round){
  const sorted = [...DATA.players].sort((a,b) => {
    const sa = round.actual_scores[a.key]??0, sb = round.actual_scores[b.key]??0;
    if (sb!==sa) return sb-sa;
    return (round.winner_probs[b.key]??0)-(round.winner_probs[a.key]??0);
  });

  // table
  const tb = document.getElementById('tbStandings');
  tb.innerHTML = '';
  sorted.forEach((p,i) => {
    const score = round.actual_scores[p.key]??0;
    const wp    = round.winner_probs[p.key]??0;
    const hidden = hiddenPlayers.has(p.key);
    const tr = document.createElement('tr');
    tr.style.opacity = hidden ? '0.35' : '';
    tr.innerHTML = `
      <td class="rank-num ${i===0?'gold':''}">${i+1}</td>
      <td><div class="pcell"><span class="dot" style="background:${p.color}"></span>${p.short}</div></td>
      <td style="color:#8a93b2;font-size:.83rem">${p.rating??'—'}</td>
      <td class="score">${score}</td>
      <td>
        <span class="winpct ${wp>.15?'hi':''}">${pct(wp)}</span>
        <div class="bar-mini"><div class="bar-fill" style="width:${Math.min(100,wp*100)}%;background:${p.color}"></div></div>
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
  const wShadow = g.result==='1-0'   ? 'box-shadow:inset 0 0 0 2.5px #f5e27a;' : '';
  const dShadow = g.result==='1/2-1/2'? 'box-shadow:inset 0 0 0 2.5px #f5e27a;' : '';
  const bShadow = g.result==='0-1'   ? 'box-shadow:inset 0 0 0 2.5px #f5e27a;' : '';

  let resultBadge = '';
  if (g.result==='1-0')
    resultBadge = `<span class="result-badge white-win">✓ ${wn} won</span>`;
  else if (g.result==='0-1')
    resultBadge = `<span class="result-badge black-win">✓ ${bn} won</span>`;
  else if (g.result==='1/2-1/2')
    resultBadge = `<span class="result-badge draw">½–½ Draw</span>`;

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
      <div class="pb white-win" style="flex:${ww};background:${hexAlpha(wc,0.8)};${wShadow}">${wp}%</div>
      <div class="pb draw" style="flex:${dd};${dShadow}">${dp}%</div>
      <div class="pb black-win" style="flex:${bw};background:${hexAlpha(bc,0.65)};${bShadow}">${bp}%</div>
    </div>
    <div class="prob-foot">
      <span>${wn} <span style="color:#6b7494">(W)</span></span>
      <span>Draw</span>
      <span>${bn} <span style="color:#6b7494">(B)</span></span>
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
    grid.innerHTML = '<p style="color:#6b7494;font-size:.88rem">No game data for this round.</p>';
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
  // Close the other panel first
  const otherVisible = isPast ? futureVisible : pastVisible;
  if (otherVisible){
    const otherId  = isPast ? 'futureGamesPanel' : 'pastGamesPanel';
    const otherBtn = isPast ? 'showFutureBtn'    : 'showPastBtn';
    document.getElementById(otherId).style.display = 'none';
    document.getElementById(otherBtn).textContent  = isPast ? '▾ Future rounds' : '▾ Past rounds';
    if (isPast) futureVisible = false; else pastVisible = false;
  }
  if (isPast) pastVisible = !pastVisible; else futureVisible = !futureVisible;
  const visible = isPast ? pastVisible : futureVisible;
  const panelId = isPast ? 'pastGamesPanel' : 'futureGamesPanel';
  const btnId   = isPast ? 'showPastBtn'    : 'showFutureBtn';
  const panel   = document.getElementById(panelId);
  const btn     = document.getElementById(btnId);
  if (visible){
    buildPanel(which);
    panel.style.display = '';
    btn.textContent = isPast ? '▴ Hide past' : '▴ Hide future';
  } else {
    panel.style.display = 'none';
    btn.textContent = isPast ? '▾ Past rounds' : '▾ Future rounds';
  }
}

function buildPanel(which){
  const isPast  = which === 'past';
  const panel   = document.getElementById(isPast ? 'pastGamesPanel' : 'futureGamesPanel');
  panel.innerHTML = '';
  const curRound = DATA.rounds[currentIdx].round_num;
  const rounds = isPast
    ? DATA.all_games.filter(ag => ag.round_num < curRound).slice().reverse()
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
  thead.innerHTML = '<tr><th>Player</th>' +
    [...Array(n)].map((_,i) => `<th>${i+1}${['st','nd','rd'][i]??'th'}</th>`).join('') + '</tr>';
  tbl.appendChild(thead);

  // sort by P(rank 1) desc, exclude hidden players
  const sorted = [...DATA.players]
    .filter(p => !hiddenPlayers.has(p.key))
    .sort((a,b) =>
      ((round.rank_matrix[b.key]??[0])[0]??0)-((round.rank_matrix[a.key]??[0])[0]??0));

  const tbody = document.createElement('tbody');
  sorted.forEach(p => {
    const rm = round.rank_matrix[p.key] ?? Array(n).fill(0);
    const tr = document.createElement('tr');
    const cells = rm.map((v,ri) => {
      const bg = heatBg(v, p.key);
      const textColor = v > 0.35 ? '#0d0f1a' : '#dde3ef';
      return `<td><span class="hm-cell" style="background:${bg};color:${textColor}" title="${pct(v,1)}">${pct(v,0)}</span></td>`;
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
        x:{grid:{color:'#1a1f35'},ticks:{font:{size:11}}},
        y:{grid:{color:'#1a1f35'},ticks:{callback:v=>v+'%',font:{size:11}},
           title:{display:true,text:'Win Probability (%)',color:'#6b7494'}}
      },
      plugins:{
        legend:{position:'bottom',labels:{boxWidth:12,padding:13,font:{size:12}}},
        tooltip:{itemSort:(a,b)=>b.parsed.y-a.parsed.y,callbacks:{label:ctx=>` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`}},
        annotation:{annotations:{vline:{type:'line',xMin:currentIdx,xMax:currentIdx,
          borderColor:'#f5e27a80',borderWidth:2,borderDash:[6,4]}}}
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
        x:{grid:{color:'#1a1f35'},ticks:{font:{size:11}}},
        y:{grid:{color:'#1a1f35'},
           ticks:{stepSize:1,font:{size:11}},
           title:{display:true,text:`Expected Final Score (out of ${DATA.meta.total_rounds})`,color:'#6b7494'}}
      },
      plugins:{
        legend:{position:'bottom',labels:{boxWidth:12,padding:13,font:{size:12}}},
        tooltip:{itemSort:(a,b)=>b.parsed.y-a.parsed.y,callbacks:{label:ctx=>` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)} pts`}},
        annotation:{annotations:{vline:{type:'line',xMin:currentIdx,xMax:currentIdx,
          borderColor:'#f5e27a80',borderWidth:2,borderDash:[6,4]}}}
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
        x:{grid:{color:'#1a1f35'},ticks:{callback:v=>v+'%',font:{size:11}},max:100},
        y:{grid:{display:false},ticks:{font:{size:12}}}
      }
    }
  });
}

// ═══════════════════════════════════════════════
// PARETO CHART
// ═══════════════════════════════════════════════
function buildPareto(){
  const pd = DATA.pareto;
  document.getElementById('paretoSection').style.display='';

  // meta badges
  const meta = document.getElementById('paretoMeta');
  meta.innerHTML = `
    <div class="pmeta-item"><div class="pk">Total Trials</div><div class="pv">${pd.total_trials.toLocaleString()}</div></div>
    <div class="pmeta-item"><div class="pk">Pareto-Optimal</div><div class="pv">${pd.pareto_count}</div></div>
    <div class="pmeta-item"><div class="pk">Best Trial</div><div class="pv">#${pd.best.n}</div></div>
    <div class="pmeta-item"><div class="pk">Game Brier</div><div class="pv">${pd.best.x.toFixed(4)}</div></div>
    <div class="pmeta-item"><div class="pk">Rank RPS</div><div class="pv">${pd.best.y.toFixed(4)}</div></div>`;

  const maxN = Math.max(...pd.all_points.map(p=>p.n));
  const nonPareto = pd.all_points.filter(p=>!p.p);
  const paretoOnly = pd.all_points.filter(p=>p.p);

  // step line dataset
  const stepLine = pd.pareto_line.map(p => ({x:p.x, y:p.y}));
  // add "step after" using manual extension
  const stepLineExt = [];
  for (let i=0; i<pd.pareto_line.length; i++){
    stepLineExt.push({x:pd.pareto_line[i].x, y:pd.pareto_line[i].y});
    if (i<pd.pareto_line.length-1)
      stepLineExt.push({x:pd.pareto_line[i+1].x, y:pd.pareto_line[i].y});
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
          borderColor:'#4fc3f760',
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
          backgroundColor: '#4fc3f7aa',
          borderColor: '#4fc3f7',
          borderWidth:1,
          pointRadius:6, pointHoverRadius:8,
          order:1,
        },
        {
          label:`★ Best (Trial ${pd.best.n})`,
          data:[{x:pd.best.x,y:pd.best.y}],
          backgroundColor:'#ffffff',
          borderColor:'#f5e27a',
          borderWidth:3,
          pointStyle:'star',
          pointRadius:20, pointHoverRadius:22,
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
            if (ctx.datasetIndex===3) return ` ★ Best: Trial ${pd.best.n} — Brier=${ctx.parsed.x.toFixed(4)}, RPS=${ctx.parsed.y.toFixed(4)}`;
            if (ctx.datasetIndex===2) {
              const pt = paretoOnly[ctx.dataIndex];
              return ` Pareto Trial ${pt?.n}: Brier=${ctx.parsed.x.toFixed(4)}, RPS=${ctx.parsed.y.toFixed(4)}`;
            }
            return ` Trial: Brier=${ctx.parsed.x.toFixed(4)}, RPS=${ctx.parsed.y.toFixed(4)}`;
          }
        }}
      },
      scales:{
        x:{grid:{color:'#1a1f35'},title:{display:true,text:'Weighted Game Brier',color:'#6b7494'},ticks:{font:{size:11}}},
        y:{grid:{color:'#1a1f35'},title:{display:true,text:'Rank RPS',color:'#6b7494'},ticks:{font:{size:11}}}
      }
    }
  });
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
  meta.textContent = `${DATA.meta.title} · ${DATA.meta.total_rounds} rounds · ${DATA.meta.gpr} games/round · Tiebreak: ${DATA.meta.tiebreak}`;

  const tb = document.getElementById('tbPlayers');
  DATA.tournament_players.forEach(p => {
    const playerInfo = P_MAP[p.name];
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><div class="pcell">
        ${playerInfo ? `<span class="dot" style="background:${playerInfo.color}"></span>` : ''}
        ${p.name}
      </div></td>
      <td style="color:#6b7494;font-size:.83rem">${p.fide_id??'—'}</td>
      <td style="font-weight:600">${p.rating??'—'}</td>
      <td style="color:#a0aec0">${p.rapid_rating??'—'}</td>
      <td style="color:#a0aec0">${p.blitz_rating??'—'}</td>`;
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
    ap.add_argument("--tournament", "-t", required=True, type=Path,
                    help="Tournament JSONC file (e.g. data/candidates2026.jsonc)")
    ap.add_argument("--rounds",     "-r", required=True, type=Path,
                    help="Directory of roundN.json files")
    ap.add_argument("--hparams",    "-p", default=None, type=Path,
                    help="Hyperparameters JSONC file (optional)")
    ap.add_argument("--db",         "-d", default=None, type=Path,
                    help="Optuna SQLite database for Pareto front (optional)")
    ap.add_argument("--study",      "-s", default="chess_montecarlo",
                    help="Optuna study name (default: chess_montecarlo)")
    ap.add_argument("--output",     "-o", required=True, type=Path,
                    help="Output HTML file path")
    ap.add_argument("--players-file", default="data/players.jsonc", type=Path,
                    help="Player name/alias mapping (default: data/players.jsonc)")

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
                print(f"  {pareto['total_trials']} trials, {pareto['pareto_count']} Pareto-optimal")

    aliases = load_aliases(args.players_file)
    if aliases:
        print(f"Loaded {len(aliases)} player aliases from: {args.players_file}")

    data = assemble(args.tournament, t_data, rounds, hp, hp_meta, pareto, aliases)

    template = html_template()
    marker   = "/*__INJECT_DATA__*/"
    data_js  = f"const DATA = {json.dumps(data, separators=(',', ':'))};"
    html     = template.replace(marker, data_js, 1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Written → {args.output}  ({args.output.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
