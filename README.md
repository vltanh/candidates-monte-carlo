# Chess Monte Carlo Simulation

A multi-threaded Monte Carlo simulator for chess tournaments with a fixed schedule. Models dynamic per-player ratings that update as games are played, then runs millions of simulated completions to estimate win probabilities.

## 2026 Candidates: Live Predictions

![Animation](results/candidates2026/animation.gif)

<!-- Add new rounds here (most recent first): copy the <details> block and update the round number and image path -->

<details>
<summary>Round 9 (latest)</summary>

![Round 9](results/candidates2026/r9.png)

*Round 8 results: Esipenko–Sindarov drew, Wei Yi–Bluebaum drew, Anish beat Pragg, Hikaru beat Fabi*

- ✓ **Wei Yi–Bluebaum drew**: draw predicted at 47.4%; correct prediction
- ✗ **Esipenko–Sindarov drew**: Sindarov win predicted at 41.2% over draw at 40.8%; Sindarov drew; a leader with Black and a near-insurmountable lead has every incentive to play for safety, which the model's standing-based draw multiplier only partially captures
- ✗ **Anish beat Pragg**: draw predicted at 51.2%; Anish won; the model correctly placed Anish's winning chances (28.6%) above Pragg's (20.2%)
- ✗ **Hikaru beat Fabi**: draw predicted at 47.4%; Hikaru won; the model gave Hikaru an extremely marginal win edge (26.33% vs 26.27%); effectively no directional signal
- Win probs: Sindarov climbed to **85.8%** (from 80.6%); Fabi dropped sharply to **8.3%** (from 15.9%) after the loss; Anish rose to **4.0%** (from 1.5%) after the win

*Round 9 predictions:*
- Hikaru–Esipenko: 34.9% / **45.5%** / 19.6%, draw most likely; Hikaru with higher winning chances
- Fabi–Anish: 38.5% / **40.5%** / 21.0%, draw most likely; Fabi with higher winning chances; key duel for second place
- Pragg–Wei Yi: 25.3% / **43.9%** / 30.9%, draw most likely; Wei Yi with higher winning chances
- Bluebaum–Sindarov: 21.0% / **46.3%** / 32.7%, draw most likely; Sindarov with higher winning chances

</details>

<details>
<summary>Round 8</summary>

![Round 8](results/candidates2026/r8.png)

*Round 7 results: Wei Yi beat Esipenko, Sindarov–Anish drew, Bluebaum–Hikaru drew, Pragg–Fabi drew*

- ✓ **Sindarov–Anish drew**: draw predicted at 43.4%; correct prediction
- ✓ **Bluebaum–Hikaru drew**: draw predicted at 49.4%; correct prediction
- ✓ **Pragg–Fabi drew**: draw predicted at 44.4%; correct prediction
- ✗ **Wei Yi beat Esipenko**: draw predicted at 46.2%; Wei Yi won; the model correctly placed Wei Yi's winning chances (30.1%) above Esipenko's (23.7%)
- Sindarov barely moved: **80.6%** (from 78.8%); drawing cost almost nothing with the lead this large; Fabi slipped to **15.9%** (from 16.8%)

*Round 8 predictions:*
- Esipenko–Sindarov: 18.0% / 40.8% / **41.2%**, Sindarov win the top prediction; Esipenko at 2/7 was an extreme underdog
- Wei Yi–Bluebaum: 28.5% / **47.4%** / 24.1%, draw most likely; Wei Yi with higher winning chances
- Anish–Pragg: 28.6% / **51.2%** / 20.2%, draw most likely; Anish with higher winning chances
- Hikaru–Fabi: 26.3% / **47.4%** / 26.3%, draw most likely; perfectly balanced; Fabi needs a win to stay alive

</details>

<details>
<summary>Round 7</summary>

![Round 7](results/candidates2026/r7.png)

*Round 6 results: Fabi–Esipenko drew, Hikaru–Pragg drew, Anish–Bluebaum drew, Sindarov beat Wei Yi*

