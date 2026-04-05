import json
import os
import re
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

parser = argparse.ArgumentParser(
    description="Visualize Monte Carlo chess tournament predictions."
)
parser.add_argument(
    "directory",
    nargs="?",
    default=".",
    help="Directory containing round{i}.txt files (default: current directory)",
)
parser.add_argument(
    "-o",
    "--output",
    default=None,
    help="Output file path (default: round{N}.png in the input directory)",
)
parser.add_argument(
    "-t",
    "--tournament",
    default=None,
    help="Path to tournament JSON to show pre-tournament Elo in the bar chart",
)
parser.add_argument(
    "-k",
    "--max-round",
    type=int,
    default=None,
    help="Only process up to this round number (default: all rounds found)",
)
args = parser.parse_args()

input_dir = args.directory

# 1. Player Aliases Mapping
PLAYER_ALIASES = {
    "Caruana, Fabiano": "Fabi",
    "Giri, Anish": "Anish",
    "Bluebaum, Matthias": "Bluebaum",
    "Sindarov, Javokhir": "Sindarov",
    "Wei, Yi": "Wei Yi",
    "Esipenko, Andrey": "Esipenko",
    "Praggnanandhaa R": "Pragg",
    "Nakamura, Hikaru": "Hikaru",
    "Firouzja, Alireza": "Alireza",
    "Nepomniachtchi, Ian": "Nepo",
    "Gukesh D": "Gukesh",
    "Vidit, Santosh Gujrathi": "Vidit",
    "Abasov, Nijat": "Abasov",
}

# 2. Load pre-tournament Elo ratings from tournament JSON (optional)
def load_elos(tournament_path: str) -> dict[str, int]:
    text = re.sub(r"//[^\n]*", "", open(tournament_path, encoding="utf-8").read())
    data = json.loads(text)
    result = {}
    for p in data["players"]:
        raw = p["name"]
        alias = PLAYER_ALIASES.get(raw, raw.split(",")[0].strip())
        result[alias] = int(p["rating"])
    return result

player_elos = load_elos(args.tournament) if args.tournament else {}

# 3. Automatically detect and sort round{i}.txt files
file_pattern = re.compile(r"round(\d+)\.txt")
files = []
for f in os.listdir(input_dir):
    match = file_pattern.match(f)
    if match:
        files.append((int(match.group(1)), os.path.join(input_dir, f)))

files.sort()
if not files:
    print("Error: No 'round{i}.txt' files found in the current directory.")
    exit(1)

if args.max_round is not None:
    files = [(k, f) for k, f in files if k <= args.max_round]
    if not files:
        print(f"Error: No round files found up to round {args.max_round}.")
        exit(1)

max_k = files[-1][0]
latest_file = files[-1][1]

# 3. Regex Patterns
round_pattern = re.compile(r"--- ROUND (\d+) ---")
match_pattern = re.compile(r"(.+) vs (.+)")
prob_pattern = re.compile(
    r"1-0:\s*([\d.]+)%\s*\|\s*1/2-1/2:\s*([\d.]+)%\s*\|\s*0-1:\s*([\d.]+)%"
)
win_prob_pattern = re.compile(r"([\d.]+)%\s*-\s*(.+)")


def parse_standings(filepath):
    st = {}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        match = re.search(r"=== Current Standings.*?===\n(.*?)\n\n", content, re.DOTALL)
        if match:
            for line in match.group(1).strip().split("\n"):
                parts = line.split(":")
                if len(parts) == 2:
                    raw_name = parts[0].strip()
                    name = PLAYER_ALIASES.get(raw_name, raw_name.split(",")[0].strip())
                    pts = float(parts[1].replace("pts", "").strip())
                    st[name] = pts
    return st


