// repelly - https://github.com/m9o8/repelly
// Copyright (C) 2026 Moritz Peist
// SPDX-License-Identifier: GPL-3.0-or-later
// This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
// redistribute it and/or modify it under the terms of the GNU General Public
// License, version 3 or later. See <https://www.gnu.org/licenses/>.

// Times the solver on random layouts of growing size against its time budget.
//
//   node benchmarks/solver.js [solver.js ...]
//
// With several solver files, each is run on the same layouts, for example to
// compare a branch with main:
//
//   git show main:src/repelly/js/solver.js > /tmp/solver-main.js
//   node benchmarks/solver.js /tmp/solver-main.js src/repelly/js/solver.js

'use strict';

const path = require('node:path');

const DEFAULT = path.join(__dirname, '..', 'src', 'repelly', 'js', 'solver.js');
const SIZES = [100, 500, 2000, 8000, 20000];
const BUDGET_MS = 40;
const RUNS = 3;

function layout(createRandom, n, seed) {
  // About as dense as a crowded scatter plot: the labels cover the plot area
  // roughly once, so many start on top of each other.
  const random = createRandom(seed);
  const width = Math.sqrt(n) * 60;
  const height = width * 0.6;
  const labels = [];
  const obstacles = { x: [], y: [], r: [] };
  for (let i = 0; i < n; i++) {
    const x = random() * width;
    const y = random() * height;
    labels.push({ x, y, width: 30 + random() * 60, height: 14, radius: 3, pointPadding: 2, priority: random() });
    obstacles.x.push(x);
    obstacles.y.push(y);
    obstacles.r.push(3);
  }
  return { labels, obstacles, bounds: { x0: 0, y0: 0, x1: width, y1: height } };
}

function median(values) {
  const sorted = values.slice().sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function count(flags) {
  let total = 0;
  for (let i = 0; i < flags.length; i++) total += flags[i];
  return total;
}

const files = process.argv.slice(2);
for (const file of files.length ? files : [DEFAULT]) {
  const solver = require(path.resolve(file));
  // One unmeasured solve so that JIT compilation does not count.
  solver.solve(Object.assign(layout(solver.createRandom, 500, 0), { options: { maxTimeMs: BUDGET_MS } }));

  console.log(`\n${file}  (budget ${BUDGET_MS} ms, median of ${RUNS})`);
  console.log('  labels   wall ms   sweeps   kept   overlapping');
  for (const n of SIZES) {
    const times = [];
    let result;
    for (let run = 0; run < RUNS; run++) {
      const problem = layout(solver.createRandom, n, run + 1);
      const started = process.hrtime.bigint();
      result = solver.solve(Object.assign(problem, { options: { maxTimeMs: BUDGET_MS, maxOverlaps: 10, seed: 42 } }));
      times.push(Number(process.hrtime.bigint() - started) / 1e6);
    }
    console.log(
      `  ${String(n).padStart(6)}  ${median(times).toFixed(0).padStart(8)}  ${String(result.sweeps).padStart(7)}` +
      `  ${String(count(result.kept)).padStart(5)}  ${String(count(result.overlapsLabel)).padStart(12)}`
    );
  }
}
