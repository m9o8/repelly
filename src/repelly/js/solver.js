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
// least penetration, regularly swapping labels whose leader lines cross. The
// relaxation stops early once nothing moves. Labels that are still stuck then
// get a ring search around their anchor, and a final pass makes any remaining
// swaps that do not cause new overlaps.
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
  var STALL_SWEEPS = 20;

  function atLeastOne(v) {
    return v > 1 ? v : 1;
  }

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
  // Dense grid in compressed-row form: obstacles are counting-sorted by cell
  // into flat typed arrays, cells numbered row by row. The cells a query
  // touches in one grid row are then one contiguous slice, so a query is a few
  // plain array scans with no hashing and no callbacks.
  function ObstacleGrid(obstacles) {
    var n = obstacles && obstacles.x ? obstacles.x.length : 0;
    this.n = n;
    this.maxR = 0;
    this.ranges = new Int32Array(0);
    this.rangeCount = 0;
    if (!n) return;
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (var i = 0; i < n; i++) {
      var ox = obstacles.x[i], oy = obstacles.y[i];
      if (ox < minX) minX = ox;
      if (ox > maxX) maxX = ox;
      if (oy < minY) minY = oy;
      if (oy > maxY) maxY = oy;
      if (obstacles.r[i] > this.maxR) this.maxR = obstacles.r[i];
    }
    var cell = Math.max(24, (maxX - minX) / 512, (maxY - minY) / 512);
    var cols = Math.floor((maxX - minX) / cell) + 1;
    var rows = Math.floor((maxY - minY) / cell) + 1;
    var start = new Int32Array(cols * rows + 1);
    var cellOf = new Int32Array(n);
    for (var j = 0; j < n; j++) {
      var c = Math.floor((obstacles.y[j] - minY) / cell) * cols + Math.floor((obstacles.x[j] - minX) / cell);
      cellOf[j] = c;
      start[c + 1]++;
    }
    for (var s = 0; s < cols * rows; s++) start[s + 1] += start[s];
    var fill = start.slice(0, cols * rows);
    this.x = new Float64Array(n);
    this.y = new Float64Array(n);
    this.r = new Float64Array(n);
    for (var k = 0; k < n; k++) {
      var at = fill[cellOf[k]]++;
      this.x[at] = obstacles.x[k];
      this.y[at] = obstacles.y[k];
      this.r[at] = obstacles.r[k];
    }
    this.minX = minX;
    this.minY = minY;
    this.cell = cell;
    this.cols = cols;
    this.rows = rows;
    this.start = start;
    this.ranges = new Int32Array(2 * rows);
  }

  // Fills this.ranges with [from, to) index pairs covering every obstacle whose
  // centre may touch the rectangle once expanded by `reach`, and returns the
  // number of pairs.
  ObstacleGrid.prototype.slices = function (x0, y0, x1, y1, reach) {
    if (!this.n) return 0;
    var margin = reach + this.maxR;
    var cx0 = Math.max(0, Math.floor((x0 - margin - this.minX) / this.cell));
    var cx1 = Math.min(this.cols - 1, Math.floor((x1 + margin - this.minX) / this.cell));
    var cy0 = Math.max(0, Math.floor((y0 - margin - this.minY) / this.cell));
    var cy1 = Math.min(this.rows - 1, Math.floor((y1 + margin - this.minY) / this.cell));
    if (cx0 > cx1 || cy0 > cy1) return 0;
    var count = 0;
    for (var cy = cy0; cy <= cy1; cy++) {
      var row = cy * this.cols;
      var from = this.start[row + cx0];
      var to = this.start[row + cx1 + 1];
      if (from < to) {
        this.ranges[2 * count] = from;
        this.ranges[2 * count + 1] = to;
        count++;
      }
    }
    return count;
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
    var pointPad = new Float64Array(n);
    var sumX = 0;
    var sumY = 0;

    for (var s = 0; s < n; s++) {
      var spec = labels[s];
      hw[s] = spec.width / 2;
      hh[s] = spec.height / 2;
      pointPad[s] = spec.pointPadding || 0;
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
    // Sweep along the axis on which labels are most spread out relative to
    // their size. For text that is usually y: labels are several times wider
    // than tall, so a y window holds far fewer candidates than an x window.
    var spanX = 0, spanY = 0;
    for (var sa = 0; sa < m; sa++) {
      spanX += hw[active[sa]];
      spanY += hh[active[sa]];
    }
    var sweepY = spanY / atLeastOne(bounds.y1 - bounds.y0) < spanX / atLeastOne(bounds.x1 - bounds.x0);
    var sp = sweepY ? py : px, sh = sweepY ? hh : hw;
    var op = sweepY ? px : py, oh = sweepY ? hw : hh;

    function resolveLabels() {
      var hits = 0;
      for (var a1 = 1; a1 < m; a1++) {
        var moving = sorted[a1];
        var left = sp[moving] - sh[moving];
        var b1 = a1 - 1;
        while (b1 >= 0 && sp[sorted[b1]] - sh[sorted[b1]] > left) {
          sorted[b1 + 1] = sorted[b1];
          b1--;
        }
        sorted[b1 + 1] = moving;
      }
      for (var u = 0; u < m; u++) {
        var i = sorted[u];
        for (var v = u + 1; v < m; v++) {
          var j = sorted[v];
          if (sp[j] - sh[j] > sp[i] + sh[i]) break;
          if (Math.abs(op[i] - op[j]) >= oh[i] + oh[j]) continue;
          hits += pushApart(i, j);
        }
      }
      return hits;
    }

    function resolveObstacles(i) {
      var hits = 0;
      var pad = pointPad[i];
      var gx = grid.x, gy = grid.y, gr = grid.r, ranges = grid.ranges;
      var count = grid.slices(px[i] - hw[i], py[i] - hh[i], px[i] + hw[i], py[i] + hh[i], pad);
      for (var s = 0; s < count; s++) {
        for (var k = ranges[2 * s], end = ranges[2 * s + 1]; k < end; k++) {
          var r = gr[k] + pad;
          var overlapX = Math.min(px[i] + hw[i], gx[k] + r) - Math.max(px[i] - hw[i], gx[k] - r);
          if (overlapX <= 0) continue;
          var overlapY = Math.min(py[i] + hh[i], gy[k] + r) - Math.max(py[i] - hh[i], gy[k] - r);
          if (overlapY <= 0) continue;
          hits++;
          var useX = moveX[i] && (!moveY[i] || overlapX < overlapY);
          if (useX) {
            var sx = px[i] === gx[k] ? (random() < 0.5 ? -1 : 1) : (px[i] < gx[k] ? -1 : 1);
            px[i] += sx * (overlapX + EPSILON);
          } else if (moveY[i]) {
            var sy = py[i] === gy[k] ? (random() < 0.5 ? -1 : 1) : (py[i] < gy[k] ? -1 : 1);
            py[i] += sy * (overlapY + EPSILON);
          }
        }
      }
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
    var stalled = 0;

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
      if (largest < 0.1) {
        // Nothing moved: either solved, or stuck against a bound with contacts
        // that further sweeps cannot clear. Leave the rest to the rescue.
        // An early stop skips the periodic untangling, so untangle once more
        // and only stop when that finds nothing to swap.
        if (hits === 0 || ++stalled >= STALL_SWEEPS) {
          if (m > UNTANGLE_LIMIT || iter >= maxIter * UNTANGLE_UNTIL || swapCrossingLabels() === 0) break;
          stalled = 0;
        }
      } else {
        stalled = 0;
      }
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
      return !touchesLabel(i, x, y, ignore) && !touchesPoint(i, x, y);
    }

    function touchesLabel(i, x, y, ignore) {
      for (var c = 0; c < m; c++) {
        var j = active[c];
        if (j === i || j === ignore) continue;
        if (Math.abs(x - px[j]) < hw[i] + hw[j] && Math.abs(y - py[j]) < hh[i] + hh[j]) return true;
      }
      return false;
    }

    function touchesPoint(i, x, y) {
      var pad = pointPad[i];
      var gx = grid.x, gy = grid.y, gr = grid.r, ranges = grid.ranges;
      var count = grid.slices(x - hw[i], y - hh[i], x + hw[i], y + hh[i], pad);
      for (var s = 0; s < count; s++) {
        for (var k = ranges[2 * s], end = ranges[2 * s + 1]; k < end; k++) {
          var r = gr[k] + pad;
          if (Math.abs(x - gx[k]) < hw[i] + r && Math.abs(y - gy[k]) < hh[i] + r) return true;
        }
      }
      return false;
    }

    function isColliding(i) {
      return !fitsAt(i, px[i], py[i], -1);
    }

    // Ring search for labels the relaxation could not free, nearest ring first.
    // Counts leader lines that the line from label i's anchor to (x, y) crosses.
    function crossingsAt(i, x, y) {
      var ax = labels[i].x, ay = labels[i].y;
      var count = 0;
      for (var c = 0; c < m; c++) {
        var j = active[c];
        if (j === i) continue;
        var cx = labels[j].x, cy = labels[j].y, dx = px[j], dy = py[j];
        if (Math.max(ax, x) < Math.min(cx, dx) || Math.max(cx, dx) < Math.min(ax, x) ||
            Math.max(ay, y) < Math.min(cy, dy) || Math.max(cy, dy) < Math.min(ay, y)) continue;
        var d1 = (x - ax) * (cy - ay) - (y - ay) * (cx - ax);
        var d2 = (x - ax) * (dy - ay) - (y - ay) * (dx - ax);
        var d3 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx);
        var d4 = (dx - cx) * (y - cy) - (dy - cy) * (x - cx);
        if (d1 * d2 < 0 && d3 * d4 < 0) count++;
      }
      return count;
    }

    // Ring search for labels the relaxation could not free, nearest ring first.
    // Each ring starts from the side the label already sits on, and prefers a
    // free spot whose leader line crosses no other.
    function rescue(i) {
      var stepX = hw[i] * 0.75 + 4;
      var stepY = hh[i] * 1.25 + 4;
      var start = Math.atan2(py[i] - ty[i], px[i] - tx[i]);
      for (var ring = 1; ring <= RING_COUNT; ring++) {
        var bestX = 0, bestY = 0, bestCross = Infinity;
        for (var t = 0; t < RING_ANGLES; t++) {
          // 0, +1, -1, +2, -2, ... steps away from the starting angle.
          var step = (t + 1) >> 1;
          var theta = start + (t & 1 ? step : -step) * (2 * Math.PI / RING_ANGLES);
          var x = tx[i] + (moveX[i] ? Math.cos(theta) * (hw[i] + ring * stepX) : 0);
          var y = ty[i] + (moveY[i] ? Math.sin(theta) * (hh[i] + ring * stepY) : 0);
          if (!fitsAt(i, x, y, -1)) continue;
          var crossings = crossingsAt(i, x, y);
          if (crossings < bestCross) {
            bestCross = crossings;
            bestX = x;
            bestY = y;
            if (crossings === 0) break;
          }
        }
        if (bestCross < Infinity) {
          px[i] = bestX;
          py[i] = bestY;
          return true;
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
    // Broad phase for leader-line crossings: two segments can only cross when
    // their bounding boxes overlap, so sweep the boxes along x, taken at the
    // start of the pass, and hand only those pairs to `visit`. Only labels free
    // to move on both axes take part, because only they may be swapped.
    var segFree, segLoX, segHiX, segLoY, segHiY;

    function forEachBoxedPair(visit) {
      if (!segFree) {
        segFree = [];
        for (var sf = 0; sf < m; sf++) if (moveX[active[sf]] && moveY[active[sf]]) segFree.push(active[sf]);
        segLoX = new Float64Array(n);
        segHiX = new Float64Array(n);
        segLoY = new Float64Array(n);
        segHiY = new Float64Array(n);
      }
      var f = segFree.length;
      for (var a = 0; a < f; a++) {
        var k = segFree[a];
        segLoX[k] = Math.min(labels[k].x, px[k]);
        segHiX[k] = Math.max(labels[k].x, px[k]);
        segLoY[k] = Math.min(labels[k].y, py[k]);
        segHiY[k] = Math.max(labels[k].y, py[k]);
      }
      for (var b = 1; b < f; b++) {
        var moving = segFree[b];
        var c = b - 1;
        while (c >= 0 && segLoX[segFree[c]] > segLoX[moving]) {
          segFree[c + 1] = segFree[c];
          c--;
        }
        segFree[c + 1] = moving;
      }
      for (var u = 0; u < f; u++) {
        var i = segFree[u];
        for (var v = u + 1; v < f; v++) {
          var j = segFree[v];
          if (segLoX[j] > segHiX[i]) break;
          if (segLoY[j] > segHiY[i] || segLoY[i] > segHiY[j]) continue;
          visit(i, j);
        }
      }
    }

    function swapCrossingLabels() {
      var swaps = 0;
      forEachBoxedPair(function (i, j) {
        if (!segmentsCross(i, j)) return;
        var swapX = px[i];
        var swapY = py[i];
        px[i] = px[j];
        py[i] = py[j];
        px[j] = swapX;
        py[j] = swapY;
        clampToBounds(i);
        clampToBounds(j);
        swaps++;
      });
      return swaps;
    }

    if (m <= UNTANGLE_LIMIT) {
      for (var pass = 0; pass < 2; pass++) {
        var swapped = false;
        forEachBoxedPair(function (si, sj) {
          if (!segmentsCross(si, sj)) return;
          if (fitsAt(si, px[sj], py[sj], sj) && fitsAt(sj, px[si], py[si], si)) {
            var keepX = px[si], keepY = py[si];
            px[si] = px[sj];
            py[si] = py[sj];
            px[sj] = keepX;
            py[sj] = keepY;
            swapped = true;
          }
        });
        if (!swapped || outOfTime()) break;
      }
    }

    var colliding = new Uint8Array(n);
    var overlapsLabel = new Uint8Array(n);
    var overlapsPoint = new Uint8Array(n);
    for (var f = 0; f < m; f++) {
      var final = active[f];
      if (!isColliding(final)) continue;
      colliding[final] = 1;
      overlapsLabel[final] = touchesLabel(final, px[final], py[final], -1) ? 1 : 0;
      overlapsPoint[final] = touchesPoint(final, px[final], py[final]) ? 1 : 0;
    }

    return {
      x: px,
      y: py,
      kept: kept,
      colliding: colliding,
      overlapsLabel: overlapsLabel,
      overlapsPoint: overlapsPoint,
      sweeps: sweeps,
      elapsedMs: clock() - started
    };
  }

  var api = { solve: solve, createRandom: createRandom };
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.__repellySolver = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