def parse_predictions(filepath, target_round):
    matches = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    current_round = None
    current_white = None
    current_black = None

    for line in lines:
        line = line.strip()
        rm = round_pattern.search(line)
        if rm:
            current_round = int(rm.group(1))
            continue

        if current_round != target_round:
            continue

        mm = match_pattern.search(line)
        if mm and "---" not in line and "===" not in line:
            raw_w = mm.group(1).strip()
            raw_b = mm.group(2).strip()
            current_white = PLAYER_ALIASES.get(raw_w, raw_w.split(",")[0].strip())
            current_black = PLAYER_ALIASES.get(raw_b, raw_b.split(",")[0].strip())
            continue

        pm = prob_pattern.search(line)
        if pm and current_white and current_black:
            matches.append(
                {
                    "White": current_white,
                    "Black": current_black,
                    "White Win": float(pm.group(1)),
                    "Draw": float(pm.group(2)),
                    "Black Win": float(pm.group(3)),
                }
            )
            current_white = None
            current_black = None
    return matches


# 4. Extract Historical Win Probabilities
win_history = []
for k, fname in files:
    with open(fname, "r", encoding="utf-8") as f:
        content = f.read()
        if "=== Tournament Win Probabilities" in content:
            lines = (
                content.split("=== Tournament Win Probabilities")[1].strip().split("\n")
            )
            for line in lines:
                wp_match = win_prob_pattern.search(line)
                if wp_match:
                    perc = float(wp_match.group(1))
                    raw_name = wp_match.group(2).strip()
                    name = PLAYER_ALIASES.get(raw_name, raw_name.split(",")[0].strip())
                    win_history.append(
                        {"Completed Rounds": k - 1, "Player": name, "Win %": perc}
                    )

df_history = pd.DataFrame(win_history)

# 5. Compile Data for ALL 14 Rounds
all_rounds_data = []
for r in range(1, 15):
    if r < max_k:
        file_before = os.path.join(input_dir, f"round{r}.txt")
        file_after = os.path.join(input_dir, f"round{r+1}.txt")
        matches = (
            parse_predictions(file_before, r) if os.path.exists(file_before) else []
        )

        if matches and os.path.exists(file_after):
            st_before = parse_standings(file_before)
            st_after = parse_standings(file_after)
            for m in matches:
                w_diff = st_after.get(m["White"], 0) - st_before.get(m["White"], 0)
                if w_diff == 1.0:
                    m["Actual"] = "1-0"
                elif w_diff == 0.5:
                    m["Actual"] = "1/2-1/2"
                elif w_diff == 0.0:
                    m["Actual"] = "0-1"
                else:
                    m["Actual"] = "Unknown"

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

colors = plt.cm.tab20(np.linspace(0, 1, len(PLAYER_ALIASES)))
player_colors = dict(zip(PLAYER_ALIASES.values(), colors))

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
latest_probs = latest_probs.sort_values(by="Win %", ascending=True).reset_index(
    drop=True
)

current_standings = parse_standings(latest_file)

bar_handles = ax_bar.barh(
    latest_probs["Player"],
    latest_probs["Win %"],
    color=[player_colors[p] for p in latest_probs["Player"]],
    edgecolor="black",
    linewidth=0.5,
)

ax_bar.set_title(f"Tournament Win %", fontsize=18, weight="bold", pad=10)
ax_bar.set_xlim(0, max(latest_probs["Win %"].max() + 25, 110))
ax_bar.set_yticks(range(len(latest_probs)))
if player_elos:
    bar_labels = [
        f"{p} ({player_elos.get(p, '?')}) · {current_standings.get(p, '?')}"
        for p in latest_probs["Player"]
    ]
else:
    bar_labels = [
        f"{p} ({current_standings.get(p, '?')})" for p in latest_probs["Player"]
    ]
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


# Map the 14 rounds cleanly around the center cell (Index 7 out of 0-14)
for r_idx in range(14):
    r = r_idx + 1

    # Calculate cell mapping, shifting by 1 after the center cell to leave it blank
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

    if r < max_k:
        status = "Completed"
    elif r == max_k:
        status = "Next"
    else:
        status = "Future"

    title = f"Round {r_num} ({status})"
    plot_matches(ax, df_m, title, is_hist)

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
plt.savefig(output_filename, dpi=300, bbox_inches="tight")
print(
    f"Successfully generated Center-Anchored 14-Round Command Center. Plot saved to '{output_filename}'"
)