- ✓ **Hikaru–Pragg drew**: draw predicted at 48.1%; correct prediction
- ✓ **Anish–Bluebaum drew**: draw predicted at 48.7%; correct prediction
- ✗ **Fabi–Esipenko drew**: Fabi win predicted at 43.6% with draw at 40.5%; the game ended in a draw; Fabi's inability to convert against lower-rated players is the central story
- ✗ **Sindarov beat Wei Yi**: draw predicted at 47.3%; Sindarov won; the model correctly placed Sindarov's winning chances (29.7%) above Wei Yi's (23.1%)
- Win probs: Sindarov surged to **78.8%** (from 62.2%) while Fabi dropped to **16.8%** (from 28.1%); Fabi's draw combined with Sindarov's win collapsed the race

*Round 7 predictions:*
- Esipenko–Wei Yi: 23.7% / **46.2%** / 30.1%, draw most likely; Wei Yi with higher winning chances
- Sindarov–Anish: 34.5% / **43.4%** / 22.1%, draw most likely; Sindarov with higher winning chances
- Bluebaum–Hikaru: 24.0% / **49.4%** / 26.6%, draw most likely; Hikaru with slight win edge
- Pragg–Fabi: 23.1% / **44.4%** / 32.6%, draw most likely; Fabi with higher winning chances; needs points to stay in contention

</details>

<details>
<summary>Round 6</summary>

![Round 6](results/candidates2026/r6.png)

*Round 5 results: Pragg–Esipenko drew, Fabi beat Bluebaum, Sindarov beat Hikaru, Anish–Wei Yi drew*

- ✓ **Pragg–Esipenko drew**: draw predicted at 44.8%; correct prediction
- ✓ **Anish–Wei Yi drew**: draw predicted at 48.5%; correct prediction
- ✗ **Fabi beat Bluebaum**: draw predicted at 46.3%; Fabi won; the model correctly placed Fabi's winning chances (35.4%) above Bluebaum's (18.3%)
- ✗ **Sindarov beat Hikaru**: draw predicted at 49.4%; Sindarov won despite Hikaru having the marginal win edge (25.6% vs 25.0%); wrong direction by the narrowest margin
- Win probs: Sindarov extended his lead to **62.2%** (from 51.1%), Fabi recovered slightly to **28.1%** (from 24.9%); Sindarov's 4.5/5 gave him commanding odds

*Round 6 predictions:*
- Fabi–Esipenko: **43.6%** / 40.5% / 15.8%, Fabi win the top prediction; model expected him to capitalize on the rating gap and close on Sindarov
- Hikaru–Pragg: 31.8% / **48.1%** / 20.1%, draw most likely; Hikaru with higher winning chances
- Anish–Bluebaum: 28.9% / **48.7%** / 22.4%, draw most likely; Anish with higher winning chances
- Wei Yi–Sindarov: 23.1% / **47.3%** / 29.7%, draw most likely; Sindarov with higher winning chances

</details>

<details>
<summary>Round 5</summary>

![Round 5](results/candidates2026/r5.png)

*Round 4 results: Anish beat Esipenko, Wei Yi–Hikaru drew, Sindarov beat Fabi, Bluebaum–Pragg drew*

- ✓ **Wei Yi–Hikaru drew**: draw predicted at 49.3%; correct prediction
- ✓ **Bluebaum–Pragg drew**: draw predicted at 51.9%; correct prediction
- ✗ **Sindarov beat Fabi**: draw predicted at 50.8%; Sindarov won; the model barely placed Sindarov's winning chances (25.2%) above Fabi's (24.0%); **the tournament's turning point** as Sindarov opened a 1-point lead
- ✗ **Anish beat Esipenko**: draw predicted at 49.2%; Anish won; the model correctly placed Anish's winning chances (26.5%) above Esipenko's (24.3%)
- Win probs swung sharply: Sindarov surged to **51.1%** (from 32.0%) while Fabi collapsed to **24.9%** (from 44.1%); Sindarov now a clear favourite at 3.5/4

*Round 5 predictions:*
- Pragg–Esipenko: 30.5% / **44.8%** / 24.7%, draw most likely; Pragg with higher winning chances
- Fabi–Bluebaum: 35.4% / **46.3%** / 18.3%, draw most likely; Fabi with higher winning chances; key bounce-back opportunity after R4 loss
- Hikaru–Sindarov: 25.6% / **49.4%** / 25.0%, draw most likely; near three-way split
- Anish–Wei Yi: 27.9% / **48.5%** / 23.5%, draw most likely; Anish with higher winning chances after R4 win

