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

*Round 7 results: Wei Yi beat Esipenko, Sindarov–Giri drew, Bluebaum–Nakamura drew, Pragg–Caruana drew*

- ✓ **Wei Yi beat Esipenko** — model had Wei Yi at 43.6%, correct
- ✓ **Bluebaum–Nakamura drew** — model near-even (37.5%/36.2%), reasonable
- ✗ **Sindarov–Giri drew** — model had Sindarov at 43.3%; with a commanding lead Sindarov has no reason to press
- ✗ **Pragg–Caruana drew** — model had Caruana at 47.8%; Caruana unable to convert yet again in a must-win situation
- Sindarov's win prob **increases** to 75.4% despite only drawing in R7 — his 1.5-point lead means draws are now strategically optimal

*Round 8 predictions:*
- Esipenko–Sindarov: 24.6% / 26.4% / **49.0%** — Sindarov heavy favourite as Black
- Wei Yi–Bluebaum: 37.2% / 26.6% / 36.2% — essentially a coin flip
- Giri–Pragg: **43.8%** / 25.9% / 30.3% — Giri favoured
- Nakamura–Caruana: 33.8% / 26.5% / **39.7%** — Caruana slight favourite

</details>

<details>
<summary>Round 7</summary>

![Round 7](results/candidates2026/r7.png)

*Round 6 results: Caruana–Esipenko drew, Nakamura–Pragg drew, Giri–Bluebaum drew, Sindarov beat Wei Yi*

- ✓ **Sindarov beat Wei Yi** — model predicted (39.7%), correct
- ✓ **Giri–Bluebaum drew** — model near-even (37.1%/36.5%), fine
- ✗ **Caruana–Esipenko drew** — model's biggest miss: Caruana was a **53% favourite** for a win against a 2698-rated opponent; Caruana's repeated failure to convert against lower-rated players is the tournament's central story
- ✗ **Nakamura–Pragg drew** — model had Nakamura at 45.3%
- Win probs: Sindarov **72.6%**, Caruana 20.9%

*Round 7 predictions:*
- Esipenko–Wei Yi: 31.2% / 25.2% / **43.6%** — Wei Yi favoured
- Sindarov–Giri: **43.3%** / 26.7% / 30.0% — Sindarov favoured
- Bluebaum–Nakamura: 37.5% / 26.3% / 36.2% — near coin-flip
- Pragg–Caruana: 27.4% / 24.8% / **47.8%** — Caruana strong favourite

</details>

<details>
<summary>Round 6</summary>

![Round 6](results/candidates2026/r6.png)

*Round 5 results: Pragg–Esipenko drew, Caruana beat Bluebaum, Sindarov beat Nakamura, Giri–Wei Yi drew*

- ✓ **Caruana beat Bluebaum** — model predicted (43.6%), correct
- ✓ **Sindarov beat Nakamura** — model had Sindarov as slight favourite (37.6%), correct
- ✓ **Pragg–Esipenko drew** — model near-even (37.6%/35.9%), draw is the natural outcome
- ✓ **Giri–Wei Yi drew** — model near-even (37.1%/36.4%), correct
- Best round for the model — all 4 outcomes matched; win probs: Sindarov **56.8%**, Caruana 30.9%

*Round 6 predictions:*
- Caruana–Esipenko: **53.0%** / 24.6% / 22.4% — Caruana strong favourite
- Nakamura–Pragg: **45.3%** / 25.5% / 29.2% — Nakamura favoured
- Giri–Bluebaum: 37.1% / 26.4% / 36.5% — near coin-flip
- Wei Yi–Sindarov: 32.9% / 27.4% / **39.7%** — Sindarov slight favourite

</details>

<details>
<summary>Round 5</summary>

![Round 5](results/candidates2026/r5.png)

*Round 4 results: Giri beat Esipenko, Wei Yi–Nakamura drew, Sindarov beat Caruana, Bluebaum–Pragg drew*

- ✓ **Giri beat Esipenko** — model had Giri at 39.5%, correct
- ✓ **Wei Yi–Nakamura drew** — model near-even (37.2%/35.2%), draw reasonable
- ✗ **Sindarov beat Caruana** — model had Caruana as marginal favourite (36.1% vs 34.7%); **the tournament's turning point** — Sindarov opens a 1-point lead for the first time
- ✗ **Bluebaum–Pragg drew** — model had Bluebaum at 44.7%, another expected win becoming a draw
- Win probability flips: Sindarov 23.6% → **46.9%**, Caruana 33.8% → 26.7%

*Round 5 predictions:*
- Pragg–Esipenko: 37.2% / 26.9% / 35.9% — near coin-flip, slight Pragg edge
- Caruana–Bluebaum: **43.1%** / 27.6% / 29.3% — Caruana favoured
- Nakamura–Sindarov: 34.8% / 27.3% / **37.9%** — Sindarov slight favourite
- Giri–Wei Yi: 36.8% / 26.3% / 36.9% — near coin-flip

</details>

<details>
<summary>Round 4</summary>

![Round 4](results/candidates2026/r4.png)

