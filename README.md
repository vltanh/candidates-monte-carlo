# Chess Monte Carlo Simulation

A multi-threaded Monte Carlo simulator for 8-player round-robin chess tournaments. Models dynamic per-player ratings that update as games are played, then runs millions of simulated completions to estimate win probabilities.

The included `data/candidates2026.json` holds the true data of the **2026 FIDE Candidates Tournament**.

## Repository Layout

```
src/                     C++ source and bundled json.hpp header
bin/                     Compiled binary (chess_montecarlo)
configs/                 hyperparameters.json and tuning snapshots
data/                    Tournament JSON files and raw PGN downloads
  raw/                   Raw PGN broadcasts downloaded from Lichess
results/                 Per-tournament visualizations and simulation outputs
  candidates2026/
    rounds/              round{N}.txt simulation outputs
    r{N}.png             Per-round bar charts
    animation.gif        Animated GIF of all rounds
scripts/                 Python helper scripts
  build_tournament.py    Build tournament.json from a Lichess broadcast
  visualize_timeline.py  Generate dashboard PNGs from round outputs
  make_gif.py            Combine round PNGs into an animated GIF
  pareto_front.py        Visualize Optuna Pareto front and print best trials
db/                      Optuna SQLite databases for hyperparameter tuning
tune.py                  Optuna hyperparameter search driver
install.sh               Dependency installation snippet
```

## Animated GIF

![Animation](results/candidates2026/animation.gif)

Run `scripts/make_gif.py` to combine all round PNGs into an animated GIF.

```bash
python3 scripts/make_gif.py results/candidates2026/

# Custom output path
python3 scripts/make_gif.py results/candidates2026/ -o results/candidates2026/animation.gif

# Custom frame durations (ms)
python3 scripts/make_gif.py results/candidates2026/ -d 3000 --last-duration 10000
```

## Visualizations

<!-- Add new rounds here (most recent first): copy the <details> block and update the round number and image path -->

<details>
<summary>Round 8 — predictions</summary>

![Round 8](results/candidates2026/r8.png)

*Round 7 results: Wei Yi beat Esipenko, Sindarov–Anish drew, Bluebaum–Hikaru drew, Pragg–Fabi drew*

- ✓ **Wei Yi beat Esipenko** — model had Wei Yi at 47.5%, correct
- ✗ **Sindarov–Anish drew** — model had Sindarov at 58.8%; with a 2.5-point lead, little incentive to press
- ✗ **Bluebaum–Hikaru drew** — model had Bluebaum at 43.0%
- ✗ **Pragg–Fabi drew** — model had Pragg at 42.9%; Fabi has now drawn 4 straight rounds since his R3 win
- Sindarov drops slightly to **88.5%** (from 90.3%) despite drawing — his cushion remains too large

*Round 8 predictions:*
- Esipenko–Sindarov: 4.2% / 15.2% / **80.6%** — Sindarov near-certain favourite; 6 wins out of 7 makes Esipenko an extreme underdog
- Wei Yi–Bluebaum: 29.8% / 30.5% / **39.8%** — Bluebaum slight edge
- Anish–Pragg: **38.2%** / 31.6% / 30.2% — Anish slight edge
- Hikaru–Fabi: 33.7% / 30.6% / **35.7%** — Fabi slight edge

</details>

<details>
<summary>Round 7</summary>

![Round 7](results/candidates2026/r7.png)

*Round 6 results: Fabi–Esipenko drew, Hikaru–Pragg drew, Anish–Bluebaum drew, Sindarov beat Wei Yi*

- ✓ **Sindarov beat Wei Yi** — model had Sindarov at 62.4%, correct
- ✗ **Fabi–Esipenko drew** — model's biggest miss of the tournament: Fabi was a **72.1% favourite** yet drew again; his inability to convert against lower-rated players is the central story
- ✗ **Hikaru–Pragg drew** — model had Pragg at 36.1%; near-coin-flip, draw not unexpected
- ✗ **Anish–Bluebaum drew** — model had Bluebaum at 40.0%
- Win probs jump: Sindarov **90.3%**, Fabi 7.3% — Fabi drawing while Sindarov winning collapses the race

