// repelly - https://github.com/m9o8/repelly
// Copyright (C) 2026 Moritz Peist
// SPDX-License-Identifier: GPL-3.0-or-later
// This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
// redistribute it and/or modify it under the terms of the GNU General Public
// License, version 3 or later. See <https://www.gnu.org/licenses/>.

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const { solve } = require(path.join(__dirname, '..', '..', 'src', 'repelly', 'js', 'solver.js'));

const BOUNDS = { x0: 0, y0: 0, x1: 800, y1: 600 };
const NO_LIMITS = { maxTimeMs: Infinity, maxOverlaps: null, seed: 7 };

function label(x, y, extra) {
  return { x, y, width: 50, height: 16, radius: 3, pointPadding: 2, ...extra };
}

function overlappingPairs(labels, result) {
  let pairs = 0;
  for (let i = 0; i < labels.length; i++) {
    if (!result.kept[i]) continue;
    for (let j = i + 1; j < labels.length; j++) {
      if (!result.kept[j]) continue;
      if (Math.abs(result.x[i] - result.x[j]) * 2 < labels[i].width + labels[j].width &&
          Math.abs(result.y[i] - result.y[j]) * 2 < labels[i].height + labels[j].height) {
        pairs++;
      }
    }
  }
  return pairs;
}

function cluster(n, cx, cy, spread) {
  const labels = [];
  for (let i = 0; i < n; i++) {
    const angle = i * 2.4;
    const radius = spread * Math.sqrt(i / n);
    labels.push(label(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius));
  }
  return labels;
}

test('separates identical anchors', () => {
  const labels = Array.from({ length: 8 }, () => label(400, 300));
  const result = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  assert.strictEqual(overlappingPairs(labels, result), 0);
});

test('separates a dense cluster without leaving the plot', () => {
  const labels = cluster(60, 400, 300, 40);
  const result = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  assert.strictEqual(overlappingPairs(labels, result), 0);
  labels.forEach((l, i) => {
    assert.ok(result.x[i] - l.width / 2 >= BOUNDS.x0 - 1e-6);
    assert.ok(result.x[i] + l.width / 2 <= BOUNDS.x1 + 1e-6);
    assert.ok(result.y[i] - l.height / 2 >= BOUNDS.y0 - 1e-6);
    assert.ok(result.y[i] + l.height / 2 <= BOUNDS.y1 + 1e-6);
  });
});

test('handles labels in the plot corners', () => {
  const labels = [label(1, 1), label(799, 1), label(1, 599), label(799, 599), label(2, 2), label(798, 598)];
  const result = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  assert.strictEqual(overlappingPairs(labels, result), 0);
});

test('is deterministic for a given seed', () => {
  const labels = cluster(40, 300, 200, 30);
  const first = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  const second = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  assert.deepStrictEqual(Array.from(first.x), Array.from(second.x));
  assert.deepStrictEqual(Array.from(first.y), Array.from(second.y));
});

test('different seeds can give different layouts', () => {
  const labels = Array.from({ length: 12 }, () => label(400, 300));
  const a = solve({ labels, bounds: BOUNDS, options: { ...NO_LIMITS, seed: 1 } });
  const b = solve({ labels, bounds: BOUNDS, options: { ...NO_LIMITS, seed: 2 } });
  assert.notDeepStrictEqual(Array.from(a.x), Array.from(b.x));
});

for (const axis of ['x', 'y']) {
  test(`direction ${axis} keeps labels on the other axis`, () => {
    const labels = cluster(10, 400, 300, 10).map((l) => ({ ...l, direction: axis }));
    const result = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
    const fixed = axis === 'x' ? 'y' : 'x';
    labels.forEach((l, i) => assert.ok(Math.abs(result[fixed][i] - l[fixed]) < 1e-9));
    assert.strictEqual(overlappingPairs(labels, result), 0);
  });
}

test('labels do not cover point obstacles', () => {
  const obstacles = { x: [], y: [], r: [] };
  for (let x = 340; x <= 460; x += 20) {
    for (let y = 270; y <= 330; y += 20) {
      obstacles.x.push(x);
      obstacles.y.push(y);
      obstacles.r.push(3);
    }
  }
  const labels = [label(400, 290), label(420, 310)];
  const result = solve({ labels, obstacles, bounds: BOUNDS, options: NO_LIMITS });
  assert.deepStrictEqual(Array.from(result.colliding), [0, 0]);
});

