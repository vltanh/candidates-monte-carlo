// chess_montecarlo.cpp
// Build: g++ -O3 -march=native -std=c++17 -pthread src/chess_montecarlo.cpp -o bin/chess_montecarlo
// Usage: ./bin/chess_montecarlo [hyperparameters.json] [tournament.json] [simulate_from_round]

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

enum TimeControl
{
    CLASSICAL,
    RAPID,
    BLITZ
};

// "shared"   — tied players split the win probability (random selection per iteration)
// "fide2024" — Rapid mini-match → Blitz mini-match → Infinite sudden-death Blitz
// "fide2026" — Rapid mini-match → Blitz mini-match → Sudden-death Armageddon
enum class TiebreakMode
{
    SHARED,
    FIDE2024,
    FIDE2026
};

struct Probs
{
    double win, draw, loss;
};

// ─── Mathematics ─────────────────────────────────────────────────────────────

static Probs winProbability(double lambdaW, double lambdaB, double nu)
{
    double p_white = lambdaW;
    double p_black = lambdaB;
    double p_draw = nu * std::sqrt(lambdaW * lambdaB);
    double denom = p_white + p_black + p_draw;
    return {p_white / denom, p_draw / denom, p_black / denom};
}

// Dynamic Length Time-Decayed Weighted Least Squares
static double calculateVelocity(const std::vector<double> &h, const std::vector<int> &games, double timeDecay)
{
    int L = h.size();
    if (L < 2)
        return 0.0;

    double sumW = 0.0, sumXW = 0.0, sumX2W = 0.0, sumYW = 0.0, sumXYW = 0.0;

    for (int i = 0; i < L; ++i)
    {
        double timeWeight = std::pow(timeDecay, (L - 1) - i);
        double w = (1.0 + games[i]) * timeWeight;
        double x = static_cast<double>(i);
        double y = h[i];

        sumW += w;
        sumXW += w * x;
        sumX2W += w * x * x;
        sumYW += w * y;
        sumXYW += w * x * y;
    }

    double denominator = (sumW * sumX2W) - (sumXW * sumXW);
    if (denominator == 0.0)
        return 0.0;
    return ((sumW * sumXYW) - (sumXW * sumYW)) / denominator;
}

// ─── Configuration ────────────────────────────────────────────────────────────

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
    int N;
    int GPR;
    TiebreakMode tiebreak;

    std::vector<std::string> names;
    std::vector<double> ratings;
    std::vector<double> rapidRatings;
    std::vector<double> blitzRatings;

    std::vector<double> aggW;
    std::vector<double> aggB;
    std::vector<double> velC;
    std::vector<double> velR;
    std::vector<double> velB;

    std::vector<KnownGame> knownGames;
    std::vector<ScheduledGame> schedule;

    int runs;
    int simulateFromRound;
    int mapIters;
    double mapTolerance;

    double priorWeightKnown;
    double priorWeightSim;
    double colorBleed;

    double initialWhiteAdv;
    double classicalNu;
    double rapidNu;
    double blitzNu;
    double aggPriorWeight;
    double defaultAggW;
    double defaultAggB;
    double standingsAggression;

    double lookaheadFactor;
    double velocityTimeDecay;
    double rapidFormWeight;
    double blitzFormWeight;
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

