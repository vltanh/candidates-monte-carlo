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
#include <chrono>
#include "json.hpp"

using json = nlohmann::json;

static constexpr int N = 8;
static constexpr int GPR = N / 2;
static constexpr double ELO_TO_THETA = 0.00575646273; // ln(10) / 400

enum TimeControl
{
    CLASSICAL,
    RAPID,
    BLITZ
};

// ─── Mathematical Core ───────────────────────────────────────────────────────

inline double sigmoid(double x)
{
    return 1.0 / (1.0 + std::exp(-x));
}

struct Probs
{
    double win, draw, loss;
};

// Ordered Logit Outcome Model
static Probs orderedLogitProb(double thetaW, double thetaB, double gamma, double c, double s = 1.0)
{
    double delta = thetaW - thetaB + gamma;
    double p_loss = sigmoid((-c - delta) / s);
    double p_win = 1.0 - sigmoid((c - delta) / s);
    double p_draw = 1.0 - p_loss - p_win;
    return {p_win, p_draw, p_loss};
}

// ─── Time-Decayed WLS in Theta Space ─────────────────────────────────────────

static double calculateThetaVelocity(const std::vector<double> &h_elo, const std::vector<int> &games, double timeDecay)
{
    int L = h_elo.size();
    if (L < 2)
        return 0.0;

    double sumW = 0.0, sumXW = 0.0, sumX2W = 0.0, sumYW = 0.0, sumXYW = 0.0;

    for (int i = 0; i < L; ++i)
    {
        double timeWeight = std::pow(timeDecay, (L - 1) - i);
        double w = (1.0 + games[i]) * timeWeight;

        double x = static_cast<double>(i);
        double y = h_elo[i] * ELO_TO_THETA; // Convert history directly to log-odds

        sumW += w;
        sumXW += w * x;
        sumX2W += w * x * x;
        sumYW += w * y;
        sumXYW += w * x * y;
    }

    double denom = (sumW * sumX2W) - (sumXW * sumXW);
    if (denom == 0.0)
        return 0.0;
    return ((sumW * sumXYW) - (sumXW * sumYW)) / denom;
}

// ─── Configuration & Data ────────────────────────────────────────────────────

struct KnownGame
{
    int w, b;
    double whitePoints;
};
struct ScheduledGame
{
    int w, b;
};

struct Config
{
    std::array<std::string, N> names;

    // Latent traits in Theta space
    std::array<double, N> thetaC;
    std::array<double, N> thetaR;
    std::array<double, N> thetaB;

    std::vector<KnownGame> knownGames;
    std::vector<ScheduledGame> schedule;

    int runs;
    int simulateFromRound;

    // Ordered Logit Parameters
    double gamma;       // White advantage in theta space
    double c_classical; // Draw threshold classical
    double c_rapid;     // Draw threshold rapid
    double c_blitz;     // Draw threshold blitz

    // Hierarchical Parameters
    double tau_sq; // Epistemic variance (e.g., 0.04)
    int nu;        // Inverse-Wishart degrees of freedom
};

static double parseResult(const std::string &s)
{
    if (s == "1-0")
        return 1.0;
    if (s == "1/2-1/2")
        return 0.5;
    if (s == "0-1")
        return 0.0;
    throw std::runtime_error("Unknown result: \"" + s + "\"");
}