test('labels stay close when there is nothing to avoid', () => {
  const labels = [label(200, 200), label(600, 400)];
  const result = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  labels.forEach((l, i) => assert.ok(Math.hypot(result.x[i] - l.x, result.y[i] - l.y) < 40));
});

test('maxOverlaps culls lower priority labels first', () => {
  const labels = Array.from({ length: 6 }, (_, i) => label(400, 300, { priority: i }));
  const result = solve({ labels, bounds: BOUNDS, options: { ...NO_LIMITS, maxOverlaps: 1 } });
  assert.deepStrictEqual(Array.from(result.kept), [0, 0, 0, 0, 1, 1]);
});

test('warm start stays put when already solved', () => {
  const labels = [label(200, 200)];
  const first = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  const warm = [{ ...labels[0], startDx: first.x[0] - 200, startDy: first.y[0] - 200 }];
  const second = solve({ labels: warm, bounds: BOUNDS, options: NO_LIMITS });
  assert.ok(Math.abs(second.x[0] - first.x[0]) < 3);
  assert.ok(Math.abs(second.y[0] - first.y[0]) < 3);
});

test('honours the time budget', () => {
  let now = 0;
  const clock = () => (now += 5);
  const labels = cluster(200, 400, 300, 20);
  const result = solve({ labels, bounds: BOUNDS, options: { ...NO_LIMITS, maxTimeMs: 20, clock } });
  assert.ok(result.sweeps < 60);
});

test('accepts an empty problem', () => {
  const result = solve({ labels: [], bounds: BOUNDS, options: NO_LIMITS });
  assert.strictEqual(result.x.length, 0);
});

test('solves 500 labels within a reasonable time', () => {
  const labels = cluster(500, 400, 300, 200);
  const result = solve({ labels, bounds: BOUNDS, options: { ...NO_LIMITS, maxTimeMs: 200 } });
  assert.ok(result.elapsedMs < 600, `took ${result.elapsedMs}ms`);
});

test('maxOverlaps can differ per label', () => {
  const labels = [
    label(400, 300, { priority: 3, maxOverlaps: Infinity }),
    label(400, 300, { priority: 2, maxOverlaps: 0 }),
    label(400, 300, { priority: 1, maxOverlaps: Infinity }),
  ];
  const result = solve({ labels, bounds: BOUNDS, options: { ...NO_LIMITS, maxOverlaps: 0 } });
  assert.deepStrictEqual(Array.from(result.kept), [1, 0, 1]);
});

function crossingPairs(labels, result) {
  const side = (ax, ay, bx, by, cx, cy) => (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
  let crossings = 0;
  for (let i = 0; i < labels.length; i++) {
    for (let j = i + 1; j < labels.length; j++) {
      const a = labels[i];
      const b = labels[j];
      if (side(a.x, a.y, result.x[i], result.y[i], b.x, b.y) *
          side(a.x, a.y, result.x[i], result.y[i], result.x[j], result.y[j]) < 0 &&
          side(b.x, b.y, result.x[j], result.y[j], a.x, a.y) *
          side(b.x, b.y, result.x[j], result.y[j], result.x[i], result.y[i]) < 0) {
        crossings++;
      }
    }
  }
  return crossings;
}

function scatteredClusters(n, seed) {
  let state = seed;
  const next = () => (state = (state * 1664525 + 1013904223) >>> 0) / 4294967296;
  const centres = [[250, 150], [520, 300], [620, 180]];
  return Array.from({ length: n }, (_, i) => {
    const [cx, cy] = centres[i % 3];
    return label(cx + (next() - 0.5) * 220, cy + (next() - 0.5) * 150, { width: 44 + next() * 40, height: 18 });
  });
}

test('leader lines rarely cross, without adding overlaps', () => {
  let crossings = 0;
  for (let seed = 1; seed <= 16; seed++) {
    const labels = scatteredClusters(60, seed * 101);
    const result = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
    crossings += crossingPairs(labels, result);
    assert.strictEqual(overlappingPairs(labels, result), 0);
  }
  assert.ok(crossings <= 20, `found ${crossings} crossings`);
});

test('labels constrained to one axis are never swapped', () => {
  const labels = [label(300, 300, { direction: 'x', startDx: 200, startDy: 0 }),
    label(500, 300, { direction: 'x', startDx: -200, startDy: 0 })];
  const result = solve({ labels, bounds: BOUNDS, options: NO_LIMITS });
  assert.ok(Math.abs(result.y[0] - 300) < 1e-9 && Math.abs(result.y[1] - 300) < 1e-9);
});