static Config buildConfig(const std::string &hyperPath, const std::string &tourneyPath, int cliSimRound)
{
    std::ifstream fh(hyperPath);
    if (!fh)
        throw std::runtime_error("Cannot open hyperparameters: " + hyperPath);
    json hDoc = json::parse(fh, nullptr, true, true);

    std::ifstream ft(tourneyPath);
    if (!ft)
        throw std::runtime_error("Cannot open tournament: " + tourneyPath);
    json tDoc = json::parse(ft, nullptr, true, true);

    Config cfg;

    cfg.runs = hDoc.value("runs", 10'000'000);
    cfg.mapIters = hDoc.value("map_iters", 100);
    cfg.mapTolerance = hDoc.value("map_tolerance", 1e-8);

    double fallbackWeight = hDoc.value("prior_weight", 1.0);
    cfg.priorWeightKnown = hDoc.value("prior_weight_known", fallbackWeight);
    cfg.priorWeightSim = hDoc.value("prior_weight_sim", fallbackWeight);

    cfg.colorBleed = hDoc.value("color_bleed", 0.10);
    cfg.initialWhiteAdv = hDoc.value("initial_white_adv", 35.0);
    cfg.classicalNu = hDoc.value("classical_nu", 2.5);
    cfg.rapidNu = hDoc.value("rapid_nu", 1.5);
    cfg.blitzNu = hDoc.value("blitz_nu", 0.8);

    cfg.aggPriorWeight = hDoc.value("agg_prior_weight", 3.0);
    cfg.defaultAggW = hDoc.value("default_aggression_w", 0.25);
    cfg.defaultAggB = hDoc.value("default_aggression_b", 0.15);
    cfg.standingsAggression = hDoc.value("standings_aggression", 0.15);

    cfg.lookaheadFactor = hDoc.value("lookahead_factor", 1.0);
    cfg.velocityTimeDecay = hDoc.value("velocity_time_decay", 0.85);
    cfg.rapidFormWeight = hDoc.value("rapid_form_weight", 0.10);
    cfg.blitzFormWeight = hDoc.value("blitz_form_weight", 0.05);

    cfg.simulateFromRound = cliSimRound;

    const auto &players = tDoc.at("players");
    cfg.N = (int)players.size();
    cfg.GPR = tDoc.value("gpr", cfg.N / 2);

    std::string tbStr = tDoc.value("tiebreak", "shared");
    if (tbStr == "fide2026")
        cfg.tiebreak = TiebreakMode::FIDE2026;
    else if (tbStr == "fide2024")
        cfg.tiebreak = TiebreakMode::FIDE2024;
    else
        cfg.tiebreak = TiebreakMode::SHARED;

    cfg.names.resize(cfg.N);
    cfg.ratings.resize(cfg.N);
    cfg.rapidRatings.resize(cfg.N);
    cfg.blitzRatings.resize(cfg.N);
    cfg.aggW.resize(cfg.N);
    cfg.aggB.resize(cfg.N);
    cfg.velC.resize(cfg.N);
    cfg.velR.resize(cfg.N);
    cfg.velB.resize(cfg.N);

    auto parseVelocity = [&](const json &p, const std::string &histKey, const std::string &gamesKey)
    {
        if (!p.contains(histKey))
            return 0.0;
        std::vector<double> h = p.at(histKey).get<std::vector<double>>();
        std::vector<int> g;
        if (p.contains(gamesKey))
        {
            g = p.at(gamesKey).get<std::vector<int>>();
            if (g.size() != h.size())
                throw std::runtime_error("History/games length mismatch");
        }
        else
        {
            g.assign(h.size(), 0);
        }
        return calculateVelocity(h, g, cfg.velocityTimeDecay);
    };

    std::unordered_map<int, int> idx;
    for (int i = 0; i < cfg.N; ++i)
    {
        const auto &p = players[i];
        int fideId = p.at("fide_id").get<int>();
        idx[fideId] = i;
        cfg.names[i] = p.at("name").get<std::string>();
        cfg.ratings[i] = p.at("rating").get<double>();
        cfg.rapidRatings[i] = p.value("rapid_rating", cfg.ratings[i]);
        cfg.blitzRatings[i] = p.value("blitz_rating", cfg.ratings[i]);

        cfg.aggW[i] = p.value("aggression_w", cfg.defaultAggW);
        cfg.aggB[i] = p.value("aggression_b", cfg.defaultAggB);

        cfg.velC[i] = parseVelocity(p, "history", "games_played");
        cfg.velR[i] = parseVelocity(p, "rapid_history", "rapid_games_played");
        cfg.velB[i] = parseVelocity(p, "blitz_history", "blitz_games_played");
    }

    const auto &schedule = tDoc.at("schedule");
    for (int gi = 0; gi < (int)schedule.size(); ++gi)
    {
        const auto &g = schedule[gi];
        int round = g.contains("round") ? g.at("round").get<int>() : (gi / cfg.GPR + 1);
        int w = idx.at(g.at("white").get<int>());
        int b = idx.at(g.at("black").get<int>());

        if (round < cfg.simulateFromRound)
        {
            if (!g.contains("result") || g.at("result").is_null())
                throw std::runtime_error("Missing result for historical game in round " + std::to_string(round));
            cfg.knownGames.push_back({w, b, parseResult(g.at("result").get<std::string>())});
        }
        else
        {
            cfg.schedule.push_back({w, b});
        }
    }
    return cfg;
}

