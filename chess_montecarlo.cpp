// chess_montecarlo.cpp
// Build: g++ -O3 -march=native -std=c++17 -pthread chess_montecarlo.cpp -o chess_montecarlo
// Usage: ./chess_montecarlo [tournament.json]

#include <array>
#include <vector>
#include <cmath>
#include <random>
#include <algorithm>
#include <numeric>
#include <string>
#include <iostream>
#include <iomanip>
#include <fstream>
#include <thread>
#include <unordered_map>
#include <stdexcept>
#include <cassert>
#include <chrono>
#include "json.hpp"

using json = nlohmann::json;

// ─── Constants ────────────────────────────────────────────────────────────────

static constexpr int    N                 = 8;
static constexpr int    GPR               = N / 2;   // games per round = 4
static constexpr int    MAP_ITERS         = 100;     // Convergence iterations
static constexpr double MAP_TOLERANCE     = 1e-8;    // Convergence threshold
static constexpr double PRIOR_WEIGHT      = 1.0;     // beta: 10 virtual games of anchor
static constexpr double INITIAL_WHITE_ADV = 35.0;    // Pre-tournament seed distribution
static constexpr double RAPID_DRAW        = 0.65;    // Stage I:  15+10
static constexpr double BLITZ_DRAW        = 0.40;    // Stage II/III: 3+2

enum TimeControl { CLASSICAL, RAPID, BLITZ };

// ─── Draw-probability table ───────────────────────────────────────────────────
static constexpr double DRAW_TABLE[8][16] = {
    {0.21, 0.24, 0.25, 0.24, 0.24, 0.22, 0.23, 0.24, 0.22, 0.22, 0.20, 0.20, 0.21, 0.19, 0.18, 0.17}, // 1400
    {0.28, 0.29, 0.30, 0.29, 0.27, 0.27, 0.27, 0.26, 0.25, 0.25, 0.23, 0.22, 0.20, 0.20, 0.20, 0.19}, // 1600
    {0.31, 0.32, 0.32, 0.32, 0.30, 0.30, 0.28, 0.27, 0.26, 0.25, 0.23, 0.23, 0.22, 0.22, 0.20, 0.20}, // 1800
    {0.35, 0.35, 0.34, 0.33, 0.32, 0.31, 0.30, 0.29, 0.27, 0.25, 0.25, 0.24, 0.21, 0.21, 0.19, 0.19}, // 2000
    {0.42, 0.42, 0.40, 0.39, 0.37, 0.36, 0.34, 0.32, 0.30, 0.28, 0.25, 0.24, 0.22, 0.20, 0.19, 0.17}, // 2200
    {0.54, 0.53, 0.51, 0.50, 0.47, 0.45, 0.41, 0.38, 0.35, 0.33, 0.30, 0.26, 0.24, 0.22, 0.19, 0.18}, // 2400
    {0.57, 0.54, 0.54, 0.52, 0.51, 0.50, 0.45, 0.42, 0.40, 0.37, 0.34, 0.31, 0.30, 0.28, 0.29, 0.25}, // 2600
    {0.60, 0.57, 0.56, 0.54, 0.52, 0.51, 0.47, 0.44, 0.42, 0.39, 0.36, 0.34, 0.32, 0.30, 0.29, 0.27}, // 2800
};

static double drawProbability(double elo1, double elo2) {
    int avg200 = static_cast<int>(std::floor((elo1 + elo2) * 0.5 / 200.0)) * 200;
    avg200 = std::max(1400, std::min(2800, avg200));
    int diff20 = static_cast<int>(std::floor(std::abs(elo1 - elo2) / 20.0)) * 20;
    diff20 = std::max(0, std::min(300, diff20));
    return DRAW_TABLE[(avg200 - 1400) / 200][diff20 / 20];
}

// ─── Win probability (Bipartite Native) ───────────────────────────────────────

struct Probs { double win, draw, loss; };

static Probs winProbability(double wElo, double bElo, double drawMult = 1.0) {
    // Standard logistic curve. WHITE_ADV is omitted because it is natively baked into the split Elos.
    double expected = 1.0 / (1.0 + std::pow(10.0, (bElo - wElo) / 400.0));
    
    double draw = drawProbability(wElo, bElo) * drawMult;
    double maxDraw = 2.0 * std::min(expected, 1.0 - expected);
    draw = std::min(draw, maxDraw);
    
    return { expected - 0.5 * draw, draw, 1.0 - expected - 0.5 * draw };
}

// ─── Tournament config ────────────────────────────────────────────────────────