</details>

<details>
<summary>Round 4</summary>

![Round 4](results/candidates2026/r4.png)

*Round 3 results: Bluebaum–Esipenko drew, Sindarov beat Pragg, Fabi beat Wei Yi, Hikaru–Anish drew*

- ✓ **Bluebaum–Esipenko drew**: draw predicted at 49.2%; correct prediction
- ✓ **Hikaru–Anish drew**: draw predicted at 47.9%; correct prediction
- ✗ **Fabi beat Wei Yi**: draw predicted at 48.8%; Fabi won; the model correctly placed Fabi's winning chances (31.6%) above Wei Yi's (19.6%)
- ✗ **Sindarov beat Pragg**: draw predicted at 49.8%; Sindarov won; the model correctly placed Sindarov's winning chances (28.1%) above Pragg's (22.1%)
- Win probs surged for both winners: Fabi jumped to **44.1%** (from 33.3%), Sindarov climbed to **32.0%** (from 23.0%); Fabi led despite equal standing, and the model weighed opponent quality

*Round 4 predictions:*
- Esipenko–Anish: 24.3% / **49.2%** / 26.5%, draw most likely; Anish with slight win edge
- Wei Yi–Hikaru: 25.8% / **49.3%** / 24.9%, draw most likely; essentially even
- Sindarov–Fabi: 25.2% / **50.8%** / 24.0%, draw most likely; essentially even; the key clash between the top two
- Bluebaum–Pragg: 27.2% / **51.9%** / 20.9%, draw most likely; Bluebaum with higher winning chances

</details>

<details>
<summary>Round 3</summary>

![Round 3](results/candidates2026/r3.png)

*Round 2 results: ALL FOUR games drew: Esipenko–Hikaru, Anish–Fabi, Wei Yi–Pragg, Sindarov–Bluebaum*

- ✓ **Esipenko–Hikaru drew**: draw predicted at 48.8%; correct prediction
- ✓ **Anish–Fabi drew**: draw predicted at 51.6%; correct prediction
- ✓ **Wei Yi–Pragg drew**: draw predicted at 50.9%; correct prediction
- ✓ **Sindarov–Bluebaum drew**: draw predicted at 49.0%; correct prediction
- Win probs barely shifted after four draws: Fabi held at **33.3%** (from 32.4%), Sindarov slipped to **23.0%** (from 23.5%), Pragg ticked up to **10.6%** (from 9.7%)

*Round 3 predictions:*
- Bluebaum–Esipenko: 30.5% / **49.2%** / 20.3%, draw most likely; Bluebaum with higher winning chances; Esipenko's R1 loss widened the rating gap
- Pragg–Sindarov: 22.1% / **49.8%** / 28.1%, draw most likely; Sindarov with higher winning chances as his R1 win carries forward
- Fabi–Wei Yi: 31.6% / **48.8%** / 19.6%, draw most likely; Fabi with higher winning chances as the pre-tournament front-runner
- Hikaru–Anish: 31.6% / **47.9%** / 20.5%, draw most likely; Hikaru with higher winning chances as White despite R1 loss

</details>

<details>
<summary>Round 2</summary>

![Round 2](results/candidates2026/r2.png)

*Round 1 results: Fabi beat Hikaru, Sindarov beat Esipenko, Pragg beat Anish, Bluebaum–Wei Yi drew*

- ✗ **Fabi beat Hikaru**: draw predicted at 51.9%; Fabi won; the model correctly placed Fabi's winning chances (26.5%) above Hikaru's (21.5%)
- ✗ **Sindarov beat Esipenko**: draw predicted at 50.5%; Sindarov won; the model correctly placed Sindarov's winning chances (31.8%) above Esipenko's (17.7%)
- ✓ **Bluebaum–Wei Yi drew**: draw predicted at 51.5%; correct prediction
- ✗ **Pragg beat Anish**: draw predicted at 51.6%; Pragg won despite Anish having higher winning chances (26.5% vs 21.9%); wrong direction
- All three R1 winners jumped sharply: Fabi 21.5% → **32.4%**, Sindarov 16.1% → **23.5%**, Pragg 5.7% → **9.7%**; strong priors still amplified single-game results immediately

