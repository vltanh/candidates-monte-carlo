#!/usr/bin/env bash

# Build
g++ -O3 -march=native -std=c++17 -pthread src/chess_montecarlo.cpp -o bin/chess_montecarlo

# Build tournament JSON from Lichess broadcast
python scripts/build_tournament.py BLA70Vds --as-of 2026-04 -o data/candidates2026.json
python scripts/build_tournament.py wEuVhT9c --as-of 2024-04 -o data/candidates2024.json
python scripts/build_tournament.py kAvAGI7N --as-of 2022-06 -o data/candidates2022.json

# Hyperparameter tuning
python tune.py configs/best_hparams_24.json data/candidates2024.json --db db/tuning_2024.db --trials 1000
python tune.py configs/best_hparams_24.json data/candidates2022.json data/candidates2024.json --db db/tuning_22_24.db --trials 1000

# Pareto front
python scripts/pareto_front.py db/tuning_2024.db --save results/pareto/tuning_24.png
python scripts/pareto_front.py db/tuning_22_24.db --save results/pareto/tuning_22_24.png

# Run simulations
for i in {1..8}; do ./bin/chess_montecarlo configs/best_hparams_24.json data/candidates2026.json $i > results/candidates2026/rounds/round$i.txt; done
for i in {1..15}; do ./bin/chess_montecarlo configs/best_hparams_24.json data/candidates2024.json $i > results/candidates2024/rounds/round$i.txt; done
for i in {1..15}; do ./bin/chess_montecarlo configs/best_hparams_24.json data/candidates2022.json $i > results/candidates2022/rounds/round$i.txt; done

# Visualize
for i in {1..8}; do python scripts/visualize_timeline.py results/candidates2026/rounds -k $i -o results/candidates2026/r${i}.png -t data/candidates2026.json; done
for i in {1..15}; do python scripts/visualize_timeline.py results/candidates2024/rounds -k $i -o results/candidates2024/r${i}.png -t data/candidates2024.json; done
for i in {1..15}; do python scripts/visualize_timeline.py results/candidates2022/rounds -k $i -o results/candidates2022/r${i}.png -t data/candidates2022.json; done

# Animated GIF
python scripts/make_gif.py results/candidates2026/ -o results/candidates2026/animation.gif