struct KnownGame     { int w, b; double whitePoints; };
struct ScheduledGame { int w, b; };

struct Config {
    std::array<std::string, N> names;
    std::array<double, N>      ratings;
    std::array<double, N>      rapidRatings;
    std::array<double, N>      blitzRatings;
    std::vector<KnownGame>     knownGames;
    std::vector<ScheduledGame> schedule;
    int runs              = 1'000'000;
    int simulateFromRound = 1;
};

static double parseResult(const std::string& s) {
    if (s == "1-0")     return 1.0;
    if (s == "1/2-1/2") return 0.5;
    if (s == "0-1")     return 0.0;
    throw std::runtime_error("Unknown result: \"" + s + "\"");
}

static Config buildConfig(const std::string& path) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot open: " + path);

    json doc = json::parse(f);
    Config cfg;
    cfg.runs              = doc.value("runs", 1'000'000);
    cfg.simulateFromRound = doc.value("simulate_from_round", 1);

    const auto& players = doc.at("players");
    if ((int)players.size() != N)
        throw std::runtime_error("Expected " + std::to_string(N) + " players, got "
                                 + std::to_string(players.size()));

    std::unordered_map<int, int> idx;
    for (int i = 0; i < N; ++i) {
        const auto& p = players[i];
        int fideId          = p.at("fide_id").get<int>();
        idx[fideId]         = i;
        cfg.names[i]        = p.at("name").get<std::string>();
        cfg.ratings[i]      = p.at("rating").get<double>();
        
        // Use rapid/blitz fallback to classical if missing in JSON
        cfg.rapidRatings[i] = p.value("rapid_rating", cfg.ratings[i]); 
        cfg.blitzRatings[i] = p.value("blitz_rating", cfg.ratings[i]); 
    }

    const auto& schedule = doc.at("schedule");
    for (int gi = 0; gi < (int)schedule.size(); ++gi) {
        const auto& g = schedule[gi];
        int round = gi / GPR + 1;
        int w = idx.at(g.at("white").get<int>());
        int b = idx.at(g.at("black").get<int>());

        if (round < cfg.simulateFromRound) {
            if (!g.contains("result") || g.at("result").is_null())
                throw std::runtime_error("Missing result for historical game in round "
                                         + std::to_string(round));
            cfg.knownGames.push_back({w, b, parseResult(g.at("result").get<std::string>())});
        } else {
            cfg.schedule.push_back({w, b});
        }
    }
    return cfg;
}

// ─── Encounter table (Bipartite Model) ───────────────────────────────────────

struct EncounterTable {
    std::array<double, N> wRating, bRating;
    std::array<double, N> initWRating, initBRating;
    std::array<double, N> points;

    double A_WB[N][N]; // Directed matrix: i played White, j played Black
    double W_W[N];     // Points scored by player strictly as White
    double W_B[N];     // Points scored by player strictly as Black

    void init(const Config& cfg) {
        for (int i = 0; i < N; ++i) {
            // Seed the split priors. 
            initWRating[i] = wRating[i] = cfg.ratings[i] + INITIAL_WHITE_ADV / 2.0;
            initBRating[i] = bRating[i] = cfg.ratings[i] - INITIAL_WHITE_ADV / 2.0;
            
            points[i] = 0.0;
            W_W[i] = 0.0;
            W_B[i] = 0.0;
        }
        for (int i = 0; i < N; ++i)
            for (int j = 0; j < N; ++j)
                A_WB[i][j] = 0.0;
    }

    void setEncounter(int w, int b, double whitePoints) {
        A_WB[w][b] += 1.0;            
        W_W[w] += whitePoints;        
        W_B[b] += 1.0 - whitePoints;  
        
        points[w] += whitePoints;
        points[b] += 1.0 - whitePoints;
    }

