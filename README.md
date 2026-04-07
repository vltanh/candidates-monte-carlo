# Chess Monte Carlo Simulation

A multi-threaded Monte Carlo simulator for chess tournaments with a fixed schedule. Models dynamic per-player ratings that update as games are played, then runs millions of simulated completions to estimate win probabilities.

## 2026 Candidates: Live Predictions

![Animation](results/candidates2026/animation.gif)

<!-- Add new rounds here (most recent first): copy the <details> block and update the round number and image path -->

<details>
<summary>Round 8: predictions</summary>

![Round 8](results/candidates2026/r8.png)

*Round 7 results: Wei Yi beat Esipenko, Sindarov–Anish drew, Bluebaum–Naka drew, Pragg–Fabi drew*

- ✓ **Wei Yi beat Esipenko**: model had Wei Yi at 36.9% to win; correct prediction
- ✗ **Sindarov–Anish drew**: model had Sindarov at 53.9% to win and only 24.8% to draw; a 2.5-point lead removes urgency to press
- ✗ **Bluebaum–Naka drew**: model had Bluebaum at 37.1% to win and 34.0% to draw; the game ended in a draw
- ✗ **Pragg–Fabi drew**: model had Pragg at 37.3% to win and 28.1% to draw; Fabi has drawn 2 straight since his R5 win vs Bluebaum
- Sindarov barely moves: **80.2%** (from 80.2%); drawing costs almost nothing when the lead is this large

*Round 8 predictions:*
- Esipenko–Sindarov: 16.7% / 21.5% / **61.8%**, Sindarov the strong favourite; Esipenko at 2/7 is an extreme underdog
- Wei Yi–Bluebaum: **37.9%** / 31.1% / 31.0%, Wei Yi with a slight edge
- Anish–Pragg: **38.5%** / 37.3% / 24.2%, Anish with a slight edge
- Naka–Fabi: **37.4%** / 31.1% / 31.6%, Naka with a slight edge

</details>

<details>
<summary>Round 7</summary>

![Round 7](results/candidates2026/r7.png)

*Round 6 results: Fabi–Esipenko drew, Naka–Pragg drew, Anish–Bluebaum drew, Sindarov beat Wei Yi*

- ✓ **Sindarov beat Wei Yi**: model had Sindarov at 41.7% to win; correct prediction
- ✗ **Fabi–Esipenko drew**: model's biggest miss of the tournament; Fabi was a **65.5% favourite** with only 21.1% to draw, and his inability to convert against lower-rated players is the central story
- ✗ **Naka–Pragg drew**: model had Naka at 41.9% to win and 32.4% to draw; the game ended in a draw
- ✗ **Anish–Bluebaum drew**: model had Anish at 40.3% to win and 32.6% to draw; the game ended in a draw
- Win probs: Sindarov **80.2%**, Fabi 14.4%; Fabi drawing while Sindarov winning collapses the race

*Round 7 predictions:*
- Esipenko–Wei Yi: 33.1% / 30.0% / **36.9%**, Wei Yi favoured
- Sindarov–Anish: **53.9%** / 24.8% / 21.4%, Sindarov the strong favourite
- Bluebaum–Naka: **37.1%** / 34.0% / 28.9%, Bluebaum with a slight edge
- Pragg–Fabi: **37.3%** / 28.1% / 34.7%, Pragg with a slight edge

</details>

<details>
<summary>Round 6</summary>

![Round 6](results/candidates2026/r6.png)

*Round 5 results: Pragg–Esipenko drew, Fabi beat Bluebaum, Sindarov beat Naka, Anish–Wei Yi drew*

- ✓ **Fabi beat Bluebaum**: model had Fabi at 53.4% to win and 27.8% to draw; correct prediction
- ✗ **Sindarov beat Naka**: model had Naka barely ahead at 34.5% with Sindarov at 32.8%; Sindarov wins despite being the underdog, though the margin was minimal
- ✗ **Anish–Wei Yi drew**: model had Anish at 42.2% to win and 32.0% to draw; the game ended in a draw
- ✗ **Pragg–Esipenko drew**: model had Pragg at 46.3% to win with only 26.9% drawing; drew
- Win probs: Sindarov **62.4%**, Fabi 26.7%; Sindarov's 4.5/5 gives him commanding odds

