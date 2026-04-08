#!/usr/bin/env python3
"""
Visualize Monte Carlo chess tournament predictions from JSON round output files.

Reads all round{N}.txt or round{N}.json files in a directory and produces a dashboard PNG showing:
  - Win probability timeline across rounds
  - Current win % bar chart
  - Per-round match prediction breakdowns (actual results highlighted in gold)

Usage:
    python tools/viz/visualize_timeline.py results/candidates2026/rounds/
    python tools/viz/visualize_timeline.py results/candidates2026/rounds/ -o my_output.png
    python tools/viz/visualize_timeline.py results/candidates2026/rounds/ -k 5 -t data/candidates2026.jsonc
"""

import json
import os
import re
import sys
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def load_jsonc(path: str) -> dict:
    """Load and parse a JSONC file by stripping comments."""
    text = re.sub(r"//[^\n]*", "", open(path, encoding="utf-8").read())
    return json.loads(text)


def _load_aliases(path: str) -> dict[str, str]:
    """Load name→alias mapping from a JSONC players file."""
    try:
        return {p["name"]: p["alias"] for p in load_jsonc(path)}
    except FileNotFoundError:
        print(
            f"[warn] Players file not found: {path!r}. No aliases applied.",
            file=sys.stderr,
        )
        return {}


parser = argparse.ArgumentParser(
    description="Visualize Monte Carlo chess tournament predictions."
)
parser.add_argument(
    "directory", nargs="?", default=".", help="Directory containing round files"
)
parser.add_argument("-o", "--output", default=None, help="Output file path")
parser.add_argument(
    "-t",
    "--tournament",
    default=None,
    help="Path to tournament JSON for Elo and actual results",
)
parser.add_argument(
    "-k", "--max-round", type=int, default=None, help="Process up to this round number"
)
parser.add_argument(
    "--players-file", default="data/players.jsonc", help="Player name/alias mappings"
)
args = parser.parse_args()

PLAYER_ALIASES = _load_aliases(args.players_file)
input_dir = args.directory

# 1. Automatically detect and sort round{i} files (supporting .txt or .json extensions)
file_pattern = re.compile(r"round(\d+)\.(txt|json)")
files = []
for f in os.listdir(input_dir):
    match = file_pattern.match(f)
    if match:
        files.append((int(match.group(1)), os.path.join(input_dir, f)))

files.sort()
if not files:
    print("Error: No 'round{i}.txt' or 'round{i}.json' files found.")
    exit(1)

if args.max_round is not None:
    files = [(k, f) for k, f in files if k <= args.max_round]
    if not files:
        print(f"Error: No round files found up to round {args.max_round}.")
        exit(1)

max_k = files[-1][0]
latest_file = files[-1][1]

# 2. Extract Ground Truth Data (Elo, Standings, Match Results)
player_elos = {}
actual_results = {}
current_standings = {}