    // 2N Anchored MAP Estimator
    void updateDynamicRatings(const Config& cfg) {
        double meanElo = 0.0;
        for (int i = 0; i < N; ++i) meanElo += cfg.ratings[i];
        meanElo /= N;

        std::array<double, N> alphaW, alphaB, lambdaW, lambdaB;
        for (int i = 0; i < N; ++i) {
            alphaW[i]  = std::pow(10.0, (initWRating[i] - meanElo) / 400.0);
            alphaB[i]  = std::pow(10.0, (initBRating[i] - meanElo) / 400.0);
            lambdaW[i] = std::pow(10.0, (wRating[i] - meanElo) / 400.0);
            lambdaB[i] = std::pow(10.0, (bRating[i] - meanElo) / 400.0);
        }

        for (int iter = 0; iter < MAP_ITERS; ++iter) {
            std::array<double, N> nextW, nextB;
            double maxDiff = 0.0;
            
            for (int i = 0; i < N; ++i) {
                // Update White Latent Strength
                double denomW = (2.0 * PRIOR_WEIGHT) / (lambdaW[i] + alphaW[i]);
                for (int j = 0; j < N; ++j) {
                    if (A_WB[i][j] > 0.0) {
                        denomW += A_WB[i][j] / (lambdaW[i] + lambdaB[j]);
                    }
                }
                nextW[i] = (PRIOR_WEIGHT + W_W[i]) / denomW;
                
                // Update Black Latent Strength
                double denomB = (2.0 * PRIOR_WEIGHT) / (lambdaB[i] + alphaB[i]);
                for (int j = 0; j < N; ++j) {
                    if (A_WB[j][i] > 0.0) { 
                        denomB += A_WB[j][i] / (lambdaW[j] + lambdaB[i]);
                    }
                }
                nextB[i] = (PRIOR_WEIGHT + W_B[i]) / denomB;
                
                double diffW = std::abs(nextW[i] - lambdaW[i]);
                double diffB = std::abs(nextB[i] - lambdaB[i]);
                if (diffW > maxDiff) maxDiff = diffW;
                if (diffB > maxDiff) maxDiff = diffB;
            }
            
            lambdaW = nextW;
            lambdaB = nextB;
            if (maxDiff < MAP_TOLERANCE) break;
        }

        double newMean = 0.0;
        for (int i = 0; i < N; ++i) {
            wRating[i] = meanElo + 400.0 * std::log10(lambdaW[i]);
            bRating[i] = meanElo + 400.0 * std::log10(lambdaB[i]);
            newMean += (wRating[i] + bRating[i]) / 2.0;
        }
        newMean /= N;
        double shift = meanElo - newMean;
        
        for (int i = 0; i < N; ++i) {
            wRating[i] += shift;
            bRating[i] += shift;
        }
    }
};

// ─── RNG ─────────────────────────────────────────────────────────────────────

struct Rng {
    std::mt19937_64 eng;
    std::uniform_real_distribution<double> dist{0.0, 1.0};
    explicit Rng(uint64_t seed) : eng(seed) {}
    double operator()() { return dist(eng); }
};

// ─── Game simulation ──────────────────────────────────────────────────────────

static double simulateGame(const EncounterTable& et, int w, int b, Rng& rng,
                           TimeControl tc, const Config& cfg, double drawMult = 1.0) {
                                
    double wElo, bElo;

    if (tc == RAPID) {
        wElo = cfg.rapidRatings[w] + INITIAL_WHITE_ADV / 2.0;
        bElo = cfg.rapidRatings[b] - INITIAL_WHITE_ADV / 2.0;
    } else if (tc == BLITZ) {
        wElo = cfg.blitzRatings[w] + INITIAL_WHITE_ADV / 2.0;
        bElo = cfg.blitzRatings[b] - INITIAL_WHITE_ADV / 2.0;
    } else {
        // Main Event: Use the dynamically updated MAP White and Black Elos
        wElo = et.wRating[w];
        bElo = et.bRating[b];
    }
    
    auto p = winProbability(wElo, bElo, drawMult);
    double r = rng();
    if (r < p.win)             return 1.0;
    if (r < p.win + p.draw)    return 0.5;
    return 0.0;
}

// ─── Playoff simulation (FIDE 2026 Regulations 4.4.2) ────────────────────────

static std::vector<int> playoffMatch(EncounterTable& et, int p1, int p2,
                                     double dm, Rng& rng, TimeControl tc, const Config& cfg) {
    double p1pts = 0.0;
    for (int g = 0; g < 2; ++g) {
        int w = (g == 0) ? p1 : p2;
        int b = (g == 0) ? p2 : p1;
        double wp = simulateGame(et, w, b, rng, tc, cfg, dm);
        p1pts += (w == p1) ? wp : 1.0 - wp;
    }
    if (p1pts > 1.0) return {p1};
    if (p1pts < 1.0) return {p2};
    return {p1, p2};
}

static std::vector<int> playoffRoundRobin(EncounterTable& et,
                                          const std::vector<int>& ids,
                                          double dm, Rng& rng, TimeControl tc, const Config& cfg) {
    std::array<double, N> pts = {};
    for (int i = 0; i < (int)ids.size(); ++i) {
        for (int j = i + 1; j < (int)ids.size(); ++j) {
            // FIDE 4.4.2.1.1: Single round robin
            int w = (rng() < 0.5) ? ids[i] : ids[j];
            int b = (w == ids[i]) ? ids[j] : ids[i];
            double wp = simulateGame(et, w, b, rng, tc, cfg, dm);
            pts[w] += wp;
            pts[b] += 1.0 - wp;
        }
    }
    double best = 0.0;
    for (int id : ids) best = std::max(best, pts[id]);
    std::vector<int> winners;
    for (int id : ids)
        if (pts[id] == best) winners.push_back(id);
    return winners;
}