*Round 6 predictions:*
- Fabi–Esipenko: **65.5%** / 21.1% / 13.4%, Fabi the overwhelming favourite; model expects him to close the gap
- Naka–Pragg: **41.9%** / 32.4% / 25.7%, Naka favoured
- Anish–Bluebaum: **40.3%** / 32.6% / 27.1%, Anish favoured
- Wei Yi–Sindarov: 28.1% / 30.2% / **41.7%**, Sindarov favoured

</details>

<details>
<summary>Round 5</summary>

![Round 5](results/candidates2026/r5.png)

*Round 4 results: Anish beat Esipenko, Wei Yi–Naka drew, Sindarov beat Fabi, Bluebaum–Pragg drew*

- ✓ **Sindarov beat Fabi**: model had Sindarov at 40.0% to win and 33.8% to draw; **the tournament's turning point** as Sindarov opens a 1-point lead
- ✗ **Anish beat Esipenko**: model had Esipenko at 39.5% to win and Anish at only 27.8%; Anish wins despite being the underdog, making it a wrong-direction miss
- ✗ **Wei Yi–Naka drew**: model had Wei Yi at 40.4% to win and 32.5% to draw; the game ended in a draw
- ✗ **Bluebaum–Pragg drew**: model had Bluebaum at 39.5% to win and 36.4% to draw; the game ended in a draw
- Win probs: Sindarov **48.4%**, Fabi 25.6%; gap widens with Sindarov at 3.5/4

*Round 5 predictions:*
- Pragg–Esipenko: **46.3%** / 26.9% / 26.8%, Pragg favoured
- Fabi–Bluebaum: **53.4%** / 27.8% / 18.7%, Fabi the strong favourite
- Naka–Sindarov: **34.5%** / 32.8% / 32.8%, near three-way split with Naka barely ahead
- Anish–Wei Yi: **42.2%** / 32.0% / 25.8%, Anish favoured

</details>

<details>
<summary>Round 4</summary>

![Round 4](results/candidates2026/r4.png)

*Round 3 results: Bluebaum–Esipenko drew, Sindarov beat Pragg, Fabi beat Wei Yi, Naka–Anish drew*

- ✓ **Fabi beat Wei Yi**: model had Fabi at 49.2% to win and 30.8% to draw; correct prediction
- ✗ **Sindarov beat Pragg**: model had Pragg at 36.9% to win and Sindarov at only 30.2%; Sindarov wins, which is the wrong direction
- ✗ **Bluebaum–Esipenko drew**: model had Bluebaum at 48.7% to win and 31.0% to draw; the biggest miss of the round
- ✗ **Naka–Anish drew**: model had Naka at 50.6% to win and only 29.5% to draw; another expected win becomes a draw
- Win probs: Fabi **41.6%**, Sindarov **32.5%**; Fabi leads despite equal standing, and the model weighs opponent quality

*Round 4 predictions:*
- Esipenko–Anish: **39.5%** / 32.7% / 27.8%, Esipenko favoured
- Wei Yi–Naka: **40.4%** / 32.5% / 27.1%, Wei Yi favoured
- Sindarov–Fabi: **40.0%** / 33.8% / 26.3%, Sindarov with a slight edge
- Bluebaum–Pragg: **39.5%** / 36.4% / 24.1%, Bluebaum favoured

</details>

<details>
<summary>Round 3</summary>

![Round 3](results/candidates2026/r3.png)

*Round 2 results: ALL FOUR games drew: Esipenko–Naka, Anish–Fabi, Wei Yi–Pragg, Sindarov–Bluebaum*

- ✓ **Anish–Fabi drew**: model had draw as the most likely outcome at 35.6%; correct prediction
- ✗ **Esipenko–Naka drew**: model had Esipenko at 37.5% to win and 32.0% to draw; drew
- ✗ **Wei Yi–Pragg drew**: model had Wei Yi at 47.1% to win and 33.4% to draw; drew
- ✗ **Sindarov–Bluebaum drew**: model had Sindarov at 49.2% to win and only 30.7% to draw; drew
- Early-round draws consistently underestimated; win probs after all draws: Fabi **33.5%**, Sindarov **20.6%**, Pragg **10.1%**