static Config buildConfig(const std::string &path, int startingRound)
{
    std::ifstream f(path);
    if (!f)
        throw std::runtime_error("Cannot open: " + path);
    json doc = json::parse(f);
    Config cfg;

    cfg.runs = doc.value("runs", 10'000'000);
    cfg.simulateFromRound = startingRound;

    double lookaheadFactor = doc.value("lookahead_factor", 1.0);
    double velocityTimeDecay = doc.value("velocity_time_decay", 0.85);

    // 35 Elo White Advantage -> Theta space
    cfg.gamma = doc.value("initial_white_adv", 35.0) * ELO_TO_THETA;

    // Calibrate 'c' boundaries from empirical draw rates
    double d_class = doc.value("draw_rate_classical", 0.55);
    double d_rapid = doc.value("draw_rate_rapid", 0.35);
    double d_blitz = doc.value("draw_rate_blitz", 0.25);

    cfg.c_classical = std::log((1.0 + d_class) / (1.0 - d_class));
    cfg.c_rapid = std::log((1.0 + d_rapid) / (1.0 - d_rapid));
    cfg.c_blitz = std::log((1.0 + d_blitz) / (1.0 - d_blitz));

    cfg.tau_sq = doc.value("epistemic_variance", 0.04);
    cfg.nu = doc.value("iw_degrees_of_freedom", 10);

    const auto &players = doc.at("players");
    if ((int)players.size() != N)
        throw std::runtime_error("Expected 8 players");

    std::unordered_map<int, int> idx;
    double sumC = 0, sumR = 0, sumB = 0;

    auto parseVel = [&](const json &p, const std::string &hKey, const std::string &gKey)
    {
        if (!p.contains(hKey))
            return 0.0;
        std::vector<double> h = p.at(hKey).get<std::vector<double>>();
        std::vector<int> g(h.size(), 0);
        if (p.contains(gKey))
            g = p.at(gKey).get<std::vector<int>>();
        return calculateThetaVelocity(h, g, velocityTimeDecay);
    };

    for (int i = 0; i < N; ++i)
    {
        const auto &p = players[i];
        idx[p.at("fide_id").get<int>()] = i;
        cfg.names[i] = p.at("name").get<std::string>();

        double rawEloC = p.at("rating").get<double>();
        double rawEloR = p.value("rapid_rating", rawEloC);
        double rawEloB = p.value("blitz_rating", rawEloC);

        double velC = parseVel(p, "history", "games_played");
        double velR = parseVel(p, "rapid_history", "rapid_games_played");
        double velB = parseVel(p, "blitz_history", "blitz_games_played");

        // Convert to Theta space and project velocity
        cfg.thetaC[i] = (rawEloC * ELO_TO_THETA) + (velC * lookaheadFactor);
        cfg.thetaR[i] = (rawEloR * ELO_TO_THETA) + (velR * lookaheadFactor);
        cfg.thetaB[i] = (rawEloB * ELO_TO_THETA) + (velB * lookaheadFactor);

        sumC += cfg.thetaC[i];
        sumR += cfg.thetaR[i];
        sumB += cfg.thetaB[i];
    }

    // Identifiability Constraint: Mean-centering in Theta Space
    double meanC = sumC / N, meanR = sumR / N, meanB = sumB / N;
    for (int i = 0; i < N; ++i)
    {
        cfg.thetaC[i] -= meanC;
        cfg.thetaR[i] -= meanR;
        cfg.thetaB[i] -= meanB;
    }

    const auto &schedule = doc.at("schedule");
    for (int gi = 0; gi < (int)schedule.size(); ++gi)
    {
        const auto &g = schedule[gi];
        int round = gi / GPR + 1;
        int w = idx.at(g.at("white").get<int>());
        int b = idx.at(g.at("black").get<int>());

        if (round < cfg.simulateFromRound)
        {
            if (!g.contains("result") || g.at("result").is_null())
            {
                throw std::runtime_error("Missing result for historical game in round " + std::to_string(round));
            }
            cfg.knownGames.push_back({w, b, parseResult(g.at("result").get<std::string>())});
        }
        else
        {
            cfg.schedule.push_back({w, b});
        }
    }

    return cfg;
}

// ─── Hierarchical Covariance Shrinkage ───────────────────────────────────────

static void applyLaplaceHierarchicalShrinkage(Config &cfg)
{
    double scale = (cfg.nu - 3 - 1) * cfg.tau_sq;
    double Lambda[3][3] = {
        {scale, 0, 0},
        {0, scale, 0},
        {0, 0, scale}};

    double S[3][3] = {0};
    for (int i = 0; i < N; ++i)
    {
        double vec[3] = {cfg.thetaC[i], cfg.thetaR[i], cfg.thetaB[i]};
        for (int r = 0; r < 3; ++r)
        {
            for (int c = 0; c < 3; ++c)
            {
                S[r][c] += vec[r] * vec[c];
            }
        }
    }
    for (int i = 0; i < 3; ++i)
        S[i][i] += N * cfg.tau_sq;

    double Sigma[3][3];
    double iw_denom = cfg.nu + N + 4;
    for (int r = 0; r < 3; ++r)
    {
        for (int c = 0; c < 3; ++c)
        {
            Sigma[r][c] = (Lambda[r][c] + S[r][c]) / iw_denom;
        }
    }

    double S_RR = Sigma[1][1], S_RB = Sigma[1][2];
    double S_BR = Sigma[2][1], S_BB = Sigma[2][2];
    double S_CR = Sigma[0][1], S_CB = Sigma[0][2];

    double det = (S_RR * S_BB) - (S_RB * S_BR);
    if (det == 0.0)
        return;

    double inv_RR = S_BB / det;
    double inv_RB = -S_RB / det;
    double inv_BR = -S_BR / det;
    double inv_BB = S_RR / det;

    for (int i = 0; i < N; ++i)
    {
        double obsR = cfg.thetaR[i];
        double obsB = cfg.thetaB[i];

        double tempR = inv_RR * obsR + inv_RB * obsB;
        double tempB = inv_BR * obsR + inv_BB * obsB;

        double shift = S_CR * tempR + S_CB * tempB;

        cfg.thetaC[i] += shift;
    }
}

