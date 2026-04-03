// chess_montecarlo.cpp
// Build: g++ -O3 -march=native -std=c++17 -pthread chess_montecarlo.cpp -o chess_montecarlo
// Usage: ./chess_montecarlo [tournament.json] [simulate_from_round]

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

static constexpr int N   = 8;
static constexpr int GPR = N / 2;

enum TimeControl { CLASSICAL, RAPID, BLITZ };

struct Probs { double win, draw, loss; };

static Probs winProbability(double lambdaW, double lambdaB, double nu) {
    double p_white = lambdaW;
    double p_black = lambdaB;
    double p_draw  = nu * std::sqrt(lambdaW * lambdaB);
    
    double denom = p_white + p_black + p_draw;
    
    return { p_white / denom, p_draw / denom, p_black / denom };
}

// ─── Tournament config ────────────────────────────────────────────────────────

struct KnownGame     { int w, b; double whitePoints; };
struct ScheduledGame { int w, b; };

struct Config {
    std::array<std::string, N> names;
    std::array<double, N>      ratings;
    std::array<double, N>      rapidRatings;
    std::array<double, N>      blitzRatings;
    std::array<double, N>      aggW;          
    std::array<double, N>      aggB;          
    std::vector<KnownGame>     knownGames;
    std::vector<ScheduledGame> schedule;
    
    // Configurable Hyperparameters
    int    runs;
    int    simulateFromRound;
    int    mapIters;
    double mapTolerance;
    double priorWeight;
    double initialWhiteAdv;
    double classicalNu;
    double rapidNu;
    double blitzNu;
    double overpushEscalation;
    double overpushNuMultiplier;
    double aggPriorWeight;
    double defaultAggW;
    double defaultAggB;
    double colorBleed; 
    
    // Psychological Hyperparameters
    double streakAggressionMod;  
    double leaderCautionPenalty; 
};

static double parseResult(const std::string& s) {
    if (s == "1-0")     return 1.0;
    if (s == "1/2-1/2") return 0.5;
    if (s == "0-1")     return 0.0;
    throw std::runtime_error("Unknown result: \"" + s + "\"");
}

static Config buildConfig(const std::string& path, int cliSimRound) {
    std::ifstream f(path);
    if (!f) throw std::runtime_error("Cannot open: " + path);

    json doc = json::parse(f);
    Config cfg;
    
    // Applied the specific defaults requested
    cfg.runs                 = doc.value("runs", 10'000'000);
    cfg.mapIters             = doc.value("map_iters", 100);
    cfg.mapTolerance         = doc.value("map_tolerance", 1e-8);
    cfg.priorWeight          = doc.value("prior_weight", 1.0);
    cfg.initialWhiteAdv      = doc.value("initial_white_adv", 35.0);
    cfg.classicalNu          = doc.value("classical_nu", 2.5);
    cfg.rapidNu              = doc.value("rapid_nu", 1.5);
    cfg.blitzNu              = doc.value("blitz_nu", 0.8);
    cfg.overpushEscalation   = doc.value("overpush_escalation", 0.02);
    cfg.overpushNuMultiplier = doc.value("overpush_nu_multiplier", 0.20);
    cfg.aggPriorWeight       = doc.value("agg_prior_weight", 4.0);
    cfg.defaultAggW          = doc.value("default_aggression_w", 0.25);
    cfg.defaultAggB          = doc.value("default_aggression_b", 0.15);
    cfg.colorBleed           = doc.value("color_bleed", 0.10); 
    
    // Maintained the psychological defaults from previous iteration
    cfg.streakAggressionMod  = doc.value("streak_aggression_mod", 0.03);
    cfg.leaderCautionPenalty = doc.value("leader_caution_penalty", 0.05);

    if (cliSimRound > 0) {
        cfg.simulateFromRound = cliSimRound;
    } else {
        cfg.simulateFromRound = doc.value("simulate_from_round", 1);
    }

    const auto& players = doc.at("players");
    if ((int)players.size() != N)
        throw std::runtime_error("Expected " + std::to_string(N) + " players");

    std::unordered_map<int, int> idx;
    for (int i = 0; i < N; ++i) {
        const auto& p = players[i];
        int fideId          = p.at("fide_id").get<int>();
        idx[fideId]         = i;
        cfg.names[i]        = p.at("name").get<std::string>();
        cfg.ratings[i]      = p.at("rating").get<double>();
        
        cfg.rapidRatings[i] = p.value("rapid_rating", cfg.ratings[i]); 
        cfg.blitzRatings[i] = p.value("blitz_rating", cfg.ratings[i]); 
        
        cfg.aggW[i] = p.value("aggression_w", cfg.defaultAggW); 
        cfg.aggB[i] = p.value("aggression_b", cfg.defaultAggB); 
    }

    const auto& schedule = doc.at("schedule");
    for (int gi = 0; gi < (int)schedule.size(); ++gi) {
        const auto& g = schedule[gi];
        int round = gi / GPR + 1;
        int w = idx.at(g.at("white").get<int>());
        int b = idx.at(g.at("black").get<int>());

        if (round < cfg.simulateFromRound) {
            if (!g.contains("result") || g.at("result").is_null())
                throw std::runtime_error("Missing result for historical game in round " + std::to_string(round));
            cfg.knownGames.push_back({w, b, parseResult(g.at("result").get<std::string>())});
        } else {
            cfg.schedule.push_back({w, b});
        }
    }
    return cfg;
}