*Round 3 predictions:*
- Bluebaum–Esipenko: **48.7%** / 31.0% / 20.3%, Bluebaum strongly favoured; Esipenko lost R1, widening the rating gap
- Pragg–Sindarov: **36.9%** / 32.9% / 30.2%, Pragg with a slight edge as White despite Sindarov's R1 win
- Fabi–Wei Yi: **49.2%** / 30.8% / 20.0%, Fabi strongly favoured
- Naka–Anish: **50.6%** / 29.5% / 19.9%, Naka strongly favoured

</details>

<details>
<summary>Round 2</summary>

![Round 2](results/candidates2026/r2.png)

*Round 1 results: Fabi beat Naka, Sindarov beat Esipenko, Pragg beat Anish, Bluebaum–Wei Yi drew*

- ✓ **Fabi beat Naka**: model had Fabi at 42.4% to win and 34.8% to draw; correct prediction
- ✓ **Sindarov beat Esipenko**: model had Sindarov at 49.0% to win; correct prediction
- ✗ **Bluebaum–Wei Yi drew**: model had Bluebaum at 38.8% to win and 35.1% to draw; the game ended in a draw
- ✗ **Pragg beat Anish**: model had draw as most likely at 35.5% with Pragg at 34.8% and Anish at 29.6%; Pragg wins; the prediction was draw, and the win rate was above the loss rate
- All three R1 winners jump sharply: Fabi 21.6% → **30.6%**, Sindarov 17.1% → **23.7%**, Pragg 5.1% → **8.3%**; moderate priors still amplify single-game results immediately

*Round 2 predictions:*
- Esipenko–Naka: **37.5%** / 32.0% / 30.5%, Esipenko now favoured (flipped from pre-R1); moderate priors absorb Naka's R1 loss meaningfully
- Anish–Fabi: 34.8% / **35.6%** / 29.6%, draw most likely
- Wei Yi–Pragg: **47.1%** / 33.4% / 19.5%, Wei Yi favoured
- Sindarov–Bluebaum: **49.2%** / 30.7% / 20.2%, Sindarov boosted further by his R1 win

</details>

<details>
<summary>Round 1</summary>

![Round 1](results/candidates2026/r1.png)

*Pre-tournament predictions*

- **Fabi** is the favourite at **21.6%**: consistent profile across all three time controls gives a stable overall estimate
- **Naka at 17.3%** despite the highest classical Elo (2810): flat classical trend and weaker rapid/blitz velocity
- **Sindarov at 17.1%** with only 2745 Elo: strongly rising classical trend [2721→2745, +24 pts] and improving rapid history; the model rewards recent momentum
- **Bluebaum at 9.9%** for a 2695-rated player: positive classical trend with no drag from weak secondary time controls
- **Pragg at only 5.1%** despite his FIDE ranking: classical rating falling [2768→2741, −27 pts]; the model tracks the trend, not the name

*Round 1 predictions:*
- Fabi–Naka: **42.4%** / 34.8% / 22.8%, Fabi the strong favourite
- Pragg–Anish: 34.8% / **35.5%** / 29.6%, draw most likely
- Bluebaum–Wei Yi: **38.8%** / 35.1% / 26.1%, Bluebaum favoured
- Sindarov–Esipenko: **49.0%** / 32.9% / 18.1%, Sindarov the strong favourite

</details>

## Repository Layout

```
src/                     C++ source and bundled json.hpp header
bin/                     Compiled binary (chess_montecarlo)
configs/                 Hyperparameter files and tuning snapshots
data/                    Tournament JSONC files and raw PGN downloads
  players.jsonc          Canonical player registry (name, alias, FIDE ID)
  raw/                   Raw PGN broadcasts downloaded from Lichess
results/                 Per-tournament visualizations and simulation outputs
  candidates2026/
    rounds/              round{N}.json simulation outputs
    r{N}.png             Per-round bar charts
    animation.gif        Animated GIF of all rounds
db/                      Optuna SQLite databases for hyperparameter tuning
tools/
  data/
    build_tournament.py  Build tournament.jsonc from a Lichess broadcast
  tuning/
    tune.py              Optuna hyperparameter search driver
    evaluate.py          Score a fixed hyperparameter set against tournament data
    utils.py             Shared scoring utilities (used by tune.py and evaluate.py)
  viz/
    generate_rounds.py     Run the C++ engine for each round and save JSON outputs
    visualize_timeline.py  Generate dashboard PNGs from round outputs
    pareto_front.py        Visualize Optuna Pareto front and print best trials
    make_gif.py            Combine round PNGs into an animated GIF
install.sh               Dependency installation snippet
```