// ─── Encounter Table ──────────────────────────────────────────────────────────

struct EncounterTable
{
    int N;
    std::vector<double> lambdaW, lambdaB;
    std::vector<double> initLambdaW, initLambdaB;
    std::vector<double> points;
    std::vector<std::vector<double>> A_WB;
    std::vector<double> W_W, W_B;
    std::vector<double> decisiveW, totalW, decisiveB, totalB;

    // For tiebreaks
    std::vector<double> wins;
    std::vector<std::vector<double>> scoreMatrix;

    void init(const Config &cfg)
    {
        N = cfg.N;
        lambdaW.resize(N);
        lambdaB.resize(N);
        initLambdaW.resize(N);
        initLambdaB.resize(N);
        points.assign(N, 0.0);
        A_WB.assign(N, std::vector<double>(N, 0.0));
        W_W.assign(N, 0.0);
        W_B.assign(N, 0.0);
        decisiveW.assign(N, 0.0);
        totalW.assign(N, 0.0);
        decisiveB.assign(N, 0.0);
        totalB.assign(N, 0.0);

        wins.assign(N, 0.0);
        scoreMatrix.assign(N, std::vector<double>(N, 0.0));

        for (int i = 0; i < N; ++i)
        {
            double projC = cfg.ratings[i] + (cfg.velC[i] * cfg.lookaheadFactor);
            double projR = cfg.rapidRatings[i] + (cfg.velR[i] * cfg.lookaheadFactor);
            double projB = cfg.blitzRatings[i] + (cfg.velB[i] * cfg.lookaheadFactor);

            double speedAdj = cfg.rapidFormWeight * (projR - projC) + cfg.blitzFormWeight * (projB - projC);
            double adjRating = projC + speedAdj;

            initLambdaW[i] = lambdaW[i] = std::pow(10.0, (adjRating + cfg.initialWhiteAdv / 2.0) / 400.0);
            initLambdaB[i] = lambdaB[i] = std::pow(10.0, (adjRating - cfg.initialWhiteAdv / 2.0) / 400.0);
        }
    }

    void setEncounter(int w, int b, double whitePoints)
    {
        A_WB[w][b] += 1.0;
        W_W[w] += whitePoints;
        W_B[b] += 1.0 - whitePoints;
        points[w] += whitePoints;
        points[b] += 1.0 - whitePoints;

        double isDecisive = (whitePoints == 0.5) ? 0.0 : 1.0;
        decisiveW[w] += isDecisive;
        totalW[w] += 1.0;
        decisiveB[b] += isDecisive;
        totalB[b] += 1.0;

        scoreMatrix[w][b] += whitePoints;
        scoreMatrix[b][w] += 1.0 - whitePoints;

        if (whitePoints == 1.0)
            wins[w] += 1.0;
        else if (whitePoints == 0.0)
            wins[b] += 1.0;
    }