*Round 2 predictions:*
- Esipenko–Hikaru: 21.7% / **48.8%** / 29.5%, draw most likely; Hikaru with higher winning chances
- Anish–Fabi: 22.0% / **51.6%** / 26.4%, draw most likely; Fabi with higher winning chances
- Wei Yi–Pragg: 30.1% / **50.9%** / 19.0%, draw most likely; Wei Yi with higher winning chances
- Sindarov–Bluebaum: 31.2% / **49.0%** / 19.8%, draw most likely; Sindarov with higher winning chances

</details>

<details>
<summary>Round 1</summary>

![Round 1](results/candidates2026/r1.png)

*Pre-tournament predictions*

- **Fabi** was the favourite at **21.5%**: consistent profile across all three time controls gave a stable overall estimate
- **Hikaru at 18.7%** despite the highest classical Elo (2810): flat classical trend and weaker rapid/blitz velocity
- **Sindarov at 16.1%** with only 2745 Elo: strongly rising classical trend [2721→2745, +24 pts] and improving rapid history; the model rewarded recent momentum
- **Bluebaum at 8.5%** for a 2695-rated player: positive classical trend with no drag from weak secondary time controls
- **Pragg at only 5.7%** despite his FIDE ranking: classical rating falling [2768→2741, −27 pts]; the model tracked the trend, not the name

*Round 1 predictions:*
- Fabi–Hikaru: 26.5% / **51.9%** / 21.5%, draw most likely; Fabi with higher winning chances
- Pragg–Anish: 21.9% / **51.6%** / 26.5%, draw most likely; Anish with higher winning chances
- Bluebaum–Wei Yi: 24.0% / **51.5%** / 24.5%, draw most likely; essentially even
- Sindarov–Esipenko: 31.8% / **50.5%** / 17.7%, draw most likely; Sindarov with higher winning chances

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

- **Dynamic Bayesian ratings**: maintains separate White and Black strength estimates per player, anchored to a prior and updated every round via MAP inference
- **Parametric draw model**: draw probability is proportional to the draw parameter scaled by the geometric mean of both players' strengths; the draw parameter is time-control-specific (`classical_nu`, `rapid_nu`, `blitz_nu`)
- **Style multiplier**: each player has Bayesian-smoothed White/Black aggression scores (fraction of decisive games); the draw parameter is scaled by the ratio of the baseline decisive-game rate to this pairing's expected decisive-game rate, shrinking the draw band when both players play sharply and inflating it when they play solidly
- **Standings multiplier**: the draw parameter is scaled by each player's *motivation*, then averaged. Motivation is computed as points deficit divided by rounds remaining: leaders at or ahead of pace play at baseline; players who need roughly one extra win per four remaining rounds get a peak desperation boost; near-eliminated players widen their draw band as they relax pressure
- **Color bleed**: aggression and strength estimates cross-pollinate between White and Black; both estimates are also geometrically blended after each MAP update and rescaled to prevent drift
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

1. **Weighted Game Brier Score**: multi-class Brier score over all predicted games, exponentially down-weighted by 0.80 per round of distance into the future; decisive and drawn games are weighted equally.
2. **Rank RPS**: Ranked Probability Score over the predicted finishing-position distribution (cumulative squared error across all rank thresholds), averaged across players.

Rank RPS is accumulated with an exponential discount of 0.95 per round, slightly favouring early-round accuracy. Game Brier weights each predicted game exponentially less the further into the future it falls from the simulation point. When multiple tournament files are supplied, scores are averaged across tournaments. `EVAL_RUNS` in `tools/tuning/utils.py` controls Monte Carlo iterations per trial (default 10 000).

```bash
python tools/tuning/pareto_front.py db/tuning_22_24.db
python tools/tuning/pareto_front.py db/tuning_22_24.db --save results/pareto/tuning_22_24.png
python tools/tuning/pareto_front.py db/tuning_22_24.db --method knee
python tools/tuning/pareto_front.py db/tuning_22_24.db --method weighted --weights 0.7 0.3
python tools/tuning/pareto_front.py db/tuning_22_24.db --method auc
```

