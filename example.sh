#!/usr/bin/env bash
set -euo pipefail

# Build tournament JSON from Lichess broadcast
python tools/data/build_tournament.py BLA70Vds --as-of 2026-04 -o data/candidates2026.jsonc --tiebreak fide2026
python tools/data/build_tournament.py wEuVhT9c --as-of 2024-04 -o data/candidates2024.jsonc --tiebreak fide2026
python tools/data/build_tournament.py kAvAGI7N --as-of 2022-06 -o data/candidates2022.jsonc --tiebreak fide2026

# Hyperparameter tuning
python tools/tuning/tune.py configs/default_hparams.jsonc data/candidates2022.jsonc --db db/tuning_22.db --trials 10000
python tools/tuning/tune.py configs/default_hparams.jsonc data/candidates2024.jsonc --db db/tuning_24.db --trials 10000
python tools/tuning/tune.py configs/default_hparams.jsonc data/candidates2022.jsonc data/candidates2024.jsonc --db db/tuning_22_24.db --trials 10000

# Pareto front
python tools/viz/pareto_front.py db/tuning_22.db --save results/pareto/tuning_22.png
python tools/viz/pareto_front.py db/tuning_24.db --save results/pareto/tuning_24.png
python tools/viz/pareto_front.py db/tuning_22_24.db --save results/pareto/tuning_22_24.png

# Evaluate
python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc data/candidates2024.jsonc data/candidates2026.jsonc

# Run simulations
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2026.jsonc results/candidates2026/rounds/ --rounds 9
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2024.jsonc results/candidates2024/rounds/ --rounds 15
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc results/candidates2022/rounds/ --rounds 15

# Visualize
for i in {1..9}; do python tools/viz/visualize_timeline.py results/candidates2026/rounds -k $i -o results/candidates2026/r${i}.png -t data/candidates2026.jsonc; done
for i in {1..15}; do python tools/viz/visualize_timeline.py results/candidates2024/rounds -k $i -o results/candidates2024/r${i}.png -t data/candidates2024.jsonc; done
for i in {1..15}; do python tools/viz/visualize_timeline.py results/candidates2022/rounds -k $i -o results/candidates2022/r${i}.png -t data/candidates2022.jsonc; done

# Animated GIF
python tools/viz/make_gif.py results/candidates2026/ -o results/candidates2026/animation.gif
