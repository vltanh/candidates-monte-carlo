#!/usr/bin/env python3
"""
Generate JSON state files for Monte Carlo visualization.
Runs the C++ engine for each round and saves the output to a specified directory.

Usage:
    python tools/viz/generate_rounds.py configs/hyperparameters.json data/candidates2024.jsonc results/candidates2024/rounds/
    python tools/viz/generate_rounds.py configs/hyperparameters.json data/candidates2024.jsonc results/candidates2024/rounds/ --rounds 9 9
    python tools/viz/generate_rounds.py configs/hyperparameters.json data/candidates2024.jsonc results/candidates2024/rounds/ --rounds 9 12
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _tournament_rounds(path: Path) -> int:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    data = json.loads(text)
    gpr = data.get("gpr", len(data["players"]) // 2)
    return len(data["schedule"]) // gpr


def main():
    parser = argparse.ArgumentParser(
        description="Generate Monte Carlo round JSON files."
    )
    parser.add_argument(
        "hyperparameters", type=Path, help="Path to hyperparameters JSON"
    )
    parser.add_argument("tournament", type=Path, help="Path to tournament JSON")
    parser.add_argument(
        "output_dir", type=Path, help="Directory to save round{N}.json files"
    )
    parser.add_argument(
        "--binary",
        type=Path,
        default=Path("./bin/chess_montecarlo"),
        help="Path to the C++ executable",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        nargs="+",
        default=None,
        metavar="N",
        help="Round range: one value sets the upper bound (lower defaults to 1), "
             "two values set lower and upper (e.g. --rounds 9 9 for a single round). "
             "Defaults to all rounds in the tournament file.",
    )

    args = parser.parse_args()

    if not args.tournament.exists():
        sys.exit(f"Error: Tournament file not found at {args.tournament}")

    total_rounds = _tournament_rounds(args.tournament)

    if args.rounds is None:
        lo, hi = 1, total_rounds
    elif len(args.rounds) == 1:
        lo, hi = 1, args.rounds[0]
    elif len(args.rounds) == 2:
        lo, hi = args.rounds
    else:
        sys.exit("Error: --rounds accepts at most 2 values")

    if lo > hi:
        sys.exit(f"Error: lower bound {lo} > upper bound {hi}")

    if not args.binary.exists():
        sys.exit(f"Error: Binary not found at {args.binary}")
    if not args.hyperparameters.exists():
        sys.exit(f"Error: Hyperparameters not found at {args.hyperparameters}")

    # Create the output directory (and any parent directories) if it doesn't exist
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory ready: {args.output_dir.resolve()}")

    rounds = range(lo, hi + 1)
    for r in rounds:
        print(f"Simulating state before Round {r:02d}... ", end="", flush=True)

        try:
            proc = subprocess.run(
                [
                    str(args.binary),
                    str(args.hyperparameters),
                    str(args.tournament),
                    str(r),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print("FAILED")
            print(f"C++ Engine Error (Code {e.returncode}):\n{e.stderr}")
            sys.exit(1)

        output_file = args.output_dir / f"round{r}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(proc.stdout)

        print("Done.")

    print(f"\nSuccessfully generated {len(rounds)} round file(s).")
    print(f"You can now run: python tools/viz/visualize_timeline.py {args.output_dir}")


if __name__ == "__main__":
    main()
