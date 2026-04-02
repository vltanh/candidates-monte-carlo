# Chess Monte Carlo Simulation

A multi-threaded Monte Carlo simulator for 8-player round-robin chess tournaments. Models dynamic per-player ratings that update as games are played, then runs millions of simulated completions to estimate win probabilities.

The included `tournament.json` models the **2026 FIDE Candidates Tournament** (Caruana, Nakamura, Giri, Yi Wei, Sindarov, Praggnanandhaa, Esipenko, Bluebaum).

## Visualizations

<!-- Add new rounds here (most recent first): copy the <details> block and update the round number and image path -->

<details>
<summary>Round 5</summary>

![Round 5](results/r5.png)

</details>

<details>
<summary>Round 4</summary>

![Round 4](results/r4.png)

</details>

<details>
<summary>Round 3</summary>

![Round 3](results/r3.png)

</details>

<details>
<summary>Round 2</summary>

![Round 2](results/r2.png)

</details>

<details>
<summary>Round 1</summary>

![Round 1](results/r1.png)

</details>

## Features

- **Dynamic Bayesian ratings** — a 2N anchored MAP estimator maintains separate White and Black latent strengths per player, updated every round
- **Empirical draw table** — draw probabilities indexed by average Elo and rating gap (1400–2800 range)
- **Time control support** — uses Classical, Rapid, or Blitz ratings for the appropriate stage
- **FIDE 2026 playoff rules** — tiebreaks follow the official Rapid → Blitz → Sudden-death knockout sequence (Regulation 4.4.2)
- **Parallel simulation** — work is distributed across all hardware threads via `std::thread`

## Build

```bash
g++ -O3 -march=native -std=c++17 -pthread chess_montecarlo.cpp -o chess_montecarlo
```

Requires a C++17-capable compiler. The only dependency is [`json.hpp`](https://github.com/nlohmann/json) (included).

## Usage

```bash
./chess_montecarlo [tournament.json]
```

Defaults to `tournament.json` in the current directory. Output is printed to stdout.

Redirect to a file to feed into the visualizer:

```bash
./chess_montecarlo tournament.json > results/rounds/round5.txt
```

## Tournament JSON format

```jsonc
{
  "runs": 1000000,               // number of Monte Carlo iterations
  "simulate_from_round": 3,      // rounds before this are treated as known history
  "players": [
    {
      "fide_id": 2020009,
      "name": "Caruana, Fabiano",
      "rating": 2793,
      "rapid_rating": 2727,      // optional, falls back to rating
      "blitz_rating": 2749       // optional, falls back to rating
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

Games are grouped into rounds of 4 (`N/2`). Games before `simulate_from_round` must have a `result`; games from that round onward are simulated.

## Visualization

Requires Python with `matplotlib`, `pandas`, and `numpy`.

```bash
python visualize_timeline.py results/rounds/
```

Reads all `round{N}.txt` files in the given directory and produces a dashboard PNG showing:

- Win probability timeline across rounds
- Current win % bar chart
- Per-round match prediction breakdowns (with actual results highlighted in gold)

```bash
python visualize_timeline.py results/rounds/ -o my_output.png  # custom output path
python visualize_timeline.py results/rounds/ -k 5              # only show up to round 5
```

Output is saved as `round{N}.png` in the input directory by default.

## How the model works

Each player has two latent strengths: one as White and one as Black. Before any games are played, these are initialized from the FIDE classical rating ± 17.5 Elo (the `INITIAL_WHITE_ADV` prior).

After each round, the simulator runs a MAP fixed-point iteration to update the White/Black strengths given all games played so far, anchored by a weak prior toward the initial values. This means early upsets cause the model to revise its expectations for future rounds.

Win and draw probabilities are computed from the updated strengths using the standard Elo expected-score formula combined with the empirical draw table.