if args.tournament and os.path.exists(args.tournament):
    t_data = load_jsonc(args.tournament)
    players_by_id = {p["fide_id"]: p["name"] for p in t_data["players"]}
    gpr = t_data.get("gpr", len(t_data["players"]) // 2)

    for p in t_data["players"]:
        raw = p["name"]
        alias = PLAYER_ALIASES.get(raw, raw.split(",")[0].strip())
        player_elos[alias] = int(p["rating"])

    for gi, g in enumerate(t_data["schedule"]):
        if "result" in g and g["result"] is not None:
            w_raw = players_by_id[g["white"]]
            b_raw = players_by_id[g["black"]]
            w = PLAYER_ALIASES.get(w_raw, w_raw.split(",")[0].strip())
            b = PLAYER_ALIASES.get(b_raw, b_raw.split(",")[0].strip())
            rnd = g.get("round", gi // gpr + 1)

            actual_results[(rnd, w, b)] = g["result"]

            # Tally points strictly up to max_k - 1
            if rnd < max_k:
                res = g["result"]
                current_standings[w] = current_standings.get(w, 0.0) + (
                    1.0 if res == "1-0" else 0.5 if res == "1/2-1/2" else 0.0
                )
                current_standings[b] = current_standings.get(b, 0.0) + (
                    0.0 if res == "1-0" else 0.5 if res == "1/2-1/2" else 1.0
                )


# 3. Data Parsing Functions (JSON API)
def parse_predictions(filepath, target_round):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        matches = []
        round_key = str(target_round)
        if "game_probs" in data and round_key in data["game_probs"]:
            for pair, probs in data["game_probs"][round_key].items():
                raw_w, raw_b = pair.split("|")
                w = PLAYER_ALIASES.get(raw_w, raw_w.split(",")[0].strip())
                b = PLAYER_ALIASES.get(raw_b, raw_b.split(",")[0].strip())
                matches.append(
                    {
                        "White": w,
                        "Black": b,
                        "White Win": probs[0] * 100.0,
                        "Draw": probs[1] * 100.0,
                        "Black Win": probs[2] * 100.0,
                    }
                )
        return matches
    except Exception as e:
        print(f"Warning: Could not parse games from {filepath} ({e})")
        return []


# 4. Extract Historical Win Probabilities
win_history = []
for k, fname in files:
    try:
        with open(fname, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "winner_probs" in data:
            for raw_name, prob in data["winner_probs"].items():
                name = PLAYER_ALIASES.get(raw_name, raw_name.split(",")[0].strip())
                win_history.append(
                    {"Completed Rounds": k - 1, "Player": name, "Win %": prob * 100.0}
                )
    except Exception:
        pass

df_history = pd.DataFrame(win_history)

# 5. Compile Data for ALL 14 Rounds
all_rounds_data = []
for r in range(1, 15):
    if r < max_k:
        actual_file = next((f[1] for f in files if f[0] == r), None)
        matches = parse_predictions(actual_file, r) if actual_file else []
        for m in matches:
            m["Actual"] = actual_results.get((r, m["White"], m["Black"]), "Unknown")
        all_rounds_data.append((r, matches, True))
    else:
        matches = parse_predictions(latest_file, r)
        all_rounds_data.append((r, matches, False))

# 6. Build the Command Center Grid Layout
fig = plt.figure(figsize=(30, 16))
fig.suptitle(
    f"Monte Carlo Predictions: State Before Round {max_k}",
    fontsize=26,
    weight="bold",
    y=0.93,
)

gs_main = fig.add_gridspec(4, 1, height_ratios=[1.3, 1, 1, 1], hspace=0.45)

# ─── ROW 0: Timeline & Bar Chart ───
gs_top = gs_main[0].subgridspec(1, 2, width_ratios=[2, 1.5], wspace=0.25)
ax_line = fig.add_subplot(gs_top[0])
ax_bar = fig.add_subplot(gs_top[1])

colors = plt.cm.tab20(np.linspace(0, 1, len(PLAYER_ALIASES) if PLAYER_ALIASES else 8))
player_colors = dict(zip(df_history["Player"].unique(), colors))

for player in df_history["Player"].unique():
    p_data = df_history[df_history["Player"] == player]
    color = player_colors.get(player)
    ax_line.plot(
        p_data["Completed Rounds"],
        p_data["Win %"],
        marker="o",
        label=player,
        color=color,
        linewidth=2.5,
        markersize=6,
    )

ax_line.set_title(
    "Evolution of Tournament Win Probabilities", fontsize=18, weight="bold", pad=10
)
ax_line.set_xlabel("Rounds Completed (0 = Before Round 1)", fontsize=13, weight="bold")
ax_line.set_ylabel("Win Probability (%)", fontsize=13, weight="bold")
ax_line.set_xlim(-0.2, 14.2)
ax_line.set_ylim(0, 100)
ax_line.set_xticks(range(0, 15))
ax_line.grid(True, linestyle="--", alpha=0.6)

latest_probs = df_history[df_history["Completed Rounds"] == max_k - 1].copy()
latest_probs["Points"] = latest_probs["Player"].map(lambda p: current_standings.get(p, 0.0))
latest_probs = latest_probs.sort_values(by=["Win %", "Points"], ascending=True).reset_index(
    drop=True
)

bar_handles = ax_bar.barh(
    latest_probs["Player"],
    latest_probs["Win %"],
    color=[player_colors.get(p, "gray") for p in latest_probs["Player"]],
    edgecolor="black",
    linewidth=0.5,
)

ax_bar.set_title(f"Tournament Win %", fontsize=18, weight="bold", pad=10)
ax_bar.set_xlim(0, max(latest_probs["Win %"].max() + 25, 110))
ax_bar.set_yticks(range(len(latest_probs)))

# Format Y-labels nicely depending on provided data
if args.tournament:
    bar_labels = [
        f"{p} ({player_elos.get(p, '?')}) · {current_standings.get(p, 0.0):g}"
        for p in latest_probs["Player"]
    ]
else:
    bar_labels = [p for p in latest_probs["Player"]]

ax_bar.set_yticklabels(bar_labels, fontsize=12, weight="bold")
ax_bar.tick_params(axis="y", length=0)
ax_bar.grid(axis="x", linestyle="--", alpha=0.5)
ax_bar.set_axisbelow(True)

for tick_label in ax_bar.get_yticklabels():
    player_name = tick_label.get_text().split(" (")[0]
    tick_label.set_color(player_colors.get(player_name, "black"))

for bar in bar_handles:
    width = bar.get_width()
    ax_bar.text(
        width + 2,
        bar.get_y() + bar.get_height() / 2,
        f"{width:.2f}%",
        va="center",
        weight="bold",
        fontsize=11,
    )

# ─── ROWS 1-3: Match Predictions Layout ───
gs_bot1 = gs_main[1].subgridspec(1, 5, wspace=0.7)
gs_bot2 = gs_main[2].subgridspec(1, 5, wspace=0.7)
gs_bot3 = gs_main[3].subgridspec(1, 5, wspace=0.7)


def plot_matches(ax, df, title, is_history=False):
    if df.empty:
        ax.axis("off")
        ax.set_title(title + "\n(Data Unavailable)", fontsize=12, color="red")
        return

    df_plot = df.iloc[::-1].reset_index(drop=True)
    match_colors = ["#F0F0F0", "#8C92AC", "#2B2B2B"]

    df_plot[["White Win", "Draw", "Black Win"]].plot(
        kind="barh",
        stacked=True,
        color=match_colors,
        edgecolor="black",
        linewidth=0.5,
        ax=ax,
        legend=False,
    )

    ax.set_title(title, fontsize=14, weight="bold", pad=8)
    ax.set_xlim(0, 100)

    ax.set_yticks(range(len(df_plot)))
    ax.set_yticklabels(df_plot["White"], fontsize=11, weight="bold")
    ax.tick_params(axis="y", length=0)

    ax_twin = ax.twinx()
    ax_twin.set_ylim(ax.get_ylim())
    ax_twin.set_yticks(range(len(df_plot)))
    ax_twin.set_yticklabels(df_plot["Black"], fontsize=11, weight="bold")
    ax_twin.tick_params(axis="y", length=0)

    for c_idx, container in enumerate(ax.containers):
        labels = [f"{w:.0f}%" if w > 9 else "" for w in container.datavalues]
        text_color = "black" if c_idx == 0 else "white"

        text_objs = ax.bar_label(
            container,
            labels=labels,
            label_type="center",
            color=text_color,
            fontsize=10,
            weight="bold",
        )

        if is_history and "Actual" in df_plot.columns:
            for i, row in df_plot.iterrows():
                actual = row["Actual"]
                correct_idx = -1
                if actual == "1-0":
                    correct_idx = 0
                elif actual == "1/2-1/2":
                    correct_idx = 1
                elif actual == "0-1":
                    correct_idx = 2

                if correct_idx != -1 and c_idx == correct_idx:
                    bar = container[i]
                    bar.set_edgecolor("#FFD700")
                    bar.set_linewidth(3.0)
                    bar.set_zorder(10)
                    text_objs[i].set_zorder(11)

    ax.grid(axis="x", linestyle="--", alpha=0.5)
    ax.set_axisbelow(True)
    return ax


for r_idx in range(14):
    r = r_idx + 1
    cell_idx = r - 1 if r <= 7 else r

    row_idx = cell_idx // 5
    col_idx = cell_idx % 5

    if row_idx == 0:
        ax = fig.add_subplot(gs_bot1[col_idx])
    elif row_idx == 1:
        ax = fig.add_subplot(gs_bot2[col_idx])
    else:
        ax = fig.add_subplot(gs_bot3[col_idx])

    r_num, df_matches_list, is_hist = all_rounds_data[r_idx]
    df_m = pd.DataFrame(df_matches_list)

    status = "Completed" if r < max_k else "Next" if r == max_k else "Future"
    plot_matches(ax, df_m, f"Round {r_num} ({status})", is_hist)

# ─── The Master Centerpiece Legend ───
ax_legend = fig.add_subplot(gs_bot2[2])
ax_legend.axis("off")

legend_elements = [
    mpatches.Patch(
        facecolor="#F0F0F0", edgecolor="black", linewidth=0.5, label="White Win"
    ),
    mpatches.Patch(facecolor="#8C92AC", edgecolor="black", linewidth=0.5, label="Draw"),
    mpatches.Patch(
        facecolor="#2B2B2B", edgecolor="black", linewidth=0.5, label="Black Win"
    ),
    mpatches.Patch(
        facecolor="none", edgecolor="#FFD700", linewidth=3.0, label="Actual Result"
    ),
]

ax_legend.legend(
    handles=legend_elements,
    loc="center",
    ncol=1,
    frameon=False,
    fontsize=17,
    title="Prediction Key",
    title_fontproperties={"weight": "bold", "size": 18},
)

plt.subplots_adjust(bottom=0.06)

output_filename = (
    args.output if args.output else os.path.join(input_dir, f"round{max_k}.png")
)
os.makedirs(os.path.dirname(os.path.abspath(output_filename)), exist_ok=True)
plt.savefig(output_filename, dpi=300, bbox_inches="tight")
print(
    f"Successfully generated Center-Anchored 14-Round Command Center. Plot saved to '{output_filename}'"
)