## Features

- **Dynamic Bayesian ratings**: a 2N anchored MAP estimator maintains separate White and Black latent strengths per player, updated every round
- **Parametric draw model**: draw probability proportional to ν·√(λW·λB), where ν is a time-control-specific tuning parameter (`classical_nu`, `rapid_nu`, `blitz_nu`)
- **Style multiplier**: each player has Bayesian-smoothed White/Black aggression scores (fraction of decisive games); ν is scaled by `baselineAgg / matchAgg`, shrinking the draw band when both players play sharply and inflating it when they play solidly
- **Standings multiplier**: ν is scaled by each player's *motivation*, then averaged. Motivation is computed from `R = deficit / roundsLeft`: leaders (R ≤ 0) play at baseline; contenders (0 < R < 0.75) get a desperation boost peaking at R = 0.375; near-eliminated players (R ≥ 0.75) widen their draw band as they relax pressure
- **Color bleed**: aggression and rating form cross-pollinate between colors; λW/λB are also geometrically blended after each MAP update and rescaled to prevent drift
- **Velocity projection**: per-player rating trends across all three time controls are estimated via time-decayed weighted least-squares regression; rapid/blitz deltas are blended in via `rapid_form_weight` and `blitz_form_weight`
- **Time control support**: uses Classical, Rapid, or Blitz ratings for the appropriate stage
- **FIDE tiebreak modes**: `fide2026`: Rapid mini-match → Blitz mini-match → Armageddon (draw = Black wins); `fide2024`: Rapid mini-match → Blitz mini-match → infinite alternate-color sudden-death Blitz; `shared`: win probability split evenly among tied players
- **Sonneborn-Berger secondary tiebreaker**: standings output orders tied players by SB score, then decisive wins, then random draw (lot)
- **Parallel simulation**: work is distributed across all hardware threads via `std::thread`

## Build

```bash
g++ -O3 -march=native -std=c++17 -pthread src/chess_montecarlo.cpp -o bin/chess_montecarlo
```