    double getDynamicAggressionW(int p, const Config &cfg) const
    {
        double rawW = (cfg.aggW[p] * cfg.aggPriorWeight + decisiveW[p]) / (cfg.aggPriorWeight + totalW[p]);
        double rawB = (cfg.aggB[p] * cfg.aggPriorWeight + decisiveB[p]) / (cfg.aggPriorWeight + totalB[p]);
        return rawW * (1.0 - cfg.colorBleed) + rawB * cfg.colorBleed;
    }

    double getDynamicAggressionB(int p, const Config &cfg) const
    {
        double rawW = (cfg.aggW[p] * cfg.aggPriorWeight + decisiveW[p]) / (cfg.aggPriorWeight + totalW[p]);
        double rawB = (cfg.aggB[p] * cfg.aggPriorWeight + decisiveB[p]) / (cfg.aggPriorWeight + totalB[p]);
        return rawB * (1.0 - cfg.colorBleed) + rawW * cfg.colorBleed;
    }

    void updateDynamicRatings(const Config &cfg, double currentWeight)
    {
        for (int iter = 0; iter < cfg.mapIters; ++iter)
        {
            std::vector<double> nextW(N), nextB(N);
            double maxDiff = 0.0;
            for (int i = 0; i < N; ++i)
            {
                double denomW = (2.0 * currentWeight) / (lambdaW[i] + initLambdaW[i]);
                for (int j = 0; j < N; ++j)
                    if (A_WB[i][j] > 0.0)
                        denomW += A_WB[i][j] / (lambdaW[i] + lambdaB[j]);
                nextW[i] = (currentWeight + W_W[i]) / denomW;

                double denomB = (2.0 * currentWeight) / (lambdaB[i] + initLambdaB[i]);
                for (int j = 0; j < N; ++j)
                    if (A_WB[j][i] > 0.0)
                        denomB += A_WB[j][i] / (lambdaW[j] + lambdaB[i]);
                nextB[i] = (currentWeight + W_B[i]) / denomB;

                maxDiff = std::max(maxDiff, std::max(
                                                std::abs(nextW[i] - lambdaW[i]),
                                                std::abs(nextB[i] - lambdaB[i])));
            }
            lambdaW = nextW;
            lambdaB = nextB;
            if (maxDiff < cfg.mapTolerance)
                break;
        }

        for (int i = 0; i < N; ++i)
        {
            double formW = lambdaW[i] / initLambdaW[i];
            double formB = lambdaB[i] / initLambdaB[i];
            double newFormW = std::pow(formW, 1.0 - cfg.colorBleed) * std::pow(formB, cfg.colorBleed);
            double newFormB = std::pow(formB, 1.0 - cfg.colorBleed) * std::pow(formW, cfg.colorBleed);
            lambdaW[i] = initLambdaW[i] * newFormW;
            lambdaB[i] = initLambdaB[i] * newFormB;
        }

        double prodInit = 1.0, prodCur = 1.0;
        for (int i = 0; i < N; ++i)
        {
            prodInit *= (initLambdaW[i] * initLambdaB[i]);
            prodCur *= (lambdaW[i] * lambdaB[i]);
        }
        double shift = std::pow(prodInit / prodCur, 1.0 / (2.0 * N));
        for (int i = 0; i < N; ++i)
        {
            lambdaW[i] *= shift;
            lambdaB[i] *= shift;
        }
    }
};

// ─── RNG ─────────────────────────────────────────────────────────────────────

struct Rng
{
    std::mt19937_64 eng;
    std::uniform_real_distribution<double> dist{0.0, 1.0};
    explicit Rng(uint64_t seed) : eng(seed) {}
    double operator()() { return dist(eng); }
};

// ─── Game simulation ──────────────────────────────────────────────────────────