// ─── Simulation Engine ───────────────────────────────────────────────────────

struct EncounterTable
{
    std::array<double, N> theta;
    std::array<double, N> points;
    int streak[N];

    void init(const Config &cfg)
    {
        theta = cfg.thetaC;
        points.fill(0.0);
        std::fill(std::begin(streak), std::end(streak), 0);
    }

    void recordGame(int w, int b, double whitePts)
    {
        points[w] += whitePts;
        points[b] += 1.0 - whitePts;

        if (whitePts == 1.0)
        {
            streak[w] = (streak[w] > 0) ? streak[w] + 1 : 1;
            streak[b] = (streak[b] < 0) ? streak[b] - 1 : -1;
        }
        else if (whitePts == 0.0)
        {
            streak[w] = (streak[w] < 0) ? streak[w] - 1 : -1;
            streak[b] = (streak[b] > 0) ? streak[b] + 1 : 1;
        }
        else
        {
            streak[w] = 0;
            streak[b] = 0;
        }
    }
};

struct Rng
{
    std::mt19937_64 eng;
    std::uniform_real_distribution<double> dist{0.0, 1.0};
    explicit Rng(uint64_t seed) : eng(seed) {}
    double operator()() { return dist(eng); }
};

static double simulateGame(EncounterTable &et, int w, int b, Rng &rng, TimeControl tc, const Config &cfg)
{
    double tW, tB, c_thresh;

    if (tc == RAPID)
    {
        tW = cfg.thetaR[w];
        tB = cfg.thetaR[b];
        c_thresh = cfg.c_rapid;
    }
    else if (tc == BLITZ)
    {
        tW = cfg.thetaB[w];
        tB = cfg.thetaB[b];
        c_thresh = cfg.c_blitz;
    }
    else
    {
        tW = et.theta[w];
        tB = et.theta[b];
        c_thresh = cfg.c_classical;

        // Dynamic Momentum
        tW += et.streak[w] * 0.2;
        tB += et.streak[b] * 0.2;
    }

    auto p = orderedLogitProb(tW, tB, cfg.gamma, c_thresh);
    double r = rng();
    if (r < p.win)
        return 1.0;
    if (r < p.win + p.draw)
        return 0.5;
    return 0.0;
}

static int simulatePlayoff(EncounterTable &et, std::vector<int> tied, Rng &rng, const Config &cfg)
{
    std::shuffle(tied.begin(), tied.end(), rng.eng);
    while (tied.size() > 1)
    {
        std::vector<int> next;
        for (int i = 0; i < (int)tied.size(); i += 2)
        {
            if (i + 1 < (int)tied.size())
            {
                int w = tied[i], b = tied[i + 1];
                double res = simulateGame(et, w, b, rng, BLITZ, cfg);
                next.push_back((res == 1.0 || (res == 0.5 && rng() > 0.5)) ? w : b);
            }
            else
            {
                next.push_back(tied[i]);
            }
        }
        tied = std::move(next);
    }
    return tied[0];
}

static int runOneIteration(const Config &cfg, Rng &rng, int tracker[N][N][3])
{
    EncounterTable et;
    et.init(cfg);

    for (const auto &g : cfg.knownGames)
    {
        et.recordGame(g.w, g.b, g.whitePoints);
    }

    for (const auto &g : cfg.schedule)
    {
        double wp = simulateGame(et, g.w, g.b, rng, CLASSICAL, cfg);

        if (wp == 1.0)
            tracker[g.w][g.b][0]++;
        else if (wp == 0.5)
            tracker[g.w][g.b][1]++;
        else
            tracker[g.w][g.b][2]++;

        et.recordGame(g.w, g.b, wp);
    }

    double maxPts = *std::max_element(et.points.begin(), et.points.end());
    std::vector<int> top;
    for (int i = 0; i < N; ++i)
        if (et.points[i] == maxPts)
            top.push_back(i);

    return (top.size() == 1) ? top[0] : simulatePlayoff(et, top, rng, cfg);
}

// ─── Execution ───────────────────────────────────────────────────────────────

struct ThreadResult
{
    std::array<int, N> wins = {};
    int tracker[N][N][3] = {};
};

static void workerThread(const Config &cfg, int iters, uint64_t seed, ThreadResult &out)
{
    Rng rng(seed);
    for (int i = 0; i < iters; ++i)
    {
        out.wins[runOneIteration(cfg, rng, out.tracker)]++;
    }
}

