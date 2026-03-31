import drawProbability from './drawProbability';

const WHITE_POINTS_BY_OUTCOME = {
    '1-0': 1,
    '0-1': 0,
    '1/2-1/2': 0.5,
};

interface TournamentEncounterPlayer {
    fideId: number;
    name: string;
    rating: number;
}
interface InternalTournamentEncounterPlayer extends TournamentEncounterPlayer {
    points: number;
}

type Outcome = '1-0' | '0-1' | '1/2-1/2';
interface EncounterGame {
    whiteFideId: number;
    blackFideId: number;
    result: Outcome;
}
interface TournamentEncounterConfig {
    players: TournamentEncounterPlayer[];
    games: EncounterGame[];
}

const bluebaumWinnerPoints = new Map<number, number>(); // points -> how often

class EncounterTable {
    private table = new Map<string, number>(); // result from view of first fideId (currently only used to check if players played...)
    private playersByFideId = new Map<number, InternalTournamentEncounterPlayer>();

    public constructor(config: TournamentEncounterConfig) {
        for (const player of config.players) {
            this.playersByFideId.set(player.fideId, { ...player, points: 0 });
        }

        for (const game of config.games) {
            this.setEncounter(game.whiteFideId, game.blackFideId, game.result);
        }
    }

    private setEncounter(fideIdWhite: number, fideIdBlack: number, result: '1-0' | '0-1' | '1/2-1/2') {
        const key = [fideIdWhite, fideIdBlack].join('/');
        const points = WHITE_POINTS_BY_OUTCOME[result];

        if (this.table.has(key)) {
            throw new Error(`Encounter ${key} already exists!`);
        }
        this.table.set(key, points);

        this.getPlayer(fideIdWhite).points += points;
        this.getPlayer(fideIdBlack).points += (1 - points);
    }

    private hasPlayed(whiteFideId: number, blackFideId: number) {
        return this.table.get([whiteFideId, blackFideId].join('/')) !== undefined;
    }

    public getPlayer(fideId: number) {
        const player = this.playersByFideId.get(fideId);
        if (!player) {
            throw new Error(`Player not found, fideId=${fideId}`);
        }
        return player;
    }

    public simulateLeftRounds() {
        for (const player of this.playersByFideId.values()) {
            for (const oppo of this.playersByFideId.values()) {
                if (player.fideId === oppo.fideId) {
                    continue;
                }
                if (!this.hasPlayed(player.fideId, oppo.fideId)) {
                    this.simulateEncounter(player.fideId, oppo.fideId);
                }
            }
        }

        // detect winner
        const players = this.getSortedPlayers();
        const maxPoints = players[0].points;
        const topPlayers = players.filter(e => e.points === maxPoints);

        // pick random winner of people with max points
        const winnerIndex = Math.floor(Math.random() * topPlayers.length);
        const winnerFideId = topPlayers[winnerIndex].fideId;
        if (winnerFideId === 24651516) {
            bluebaumWinnerPoints.set(maxPoints, (bluebaumWinnerPoints.get(maxPoints) ?? 0) + 1);
        }
        return winnerFideId;
    }

    private simulateEncounter(whiteFideId: number, blackFideId: number) {
        const whiteRating = this.getPlayer(whiteFideId).rating;
        const blackRating = this.getPlayer(blackFideId).rating;

        const prob = this.calculateWinProbability(whiteRating, blackRating);
        const rand = Math.random();

        if (rand < prob.win) {
            this.setEncounter(whiteFideId, blackFideId, '1-0');
        } else if (rand < (prob.win + prob.draw)) {
            this.setEncounter(whiteFideId, blackFideId, '1/2-1/2');
        } else {
            this.setEncounter(whiteFideId, blackFideId, '0-1');
        }
    }

    private calculateWinProbability(whiteRating: number, blackRating: number) {
        const WHITE_ADVANTAGE_RATING = 35;
        const expectedWinWhite = 1 / (1 + Math.pow(10, (blackRating - whiteRating - WHITE_ADVANTAGE_RATING) / 400));

        const draw = drawProbability(whiteRating, blackRating);
        const win = expectedWinWhite * (1 - draw);
        const loss = (1 - expectedWinWhite) * (1 - draw);

        return { win, draw, loss };
    }

    public getSortedPlayers() {
        const players = [...this.playersByFideId.values()];
        return players.sort((a, b) => (b.points - a.points));
    }
}

async function runMonteCarlo(config: TournamentEncounterConfig, iterations: number) {
    const stats = new Map<number, {
        fideId: number;
        wins: number;
    }>();
    for (const player of config.players) {
        stats.set(player.fideId, { fideId: player.fideId, wins: 0 });
    }
    const table = new EncounterTable(config);

    for (let i = 0; i < iterations; i += 1) {
        if (i % 10_000 === 0) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        const simulation = new EncounterTable(config);
        const winnerId = simulation.simulateLeftRounds();
        stats.get(winnerId)!.wins += 1;
    }

    let result = '';
    result += `Results after ${iterations.toLocaleString('en')} iterations.\n`;
    const players = [...stats.values()].sort((a, b) => b.wins - a.wins);
    const results: Array<{ fideId: number; perc: number; wins: number; }> = []; // machine-readable
    for (const p of players) {
        const player = table.getPlayer(p.fideId);
        const perc = (100 * p.wins / iterations);
        results.push({ fideId: p.fideId, perc, wins: p.wins });
        result += `- ${perc.toFixed(2).padStart(6, ' ')}% wins - ${player.name} (${player.rating} rating, current points: ${player.points}, wins: ${p.wins})\n`;
    }
    console.log(result);
    // console.log('#BluebaumSweeps');
    // console.log([...bluebaumWinnerPoints.entries()].sort((a, b) => b[0] - a[0]).map(([points, count]) => `${points.toFixed(1)}: ${count}`).join('\n'));
}


const RUNS = 10_000;

runMonteCarlo({
    players: [
        { "name": "Caruana, Fabiano", "fideId": 2020009, "rating": 2795 },
        { "name": "Giri, Anish", "fideId": 24116068, "rating": 2753 },
        { "name": "Bluebaum, Matthias", "fideId": 24651516, "rating": 2698 },
        { "name": "Sindarov, Javokhir", "fideId": 14205483, "rating": 2745 },
        { "name": "Yi, Wei", "fideId": 8603405, "rating": 2754 },
        { "name": "Esipenko, Andrey", "fideId": 24175439, "rating": 2698 },
        { "name": "Praggnanandhaa R", "fideId": 25059530, "rating": 2741 },
        { "name": "Nakamura, Hikaru", "fideId": 2016192, "rating": 2810 }
    ],
    games: [
        { whiteFideId: 2020009, blackFideId: 2016192, result: "1-0" },
        { whiteFideId: 25059530, blackFideId: 24116068, result: "1-0" },
        { whiteFideId: 24651516, blackFideId: 8603405, result: "1/2-1/2" },
        { whiteFideId: 14205483, blackFideId: 24175439, result: "1-0" },
        { whiteFideId: 24175439, blackFideId: 2016192, result: "1/2-1/2" },
        { whiteFideId: 24116068, blackFideId: 2020009, result: "1/2-1/2" },
        { whiteFideId: 8603405, blackFideId: 25059530, result: "1/2-1/2" },
        { whiteFideId: 14205483, blackFideId: 24651516, result: "1/2-1/2" },
    ],
}, RUNS);