![Pareto Front](results/pareto/tuning_22_24.png)

All methods use scale-invariant normalization: each objective divided by its minimum value (percentage deviation from best), which correctly accounts for objectives with different absolute ranges. `--method` (default `utopia`) selects the suggested best trial: `utopia` minimizes distance to the ideal corner; `knee` finds the point of maximum curvature; `weighted` minimizes a weighted sum (`--weights W_GAME W_RPS`, default `0.5 0.5`); `auc` returns the area median (50% of the curve area).

The #1 trial is saved as `configs/best_hparams_22_24.jsonc` and used for the 2026 Candidates predictions.

### `best_hparams_22_24.jsonc`: parameter interpretation

| Parameter | Value | Interpretation |
|---|---|---|
| `prior_weight_known/sim` | 7.96 / 9.31 | Strong priors; each result shifts ratings meaningfully but not dramatically |
| `initial_white_adv` | 19.5 Elo | Small White color advantage; White and Black starting ratings are initialized ~10 Elo apart (±9.8 each) |
| `lookahead_factor` | 5.00 | Rating trend is strongly extrapolated forward; players with rising ratings are credited substantially |
| `velocity_time_decay` | 0.313 | Steep decay; recent rating history is weighted heavily over older entries |
| `rapid_form_weight / blitz_form_weight` | −0.38 / −0.34 | Rapid and blitz trends slightly reduce the classical form anchor |
| `color_bleed` | 0.0091 | Minimal cross-pollination between White and Black latent strengths; color-specific ratings are nearly independent |
| `classical_nu` | 2.17 | High draw rate for classical games; draws are the modal outcome between similarly-rated players |
| `rapid_nu` | 0.22 | Low draw rate for rapid tiebreaks; rapid is substantially more decisive than classical |
| `blitz_nu` | 0.025 | Very low draw rate for blitz; almost all blitz tiebreakers produce a decisive result |
| `agg_prior_weight` | 35.7 | Strong aggression prior; individual style scores are anchored tightly to the default |
| `default_aggression_w` | 0.229 | Prior for White decisive-game fraction; ~23% of White games are expected to be decisive before any game history is observed |
| `default_aggression_b` | 0.033 | Prior for Black decisive-game fraction; ~3.3% of Black games decisive by default; Black has a very drawish baseline |
| `standings_aggression` | 0.109 | Small desperation effect; tournament standings have some influence on game aggression |

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

`generate_rounds.py` invokes the binary once per round and saves the JSON output to `round{N}.json` files. `visualize_timeline.py` reads all `round{N}.txt` or `round{N}.json` files in the given directory and produces a dashboard PNG showing win probability timeline, current win % bar chart (players with equal win probability are ordered by their current points), and per-round match prediction breakdowns (with actual results highlighted in gold).

## How the model works

Each player has separate White and Black strength estimates, initialized from a projected FIDE rating with White given a bonus and Black a penalty of half `initial_white_adv`. If rating history is provided, a time-decayed velocity is estimated and projected forward by `lookahead_factor`; rapid/blitz trends blend in via `rapid_form_weight` / `blitz_form_weight`.

After each round, both strength estimates are updated via:
1. **MAP fixed-point iteration**: anchored Bradley-Terry MAP given all games played; prior strength is `prior_weight_known` for historical rounds and `prior_weight_sim` for simulated ones.
2. **Color bleed**: White and Black strength estimates are geometrically blended via `color_bleed`, then rescaled to prevent drift.

Win probability is the White player's strength divided by the total; draw probability is the draw parameter times the geometric mean of both players' strengths divided by the total; loss probability is the Black player's strength divided by the total. The draw parameter is scaled per game by:
- **Style multiplier**: baseline decisive-game rate divided by this pairing's expected decisive-game rate; aggressive pairings shrink the draw band.
- **Standings multiplier**: average of both players' motivation (points deficit divided by rounds remaining); players needing roughly one extra win per four remaining rounds peak in desperation, near-eliminated players widen the draw band.