*Round 7 predictions:*
- Esipenko–Wei Yi: 23.6% / 28.9% / **47.5%** — Wei Yi favoured
- Sindarov–Anish: **58.8%** / 25.6% / 15.7% — Sindarov strong favourite
- Bluebaum–Hikaru: **43.0%** / 30.5% / 26.5% — Bluebaum favoured
- Pragg–Fabi: **42.9%** / 29.3% / 27.8% — Pragg narrow favourite as White; Fabi's 4 consecutive draws since R3 have eroded his estimated strength

</details>

<details>
<summary>Round 6</summary>

![Round 6](results/candidates2026/r6.png)

*Round 5 results: Pragg–Esipenko drew, Fabi beat Bluebaum, Sindarov beat Hikaru, Anish–Wei Yi drew*

- ✓ **Fabi beat Bluebaum** — model predicted (50.7%), correct
- ✓ **Sindarov beat Hikaru** — model had Sindarov as heavy favourite (55.0%), correct
- ✓ **Anish–Wei Yi drew** — model near-even (39.0%/30.6%), draw fine
- ✗ **Pragg–Esipenko drew** — model had Pragg at 48.5%; near-even matchup, draw is plausible
- Win probs: Sindarov **75.1%**, Fabi 19.1% — Sindarov's 4.5/5 gives him commanding odds

*Round 6 predictions:*
- Fabi–Esipenko: **72.1%** / 20.0% / 7.9% — Fabi overwhelming favourite; model expects him to close the gap
- Hikaru–Pragg: 33.1% / 30.8% / **36.1%** — Pragg slight edge
- Anish–Bluebaum: 29.5% / 30.5% / **40.0%** — Bluebaum favoured
- Wei Yi–Sindarov: 12.8% / 24.8% / **62.4%** — Sindarov heavy favourite

</details>

<details>
<summary>Round 5</summary>

![Round 5](results/candidates2026/r5.png)

*Round 4 results: Anish beat Esipenko, Wei Yi–Hikaru drew, Sindarov beat Fabi, Bluebaum–Pragg drew*

- ✓ **Sindarov beat Fabi** — model had Sindarov at 41.8%; **the tournament's turning point** — Sindarov opens a 1-point lead
- ✗ **Anish beat Esipenko** — model had Esipenko at 42.9%; Anish punching above expectations
- ✓ **Wei Yi–Hikaru drew** — model near-even (40.9%/28.7%), draw fine
- ✓ **Bluebaum–Pragg drew** — model near-coin-flip (33.9%/34.7%), draw expected
- Win probs: Sindarov **67.5%**, Fabi 17.1% — with Sindarov at 3.5/4, the model already sees him as dominant

*Round 5 predictions:*
- Pragg–Esipenko: **48.5%** / 28.4% / 23.2% — Pragg favoured
- Fabi–Bluebaum: **50.7%** / 28.4% / 20.9% — Fabi strong favourite
- Hikaru–Sindarov: 17.5% / 27.5% / **55.0%** — Sindarov heavy favourite after 3.5/4
- Anish–Wei Yi: **39.0%** / 30.5% / 30.6% — Anish slight edge

</details>

<details>
<summary>Round 4</summary>

![Round 4](results/candidates2026/r4.png)

*Round 3 results: Bluebaum–Esipenko drew, Sindarov beat Pragg, Fabi beat Wei Yi, Hikaru–Anish drew*

- ✓ **Fabi beat Wei Yi** — model predicted (51.1%), correct
- ✗ **Sindarov beat Pragg** — model had Pragg slightly favoured as White (39.7% vs 29.8%); Sindarov wins anyway
- ✗ **Bluebaum–Esipenko drew** — model had Bluebaum at 53.3%; biggest miss of the round
- ✗ **Hikaru–Anish drew** — model had Hikaru at 51.6%; another expected win becomes a draw
- Win probs: Sindarov **44.2%**, Fabi 38.7% — Sindarov overtakes Fabi for the first time

*Round 4 predictions:*
- Esipenko–Anish: **42.9%** / 30.3% / 26.8% — Esipenko favoured
- Wei Yi–Hikaru: **40.9%** / 30.5% / 28.7% — Wei Yi slight edge
- Sindarov–Fabi: **41.8%** / 30.7% / 27.5% — Sindarov slight favourite
- Bluebaum–Pragg: 33.9% / 31.4% / **34.7%** — near coin-flip, marginal Pragg edge

</details>

<details>
<summary>Round 3</summary>

![Round 3](results/candidates2026/r3.png)

*Round 2 results: ALL FOUR games drew — Esipenko–Hikaru, Anish–Fabi, Wei Yi–Pragg, Sindarov–Bluebaum*