static double simulateGame(const EncounterTable &et, int w, int b, Rng &rng,
                           TimeControl tc, const Config &cfg)
{
    double lW, lB, nu;

    if (tc == RAPID)
    {
        lW = std::pow(10.0, (cfg.rapidRatings[w] + cfg.initialWhiteAdv / 2.0) / 400.0);
        lB = std::pow(10.0, (cfg.rapidRatings[b] - cfg.initialWhiteAdv / 2.0) / 400.0);
        nu = cfg.rapidNu;
    }
    else if (tc == BLITZ)
    {
        lW = std::pow(10.0, (cfg.blitzRatings[w] + cfg.initialWhiteAdv / 2.0) / 400.0);
        lB = std::pow(10.0, (cfg.blitzRatings[b] - cfg.initialWhiteAdv / 2.0) / 400.0);
        nu = cfg.blitzNu;
    }
    else
    {
        lW = et.lambdaW[w];
        lB = et.lambdaB[b];

        double dynAggW = et.getDynamicAggressionW(w, cfg);
        double dynAggB = et.getDynamicAggressionB(b, cfg);
        double baselineAgg = (cfg.defaultAggW + cfg.defaultAggB) / 2.0;
        double matchAgg = (dynAggW + dynAggB) / 2.0;
        double styleMultiplier = baselineAgg / std::max(0.01, matchAgg);

        double leaderPts = *std::max_element(et.points.begin(), et.points.end());
        int totalRounds = (cfg.knownGames.size() + cfg.schedule.size()) / cfg.GPR;

        auto calcMotivation = [&](int p)
        {
            double gamesPlayed = et.totalW[p] + et.totalB[p];
            double roundsLeft = std::max(1.0, static_cast<double>(totalRounds) - gamesPlayed);
            double deficit = leaderPts - et.points[p];
            double R = deficit / roundsLeft;

            if (R <= 0.0)
                return 1.0;
            if (R < 0.75)
            {
                double dist = std::abs(R - 0.375) / 0.375;
                return 1.0 - cfg.standingsAggression * (1.0 - dist);
            }
            else
            {
                double chillFactor = std::min(1.0, (R - 0.75) / 0.25);
                return 1.0 + (cfg.standingsAggression * 1.5) * chillFactor;
            }
        };

        double standingsMultiplier = (calcMotivation(w) + calcMotivation(b)) / 2.0;
        nu = cfg.classicalNu * styleMultiplier * standingsMultiplier;
    }

    auto p = winProbability(lW, lB, nu);
    double r = rng();
    if (r < p.win)
        return 1.0;
    if (r < p.win + p.draw)
        return 0.5;
    return 0.0;
}

// ─── Playoff simulation ──────────────────────────────────────────────────────

static std::vector<int> playoffMatch(EncounterTable &et, int p1, int p2,
                                     Rng &rng, TimeControl tc, const Config &cfg)
{
    double p1pts = 0.0;
    for (int g = 0; g < 2; ++g)
    {
        int w = (g == 0) ? p1 : p2;
        int b = (g == 0) ? p2 : p1;
        double wp = simulateGame(et, w, b, rng, tc, cfg);
        p1pts += (w == p1) ? wp : 1.0 - wp;
    }
    if (p1pts > 1.0)
        return {p1};
    if (p1pts < 1.0)
        return {p2};
    return {p1, p2};
}

static std::vector<int> playoffRoundRobin(EncounterTable &et, const std::vector<int> &ids,
                                          Rng &rng, TimeControl tc, const Config &cfg)
{
    std::vector<double> pts(cfg.N, 0.0);
    for (int i = 0; i < (int)ids.size(); ++i)
        for (int j = i + 1; j < (int)ids.size(); ++j)
        {
            int w = (rng() < 0.5) ? ids[i] : ids[j];
            int b = (w == ids[i]) ? ids[j] : ids[i];
            double wp = simulateGame(et, w, b, rng, tc, cfg);
            pts[w] += wp;
            pts[b] += 1.0 - wp;
        }
    double best = 0.0;
    for (int id : ids)
        best = std::max(best, pts[id]);
    std::vector<int> winners;
    for (int id : ids)
        if (pts[id] == best)
            winners.push_back(id);
    return winners;
}