static int knockoutMatch(EncounterTable& et, int p1, int p2, Rng& rng, const Config& cfg) {
    // 4.4.2.1.3 (a) - One game, colors by lot
    int w1 = (rng() < 0.5) ? p1 : p2;
    int b1 = (w1 == p1) ? p2 : p1;

    double r1 = simulateGame(et, w1, b1, rng, BLITZ, cfg, BLITZ_DRAW);
    if (r1 != 0.5) return (r1 == 1.0) ? w1 : b1;

    // 4.4.2.1.3 (b) - Colors reversed
    double r2 = simulateGame(et, b1, w1, rng, BLITZ, cfg, BLITZ_DRAW);
    if (r2 != 0.5) return (r2 == 1.0) ? b1 : w1;

    // 4.4.2.1.3 (c) - Sudden death. Draw = Black wins
    int sdw = (rng() < 0.5) ? w1 : b1;
    int sdb = (sdw == w1) ? b1 : w1;
    return (simulateGame(et, sdw, sdb, rng, BLITZ, cfg, BLITZ_DRAW) == 1.0) ? sdw : sdb;
}

static int simulatePlayoff(EncounterTable& et, std::vector<int> tied, Rng& rng, const Config& cfg) {
    tied = (tied.size() == 2)
        ? playoffMatch(et, tied[0], tied[1], RAPID_DRAW, rng, RAPID, cfg)
        : playoffRoundRobin(et, tied, RAPID_DRAW, rng, RAPID, cfg);
    if (tied.size() == 1) return tied[0];

    tied = (tied.size() == 2)
        ? playoffMatch(et, tied[0], tied[1], BLITZ_DRAW, rng, BLITZ, cfg)
        : playoffRoundRobin(et, tied, BLITZ_DRAW, rng, BLITZ, cfg);
    if (tied.size() == 1) return tied[0];

    std::shuffle(tied.begin(), tied.end(), rng.eng);
    while (tied.size() > 1) {
        std::vector<int> next;
        for (int i = 0; i < (int)tied.size(); i += 2) {
            next.push_back((i + 1 < (int)tied.size())
                ? knockoutMatch(et, tied[i], tied[i + 1], rng, cfg)
                : tied[i]);
        }
        tied = std::move(next);
    }
    return tied[0];
}

// ─── One Monte Carlo iteration ────────────────────────────────────────────────

static int runOneIteration(const Config& cfg, Rng& rng, int tracker[N][N][3]) {
    EncounterTable et;
    et.init(cfg);

    // Warm-start historical games dynamically
    for (int i = 0; i < (int)cfg.knownGames.size(); ++i) {
        const auto& g = cfg.knownGames[i];
        et.setEncounter(g.w, g.b, g.whitePoints);
        if ((i + 1) % GPR == 0) {
            et.updateDynamicRatings(cfg);
        }
    }
    if (!cfg.knownGames.empty() && cfg.knownGames.size() % GPR != 0) {
        et.updateDynamicRatings(cfg);
    }

    const int nGames = static_cast<int>(cfg.schedule.size());
    for (int i = 0; i < nGames; ++i) {
        auto [w, b] = cfg.schedule[i];
        
        // Main event games use the CLASSICAL time control enum
        double wp = simulateGame(et, w, b, rng, CLASSICAL, cfg, 1.0);

        if      (wp == 1.0) tracker[w][b][0]++;
        else if (wp == 0.5) tracker[w][b][1]++;
        else                tracker[w][b][2]++;

        et.setEncounter(w, b, wp);

        // Update dynamic ratings once per round
        int abs_game = static_cast<int>(cfg.knownGames.size()) + i + 1;
        if (abs_game % GPR == 0) et.updateDynamicRatings(cfg);
    }

    double maxPts = *std::max_element(et.points.begin(), et.points.end());
    std::vector<int> top;
    for (int i = 0; i < N; ++i)
        if (et.points[i] == maxPts) top.push_back(i);

    return (top.size() == 1) ? top[0] : simulatePlayoff(et, top, rng, cfg);
}

// ─── Parallel Monte Carlo ─────────────────────────────────────────────────────

