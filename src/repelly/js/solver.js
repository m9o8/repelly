// repelly - https://github.com/m9o8/repelly
// Copyright (C) 2026 Moritz Peist
// SPDX-License-Identifier: GPL-3.0-or-later
// This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
// redistribute it and/or modify it under the terms of the GNU General Public
// License, version 3 or later. See <https://www.gnu.org/licenses/>.

// repelly label placement solver.
//
// Places label boxes near their anchor points so that they overlap neither one
// another nor the plotted points. Everything is in pixels. The solver has no
// DOM or Plotly dependency, so it can be unit tested under Node.
//
// Method: position-based relaxation. Each sweep applies a decaying pull towards
// the anchor and then projects overlapping boxes apart along their axis of
// least penetration, regularly swapping labels whose leader lines cross. Labels
// that are still stuck afterwards get a ring search around their anchor, and a
// final pass makes any remaining swaps that do not cause new overlaps.
(function (root) {
  'use strict';

  var GOLDEN_ANGLE = 2.399963229728653;
  var EPSILON = 0.01;
  var POLISH_SWEEPS = 60;
  var RING_COUNT = 10;
  var RING_ANGLES = 16;
  var UNTANGLE_LIMIT = 400;
  var UNTANGLE_EVERY = 5;
  var UNTANGLE_UNTIL = 0.7;
  var PULL_SLACK = 2;

  function createRandom(seed) {
    var state = (seed | 0) ^ 0x2545f491;
    if (state === 0) state = 0x6b43a9b5;
    return function () {
      state ^= state << 13;
      state ^= state >>> 17;
      state ^= state << 5;
      return (state >>> 0) / 4294967296;
    };
  }

  function defaultClock() {
    return typeof performance !== 'undefined' ? performance.now() : Date.now();
  }

  // Uniform hash grid over point obstacles. Each obstacle is stored only under
  // its centre, and queries are widened by the largest radius.
  function ObstacleGrid(obstacles) {
    var n = obstacles && obstacles.x ? obstacles.x.length : 0;
    this.x = n ? obstacles.x : [];
    this.y = n ? obstacles.y : [];
    this.r = n ? obstacles.r : [];
    this.n = n;
    this.maxR = 0;
    this.cell = 24;
    this.cells = new Map();
    for (var i = 0; i < n; i++) {
      if (this.r[i] > this.maxR) this.maxR = this.r[i];
      var key = this.key(Math.floor(this.x[i] / this.cell), Math.floor(this.y[i] / this.cell));
      var bucket = this.cells.get(key);
      if (bucket) bucket.push(i);
      else this.cells.set(key, [i]);
    }
  }

  ObstacleGrid.prototype.key = function (cx, cy) {
    return (cx + 32768) * 65536 + (cy + 32768);
  };

  // Calls visit(index) for obstacles whose centre may touch the given rectangle
  // once expanded by `reach`. Returns early when visit returns true.
  ObstacleGrid.prototype.query = function (x0, y0, x1, y1, reach, visit) {
    if (!this.n) return;
    var margin = reach + this.maxR;
    var cx0 = Math.floor((x0 - margin) / this.cell);
    var cx1 = Math.floor((x1 + margin) / this.cell);
    var cy0 = Math.floor((y0 - margin) / this.cell);
    var cy1 = Math.floor((y1 + margin) / this.cell);
    for (var cx = cx0; cx <= cx1; cx++) {
      for (var cy = cy0; cy <= cy1; cy++) {
        var bucket = this.cells.get(this.key(cx, cy));
        if (!bucket) continue;
        for (var k = 0; k < bucket.length; k++) {
          if (visit(bucket[k]) === true) return;
        }
      }
    }
  };

  function orderByPriority(labels) {
    var order = [];
    for (var i = 0; i < labels.length; i++) order.push(i);
    order.sort(function (a, b) {
      var pa = Number.isFinite(labels[a].priority) ? labels[a].priority : 0;
      var pb = Number.isFinite(labels[b].priority) ? labels[b].priority : 0;
      return pb - pa || a - b;
    });
    return order;
  }

  function isNudged(label) {
    return !!(label.nudgeX || label.nudgeY);
  }

  function targetX(label) {
    return label.x + (label.nudgeX || 0);
  }

  function targetY(label) {
    return label.y + (label.nudgeY || 0);
  }

  // Drops labels that would start on top of more than their allowed number of
  // higher priority labels, mirroring the crowding limit in ggrepel. A label's
  // own `maxOverlaps` takes precedence over the solver-wide default.
  function cullCrowded(labels, order, defaultLimit) {
    var kept = new Uint8Array(labels.length);
    var placed = [];
    for (var o = 0; o < order.length; o++) {
      var i = order[o];
      var a = labels[i];
      var limit = a.maxOverlaps == null ? defaultLimit : a.maxOverlaps;
      var count = 0;
      if (Number.isFinite(limit)) {
        for (var p = 0; p < placed.length && count <= limit; p++) {
          var b = labels[placed[p]];
          if (Math.abs(targetX(a) - targetX(b)) * 2 < a.width + b.width &&
              Math.abs(targetY(a) - targetY(b)) * 2 < a.height + b.height) {
            count++;
          }
        }
      }
      if (count <= limit) {
        kept[i] = 1;
        placed.push(i);
      }
    }
    return kept;
  }

  function solve(input) {
    var labels = input.labels || [];
    var n = labels.length;
    var bounds = input.bounds;
    var opts = input.options || {};
    var clock = opts.clock || defaultClock;
    var maxIter = opts.maxIter > 0 ? opts.maxIter : 400;
    var budget = opts.maxTimeMs == null ? Infinity : opts.maxTimeMs;
    var maxOverlaps = opts.maxOverlaps == null ? Infinity : opts.maxOverlaps;
    var random = createRandom(opts.seed == null ? 42 : opts.seed);
    var started = clock();
    var grid = new ObstacleGrid(input.obstacles);

    var order = orderByPriority(labels);
    var kept = cullCrowded(labels, order, maxOverlaps);

    var active = [];
    for (var a = 0; a < n; a++) if (kept[a]) active.push(a);
    var m = active.length;

    var px = new Float64Array(n);
    var py = new Float64Array(n);
    var hw = new Float64Array(n);
    var hh = new Float64Array(n);
    var moveX = new Uint8Array(n);
    var moveY = new Uint8Array(n);
    var tx = new Float64Array(n);
    var ty = new Float64Array(n);
    var sumX = 0;
    var sumY = 0;

    for (var s = 0; s < n; s++) {
      var spec = labels[s];
      hw[s] = spec.width / 2;
      hh[s] = spec.height / 2;
      moveX[s] = spec.direction === 'y' ? 0 : 1;
      moveY[s] = spec.direction === 'x' ? 0 : 1;
      tx[s] = targetX(spec);
      ty[s] = targetY(spec);
      px[s] = tx[s];
      py[s] = ty[s];
      if (kept[s]) {
        sumX += tx[s];
        sumY += ty[s];
      }
    }

    function clampInto(i, area) {
      var loX = area.x0 + hw[i];
      var hiX = area.x1 - hw[i];
      var loY = area.y0 + hh[i];
      var hiY = area.y1 - hh[i];
      px[i] = loX > hiX ? (area.x0 + area.x1) / 2 : Math.min(hiX, Math.max(loX, px[i]));
      py[i] = loY > hiY ? (area.y0 + area.y1) / 2 : Math.min(hiY, Math.max(loY, py[i]));
    }

    // A label's own area can be too small to hold it, so the plot area is applied
    // last and always wins.
    function clampToBounds(i) {
      if (labels[i].bounds) clampInto(i, labels[i].bounds);
      clampInto(i, bounds);
    }

    // Seed positions: reuse the previous solution when given, otherwise fan out
    // from the centre of the labelled points so clusters unfold outwards.
    var centreX = m ? sumX / m : 0;
    var centreY = m ? sumY / m : 0;
    for (var q = 0; q < m; q++) {
      var i0 = active[q];
      var l0 = labels[i0];
      if (Number.isFinite(l0.startDx) && Number.isFinite(l0.startDy)) {
        px[i0] = moveX[i0] ? l0.x + l0.startDx : tx[i0];
        py[i0] = moveY[i0] ? l0.y + l0.startDy : ty[i0];
      } else if (isNudged(l0)) {
        px[i0] = tx[i0] + (moveX[i0] ? random() - 0.5 : 0);
        py[i0] = ty[i0] + (moveY[i0] ? random() - 0.5 : 0);
      } else {
        var offX = tx[i0] - centreX;
        var offY = ty[i0] - centreY;
        var base = offX * offX + offY * offY > 1 ? Math.atan2(offY, offX) : q * GOLDEN_ANGLE;
        var angle = base + (random() - 0.5) * 1.2;
        var reach = (l0.radius || 0) + (l0.pointPadding || 0) + 2;
        px[i0] = tx[i0] + (moveX[i0] ? Math.cos(angle) * (hw[i0] + reach) : 0);
        py[i0] = ty[i0] + (moveY[i0] ? Math.sin(angle) * (hh[i0] + reach) : 0);
      }
      clampToBounds(i0);
    }

    function pushApart(i, j) {
      var overlapX = Math.min(px[i] + hw[i], px[j] + hw[j]) - Math.max(px[i] - hw[i], px[j] - hw[j]);
      var overlapY = Math.min(py[i] + hh[i], py[j] + hh[j]) - Math.max(py[i] - hh[i], py[j] - hh[j]);
      if (overlapX <= 0 || overlapY <= 0) return 0;

      var canX = moveX[i] || moveX[j];
      var canY = moveY[i] || moveY[j];
      var useX = canX && (!canY || overlapX < overlapY);
      var strength = Math.min(1, Math.max(0.05, ((labels[i].push || 1) + (labels[j].push || 1)) / 2));

      if (useX) {
        var dirX = px[i] === px[j] ? (random() < 0.5 ? -1 : 1) : (px[i] < px[j] ? -1 : 1);
        var shareX = moveX[i] && moveX[j] ? 0.5 : 1;
        var stepX = (overlapX + EPSILON) * shareX * strength;
        if (moveX[i]) px[i] += dirX * stepX;
        if (moveX[j]) px[j] -= dirX * stepX;
      } else {
        var dirY = py[i] === py[j] ? (random() < 0.5 ? -1 : 1) : (py[i] < py[j] ? -1 : 1);
        var shareY = moveY[i] && moveY[j] ? 0.5 : 1;
        var stepY = (overlapY + EPSILON) * shareY * strength;
        if (moveY[i]) py[i] += dirY * stepY;
        if (moveY[j]) py[j] -= dirY * stepY;
      }
      return 1;
    }

    // Sweep and prune along x. `sorted` is reused between sweeps, so it is
    // nearly in order each time and insertion sort stays close to linear.
    var sorted = active.slice();

    function resolveLabels() {
      var hits = 0;
      for (var a1 = 1; a1 < m; a1++) {
        var moving = sorted[a1];
        var left = px[moving] - hw[moving];
        var b1 = a1 - 1;
        while (b1 >= 0 && px[sorted[b1]] - hw[sorted[b1]] > left) {
          sorted[b1 + 1] = sorted[b1];
          b1--;
        }
        sorted[b1 + 1] = moving;
      }
      for (var u = 0; u < m; u++) {
        var i = sorted[u];
        for (var v = u + 1; v < m; v++) {
          var j = sorted[v];
          if (px[j] - hw[j] > px[i] + hw[i]) break;
          hits += pushApart(i, j);
        }
      }
      return hits;
    }

    function resolveObstacles(i) {
      var hits = 0;
      var pad = labels[i].pointPadding || 0;
      grid.query(px[i] - hw[i], py[i] - hh[i], px[i] + hw[i], py[i] + hh[i], pad, function (k) {
        var r = grid.r[k] + pad;
        var overlapX = Math.min(px[i] + hw[i], grid.x[k] + r) - Math.max(px[i] - hw[i], grid.x[k] - r);
        var overlapY = Math.min(py[i] + hh[i], grid.y[k] + r) - Math.max(py[i] - hh[i], grid.y[k] - r);
        if (overlapX <= 0 || overlapY <= 0) return false;
        hits++;
        var useX = moveX[i] && (!moveY[i] || overlapX < overlapY);
        if (useX) {
          var sx = px[i] === grid.x[k] ? (random() < 0.5 ? -1 : 1) : (px[i] < grid.x[k] ? -1 : 1);
          px[i] += sx * (overlapX + EPSILON);
        } else if (moveY[i]) {
          var sy = py[i] === grid.y[k] ? (random() < 0.5 ? -1 : 1) : (py[i] < grid.y[k] ? -1 : 1);
          py[i] += sy * (overlapY + EPSILON);
        }
        return false;
      });
      return hits;
    }

    // Moves a label towards its target. Unless nudged, the target is the label's
    // own point, so the last few pixels stay open and the pull does not fight the
    // push from that point.
    function pull(i, rate) {
      var dx = tx[i] - px[i];
      var dy = ty[i] - py[i];
      var limit = 1;
      if (!isNudged(labels[i])) {
        var pad = (labels[i].radius || 0) + (labels[i].pointPadding || 0) + PULL_SLACK;
        var gap = Math.max(Math.abs(dx) - hw[i], Math.abs(dy) - hh[i]) - pad;
        if (gap <= 0) return;
        limit = Math.min(1, gap / Math.max(1e-6, Math.sqrt(dx * dx + dy * dy)));
      }
      var amount = Math.min(rate * (labels[i].pull == null ? 1 : labels[i].pull), limit);
      if (moveX[i]) px[i] += dx * amount;
      if (moveY[i]) py[i] += dy * amount;
    }

    function outOfTime() {
      return clock() - started > budget;
    }

    var prevX = new Float64Array(n);
    var prevY = new Float64Array(n);
    var sweeps = 0;

    for (var iter = 0; iter < maxIter && m > 0; iter++) {
      if ((iter & 7) === 7 && outOfTime()) break;
      sweeps++;
      prevX.set(px);
      prevY.set(py);
      var decay = 1 - iter / maxIter;
      var rate = 0.1 * decay * decay;
      for (var w = 0; w < m; w++) pull(active[w], rate);

      var hits = resolveLabels();
      for (var w2 = 0; w2 < m; w2++) {
        hits += resolveObstacles(active[w2]);
        clampToBounds(active[w2]);
      }

      if (iter % UNTANGLE_EVERY === UNTANGLE_EVERY - 1 && iter < maxIter * UNTANGLE_UNTIL &&
          m <= UNTANGLE_LIMIT) {
        hits += swapCrossingLabels();
      }

      var largest = 0;
      for (var w3 = 0; w3 < m; w3++) {
        var idx = active[w3];
        var move = Math.abs(px[idx] - prevX[idx]) + Math.abs(py[idx] - prevY[idx]);
        if (move > largest) largest = move;
      }
      if (hits === 0 && largest < 0.1) break;
    }

    // Pull-free sweeps to clear contacts the pull may have left behind.
    for (var p1 = 0; p1 < POLISH_SWEEPS && m > 0; p1++) {
      if (outOfTime()) break;
      sweeps++;
      var remaining = resolveLabels();
      for (var p2 = 0; p2 < m; p2++) {
        remaining += resolveObstacles(active[p2]);
        clampToBounds(active[p2]);
      }
      if (remaining === 0) break;
    }

    function fitsAt(i, x, y, ignore) {
      var area = labels[i].bounds || bounds;
      if (x - hw[i] < area.x0 || x + hw[i] > area.x1 ||
          y - hh[i] < area.y0 || y + hh[i] > area.y1) {
        return false;
      }
      for (var c = 0; c < m; c++) {
        var j = active[c];
        if (j === i || j === ignore) continue;
        if (Math.abs(x - px[j]) < hw[i] + hw[j] && Math.abs(y - py[j]) < hh[i] + hh[j]) return false;
      }
      var clear = true;
      var pad = labels[i].pointPadding || 0;
      grid.query(x - hw[i], y - hh[i], x + hw[i], y + hh[i], pad, function (k) {
        var r = grid.r[k] + pad;
        if (Math.abs(x - grid.x[k]) < hw[i] + r && Math.abs(y - grid.y[k]) < hh[i] + r) {
          clear = false;
          return true;
        }
        return false;
      });
      return clear;
    }

    function isColliding(i) {
      return !fitsAt(i, px[i], py[i], -1);
    }

    // Ring search for labels the relaxation could not free, nearest ring first.
    function rescue(i) {
      var stepX = hw[i] * 0.75 + 4;
      var stepY = hh[i] * 1.25 + 4;
      for (var ring = 1; ring <= RING_COUNT; ring++) {
        for (var t = 0; t < RING_ANGLES; t++) {
          var theta = (t / RING_ANGLES) * 2 * Math.PI;
          var x = tx[i] + (moveX[i] ? Math.cos(theta) * (hw[i] + ring * stepX) : 0);
          var y = ty[i] + (moveY[i] ? Math.sin(theta) * (hh[i] + ring * stepY) : 0);
          if (fitsAt(i, x, y, -1)) {
            px[i] = x;
            py[i] = y;
            return true;
          }
        }
      }
      return false;
    }

    for (var o = 0; o < order.length; o++) {
      var r0 = order[o];
      if (kept[r0] && isColliding(r0)) {
        if (outOfTime()) break;
        rescue(r0);
      }
    }

    function segmentsCross(i, j) {
      var ax = labels[i].x, ay = labels[i].y;
      var bx = px[i], by = py[i];
      var cx = labels[j].x, cy = labels[j].y;
      var dx = px[j], dy = py[j];
      var d1 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
      var d2 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax);
      var d3 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx);
      var d4 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx);
      return d1 * d2 < 0 && d3 * d4 < 0;
    }

    // During relaxation a swap may overlap neighbours, because later sweeps
    // separate them again. The ggrepel solver resolves crossings the same way.
    function swapCrossingLabels() {
      var swaps = 0;
      for (var c1 = 0; c1 < m; c1++) {
        for (var c2 = c1 + 1; c2 < m; c2++) {
          var i = active[c1];
          var j = active[c2];
          if (!moveX[i] || !moveY[i] || !moveX[j] || !moveY[j] || !segmentsCross(i, j)) continue;
          var swapX = px[i];
          var swapY = py[i];
          px[i] = px[j];
          py[i] = py[j];
          px[j] = swapX;
          py[j] = swapY;
          clampToBounds(i);
          clampToBounds(j);
          swaps++;
        }
      }
      return swaps;
    }

    if (m <= UNTANGLE_LIMIT) {
      for (var pass = 0; pass < 2; pass++) {
        var swapped = false;
        for (var e1 = 0; e1 < m; e1++) {
          for (var e2 = e1 + 1; e2 < m; e2++) {
            var si = active[e1];
            var sj = active[e2];
            if (!moveX[si] || !moveY[si] || !moveX[sj] || !moveY[sj]) continue;
            if (!segmentsCross(si, sj)) continue;
            if (fitsAt(si, px[sj], py[sj], sj) && fitsAt(sj, px[si], py[si], si)) {
              var tx = px[si], ty = py[si];
              px[si] = px[sj];
              py[si] = py[sj];
              px[sj] = tx;
              py[sj] = ty;
              swapped = true;
            }
          }
        }
        if (!swapped || outOfTime()) break;
      }
    }

    var colliding = new Uint8Array(n);
    for (var f = 0; f < m; f++) {
      if (isColliding(active[f])) colliding[active[f]] = 1;
    }

    return {
      x: px,
      y: py,
      kept: kept,
      colliding: colliding,
      sweeps: sweeps,
      elapsedMs: clock() - started
    };
  }

  var api = { solve: solve, createRandom: createRandom };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.__repellySolver = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