static int knockoutMatch(EncounterTable &et, int p1, int p2, Rng &rng, const Config &cfg)
{
    if (cfg.tiebreak == TiebreakMode::FIDE2024)
    {
        int w = (rng() < 0.5) ? p1 : p2;
        int b = (w == p1) ? p2 : p1;

        while (true)
        {
            double r = simulateGame(et, w, b, rng, BLITZ, cfg);
            if (r == 1.0)
                return w;
            if (r == 0.0)
                return b;
            std::swap(w, b);
        }
    }
    else
    {
        int w1 = (rng() < 0.5) ? p1 : p2;
        int b1 = (w1 == p1) ? p2 : p1;
        double r1 = simulateGame(et, w1, b1, rng, BLITZ, cfg);
        if (r1 != 0.5)
            return (r1 == 1.0) ? w1 : b1;

        double r2 = simulateGame(et, b1, w1, rng, BLITZ, cfg);
        if (r2 != 0.5)
            return (r2 == 1.0) ? b1 : w1;

        int sdw = (rng() < 0.5) ? w1 : b1;
        int sdb = (sdw == w1) ? b1 : w1;
        return (simulateGame(et, sdw, sdb, rng, BLITZ, cfg) == 1.0) ? sdw : sdb;
    }
}

static int simulatePlayoff(EncounterTable &et, std::vector<int> tied, Rng &rng, const Config &cfg)
{
    tied = (tied.size() == 2)
               ? playoffMatch(et, tied[0], tied[1], rng, RAPID, cfg)
               : playoffRoundRobin(et, tied, rng, RAPID, cfg);
    if (tied.size() == 1)
        return tied[0];

    tied = (tied.size() == 2)
               ? playoffMatch(et, tied[0], tied[1], rng, BLITZ, cfg)
               : playoffRoundRobin(et, tied, rng, BLITZ, cfg);
    if (tied.size() == 1)
        return tied[0];

    std::shuffle(tied.begin(), tied.end(), rng.eng);
    while (tied.size() > 1)
    {
        std::vector<int> next;
        for (int i = 0; i < (int)tied.size(); i += 2)
            next.push_back((i + 1 < (int)tied.size())
                               ? knockoutMatch(et, tied[i], tied[i + 1], rng, cfg)
                               : tied[i]);
        tied = std::move(next);
    }
    return tied[0];
}

// ─── Threading Structures ─────────────────────────────────────────────────────

struct ThreadResult
{
    std::vector<int> wins;
    std::vector<double> expectedPoints;
    std::vector<std::vector<int>> rankMatrix;
    std::vector<std::vector<std::array<int, 3>>> tracker;

    explicit ThreadResult(int n)
        : wins(n, 0),
          expectedPoints(n, 0.0),
          rankMatrix(n, std::vector<int>(n, 0)),
          tracker(n, std::vector<std::array<int, 3>>(n, std::array<int, 3>{})) {}
};

// ─── One Monte Carlo iteration ────────────────────────────────────────────────

