#!/usr/bin/env python3
"""
Build a tournament JSON file for chess_montecarlo from a Lichess broadcast.

Downloads all games, fetches FIDE rating history, and writes a JSONC file
formatted like tournament.json (round headers, compact single-line entries,
inline player-name comments).

Dependencies:
    pip install requests python-chess

Usage:
    python build_tournament.py wEuVhT9c -o data/candidates2024.json
    python build_tournament.py https://lichess.org/broadcast/fide-candidates-2024--open/wEuVhT9c
    python build_tournament.py wEuVhT9c --as-of 2024-04          # slice history to Apr 2024
    python build_tournament.py wEuVhT9c --no-fide                 # skip FIDE history
    python build_tournament.py wEuVhT9c --periods 8               # 8 history entries

API endpoints used:
    GET /api/broadcast/{tourId}.pgn     → all games in one download
    FIDE chart: ratings.fide.com/a_chart_data.phtml?event={id}[&rid=2|3]
"""

import argparse
import io
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import chess.pgn
import requests

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
    "Ding, Liren": "Ding",
    "Rapport, Richard": "Rapport",
    "Radjabov, Teimour": "Radjabov",
    "Duda, Jan-Krzysztof": "Duda",
}

LICHESS_API = "https://lichess.org/api"
FIDE_CHART = "https://ratings.fide.com/a_chart_data.phtml"

RESULT_MAP = {"1-0": "1-0", "0-1": "0-1", "1/2-1/2": "1/2-1/2"}


MONTH_ABBR = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


# ── Lichess ────────────────────────────────────────────────────────────────────


def parse_tournament_id(url_or_id: str) -> str:
    """Extract the tournament ID from a full URL or return the ID directly."""
    parts = [p for p in url_or_id.rstrip("/").split("/") if p]
    return parts[-1]


def download_all_pgn(tour_id: str, cache_dir: Path | None = None) -> str:
    """Download PGN for every game via GET /api/broadcast/{tourId}.pgn"""
    if cache_dir is not None:
        cache_file = cache_dir / f"lichess_{tour_id}.pgn"
        if cache_file.exists():
            print(f"Loading PGN from cache: {cache_file}")
            return cache_file.read_text()

    url = f"{LICHESS_API}/broadcast/{tour_id}.pgn"
    print(f"Downloading: {url} ...")
    r = requests.get(url, timeout=300, headers={"Accept": "application/x-chess-pgn"})
    r.raise_for_status()
    print(f"  {len(r.content):,} bytes.")

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(r.text)
        print(f"  Saved to cache: {cache_file}")
    return r.text


# ── PGN parsing ────────────────────────────────────────────────────────────────


def round_from_header(round_str: str) -> int:
    """Parse "1.1", "1.2" → 1;  "7" → 7;  "" → 0"""
    m = re.match(r"(\d+)", round_str or "")
    return int(m.group(1)) if m else 0


def parse_all_games(pgn_text: str) -> list[dict]:
    """
    Parse every game from the PGN dump.
    Returns list of dicts: white, black, white_fide_id, black_fide_id,
                           white_elo, black_elo, result (None if ongoing), round.
    """
    games = []
    reader = io.StringIO(pgn_text)
    while True:
        game = chess.pgn.read_game(reader)
        if game is None:
            break
        h = game.headers

        def maybe_int(key):
            val = h.get(key, "").strip()
            return int(val) if val.lstrip("-").isdigit() else None

        games.append(
            {
                "white": h.get("White", "").strip(),
                "black": h.get("Black", "").strip(),
                "white_fide_id": maybe_int("WhiteFideId"),
                "black_fide_id": maybe_int("BlackFideId"),
                "white_elo": maybe_int("WhiteElo"),
                "black_elo": maybe_int("BlackElo"),
                "result": RESULT_MAP.get(h.get("Result", "*")),
                "round": round_from_header(h.get("Round", "")),
            }
        )
    return games


# ── FIDE rating history ────────────────────────────────────────────────────────