Requires a C++17-capable compiler. The only dependency is [`json.hpp`](https://github.com/nlohmann/json) (included in `src/`).

## Usage

```bash
./bin/chess_montecarlo [hyperparameters.jsonc] [tournament.jsonc] [simulate_from_round]
```

`simulate_from_round` defaults to 1 (simulate all rounds). Output is **JSON** printed to stdout, captured to a file for downstream tools.

```bash
./bin/chess_montecarlo configs/best_hparams_22_24.jsonc data/candidates2026.jsonc 8 > results/candidates2026/rounds/round8.json
```

`tools/viz/generate_rounds.py` automates running all rounds at once:

```bash
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2026.jsonc results/candidates2026/rounds/
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2026.jsonc results/candidates2026/rounds/ --rounds 8
```

Output fields:

| Field | Description |
|---|---|
| `metadata.time_seconds` | Wall-clock simulation time |
| `winner_probs` | `{player: probability}`: tournament win probability |
| `expected_points` | `{player: points}`: average final score |
| `rank_matrix` | `{player: [p_rank1, p_rank2, ...]}`: finishing position distribution |
| `game_probs` | `{"N": {"White\|Black": [p_white_win, p_draw, p_black_win]}}`: N is the round number as a string |

## JSON format

**`configs/best_hparams_22_24.jsonc`** (hyperparameters): all fields are tunable. Key groups: `runs`/`map_iters`/`map_tolerance` (simulation), `prior_weight_known`/`prior_weight_sim` (MAP priors), `initial_white_adv`/`velocity_time_decay`/`lookahead_factor` (rating init), `rapid_form_weight`/`blitz_form_weight`/`color_bleed` (cross-time-control blending), `classical_nu`/`rapid_nu`/`blitz_nu` (draw model), `agg_prior_weight`/`default_aggression_w`/`default_aggression_b`/`standings_aggression` (aggression).

**`data/candidates2026.jsonc`** (tournament): top-level fields:
- `"gpr"`: games per round (default `N/2`)
- `"tiebreak"`: `"shared"` | `"fide2024"` | `"fide2026"` (default `"shared"`)
- `"players"`: array of N players; required: `fide_id`, `name`, `rating`; optional: `rapid_rating`, `blitz_rating`, `aggression_w/b`, `history`/`games_played`, `rapid_history`/`rapid_games_played`, `blitz_history`/`blitz_games_played`
- `"schedule"`: array of `{white, black[, result, round]}`; games without `result` are simulated; the optional `round` field overrides the GPR-based round inference

## Building tournament data

`tools/data/build_tournament.py` downloads games from a Lichess broadcast, fetches FIDE rating history, and writes a ready-to-use tournament JSONC.

```bash
pip install requests python-chess

python tools/data/build_tournament.py wEuVhT9c -o data/my_tournament.jsonc
python tools/data/build_tournament.py wEuVhT9c --tiebreak fide2026   # set tiebreak mode
python tools/data/build_tournament.py wEuVhT9c --as-of 2024-04       # slice FIDE history to a month
python tools/data/build_tournament.py wEuVhT9c --no-fide              # skip FIDE fetch
python tools/data/build_tournament.py wEuVhT9c --periods 8            # history depth (default: 6)
python tools/data/build_tournament.py wEuVhT9c --players-file data/players.jsonc  # player aliases/FIDE IDs
```

## Hyperparameter tuning

`tools/tuning/tune.py` uses [Optuna](https://optuna.org) to search for the best model parameters via multi-objective optimization.

```bash
pip install optuna

# Run 200 trials on a single tournament (always resumes an existing study automatically)
python tools/tuning/tune.py configs/default_hparams.jsonc data/candidates2024.jsonc

# Run against multiple tournaments simultaneously (scores are averaged)
python tools/tuning/tune.py configs/default_hparams.jsonc data/candidates2022.jsonc data/candidates2024.jsonc

# Custom binary or database path
python tools/tuning/tune.py configs/default_hparams.jsonc data/candidates2024.jsonc \
    --binary ./bin/chess_montecarlo \
    --db db/tuning_2024.db \
    --trials 500
```

For each round K with known results, the binary runs with `simulate_from_round = K`; rounds K onward are held-out predictions. Two objectives are minimized simultaneously:

1. **Weighted Game Brier Score**: multi-class Brier score over all predicted games, decay-weighted by `FUTURE_DECAY_WEIGHT^distance`. Decisive outcomes are up-weighted by `DECISIVE_GAME_WEIGHT` to combat the lazy-draw problem.
2. **Rank RPS**: Ranked Probability Score over the predicted finishing-position distribution (cumulative squared error across all rank thresholds), averaged across players.

Rank RPS is accumulated weighted by round number: a round-13 error counts 13× more than round 1. Game Brier weights each predicted game by how far into the future it falls from the simulation point, giving exponentially less weight to games further ahead. When multiple tournament files are supplied, scores are averaged across tournaments. `EVAL_RUNS` in `tools/tuning/utils.py` controls Monte Carlo iterations per trial (default 10 000).

```bash
python tools/viz/pareto_front.py db/tuning_22_24.db
python tools/viz/pareto_front.py db/tuning_22_24.db --save results/pareto/tuning_22_24.png
```

**2022 + 2024 Candidates: 8 970 trials, 48 Pareto-optimal:**

![Pareto Front](results/pareto/tuning_22_24.png)

`pareto_front.py` ranks Pareto-optimal trials by **Normalized Distance to Utopia**; each objective is scaled to [0,1] by the observed range, then Euclidean distance to the best-seen corner is minimized. The #1 trial is saved as `configs/best_hparams_22_24.jsonc` and used for the 2026 Candidates predictions.

### `best_hparams_22_24.jsonc`: parameter interpretation

| Parameter | Value | Interpretation |
|---|---|---|
| `prior_weight_known/sim` | 2.63 / 4.00 | Moderate priors; the model updates meaningfully on each result but does not overreact to a single game |
| `initial_white_adv` | 84.8 Elo | Large White color advantage; White and Black starting ratings are initialized ~85 Elo apart (±42 each) |
| `lookahead_factor` | 4.89 | Rating trend is strongly extrapolated forward; players with rising ratings are credited substantially |
| `velocity_time_decay` | 0.386 | Steep decay; recent rating history is weighted heavily over older entries |
| `rapid_form_weight / blitz_form_weight` | −0.40 / −0.38 | Rapid and blitz trends slightly reduce the classical form anchor |
| `color_bleed` | 0.0082 | Minimal cross-pollination between White and Black latent strengths; color-specific ratings are nearly independent |
| `classical_nu` | 1.12 | Moderate draw rate for classical games |
| `rapid_nu` | 0.96 | Slightly lower draw rate for rapid tiebreaks |
| `blitz_nu` | 0.60 | Lowest draw rate for blitz tiebreaks |
| `agg_prior_weight` | 18.2 | Moderate aggression prior; individual aggression scores can deviate meaningfully from the default |
| `default_aggression_w` | 0.240 | Prior for White decisive-game fraction; ~24% of White games are expected to be decisive before any game history is observed |
| `default_aggression_b` | 0.058 | Prior for Black decisive-game fraction; ~6% of Black games decisive by default, roughly one quarter the White rate; Black is expected to be very drawish before any game history is observed |
| `standings_aggression` | 0.081 | Small desperation effect; tournament standings have some influence on game aggression |

## Evaluating a fixed parameter set

`tools/tuning/evaluate.py` scores a specific hyperparameter file against one or more tournament files. Reports four metrics per round and in aggregate.

```bash
# Score 2022+2024-tuned params against 2022 data
python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc

# Cross-validate: check against a different tournament
python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc data/candidates2024.jsonc

# Ongoing tournament: winner-based metrics are skipped automatically
python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2026.jsonc

# Higher fidelity (default is 10 000)
python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2024.jsonc --runs 100000
```

Per-round output: `g_brier` (Weighted Game Brier), `win_brier` (Winner Brier), `pts_mse` (Expected Points MSE), `rps` (Rank RPS). For ongoing tournaments, the last three are reported as `N/A`. When multiple tournament files are supplied, `g_brier` is averaged across all tournaments; the other three are averaged across completed tournaments only.

## Visualization

Requires Python with `matplotlib`, `pandas`, and `numpy`.

```bash
# Run simulations for all rounds (saves round{N}.json files)
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2026.jsonc results/candidates2026/rounds/
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2026.jsonc results/candidates2026/rounds/ --rounds 8

# Generate per-round dashboard PNGs
python tools/viz/visualize_timeline.py results/candidates2026/rounds/
python tools/viz/visualize_timeline.py results/candidates2026/rounds/ -o my_output.png
python tools/viz/visualize_timeline.py results/candidates2026/rounds/ -k 5 -t data/candidates2026.jsonc

# Combine all round PNGs into an animated GIF
python tools/viz/make_gif.py results/candidates2026/
python tools/viz/make_gif.py results/candidates2026/ -d 3000 --last-duration 10000
```

`generate_rounds.py` invokes the binary once per round and saves the JSON output to `round{N}.json` files. `visualize_timeline.py` reads all `round{N}.txt` or `round{N}.json` files in the given directory and produces a dashboard PNG showing win probability timeline, current win % bar chart, and per-round match prediction breakdowns (with actual results highlighted in gold).

## How the model works

Each player has latent strengths λW (White) and λB (Black), initialized from a projected FIDE rating ± `initial_white_adv/2` Elo. If rating history is provided, a time-decayed least-squares velocity is estimated and projected forward by `lookahead_factor`; rapid/blitz deltas blend in via `rapid_form_weight` / `blitz_form_weight`.

After each round, λW/λB are updated via:
1. **MAP fixed-point iteration**: anchored Bradley-Terry MAP given all games played; prior strength is `prior_weight_known` for historical rounds and `prior_weight_sim` for simulated ones.
2. **Color bleed**: White/Black relative form are geometrically blended via `color_bleed`, then population-rescaled to prevent drift.

Game probabilities: `p_win = λW[w]/Z`, `p_draw = ν·√(λW[w]·λB[b])/Z`, `p_loss = λB[b]/Z`. The draw parameter ν is scaled per game by:
- **Style multiplier**: `baselineAgg / matchAgg` (Bayesian-smoothed decisive-game fractions); aggressive pairings shrink the draw band.
- **Standings multiplier**: average of both players' motivation from `R = deficit / roundsLeft`; contenders at R ≈ 0.375 peak in desperation, near-eliminated players widen the draw band.