static void runOneIteration(const Config &cfg, Rng &rng, ThreadResult &out, EncounterTable et)
{
    const int nGames = static_cast<int>(cfg.schedule.size());
    for (int i = 0; i < nGames; ++i)
    {
        auto [w, b] = cfg.schedule[i];
        int absolute_gi = static_cast<int>(cfg.knownGames.size()) + i;

        double wp = simulateGame(et, w, b, rng, CLASSICAL, cfg);
        if (wp == 1.0)
            out.tracker[w][b][0]++;
        else if (wp == 0.5)
            out.tracker[w][b][1]++;
        else
            out.tracker[w][b][2]++;

        et.setEncounter(w, b, wp);
        if ((absolute_gi + 1) % cfg.GPR == 0)
            et.updateDynamicRatings(cfg, cfg.priorWeightSim);
    }

    std::vector<int> standingsOrder(cfg.N);
    std::iota(standingsOrder.begin(), standingsOrder.end(), 0);

    // 4.4.2.3.a: Sonneborn-Berger
    std::vector<double> sb(cfg.N, 0.0);
    for (int i = 0; i < cfg.N; ++i)
    {
        for (int j = 0; j < cfg.N; ++j)
        {
            sb[i] += et.scoreMatrix[i][j] * et.points[j];
        }
    }

    // 4.4.2.3.d: Random Jitter (Drawing of lots)
    std::vector<double> jitter(cfg.N);
    for (int i = 0; i < cfg.N; ++i)
    {
        jitter[i] = rng();
    }

    std::sort(standingsOrder.begin(), standingsOrder.end(), [&](int a, int b)
              {
        if (std::abs(et.points[a] - et.points[b]) > 1e-9) 
            return et.points[a] > et.points[b];
            
        if (std::abs(sb[a] - sb[b]) > 1e-9) 
            return sb[a] > sb[b];
            
        if (et.wins[a] != et.wins[b]) 
            return et.wins[a] > et.wins[b];
            
        return jitter[a] > jitter[b]; });

    double maxPts = et.points[standingsOrder[0]];
    std::vector<int> top;
    for (int i = 0; i < cfg.N; ++i)
    {
        if (std::abs(et.points[i] - maxPts) < 1e-9)
            top.push_back(i);
    }

    int winner = standingsOrder[0];
    if (top.size() > 1)
    {
        if (cfg.tiebreak != TiebreakMode::SHARED)
        {
            winner = simulatePlayoff(et, top, rng, cfg);
        }
        else
        {
            std::uniform_int_distribution<int> d(0, (int)top.size() - 1);
            winner = top[d(rng.eng)];
        }

        auto it = std::find(standingsOrder.begin(), standingsOrder.end(), winner);
        if (it != standingsOrder.begin())
        {
            standingsOrder.erase(it);
            standingsOrder.insert(standingsOrder.begin(), winner);
        }
    }

    out.wins[winner]++;
    for (int rank = 0; rank < cfg.N; ++rank)
    {
        int p = standingsOrder[rank];
        out.rankMatrix[p][rank]++;
        out.expectedPoints[p] += et.points[p];
    }
}

// ─── Parallel Monte Carlo ─────────────────────────────────────────────────────

static void workerThread(const Config &cfg, int iters, uint64_t seed,
                         ThreadResult &out, const EncounterTable &base_et)
{
    Rng rng(seed);
    for (int i = 0; i < iters; ++i)
        runOneIteration(cfg, rng, out, base_et);
}