int main(int argc, char *argv[])
{
    try
    {
        const std::string path = (argc > 1) ? argv[1] : "tournament.json";
        int startingRound = (argc > 2) ? std::stoi(argv[2]) : 1;

        Config cfg = buildConfig(path, startingRound);
        applyLaplaceHierarchicalShrinkage(cfg);

        // --- CALC CURRENT STANDINGS ---
        std::array<double, N> currentPts = {0};
        for (const auto &g : cfg.knownGames)
        {
            currentPts[g.w] += g.whitePoints;
            currentPts[g.b] += 1.0 - g.whitePoints;
        }

        std::array<int, N> standingsOrder;
        std::iota(standingsOrder.begin(), standingsOrder.end(), 0);
        std::sort(standingsOrder.begin(), standingsOrder.end(), [&](int a, int b)
                  { return currentPts[a] > currentPts[b]; });

        int completedGames = cfg.knownGames.size();
        int currentRound = completedGames / GPR + 1;
        bool isMidRound = (completedGames % GPR != 0);

        std::cout << "=== Current Standings (" << (isMidRound ? "Mid-Round " : "Before Round ")
                  << currentRound << ") ===\n";
        for (int i : standingsOrder)
        {
            std::cout << cfg.names[i] << ": " << currentPts[i] << " pts\n";
        }
        std::cout << "\n";

        int nThreads = static_cast<int>(std::thread::hardware_concurrency());
        if (nThreads <= 0)
            nThreads = 4;

        std::cout << "Hierarchical Ordered Logit Engine initialized.\n";
        std::cout << "Simulating from Round " << startingRound << "...\n";
        std::cout << "Running " << cfg.runs << " iterations across " << nThreads << " threads...\n";

        auto t0 = std::chrono::high_resolution_clock::now();

        std::vector<ThreadResult> results(nThreads);
        std::vector<std::thread> threads;
        std::mt19937_64 seedGen(42);

        int base = cfg.runs / nThreads;
        int rem = cfg.runs % nThreads;
        for (int t = 0; t < nThreads; ++t)
        {
            int iters = base + (t < rem ? 1 : 0);
            threads.emplace_back(workerThread, std::cref(cfg), iters, seedGen(), std::ref(results[t]));
        }
        for (auto &th : threads)
            th.join();

        double elapsed = std::chrono::duration<double>(std::chrono::high_resolution_clock::now() - t0).count();

        std::array<int, N> wins = {};
        int tracker[N][N][3] = {};
        for (const auto &r : results)
        {
            for (int i = 0; i < N; ++i)
                wins[i] += r.wins[i];
            for (int i = 0; i < N; ++i)
            {
                for (int j = 0; j < N; ++j)
                {
                    for (int k = 0; k < 3; ++k)
                        tracker[i][j][k] += r.tracker[i][j][k];
                }
            }
        }

        std::cout << std::fixed << std::setprecision(2) << "Done in " << elapsed << "s\n\n";

        // --- PRINT MATCH PREDICTIONS ---
        std::cout << "=== Monte Carlo Match Predictions ===\n";
        for (int i = 0; i < (int)cfg.schedule.size(); ++i)
        {
            int absolute_gi = completedGames + i;
            if (i == 0 || absolute_gi % GPR == 0)
            {
                int calcRound = absolute_gi / GPR + 1;
                bool isOngoing = (i == 0 && absolute_gi % GPR != 0);
                std::cout << "\n--- ROUND " << calcRound << (isOngoing ? " (Ongoing)" : "") << " ---\n";
            }
            auto [w, b] = cfg.schedule[i];

            double pw = 100.0 * tracker[w][b][0] / cfg.runs;
            double pd = 100.0 * tracker[w][b][1] / cfg.runs;
            double pb = 100.0 * tracker[w][b][2] / cfg.runs;

            std::cout << cfg.names[w] << " vs " << cfg.names[b] << "\n"
                      << "  1-0: " << std::fixed << std::setprecision(1) << pw
                      << "% | 1/2-1/2: " << pd << "% | 0-1: " << pb << "%\n";
        }
        std::cout << "\n";

        // --- PRINT OVERALL WIN PROBABILITIES ---
        std::array<int, N> order;
        std::iota(order.begin(), order.end(), 0);
        std::sort(order.begin(), order.end(), [&](int a, int b)
                  { return wins[a] > wins[b]; });

        int r_out = completedGames / GPR + 1;
        std::cout << "=== Tournament Win Probabilities (from Round " << r_out << ") ===\n";
        for (int i : order)
        {
            std::cout << std::setw(7) << std::fixed << std::setprecision(2)
                      << (100.0 * wins[i] / cfg.runs) << "% - " << cfg.names[i] << "\n";
        }
    }
    catch (const std::exception &e)
    {
        std::cerr << "Fatal Error: " << e.what() << "\n";
        return 1;
    }
    return 0;
}