- ✗ **All 4 Round 2 games drew** — model had the expected leader winning in each (Esipenko 40.2%, Fabi 39.7%, Wei Yi 44.7%, Sindarov 47.6%)
- Early-round draws are consistently underestimated; with no score pressure yet, all-draw rounds are plausible
- Win probs barely shift (Fabi 31.3%, Sindarov 23.0%, Pragg 15.0%) — stable, all leaders drew

*Round 3 predictions:*
- Bluebaum–Esipenko: **53.3%** / 28.1% / 18.6% — Bluebaum strongly favoured; R1 win at very low prior creates an outsized strength estimate
- Pragg–Sindarov: **39.7%** / 30.5% / 29.8% — Pragg slight edge as White despite Sindarov's R1 win
- Fabi–Wei Yi: **51.1%** / 28.6% / 20.3% — Fabi strongly favoured
- Hikaru–Anish: **51.6%** / 28.2% / 20.2% — Hikaru strongly favoured

</details>

<details>
<summary>Round 2</summary>

![Round 2](results/candidates2026/r2.png)

*Round 1 results: Fabi beat Hikaru, Pragg beat Anish, Bluebaum–Wei Yi drew, Sindarov beat Esipenko*

- ✓ **Fabi beat Hikaru** — model's top pick (40.7%), correct
- ✓ **Sindarov beat Esipenko** — strongly predicted (44.2%), correct
- ✓ **Bluebaum–Wei Yi drew** — model near-even (35.6%/33.4%), draw fine
- ✗ **Pragg beat Anish** — model had Anish at 39.0%; Pragg punching above his pre-tournament rating
- All three R1 winners jump sharply: Fabi 18.9% → **30.5%**, Sindarov 15.3% → **25.0%**, Pragg 6.6% → **12.7%** — very low priors amplify single-game results immediately

*Round 2 predictions:*
- Esipenko–Hikaru: **40.2%** / 30.3% / 29.5% — Esipenko now favoured (flipped from pre-R1); low priors absorb Hikaru's R1 loss aggressively
- Anish–Fabi: 29.5% / 30.9% / **39.7%** — Fabi favoured
- Wei Yi–Pragg: **44.7%** / 30.1% / 25.2% — Wei Yi favoured
- Sindarov–Bluebaum: **47.6%** / 29.3% / 23.0% — Sindarov boosted further by R1 win

</details>

<details>
<summary>Round 1</summary>

![Round 1](results/candidates2026/r1.png)

*Pre-tournament predictions*