struct ThreadResult {
    std::array<int, N> wins = {};
    int tracker[N][N][3] = {};
};

static void workerThread(const Config& cfg, int iters, uint64_t seed,
                         ThreadResult& out) {
    Rng rng(seed);
    for (int i = 0; i < iters; ++i)
        out.wins[runOneIteration(cfg, rng, out.tracker)]++;
}

static void runMonteCarlo(const Config& cfg, int totalIters) {
    // Print standings based on known games
    {
        EncounterTable et;
        et.init(cfg);
        
        for (int i = 0; i < (int)cfg.knownGames.size(); ++i) {
            const auto& g = cfg.knownGames[i];
            et.setEncounter(g.w, g.b, g.whitePoints);
        }

        std::array<int, N> order;
        std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(),
            [&](int a, int b) { return et.points[a] > et.points[b]; });

        int completedGames = static_cast<int>(cfg.knownGames.size());
        int currentRound = completedGames / GPR + 1;
        bool isMidRound = (completedGames % GPR != 0);

        std::cout << "=== Current Standings (" 
                  << (isMidRound ? "Mid-Round " : "Before Round ") 
                  << currentRound << ") ===\n";
        for (int i : order)
            std::cout << cfg.names[i] << ": " << et.points[i] << " pts\n";
    }

    int nThreads = static_cast<int>(std::thread::hardware_concurrency());
    if (nThreads <= 0) nThreads = 4;

    std::cout << "\nRunning " << totalIters << " iterations across "
              << nThreads << " threads...\n";

    auto t0 = std::chrono::high_resolution_clock::now();

    std::vector<ThreadResult> results(nThreads);
    std::vector<std::thread>  threads;
    std::mt19937_64 seedGen(42);

    int base = totalIters / nThreads;
    int rem  = totalIters % nThreads;
    for (int t = 0; t < nThreads; ++t) {
        int iters = base + (t < rem ? 1 : 0);
        threads.emplace_back(workerThread, std::cref(cfg), iters,
                             seedGen(), std::ref(results[t]));
    }
    for (auto& th : threads) th.join();

    double elapsed = std::chrono::duration<double>(
        std::chrono::high_resolution_clock::now() - t0).count();

    // Merge
    std::array<int, N> wins = {};
    int tracker[N][N][3] = {};
    for (const auto& r : results) {
        for (int i = 0; i < N; ++i) wins[i] += r.wins[i];
        for (int i = 0; i < N; ++i)
            for (int j = 0; j < N; j++)
                for (int k = 0; k < 3; k++)
                    tracker[i][j][k] += r.tracker[i][j][k];
    }

    std::cout << std::fixed << std::setprecision(2)
              << "Done in " << elapsed << "s\n";

    // Match predictions
    int completedGames = static_cast<int>(cfg.knownGames.size());
    std::cout << "\n=== Monte Carlo Match Predictions ===";
    for (int i = 0; i < (int)cfg.schedule.size(); ++i) {
        int absolute_gi = completedGames + i;
        
        if (i == 0 || absolute_gi % GPR == 0) {
            int calcRound = absolute_gi / GPR + 1;
            bool isOngoing = (i == 0 && absolute_gi % GPR != 0);
            std::cout << "\n\n--- ROUND " << calcRound 
                      << (isOngoing ? " (Ongoing)" : "") << " ---\n";
        }
        
        auto [w, b] = cfg.schedule[i];
        double pw = 100.0 * tracker[w][b][0] / totalIters;
        double pd = 100.0 * tracker[w][b][1] / totalIters;
        double pb = 100.0 * tracker[w][b][2] / totalIters;
        std::cout << cfg.names[w] << " vs " << cfg.names[b] << "\n"
                  << "  1-0: " << std::setprecision(1) << pw
                  << "% | 1/2-1/2: " << pd
                  << "% | 0-1: " << pb << "%\n";
    }

    // Win probabilities
    std::array<int, N> order;
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(),
        [&](int a, int b) { return wins[a] > wins[b]; });

    int r_out = completedGames / GPR + 1;
    std::cout << "\n=== Tournament Win Probabilities (from Round " << r_out << ") ===\n";
    for (int i : order) {
        double perc = 100.0 * wins[i] / totalIters;
        std::cout << std::setw(7) << std::setprecision(2) << std::fixed
                  << perc << "% - " << cfg.names[i] << "\n";
    }
}

// ─── Entry point ─────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    const std::string path = (argc > 1) ? argv[1] : "tournament.json";
    Config cfg = buildConfig(path);
    runMonteCarlo(cfg, cfg.runs);
    return 0;
}