def _parse_period_label(label: str) -> tuple[int, int] | None:
    """
    Parse a FIDE period label to a (year, month) tuple for comparison.
    Handles new format "2024-Jan" and old format "Jan 2024".
    Returns None if unparseable.
    """
    label = label.strip()
    # New format: "2024-Jan"
    if "-" in label:
        year_str, mon_str = label.split("-", 1)
        try:
            year = int(year_str)
        except ValueError:
            return None
        month = MONTH_ABBR.get(mon_str.lower()[:3])
    else:
        # Old format: "Jan 2024"
        parts = label.split()
        if len(parts) != 2:
            return None
        month = MONTH_ABBR.get(parts[0].lower()[:3])
        try:
            year = int(parts[1])
        except ValueError:
            return None
    if month and 1900 <= year <= 2100:
        return (year, month)
    return None


def _fetch_fide_raw(fide_id: int, cache_dir: Path | None = None) -> list[dict]:
    """
    POST /a_chart_data.phtml?event=<id>&period=0
    Returns the raw list of period dicts, oldest-first, or [] on failure.
    Each dict has keys: date_2, rating, period_games,
                        rapid_rtng, rapid_games, blitz_rtng, blitz_games.
    """
    if cache_dir is not None:
        cache_file = cache_dir / f"fide_{fide_id}.json"
        if cache_file.exists():
            print(f"    Loading FIDE data from cache: {cache_file}", file=sys.stderr)
            return json.loads(cache_file.read_text())

    try:
        r = requests.post(
            FIDE_CHART,
            params={"event": fide_id, "period": 0},
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": f"https://ratings.fide.com/profile/{fide_id}/chart",
                "Origin": "https://ratings.fide.com",
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        r.raise_for_status()
    except Exception as e:
        print(f"    [warn] FIDE fetch for {fide_id}: {e}", file=sys.stderr)
        return []

    print(f"    [debug] {fide_id}: POST → {r.status_code} "
          f"({len(r.content)} bytes, Content-Type: {r.headers.get('Content-Type', '?')})",
          file=sys.stderr)

    text = r.text.strip()
    if not text:
        print(f"    [debug] {fide_id}: empty response body", file=sys.stderr)
        return []
    if not text.startswith("["):
        print(f"    [warn] {fide_id}: unexpected response (first 200): {text[:200]}",
              file=sys.stderr)
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    [warn] {fide_id}: JSON parse error: {e} | first 200: {text[:200]}",
              file=sys.stderr)
        return []
    if not isinstance(data, list) or not data:
        print(f"    [warn] {fide_id}: unexpected JSON structure: {type(data)}", file=sys.stderr)
        return []

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data))
        print(f"    Saved to cache: {cache_file}", file=sys.stderr)
    return data  # already oldest-first


def fetch_fide_all(fide_id: int, n: int, as_of: tuple[int, int] | None = None, cache_dir: Path | None = None) -> dict:
    """
    Fetch FIDE classical/rapid/blitz history in one POST.
    as_of: (year, month) upper bound — e.g. (2024, 4) for April 2024.
    Returns partial player dict with rating + history fields (only populated keys).
    """
    time.sleep(0.8)
    raw = _fetch_fide_raw(fide_id, cache_dir)
    if not raw:
        return {}

    print(f"    [debug] {fide_id}: {len(raw)} periods fetched "
          f"({raw[0]['date_2']} … {raw[-1]['date_2']})", file=sys.stderr)

    if as_of:
        before = len(raw)
        raw = [e for e in raw
               if (p := _parse_period_label(e["date_2"])) is not None and p <= as_of]
        print(f"    [debug] {fide_id}: {before} → {len(raw)} periods after as_of filter",
              file=sys.stderr)

    if not raw:
        print(f"    [debug] {fide_id}: all periods filtered out", file=sys.stderr)
        return {}

    def _int(val) -> int | None:
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    result: dict = {}
    specs = [
        ("classical", "rating",     "period_games", "history",       "games_played",       "rating"),
        ("rapid",     "rapid_rtng", "rapid_games",  "rapid_history", "rapid_games_played", "rapid_rating"),
        ("blitz",     "blitz_rtng", "blitz_games",  "blitz_history", "blitz_games_played", "blitz_rating"),
    ]
    for tc, rtng_key, games_key, hist_key, ghist_key, rating_key in specs:
        entries = [(_int(e[rtng_key]), _int(e[games_key])) for e in raw]
        valid_idx = [i for i, (r, _) in enumerate(entries) if r is not None]
        if not valid_idx:
            print(f"    [debug] {fide_id}/{tc}: no valid rating entries", file=sys.stderr)
            continue
        last = valid_idx[-1]
        result[rating_key] = entries[last][0]
        recent = entries[max(0, last + 1 - n): last + 1]
        result[hist_key] = [r for r, _ in recent]
        result[ghist_key] = [g or 0 for _, g in recent]
        print(f"    [debug] {fide_id}/{tc}: rating={result[rating_key]}, "
              f"history={result[hist_key]}", file=sys.stderr)

    return result


