
// based on https://web.archive.org/web/20160806071058/http://chess-db.com/public/research/draw_rate.html

const drawTable: { [key: number]: number[] } = {
    //      0, 20, 40, 60, 80,100,120,140,160,180,200,220,240,260,280,300
    1400: [21, 24, 25, 24, 24, 22, 23, 24, 22, 22, 20, 20, 21, 19, 18, 17],
    1600: [28, 29, 30, 29, 27, 27, 27, 26, 25, 25, 23, 22, 20, 20, 20, 19],
    1800: [31, 32, 32, 32, 30, 30, 28, 27, 26, 25, 23, 23, 22, 22, 20, 20],
    2000: [35, 35, 34, 33, 32, 31, 30, 29, 27, 25, 25, 24, 21, 21, 19, 19],
    2200: [42, 42, 40, 39, 37, 36, 34, 32, 30, 28, 25, 24, 22, 20, 19, 17],
    2400: [54, 53, 51, 50, 47, 45, 41, 38, 35, 33, 30, 26, 24, 22, 19, 18],
    2600: [57, 54, 54, 52, 51, 50, 45, 42, 40, 37, 34, 31, 30, 28, 29, 25],
};

export default function drawProbability(elo1: number, elo2: number) {
    const avg200 = Math.min(2600, Math.max(1400, Math.floor(((elo1 + elo2) / 2) / 200) * 200));
    const diff = Math.min(300, Math.max(0, Math.floor(Math.abs(elo1 - elo2) / 20) * 20));
    const diffIndex = Math.floor(diff / 20);
    return (drawTable[avg200][diffIndex] / 100);
}