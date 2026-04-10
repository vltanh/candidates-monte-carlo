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
    "#18ffff",  # cyan neon
    "#ff5252",  # signal red
    "#c6ff00",  # acid lime
    "#ff6e40",  # deep orange
    "#ea80fc",  # bright fuchsia
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

        vals   = np.array([t.values for t in pareto])
        mins   = vals.min(axis=0)
        ranges = np.where(mins == 0, 1.0, mins)
        norm   = (vals - mins) / ranges
        best   = pareto[int(np.sqrt((norm**2).sum(axis=1)).argmin())]

        # Normalize all points by Pareto-front minimum (1.0 = optimal)
        x_min, y_min = float(mins[0]), float(mins[1])

        all_pts = (
            [{"x": t.values[0]/x_min, "y": t.values[1]/y_min,
              "rx": t.values[0], "ry": t.values[1], "n": t.number, "p": False}
             for t in non_p[::step]]
            + [{"x": t.values[0]/x_min, "y": t.values[1]/y_min,
                "rx": t.values[0], "ry": t.values[1], "n": t.number, "p": True}
               for t in pareto]
        )

        p_sorted = sorted(pareto, key=lambda t: t.values[0])
        return {
            "all_points":   all_pts,
            "pareto_line":  [{"x": t.values[0]/x_min, "y": t.values[1]/y_min, "n": t.number,
                              "rx": t.values[0], "ry": t.values[1]} for t in p_sorted],
            "best":         {"x": best.values[0]/x_min, "y": best.values[1]/y_min, "n": best.number,
                             "rx": best.values[0], "ry": best.values[1]},
            "norm_min":     {"x": x_min, "y": y_min},
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
  max-width:12ch;
}
.hdr h1 em{
  font-style:italic;
  font-variation-settings:"opsz" 144,"SOFT" 100;
  font-weight:300;
  color:var(--azure);
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
  background:transparent;
  border:1px solid var(--rule-2);
  padding:.4rem .8rem;
  border-radius:0;
}
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
  transition:all .2s;
}
.gh-link:hover{color:var(--paper);background:var(--azure-3);border-color:var(--azure-3)}

/* dot-leader hairline beneath masthead */
.hdr::after{
  content:'';display:block;margin-top:1.5rem;height:1px;
  background:var(--rule-2);
}

/* ═══════════════ SECTIONS ═══════════════ */
section{margin-bottom:3.25rem}

.card{
  background:var(--ink-2);
  border:1px solid var(--rule);
  padding:1.5rem 1.6rem;
  position:relative;
}
.card::before,.card::after{
  content:'';position:absolute;width:14px;height:14px;pointer-events:none;
}
.card::before{top:-1px;left:-1px;border-top:1px solid var(--azure-3);border-left:1px solid var(--azure-3)}
.card::after{bottom:-1px;right:-1px;border-bottom:1px solid var(--azure-3);border-right:1px solid var(--azure-3)}

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
  transition:color .18s;
}
.tab:hover:not(:disabled){color:var(--paper)}
.tab.active{color:var(--azure)}
.tab.active::after{
  content:'';position:absolute;left:50%;transform:translateX(-50%);
  bottom:-.95rem;width:28px;height:2px;background:var(--azure);
}
.tab:disabled{color:var(--paper-4);cursor:not-allowed}
.tab:disabled::after{content:'';display:none}

/* ═══════════════ CHARTS ═══════════════ */
.chart-wrap{position:relative}
.chart-wrap.tall{height:400px}
.chart-wrap.med{height:290px}

.two-col{display:grid;grid-template-columns:1.05fr .95fr;gap:1.1rem}
@media(max-width:780px){.two-col{grid-template-columns:1fr}}

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
tbody tr{border-bottom:1px solid var(--rule);transition:background .15s}
tbody tr:last-child{border-bottom:none}
tbody td{padding:.75rem .55rem;vertical-align:middle}
tbody tr:hover{background:rgba(106,166,255,.045)}
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
.bar-inline{flex:1;height:14px;background:var(--rule);overflow:hidden;min-width:80px}
.bar-inline .bar-fill{height:100%;transition:width .3s}
.bar-fill{height:100%}

/* ═══════════════ PLAYER TOGGLES ═══════════════ */
.player-toggles{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1.25rem}
.ptoggle{
  display:inline-flex;align-items:center;gap:.45rem;
  padding:.32rem .75rem;
  border:1px solid;border-radius:0;
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
  transition:border-color .18s,background .18s;
}
.gcard:hover{border-color:var(--rule-2);background:var(--ink-3)}
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
  height:32px;display:flex;gap:1px;
  border:1px solid var(--rule);
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
  padding:.25rem .7rem;
  font-family:'JetBrains Mono',monospace;
  font-size:.64rem;font-weight:700;
  letter-spacing:.12em;text-transform:uppercase;
  border:1px solid #ffee58;
  color:#ffee58;
  background:rgba(255,238,88,.10);
}
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
  cursor:pointer;transition:all .18s;
}
.show-more-btn:hover{color:var(--azure);border-color:var(--azure);background:rgba(106,166,255,.04)}
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
}