# ── JSONC output ───────────────────────────────────────────────────────────────


def _player_line(p: dict) -> str:
    """Render one player as a compact JSON object string (no outer newline)."""
    fields = []
    for key in (
        "fide_id",
        "name",
        "rating",
        "rapid_rating",
        "blitz_rating",
        "history",
        "games_played",
        "rapid_history",
        "rapid_games_played",
        "blitz_history",
        "blitz_games_played",
    ):
        if key in p:
            fields.append(f'"{key}": {json.dumps(p[key], separators=(", ", ": "))}')
    inner = ",\n      ".join(fields)
    return "{\n      " + inner + "\n    }"


def _game_line(entry: dict, name_map: dict[int, str], last: bool) -> str:
    """Render one schedule entry as a compact JSONC line with inline comment."""
    w_id = entry["white"]
    b_id = entry["black"]
    result = entry.get("result")

    if result:
        body = f'{{ "white": {w_id}, "black": {b_id}, "result": "{result}" }}'
    else:
        body = f'{{ "white": {w_id}, "black": {b_id} }}'

    comma = "" if last else ","
    w_name = name_map.get(w_id, str(w_id))
    b_name = name_map.get(b_id, str(b_id))
    return f"    {body}{comma} // {w_name} vs {b_name}"


def write_jsonc(
    players: list[dict], schedule: list[dict], name_map: dict[int, str], path: Path
) -> None:
    """Write tournament data as formatted JSONC."""
    lines = ["{"]

    # Players
    lines.append('  "players": [')
    for i, p in enumerate(players):
        comma = "," if i < len(players) - 1 else ""
        lines.append(f"    {_player_line(p)}{comma}")
    lines.append("  ],")

    # Schedule — group by round
    lines.append('  "schedule": [')
    by_round: dict[int, list[dict]] = defaultdict(list)
    for entry in schedule:
        by_round[entry.get("_round", 0)].append(entry)

    sorted_rounds = sorted(by_round.keys())
    total = len(schedule)
    idx = 0
    for rnd in sorted_rounds:
        entries = by_round[rnd]
        lines.append(f"    // Round {rnd}")
        for entry in entries:
            idx += 1
            lines.append(_game_line(entry, name_map, last=(idx == total)))
    lines.append("  ]")
    lines.append("}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


# ── Build ──────────────────────────────────────────────────────────────────────


def build_tournament(
    url_or_id: str, fetch_fide: bool, periods: int, as_of: tuple[int, int] | None,
    cache_dir: Path | None = None,
) -> tuple[list, list, dict]:
    """
    Returns (players, schedule_with_round, name_map).
    schedule entries include a "_round" key for JSONC grouping.
    """
    tour_id = parse_tournament_id(url_or_id)
    pgn_text = download_all_pgn(tour_id, cache_dir)
    games = parse_all_games(pgn_text)
    print(f"Parsed {len(games)} games.")

    players_info: dict[int, dict] = {}
    for g in games:
        for color in ("white", "black"):
            fid = g[f"{color}_fide_id"]
            name = g[color]
            elo = g[f"{color}_elo"]
            if fid and fid not in players_info:
                players_info[fid] = {"fide_id": fid, "name": name, "rating": elo}

    if not players_info:
        print("No players with FIDE IDs found — check the broadcast ID.")
        sys.exit(1)

    # Schedule sorted by round; keep _round for JSONC grouping
    schedule: list[dict] = []
    for g in sorted(games, key=lambda x: x["round"]):
        entry: dict = {
            "white": g["white_fide_id"],
            "black": g["black_fide_id"],
            "_round": g["round"],
        }
        if g["result"] is not None:
            entry["result"] = g["result"]
        schedule.append(entry)

    players = list(players_info.values())

    if fetch_fide:
        label = f"≤ {as_of[0]}-{as_of[1]:02d}" if as_of else "latest"
        print(f"\nFetching FIDE history ({periods} periods, {label}) ...")
        enriched = []
        for p in players:
            print(f"  {p['name']} (FIDE {p['fide_id']}) ...")
            fide_data = fetch_fide_all(p["fide_id"], n=periods, as_of=as_of, cache_dir=cache_dir)
            entry: dict = {"fide_id": p["fide_id"], "name": p["name"]}
            entry["rating"] = fide_data.get("rating", p.get("rating"))
            entry["rapid_rating"] = fide_data.get("rapid_rating", p.get("rapid_rating"))
            entry["blitz_rating"] = fide_data.get("blitz_rating", p.get("blitz_rating"))
            entry = {k: v for k, v in entry.items() if v is not None}
            for key in (
                "history",
                "games_played",
                "rapid_history",
                "rapid_games_played",
                "blitz_history",
                "blitz_games_played",
            ):
                if key in fide_data:
                    entry[key] = fide_data[key]
            enriched.append(entry)
        players = enriched

    players.sort(key=lambda p: p.get("rating") or 0, reverse=True)
    name_map = {p["fide_id"]: PLAYER_ALIASES.get(p["name"], p["name"].split(",")[0].strip()) for p in players}
    return players, schedule, name_map


# ── Entry point ────────────────────────────────────────────────────────────────


def parse_as_of(s: str) -> tuple[int, int]:
    """Parse "YYYY-MM" → (year, month)."""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if not m:
        raise argparse.ArgumentTypeError(f"--as-of must be YYYY-MM, got {s!r}")
    return (int(m.group(1)), int(m.group(2)))


def main():
    parser = argparse.ArgumentParser(
        description="Build a JSONC tournament file from a Lichess broadcast + FIDE history."
    )
    parser.add_argument(
        "broadcast_id",
        help="Lichess broadcast URL or tournament ID.  Example: wEuVhT9c",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="tournament_new.json",
        help="Output path (default: tournament_new.json)",
    )
    parser.add_argument(
        "--no-fide",
        dest="fide",
        action="store_false",
        default=True,
        help="Skip FIDE history fetch",
    )
    parser.add_argument(
        "--periods",
        type=int,
        default=6,
        help="Number of monthly history periods per time control (default: 6)",
    )
    parser.add_argument(
        "--as-of",
        dest="as_of",
        type=parse_as_of,
        default=None,
        metavar="YYYY-MM",
        help="Only include FIDE history up to this month (e.g. 2024-04 for April 2024)",
    )
    parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        default="data/raw",
        metavar="DIR",
        help="Directory for caching PGN and FIDE responses (default: data/raw). "
             "Use --no-cache to disable.",
    )
    parser.add_argument(
        "--no-cache",
        dest="cache_dir",
        action="store_const",
        const=None,
        help="Disable caching; always fetch from network",
    )
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    players, schedule, name_map = build_tournament(
        args.broadcast_id,
        fetch_fide=args.fide,
        periods=args.periods,
        as_of=args.as_of,
        cache_dir=cache_dir,
    )

    out = Path(args.output)
    write_jsonc(players, schedule, name_map, out)
    print(f"\nWrote {len(players)} players, {len(schedule)} games → {out}")


if __name__ == "__main__":
    main()
