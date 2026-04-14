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
python tools/tuning/pareto_front.py db/tuning_22.db --save imgs/pareto/tuning_22.png
python tools/tuning/pareto_front.py db/tuning_24.db --save imgs/pareto/tuning_24.png
python tools/tuning/pareto_front.py db/tuning_22_24.db --save imgs/pareto/tuning_22_24.png

# Evaluate
python tools/tuning/evaluate.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc data/candidates2024.jsonc data/candidates2026.jsonc

# Run simulations
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2026.jsonc results/candidates2026/ --rounds 15
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2024.jsonc results/candidates2024/ --rounds 15
python tools/viz/generate_rounds.py configs/best_hparams_22_24.jsonc data/candidates2022.jsonc results/candidates2022/ --rounds 15

# Visualize
for i in {1..15}; do python tools/viz/visualize_timeline.py results/candidates2026 -k $i -o imgs/candidates2026/r${i}.png -t data/candidates2026.jsonc; done
for i in {1..15}; do python tools/viz/visualize_timeline.py results/candidates2024 -k $i -o imgs/candidates2024/r${i}.png -t data/candidates2024.jsonc; done
for i in {1..15}; do python tools/viz/visualize_timeline.py results/candidates2022 -k $i -o imgs/candidates2022/r${i}.png -t data/candidates2022.jsonc; done

# Dashboard
python tools/viz/generate_html.py --tournament data/candidates2026.jsonc --rounds results/candidates2026/ --hparams configs/best_hparams_22_24.jsonc --db db/tuning_22_24.db --output /home/vltanh/Documents/vltanh.github.io/assets/chess/candidates2026.html