*Round 3 results: Bluebaum–Esipenko drew, Sindarov beat Pragg, Caruana beat Wei Yi, Nakamura–Giri drew*

- ✓ **Sindarov beat Pragg** — model predicted (43.8%), correct
- ✓ **Caruana beat Wei Yi** — model predicted (42.4%), correct
- ✗ **Bluebaum–Esipenko drew** — model had Bluebaum at 44.2%; another expected win becomes a draw
- ✗ **Nakamura–Giri drew** — model had Nakamura at 40.8%, same pattern; early draws are consistently underestimated
- Win probs: Caruana **33.8%**, Sindarov 23.6% — both leaders won so their relative order holds

*Round 4 predictions:*
- Esipenko–Giri: 33.0% / 27.4% / **39.6%** — Giri slight favourite
- Wei Yi–Nakamura: **37.0%** / 27.9% / 35.1% — near coin-flip, Wei Yi marginal edge
- Sindarov–Caruana: 34.9% / 28.7% / **36.4%** — near coin-flip, slight Caruana edge
- Bluebaum–Pragg: **44.5%** / 27.3% / 28.1% — Bluebaum favoured

</details>

<details>
<summary>Round 3</summary>

![Round 3](results/candidates2026/r3.png)

*Round 2 results: ALL FOUR games drew — Esipenko–Nakamura, Giri–Caruana, Wei Yi–Pragg, Sindarov–Bluebaum*

- ✗ **All 4 Round 2 games drew** — model had the higher-rated player winning in each: Nakamura 42.6%, Caruana 41.1%, Wei Yi 44.8%, Sindarov 40.1%
- Early-round draws are systematically underestimated; no score pressure yet, players play solidly
- Win probs barely shift (Caruana 33.8%, Sindarov 23.6%) — correct, since both leaders drew

*Round 3 predictions:*
- Bluebaum–Esipenko: **44.3%** / 27.8% / 28.0% — Bluebaum favoured
- Pragg–Sindarov: 27.9% / 28.2% / **43.8%** — Sindarov favoured
- Caruana–Wei Yi: **42.4%** / 27.8% / 29.8% — Caruana favoured
- Nakamura–Giri: **40.8%** / 26.9% / 32.2% — Nakamura favoured

</details>

<details>
<summary>Round 2</summary>

![Round 2](results/candidates2026/r2.png)

*Round 1 results: Caruana beat Nakamura, Pragg beat Giri, Bluebaum–Wei Yi drew, Sindarov beat Esipenko*

- ✓ **Caruana beat Nakamura** — model's top pick (40.4%), correct
- ✓ **Sindarov beat Esipenko** — strongly predicted (46.1%), correct
- ✓ **Bluebaum–Wei Yi drew** — model near-even (36.6%/35.1%), draw is reasonable
- ✗ **Pragg beat Giri** — model had Giri at 41.4%; Pragg punching above his pre-tournament rating
- Pragg wins but only moves 3.6% → 6.0% — low prior absorbs results slowly; Giri drops from 10.2% → 4.8%

*Round 2 predictions:*
- Esipenko–Nakamura: 30.4% / 27.8% / **41.9%** — Nakamura favoured
- Giri–Caruana: 30.5% / 28.3% / **41.1%** — Caruana favoured
- Wei Yi–Pragg: **44.8%** / 27.7% / 27.5% — Wei Yi favoured
- Sindarov–Bluebaum: **40.1%** / 27.9% / 32.0% — Sindarov favoured

</details>

<details>
<summary>Round 1</summary>

![Round 1](results/candidates2026/r1.png)

*Pre-tournament predictions*

- **Caruana** is the favourite at **24.4%** despite not having the highest classical Elo (Nakamura leads at 2810 vs Caruana's 2793) — stable flat rating history and balanced overall profile
- **Nakamura at only 15.0%** despite the highest classical Elo — his rapid/blitz velocity parameters slightly dampen his classical projection; his rating is stable-to-declining [2813→2810]
- **Sindarov at 17.7%** with only 2745 Elo — strongly rising classical trend [2721→2745, +24 pts] and improving rapid history [2688→2727]; the model rewards momentum
- **Bluebaum at 11.7%** seems elevated for a 2695-rated player — positive classical trend [2680→2695] and no rapid/blitz data, so no penalty for potential weakness there
- **Pragg at 3.6%** despite his FIDE ranking — classical rating has been **falling** [2768→2741, −27 pts]; the model tracks the downtrend, not the name

*Round 1 predictions:*
- Caruana–Nakamura: **40.4%** / 28.8% / 30.8% — Caruana slight favourite
- Pragg–Giri: 30.5% / 28.1% / **41.4%** — Giri favoured
- Bluebaum–Wei Yi: 36.6% / 28.3% / 35.1% — near coin-flip
- Sindarov–Esipenko: **46.1%** / 27.4% / 26.5% — Sindarov clear favourite

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

The Optuna #1 ranked trial from this front (Trial 5617, Game Brier: 0.2989, Winner Brier: 0.2424) is saved as `configs/best_hparams_24.json` and used as the base config for the 2026 Candidates predictions.

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