// ─── Encounter table ──────────────────────────────────────────────────────────

struct EncounterTable {
    std::array<double, N> lambdaW, lambdaB; 
    std::array<double, N> initLambdaW, initLambdaB;
    std::array<double, N> points;

    double A_WB[N][N]; 
    double W_W[N];     
    double W_B[N];     
    
    double decisiveW[N];
    double totalW[N];
    double decisiveB[N];
    double totalB[N];
    
    int streak[N];

    void init(const Config& cfg) {
        for (int i = 0; i < N; ++i) {
            initLambdaW[i] = lambdaW[i] = std::pow(10.0, (cfg.ratings[i] + cfg.initialWhiteAdv / 2.0) / 400.0);
            initLambdaB[i] = lambdaB[i] = std::pow(10.0, (cfg.ratings[i] - cfg.initialWhiteAdv / 2.0) / 400.0);
            
            points[i] = 0.0;
            W_W[i] = 0.0;
            W_B[i] = 0.0;
            
            decisiveW[i] = 0.0;
            totalW[i] = 0.0;
            decisiveB[i] = 0.0;
            totalB[i] = 0.0;
            
            streak[i] = 0; 
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
        
        double isDecisive = (whitePoints == 0.5) ? 0.0 : 1.0;
        
        decisiveW[w] += isDecisive;
        totalW[w]    += 1.0;
        
        decisiveB[b] += isDecisive;
        totalB[b]    += 1.0;
        
        if (whitePoints == 1.0) {
            streak[w] = (streak[w] > 0) ? streak[w] + 1 : 1;
            streak[b] = (streak[b] < 0) ? streak[b] - 1 : -1;
        } else if (whitePoints == 0.0) {
            streak[w] = (streak[w] < 0) ? streak[w] - 1 : -1;
            streak[b] = (streak[b] > 0) ? streak[b] + 1 : 1;
        } else {
            streak[w] = 0;
            streak[b] = 0;
        }
    }

    double getDynamicAggressionW(int p, const Config& cfg) const {
        double rawW = (cfg.aggW[p] * cfg.aggPriorWeight + decisiveW[p]) / 
                      (cfg.aggPriorWeight + totalW[p]);
        double rawB = (cfg.aggB[p] * cfg.aggPriorWeight + decisiveB[p]) / 
                      (cfg.aggPriorWeight + totalB[p]);
        return rawW * (1.0 - cfg.colorBleed) + rawB * cfg.colorBleed;
    }
    
    double getDynamicAggressionB(int p, const Config& cfg) const {
        double rawW = (cfg.aggW[p] * cfg.aggPriorWeight + decisiveW[p]) / 
                      (cfg.aggPriorWeight + totalW[p]);
        double rawB = (cfg.aggB[p] * cfg.aggPriorWeight + decisiveB[p]) / 
                      (cfg.aggPriorWeight + totalB[p]);
        return rawB * (1.0 - cfg.colorBleed) + rawW * cfg.colorBleed;
    }

    void updateDynamicRatings(const Config& cfg) {
        for (int iter = 0; iter < cfg.mapIters; ++iter) {
            std::array<double, N> nextW, nextB;
            double maxDiff = 0.0;
            
            for (int i = 0; i < N; ++i) {
                double denomW = (2.0 * cfg.priorWeight) / (lambdaW[i] + initLambdaW[i]);
                for (int j = 0; j < N; ++j) {
                    if (A_WB[i][j] > 0.0) denomW += A_WB[i][j] / (lambdaW[i] + lambdaB[j]);
                }
                nextW[i] = (cfg.priorWeight + W_W[i]) / denomW;
                
                double denomB = (2.0 * cfg.priorWeight) / (lambdaB[i] + initLambdaB[i]);
                for (int j = 0; j < N; ++j) {
                    if (A_WB[j][i] > 0.0) denomB += A_WB[j][i] / (lambdaW[j] + lambdaB[i]);
                }
                nextB[i] = (cfg.priorWeight + W_B[i]) / denomB;
                
                double diffW = std::abs(nextW[i] - lambdaW[i]);
                double diffB = std::abs(nextB[i] - lambdaB[i]);
                if (diffW > maxDiff) maxDiff = diffW;
                if (diffB > maxDiff) maxDiff = diffB;
            }
            
            lambdaW = nextW;
            lambdaB = nextB;
            if (maxDiff < cfg.mapTolerance) break;
        }

        for (int i = 0; i < N; ++i) {
            double formW = lambdaW[i] / initLambdaW[i];
            double formB = lambdaB[i] / initLambdaB[i];
            
            double newFormW = std::pow(formW, 1.0 - cfg.colorBleed) * std::pow(formB, cfg.colorBleed);
            double newFormB = std::pow(formB, 1.0 - cfg.colorBleed) * std::pow(formW, cfg.colorBleed);
            
            lambdaW[i] = initLambdaW[i] * newFormW;
            lambdaB[i] = initLambdaB[i] * newFormB;
        }

        double prodInit = 1.0;
        double prodCur = 1.0;
        for (int i = 0; i < N; ++i) {
            prodInit *= (initLambdaW[i] * initLambdaB[i]);
            prodCur  *= (lambdaW[i] * lambdaB[i]);
        }
        double shift = std::pow(prodInit / prodCur, 1.0 / (2.0 * N));
        
        for (int i = 0; i < N; ++i) {
            lambdaW[i] *= shift;
            lambdaB[i] *= shift;
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
                           TimeControl tc, const Config& cfg, int currentRound = 1) {
                                
    double lW, lB, nu;

    if (tc == RAPID) {
        lW = std::pow(10.0, (cfg.rapidRatings[w] + cfg.initialWhiteAdv / 2.0) / 400.0);
        lB = std::pow(10.0, (cfg.rapidRatings[b] - cfg.initialWhiteAdv / 2.0) / 400.0);
        nu = cfg.rapidNu;
    } else if (tc == BLITZ) {
        lW = std::pow(10.0, (cfg.blitzRatings[w] + cfg.initialWhiteAdv / 2.0) / 400.0);
        lB = std::pow(10.0, (cfg.blitzRatings[b] - cfg.initialWhiteAdv / 2.0) / 400.0);
        nu = cfg.blitzNu;
    } else {
        lW = et.lambdaW[w];
        lB = et.lambdaB[b];
        nu = cfg.classicalNu;
        
        double dynAggW = et.getDynamicAggressionW(w, cfg);
        double dynAggB = et.getDynamicAggressionB(b, cfg);
        
        dynAggW += et.streak[w] * cfg.streakAggressionMod;
        dynAggB += et.streak[b] * cfg.streakAggressionMod;
        
        double leaderPts = *std::max_element(et.points.begin(), et.points.end());
        if (leaderPts > 0.0) {
            if (et.points[w] >= leaderPts) dynAggW -= cfg.leaderCautionPenalty;
            if (et.points[b] >= leaderPts) dynAggB -= cfg.leaderCautionPenalty;
        }
        
        dynAggW = std::clamp(dynAggW, 0.0, 1.0);
        dynAggB = std::clamp(dynAggB, 0.0, 1.0);
        
        double urgency = 1.0 + cfg.overpushEscalation * (currentRound - 1);
        double baseOverpush = (dynAggW + dynAggB) / 2.0;
        double p_chaos = std::min(1.0, baseOverpush * urgency);
        
        if (rng() < p_chaos) {
            nu *= cfg.overpushNuMultiplier;
        }
    }
    
    auto p = winProbability(lW, lB, nu);
    double r = rng();
    if (r < p.win)             return 1.0;
    if (r < p.win + p.draw)    return 0.5;
    return 0.0;
}

// ─── Playoff simulation (FIDE 2026 Regulations 4.4.2) ────────────────────────

static std::vector<int> playoffMatch(EncounterTable& et, int p1, int p2,
                                     Rng& rng, TimeControl tc, const Config& cfg) {
    double p1pts = 0.0;
    for (int g = 0; g < 2; ++g) {
        int w = (g == 0) ? p1 : p2;
        int b = (g == 0) ? p2 : p1;
        double wp = simulateGame(et, w, b, rng, tc, cfg);
        p1pts += (w == p1) ? wp : 1.0 - wp;
    }
    if (p1pts > 1.0) return {p1};
    if (p1pts < 1.0) return {p2};
    return {p1, p2};
}

static std::vector<int> playoffRoundRobin(EncounterTable& et,
                                          const std::vector<int>& ids,
                                          Rng& rng, TimeControl tc, const Config& cfg) {
    std::array<double, N> pts = {};
    for (int i = 0; i < (int)ids.size(); ++i) {
        for (int j = i + 1; j < (int)ids.size(); ++j) {
            int w = (rng() < 0.5) ? ids[i] : ids[j];
            int b = (w == ids[i]) ? ids[j] : ids[i];
            double wp = simulateGame(et, w, b, rng, tc, cfg);
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
    int w1 = (rng() < 0.5) ? p1 : p2;
    int b1 = (w1 == p1) ? p2 : p1;

    double r1 = simulateGame(et, w1, b1, rng, BLITZ, cfg);
    if (r1 != 0.5) return (r1 == 1.0) ? w1 : b1;

    double r2 = simulateGame(et, b1, w1, rng, BLITZ, cfg);
    if (r2 != 0.5) return (r2 == 1.0) ? b1 : w1;

    int sdw = (rng() < 0.5) ? w1 : b1;
    int sdb = (sdw == w1) ? b1 : w1;
    return (simulateGame(et, sdw, sdb, rng, BLITZ, cfg) == 1.0) ? sdw : sdb;
}

static int simulatePlayoff(EncounterTable& et, std::vector<int> tied, Rng& rng, const Config& cfg) {
    tied = (tied.size() == 2)
        ? playoffMatch(et, tied[0], tied[1], rng, RAPID, cfg)
        : playoffRoundRobin(et, tied, rng, RAPID, cfg);
    if (tied.size() == 1) return tied[0];

    tied = (tied.size() == 2)
        ? playoffMatch(et, tied[0], tied[1], rng, BLITZ, cfg)
        : playoffRoundRobin(et, tied, rng, BLITZ, cfg);
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
        
        int absolute_gi = static_cast<int>(cfg.knownGames.size()) + i;
        int currentRound = (absolute_gi / GPR) + 1;
        
        double wp = simulateGame(et, w, b, rng, CLASSICAL, cfg, currentRound);

        if      (wp == 1.0) tracker[w][b][0]++;
        else if (wp == 0.5) tracker[w][b][1]++;
        else                tracker[w][b][2]++;

        et.setEncounter(w, b, wp);

        if ((absolute_gi + 1) % GPR == 0) et.updateDynamicRatings(cfg);
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
    int cliSimRound = (argc > 2) ? std::stoi(argv[2]) : -1;
    
    Config cfg = buildConfig(path, cliSimRound);
    runMonteCarlo(cfg, cfg.runs);
    return 0;
}