- **Fabi** is the favourite at **18.9%** despite not having the highest classical Elo (Hikaru leads at 2810 vs Fabi's 2793) — stable rating history across all three time controls gives a consistent overall profile
- **Hikaru at only 13.8%** despite the highest classical Elo — his rapid/blitz velocity trends are weaker, and his classical rating is flat [2813→2810]
- **Sindarov at 15.3%** with only 2745 Elo — strongly rising classical trend [2721→2745, +24 pts] and improving rapid history [2688→2727]; the model rewards recent momentum
- **Bluebaum at 12.7%** for a 2695-rated player — positive classical trend [2680→2695] and no rapid/blitz history, so no drag from weaker secondary time controls
- **Pragg at only 6.6%** despite his FIDE ranking — classical rating has been **falling** [2768→2741, −27 pts]; the model tracks the trend, not the name

*Round 1 predictions:*
- Fabi–Hikaru: **40.7%** / 30.9% / 28.4% — Fabi slight favourite
- Pragg–Anish: 30.1% / 30.9% / **39.0%** — Anish favoured
- Bluebaum–Wei Yi: **35.6%** / 31.0% / 33.4% — near coin-flip
- Sindarov–Esipenko: **44.2%** / 30.2% / 25.5% — Sindarov clear favourite

</details>

## Features

- **Dynamic Bayesian ratings** — a 2N anchored MAP estimator maintains separate White and Black latent strengths per player, updated every round
- **Parametric draw model** — draw probability proportional to ν·√(λW·λB), where ν is a time-control-specific tuning parameter (`classical_nu`, `rapid_nu`, `blitz_nu`)
- **Style multiplier** — each player has Bayesian-smoothed White/Black aggression scores (fraction of decisive games); ν is scaled by `baselineAgg / matchAgg`, shrinking the draw band when both players play sharply and inflating it when they play solidly
- **Standings multiplier** — ν is scaled by each player's *motivation*, then averaged. Motivation is computed from `R = deficit / roundsLeft` (points needed as a fraction of points still available): leaders (R ≤ 0) play at baseline (×1.0); contenders (0 < R < 0.75) get a desperation boost that peaks at R = 0.375 (multiplier ≈ `1 − standings_aggression`); near-eliminated or fully eliminated players (R ≥ 0.75) widen their draw band up to `1 + 1.5 × standings_aggression` as they relax pressure
- **Color bleed** — aggression and rating form cross-pollinate between colors: a player's White aggression is informed slightly by their Black results and vice versa; λW/λB are also geometrically blended after each MAP update and rescaled to prevent drift
- **Velocity projection** — per-player rating trends across all three time controls are estimated via time-decayed weighted least-squares regression; projected ratings initialize λW/λB, with rapid/blitz deltas blended in via `rapid_form_weight` and `blitz_form_weight`
- **Time control support** — uses Classical, Rapid, or Blitz ratings for the appropriate stage
- **FIDE 2026 playoff rules** — tiebreaks follow the official Rapid → Blitz → Sudden-death knockout sequence (Regulation 4.4.2)
- **Parallel simulation** — work is distributed across all hardware threads via `std::thread`

## Build

```bash
g++ -O3 -march=native -std=c++17 -pthread src/chess_montecarlo.cpp -o bin/chess_montecarlo
```

Requires a C++17-capable compiler. The only dependency is [`json.hpp`](https://github.com/nlohmann/json) (included in `src/`).

## Usage

```bash
./bin/chess_montecarlo [hyperparameters.json] [tournament.json] [simulate_from_round]
```

Both files default to their names in the current directory. `simulate_from_round` must be passed as a CLI argument. Output is printed to stdout.

Redirect to a file to feed into the visualizer:

```bash
./bin/chess_montecarlo configs/hyperparameters.json data/candidates2026.json 8 > results/candidates2026/rounds/round8.txt
```

## JSON format

### `configs/hyperparameters.json`

```jsonc
{
  // ── Simulation ───────────────────────────────────────────────────────────
  "runs": 1000000,
  "map_iters": 100,
  "map_tolerance": 1e-8,

  // ── MAP prior weights ────────────────────────────────────────────────────
  "prior_weight": 1.0,           // sets both known and sim; override individually below
  "prior_weight_known": 0.5,
  "prior_weight_sim": 2.0,

  // ── Rating initialization & velocity ────────────────────────────────────
  "initial_white_adv": 35.0,     // Elo points of White advantage split ±17.5 per side
  "velocity_time_decay": 0.95,
  "lookahead_factor": 1.0,

  // ── Cross-time-control blending ──────────────────────────────────────────
  "rapid_form_weight": 0.25,
  "blitz_form_weight": 0.15,
  "color_bleed": 0.20,

  // ── Draw model ───────────────────────────────────────────────────────────
  "classical_nu": 2.5,
  "rapid_nu": 1.5,
  "blitz_nu": 0.8,

  // ── Aggression & overpush ────────────────────────────────────────────────
  "agg_prior_weight": 3.0,
  "default_aggression_w": 0.30,
  "default_aggression_b": 0.10,
  "standings_aggression": 0.15
}
```

### `data/candidates2026.json`

```jsonc
{
  "players": [
    {
      "fide_id": 2020009,
      "name": "Caruana, Fabiano",
      "rating": 2793,
      "rapid_rating": 2727,             // optional, falls back to rating
      "blitz_rating": 2749,             // optional, falls back to rating
      "aggression_w": 0.25,             // optional, prior decisive-game fraction as White
      "aggression_b": 0.15,             // optional, prior decisive-game fraction as Black
      "history": [2780, 2790, 2793],    // optional, classical rating history for velocity (oldest → newest)
      "games_played": [10, 12, 11],     // optional, game counts per history entry (used as weights)
      "rapid_history": [2720, 2727],    // optional, rapid rating history
      "rapid_games_played": [8, 9],     // optional, rapid game counts per history entry
      "blitz_history": [2740, 2749],    // optional, blitz rating history
      "blitz_games_played": [15, 14]    // optional, blitz game counts per history entry
    }
    // ... 7 more players (exactly 8 required)
  ],
  "schedule": [
    { "white": 2020009, "black": 2016192, "result": "1-0"     }, // known game
    { "white": 2020009, "black": 2016192, "result": "1/2-1/2" }, // known game
    { "white": 2020009, "black": 2016192 }                       // future game (no result)
  ]
}
```

Games are grouped into rounds of 4 (`N/2`). Games with a `result` are treated as known history up to `simulate_from_round` (passed via CLI); games from that round onward are simulated.

## Building tournament data

`scripts/build_tournament.py` downloads games from a Lichess broadcast, fetches FIDE rating history, and writes a ready-to-use tournament JSON file.

```bash
pip install requests python-chess

# Build from a Lichess broadcast ID or URL
python scripts/build_tournament.py wEuVhT9c -o data/my_tournament.json

# Slice FIDE history to a specific month 
python scripts/build_tournament.py wEuVhT9c --as-of 2024-04 -o data/candidates2024.json

# Skip FIDE history fetch (uses ratings from PGN headers only)
python scripts/build_tournament.py wEuVhT9c --no-fide

# Control how many monthly history periods to fetch (default: 6)
python scripts/build_tournament.py wEuVhT9c --periods 8
```

## Hyperparameter tuning

`tune.py` uses [Optuna](https://optuna.org) to search for the best model parameters.

```bash
pip install optuna

# Run 200 trials on a single tournament (always resumes an existing study automatically)
python tune.py configs/hyperparameters.json data/candidates2024.json

# Run against multiple tournaments simultaneously (scores are averaged)
python tune.py configs/hyperparameters.json data/candidates2024.json data/candidates2026.json

# Fewer trials
python tune.py configs/hyperparameters.json data/candidates2024.json --trials 50

# Custom binary or database path
python tune.py configs/hyperparameters.json data/candidates2024.json \
    --binary ./bin/chess_montecarlo \
    --db db/tuning_2024.db
```

**Evaluation strategy — multi-objective progressive round scoring:** for each round K with known results, the binary is run with `simulate_from_round = K` so rounds 1…K−1 are treated as history and rounds K onward are the held-out predictions. Two independent objectives are minimized simultaneously:

1. **Weighted Game Brier Score** — multi-class Brier score (`(pw − actual_w)² + (pd − actual_d)² + (pb − actual_b)²`) over all predicted games, decay-weighted by `FUTURE_DECAY_WEIGHT^distance` for games further in the future. Decisive outcomes (wins/losses) are up-weighted by `DECISIVE_GAME_WEIGHT` to combat the lazy-draw problem. Each round's score is normalized by its own weight sum.

2. **Winner Brier Score** — Brier score over tournament win probability predictions.

Both objectives are accumulated **weighted by round number** (`score × r / Σr`): a prediction error at round 13 counts 13× more than one at round 1, reflecting that you should be increasingly accurate as more results are known. When multiple tournament files are supplied, each is evaluated independently and the two objectives are averaged across tournaments before being returned to Optuna.

Optuna returns a **Pareto front** of trials offering unique trade-offs between the two objectives. `EVAL_RUNS` at the top of the script controls Monte Carlo iterations per trial (default 10 000 — fast; raise to 200 000+ for a final search).

Results are stored in `db/`. To inspect the Pareto front:

```bash
# Interactive scatter plot + console table (defaults to db/tuning_2024.db, study chess_montecarlo)
python scripts/pareto_front.py

# Custom database or study name
python scripts/pareto_front.py db/tuning_2024.db chess_montecarlo

# Save plot to file instead of showing it
python scripts/pareto_front.py --save results/pareto.png
```

The plot shows all completed trials as blue-gradient dots (darker = later trial), Pareto-optimal trials as highlighted points connected by a staircase line, and each optimal trial's number as a label. The console table prints all 15 parameters for each Pareto-optimal trial, sorted by combined objective score.

**Example (2024 Candidates — 5 700 trials):**

![Pareto Front](results/pareto/tuning_24.png)

The Optuna #1 ranked trial from this front (Trial 5617, Game Brier: 0.2989, Winner Brier: 0.2424) is saved as `configs/best_hparams_24.json`.

**Example (2022 + 2024 Candidates — 1 000 trials):**

![Pareto Front](results/pareto/tuning_22_24.png)

Trial 1272 (#2 on the combined Pareto front, Game Brier: 0.3025, Winner Brier: 0.2015) is saved as `configs/best_hparams_22_24.json` and used for the 2026 Candidates predictions.

### Config comparison: `best_hparams_24.json` vs `best_hparams_22_24.json`

| Parameter | 2024-only | 2022+2024 | Effect |
|---|---|---|---|
| `prior_weight_known/sim` | 16.3 / 20.0 | 0.60 / 0.60 | 2022+2024 is far more reactive — one win can nearly double a player's win probability |
| `classical_nu` | 0.818 | 0.906 | 2022+2024 predicts more draws in classical games |
| `rapid_nu` | 0.586 | 0.824 | 2022+2024 predicts many more draws in rapid tiebreaks |
| `initial_white_adv` | 8.6 Elo | 17.3 Elo | 2022+2024 gives substantially more weight to the White color advantage |
| `standings_aggression` | 0.204 | 0.033 | 2024-only has stronger desperation/over-pressing effects |
| `velocity_time_decay` | 0.555 | 0.795 | 2022+2024 weights older rating history more evenly |

The 2022+2024 model converges much more aggressively once a player builds a lead, and its pre-tournament probabilities are more compressed (Elo differences matter less when priors are weak). Adding 2022 Candidates data appears to support a higher draw rate and stronger White advantage.

## Visualization

Requires Python with `matplotlib`, `pandas`, and `numpy`.

```bash
python scripts/visualize_timeline.py results/candidates2026/rounds/
```

Reads all `round{N}.txt` files in the given directory and produces a dashboard PNG showing:

- Win probability timeline across rounds
- Current win % bar chart
- Per-round match prediction breakdowns (with actual results highlighted in gold)

```bash
python scripts/visualize_timeline.py results/candidates2026/rounds/ -o my_output.png  # custom output path
python scripts/visualize_timeline.py results/candidates2026/rounds/ -k 5              # only show up to round 5
```

Output is saved as `round{N}.png` in the input directory by default.

## How the model works

Each player has two latent strengths: λW (White) and λB (Black). Before any games are played, these are initialized from a projected rating derived from FIDE ratings ± 17.5 Elo (half of `initial_white_adv`).

**Rating velocity and form anchor:** if a player has rating history entries (`history`, `rapid_history`, `blitz_history`), the simulator fits a time-decayed weighted least-squares slope to estimate a velocity (rating points per period). The initial λW/λB are anchored to `projC + speedAdj`, where `projC = classical_rating + velC × lookahead_factor` and `speedAdj = rapid_form_weight × (projR − projC) + blitz_form_weight × (projB − projC)`. This lets rapid and blitz trends inform the classical form anchor.

After each round, the simulator updates λW and λB in three steps:

1. **MAP fixed-point iteration** — solves the anchored Bradley-Terry MAP equations given all games played so far. The prior pulls each λ back toward its initial value (strength controlled by `prior_weight_known` for historical rounds, `prior_weight_sim` for simulated rounds). Early upsets shift the posterior, revising expectations for future rounds.

2. **Geometric form blending (color bleed)** — a player's relative form as White (λW / λW₀) is blended with their relative form as Black (λB / λB₀), and vice versa, using a weighted geometric mean controlled by `color_bleed`. This lets a player who has been performing well in general also benefit slightly across both colors.

3. **Population rescaling** — the geometric mean of all λ values is kept equal to the initial baseline, preventing floating-point drift over many rounds.

Win and draw probabilities for a game between White player w and Black player b are:

```
p_win  = λW[w] / Z
p_draw = ν · √(λW[w] · λB[b]) / Z
p_loss = λB[b] / Z
```

where Z is the normalizing sum and ν is the time-control draw-rate parameter.

**Draw band scaling:** before each classical game, ν is scaled by two independent multipliers:

1. **Style multiplier** — `baselineAgg / matchAgg`, where `matchAgg` is the average Bayesian-smoothed aggression (decisive-game fraction, cross-pollinated via `color_bleed`) of both players. Aggressive pairings shrink the draw band; solid pairings widen it.

2. **Standings multiplier** — each player's motivation is computed from `R = (leaderPoints − playerPoints) / roundsLeft`:
   - **R ≤ 0** (leader): motivation = 1.0 (standard play)
   - **0 < R < 0.75** (contender): motivation = `1 − standings_aggression × (1 − |R − 0.375| / 0.375)`, which peaks in desperation at R = 0.375 (roughly half the remaining points needed)
   - **R ≥ 0.75** (near/fully eliminated): motivation = `1 + 1.5 × standings_aggression × clamp((R − 0.75) / 0.25)`, widening the draw band as the player relaxes

   The final multiplier is the average of both players' motivation values.