/* ═══════════════ PARETO ═══════════════ */
.pareto-meta{display:flex;gap:.8rem;flex-wrap:wrap;margin-bottom:1.3rem}
.pmeta-item{
  background:transparent;
  border:1px solid var(--rule-2);
  padding:.55rem 1rem;
  position:relative;
}
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
}
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
}
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
  transition:color .15s;
}
summary:hover{color:var(--azure)}
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
.details-body{padding:1.1rem 0 0}
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

/* selection */
::selection{background:rgba(106,166,255,.35);color:var(--paper)}

/* scrollbar */
html{scrollbar-color:var(--rule-2) var(--ink)}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:var(--ink)}
::-webkit-scrollbar-thumb{background:var(--rule-2);border:2px solid var(--ink)}
::-webkit-scrollbar-thumb:hover{background:var(--azure-3)}

/* ═══════════════ APPENDIX DIVIDER ═══════════════ */
.appendix-divider{
  margin:3rem 0 1.5rem;
  display:flex;align-items:center;gap:1rem;
}
.appendix-divider::before,.appendix-divider::after{
  content:'';flex:1;height:1px;background:var(--rule);
}
.appendix-label{
  font-family:'JetBrains Mono',monospace;
  font-size:.7rem;letter-spacing:.25em;text-transform:uppercase;
  color:var(--paper-3);white-space:nowrap;
}

/* ═══════════════ BACK TO TOP ═══════════════ */
.back-to-top{
  display:block;margin:2.5rem auto 1rem;
  padding:.5rem 1.5rem;
  font-family:'JetBrains Mono',monospace;
  font-size:.72rem;letter-spacing:.15em;text-transform:uppercase;
  color:var(--paper-3);background:transparent;
  border:1px solid var(--rule);cursor:pointer;
  transition:color .2s,border-color .2s;
}
.back-to-top:hover{color:var(--azure);border-color:var(--azure-3)}
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
      <th data-sort="rank">#</th><th data-sort="player">Player</th><th data-sort="elo">Elo</th><th data-sort="score">Score</th><th data-sort="winpct">Win %</th>
    </tr></thead><tbody id="tbStandings"></tbody></table></div>
    <div style="display:none"><canvas id="cWinPct"></canvas></div>
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

<button class="back-to-top" id="backToTop" onclick="window.scrollTo({top:0,behavior:'smooth'})">↑ Top</button>

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

let standingsSort = {col:'score', dir:-1};
let heatmapSort   = {col:0, dir:-1};     // 0 = first rank column
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
  // Header / masthead
  document.getElementById('pageTitle').textContent = DATA.meta.title + ' — Monte Carlo';

  // Split "2026 FIDE Candidates" into "FIDE Candidates" + italic year
  const titleEl = document.getElementById('hdr-title');
  const m = DATA.meta.title.match(/^(\d{4})\s+(.*)$/);
  titleEl.innerHTML = m
    ? `${m[2]} <em>${m[1]}</em>`
    : DATA.meta.title;

  // Volume line: roman numeral year
  const volEl = document.getElementById('hdr-vol');
  if (volEl) volEl.textContent = `VOL. ${toRoman(DATA.meta.year)}`;

  const badges = document.getElementById('hdr-badges');
  const latest = DATA.rounds[DATA.rounds.length-1];
  const latestNum = latest.round_num;
  const totalR = DATA.meta.total_rounds;
  badges.innerHTML = `
    <span class="badge live">Round ${latestNum} · Live</span>
    <span class="badge">${totalR} Rounds · ${DATA.meta.gpr}/Round</span>
    <span class="badge">Tiebreak · ${DATA.meta.tiebreak}</span>`;
  document.getElementById('totalRounds').textContent = totalR;

  buildTabs();
  initTimeline();
  initExpScore();
  initWinPct();
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
    return standingsSort.dir * (va - vb);
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
      <td style="color:var(--paper-3);font-size:.83rem">${p.rating??'—'}</td>
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

  const valFn = (p) => {
    if (heatmapSort.col === 'player') return p.short.toLowerCase();
    const rm = round.rank_matrix[p.key] ?? [];
    return rm[heatmapSort.col] ?? 0;
  };
  const sorted = [...DATA.players]
    .filter(p => !hiddenPlayers.has(p.key))
    .sort((a,b) => {
      const va = valFn(a), vb = valFn(b);
      if (typeof va === 'string') return heatmapSort.dir * va.localeCompare(vb);
      return heatmapSort.dir * (va - vb);
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
  meta.textContent = `${DATA.meta.title} · ${DATA.meta.total_rounds} rounds · ${DATA.meta.gpr} games/round · Tiebreak: ${DATA.meta.tiebreak}`;
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