static void runMonteCarlo(const Config &cfg, int totalIters)
{
    EncounterTable base_et;
    base_et.init(cfg);
    for (int i = 0; i < (int)cfg.knownGames.size(); ++i)
    {
        const auto &g = cfg.knownGames[i];
        base_et.setEncounter(g.w, g.b, g.whitePoints);
        if ((i + 1) % cfg.GPR == 0)
            base_et.updateDynamicRatings(cfg, cfg.priorWeightKnown);
    }
    if (!cfg.knownGames.empty() && cfg.knownGames.size() % cfg.GPR != 0)
        base_et.updateDynamicRatings(cfg, cfg.priorWeightKnown);

    int nThreads = static_cast<int>(std::thread::hardware_concurrency());
    if (nThreads <= 0)
        nThreads = 4;

    std::vector<ThreadResult> results(nThreads, ThreadResult(cfg.N));
    std::vector<std::thread> threads;
    std::mt19937_64 seedGen(42);

    int base = totalIters / nThreads;
    int rem = totalIters % nThreads;

    // --- Start Timer ---
    auto t0 = std::chrono::high_resolution_clock::now();

    for (int t = 0; t < nThreads; ++t)
    {
        int iters = base + (t < rem ? 1 : 0);
        threads.emplace_back(workerThread, std::cref(cfg), iters, seedGen(),
                             std::ref(results[t]), std::cref(base_et));
    }
    for (auto &th : threads)
        th.join();

    // --- End Timer ---
    auto t1 = std::chrono::high_resolution_clock::now();
    double elapsed_time = std::chrono::duration<double>(t1 - t0).count();

    std::vector<int> wins(cfg.N, 0);
    std::vector<double> expectedPoints(cfg.N, 0.0);
    std::vector<std::vector<int>> rankMatrix(cfg.N, std::vector<int>(cfg.N, 0));
    std::vector<std::vector<std::array<int, 3>>> tracker(
        cfg.N, std::vector<std::array<int, 3>>(cfg.N, std::array<int, 3>{}));

    for (const auto &r : results)
    {
        for (int i = 0; i < cfg.N; ++i)
        {
            wins[i] += r.wins[i];
            expectedPoints[i] += r.expectedPoints[i];
            for (int j = 0; j < cfg.N; ++j)
            {
                rankMatrix[i][j] += r.rankMatrix[i][j];
            }
            for (int j = 0; j < cfg.N; ++j)
            {
                for (int k = 0; k < 3; ++k)
                {
                    tracker[i][j][k] += r.tracker[i][j][k];
                }
            }
        }
    }

    // Using ordered_json preserves the exact top-to-bottom insertion order
    // and prevents "10" from sorting before "2".
    nlohmann::ordered_json jOut;

    // 1. Metadata (Wall-clock time)
    jOut["metadata"] = {{"time_seconds", elapsed_time}};

    // 2. End-Tournament Results (Placed at the top)
    jOut["winner_probs"] = nlohmann::ordered_json::object();
    jOut["expected_points"] = nlohmann::ordered_json::object();
    jOut["rank_matrix"] = nlohmann::ordered_json::object();

    for (int i = 0; i < cfg.N; ++i)
    {
        std::string name = cfg.names[i];
        jOut["winner_probs"][name] = (double)wins[i] / totalIters;
        jOut["expected_points"][name] = expectedPoints[i] / totalIters;

        jOut["rank_matrix"][name] = nlohmann::ordered_json::array();
        for (int r = 0; r < cfg.N; ++r)
        {
            jOut["rank_matrix"][name].push_back((double)rankMatrix[i][r] / totalIters);
        }
    }

    // 3. Round-by-Round Results
    jOut["game_probs"] = nlohmann::ordered_json::object();

    int completedGames = static_cast<int>(cfg.knownGames.size());
    for (int i = 0; i < (int)cfg.schedule.size(); ++i)
    {
        int absolute_gi = completedGames + i;
        int calcRound = absolute_gi / cfg.GPR + 1;
        std::string rKey = std::to_string(calcRound);

        if (!jOut["game_probs"].contains(rKey))
        {
            jOut["game_probs"][rKey] = nlohmann::ordered_json::object();
        }

        auto [w, b] = cfg.schedule[i];
        std::string pairKey = cfg.names[w] + "|" + cfg.names[b];

        // Use an array to preserve exactly [White Win, Draw, Black Win]
        jOut["game_probs"][rKey][pairKey] = nlohmann::ordered_json::array({(double)tracker[w][b][0] / totalIters,
                                                                           (double)tracker[w][b][1] / totalIters,
                                                                           (double)tracker[w][b][2] / totalIters});
    }

    // Dump with 4-space indent
    std::cout << jOut.dump(4) << "\n";
}

// ─── Entry point ─────────────────────────────────────────────────────────────

int main(int argc, char *argv[])
{
    const std::string hyperPath = (argc > 1) ? argv[1] : "hyperparameters.json";
    const std::string tourneyPath = (argc > 2) ? argv[2] : "tournament.json";
    int cliSimRound = (argc > 3) ? std::stoi(argv[3]) : 1;

    try
    {
        Config cfg = buildConfig(hyperPath, tourneyPath, cliSimRound);
        runMonteCarlo(cfg, cfg.runs);
    }
    catch (const std::exception &e)
    {
        std::cerr << "Error: " << e.what() << "\n";
        return 1;
    }

    return 0;
}