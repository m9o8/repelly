// repelly - https://github.com/m9o8/repelly
// Copyright (C) 2026 Moritz Peist
// SPDX-License-Identifier: GPL-3.0-or-later
// This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
// redistribute it and/or modify it under the terms of the GNU General Public
// License, version 3 or later. See <https://www.gnu.org/licenses/>.

// repelly browser runtime.
//
// Reads the label configuration stored in layout.meta.repelly, measures labels,
// runs the solver for each subplot panel, and writes the result back as native
// Plotly annotations. Labels therefore appear in the modebar's PNG download and
// keep following their points during a drag, before the next solve.
(function (root) {
  'use strict';

  var VERSION = '0.1.0';
  if (root.repelly && root.repelly.version === VERSION) return;

  var Solver = root.__repellySolver;
  var NAME_PREFIX = 'repelly-';
  var DEBOUNCE = { render: 0, frame: 0, zoom: 60, resize: 120 };
  var MAX_CHAINED_RUNS = 3;
  var LINE_HEIGHT = 1.3;
  var SCRIPT_SCALE = 0.7;
  var DEFAULT_RADIUS = 3;
  var DEDUPE_CELL = 3;
  var ENTITIES = { '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"', '&#39;': "'" };

  function at(column, i) {
    return Array.isArray(column) ? column[i] : column;
  }

  function getConfig(gd) {
    var meta = gd.layout && gd.layout.meta;
    return meta && typeof meta === 'object' && meta.repelly ? meta.repelly : null;
  }

  function axisName(ref) {
    return ref.charAt(0) + 'axis' + ref.slice(1);
  }

  function isOurs(annotation) {
    return !!annotation && typeof annotation.name === 'string' &&
      annotation.name.indexOf(NAME_PREFIX) === 0;
  }

  function countOurs(gd) {
    return ((gd.layout && gd.layout.annotations) || []).filter(isOurs).length;
  }

  function traceHidden(gd, index) {
    var trace = gd.data && gd.data[index];
    return !!trace && trace.visible !== undefined && trace.visible !== true;
  }

  function activeFrame(gd, state, cfg) {
    if (state.frame != null) return state.frame;
    var current = gd._fullLayout && gd._fullLayout._currentFrame;
    if (current != null) return String(current);
    return cfg.first_frame != null ? String(cfg.first_frame) : null;
  }

  function touchedAxes(cfg) {
    var seen = {};
    cfg.layers.forEach(function (layer) {
      [layer.xref, layer.yref].forEach(function (column) {
        (Array.isArray(column) ? column : [column]).forEach(function (ref) {
          seen[ref] = true;
        });
      });
    });
    return Object.keys(seen).sort();
  }

  function captureParts(gd, state, cfg) {
    var full = gd._fullLayout;
    var ranges = [];
    var size = [];
    touchedAxes(cfg).forEach(function (ref) {
      var axis = full[axisName(ref)];
      if (!axis) return;
      ranges.push(ref + ':' + axis.range.map(function (v) {
        return typeof v === 'number' ? v.toPrecision(10) : String(v);
      }).join(','));
      size.push(Math.round(axis._length) + '@' + Math.round(axis._offset));
    });
    return {
      config: cfg.hash,
      count: countOurs(gd),
      traces: (gd.data || []).map(function (t) { return t.visible === undefined ? true : t.visible; }).join(),
      frame: String(activeFrame(gd, state, cfg)),
      size: size.join('|'),
      ranges: ranges.join('|')
    };
  }

  function measureContext() {
    if (!root.__repellyCanvas) root.__repellyCanvas = document.createElement('canvas');
    return root.__repellyCanvas.getContext('2d');
  }

  function decodeEntities(text) {
    return text.replace(/&(amp|lt|gt|quot|#39);/g, function (m) { return ENTITIES[m]; });
  }

  // Measures a line piece by piece, following Plotly's pseudo-HTML tags, because
  // bold and superscript runs have different widths from the surrounding text.
  function measureLine(ctx, line, font) {
    var depth = { b: 0, i: 0, em: 0, sub: 0, sup: 0 };
    var width = 0;
    var last = 0;
    var tag = /<(\/?)([a-z]+)\b[^>]*>/gi;

    function addText(text) {
      if (!text) return;
      var size = depth.sub || depth.sup ? font.size * SCRIPT_SCALE : font.size;
      ctx.font = [
        depth.i || depth.em ? 'italic' : font.style,
        depth.b ? 'bold' : font.weight,
        size + 'px',
        font.family
      ].join(' ');
      width += ctx.measureText(decodeEntities(text)).width;
    }

    for (var match = tag.exec(line); match; match = tag.exec(line)) {
      addText(line.slice(last, match.index));
      last = tag.lastIndex;
      var name = match[2].toLowerCase();
      if (name in depth) depth[name] = Math.max(0, depth[name] + (match[1] ? -1 : 1));
    }
    addText(line.slice(last));
    return width;
  }

  function measure(ctx, text, font) {
    var lines = String(text).split(/<br\s*\/?>/i);
    var width = 0;
    lines.forEach(function (line) {
      width = Math.max(width, measureLine(ctx, line, font));
    });
    return { width: width, height: lines.length * font.size * LINE_HEIGHT };
  }

  function markerRadius(marker, i) {
    var size = at(marker.size, i);
    if (!(size > 0)) return DEFAULT_RADIUS;
    var ref = marker.sizeref || 1;
    return marker.sizemode === 'area' ? Math.sqrt(size / 2 / ref) : size / 2 / ref;
  }

  function panelKey(xa, ya) {
    return [xa._offset, xa._length, ya._offset, ya._length].map(Math.round).join('/');
  }

  // Marker positions per panel, thinned to one entry per small pixel cell so
  // the obstacle count is bounded by the panel area rather than the data size.
  function collectObstacles(gd) {
    var full = gd._fullLayout;
    var panels = {};
    (gd._fullData || []).forEach(function (trace) {
      if (trace.visible !== true) return;
      if (trace.type !== 'scatter' && trace.type !== 'scattergl') return;
      if (String(trace.mode).indexOf('markers') === -1) return;
      var xa = full[axisName(trace.xaxis || 'x')];
      var ya = full[axisName(trace.yaxis || 'y')];
      if (!xa || !ya) return;
      var key = panelKey(xa, ya);
      var cells = panels[key] || (panels[key] = new Map());
      var n = trace._length || (trace.y ? trace.y.length : 0);
      for (var i = 0; i < n; i++) {
        var xv = trace.x ? trace.x[i] : (trace.x0 || 0) + i * (trace.dx || 1);
        var yv = trace.y ? trace.y[i] : (trace.y0 || 0) + i * (trace.dy || 1);
        var relX = xa.d2p(xv);
        var relY = ya.d2p(yv);
        if (!(relX >= 0 && relX <= xa._length && relY >= 0 && relY <= ya._length)) continue;
        var px = xa._offset + relX;
        var py = ya._offset + relY;
        var radius = markerRadius(trace.marker || {}, i);
        var cell = Math.floor(px / DEDUPE_CELL) * 100000 + Math.floor(py / DEDUPE_CELL);
        var existing = cells.get(cell);
        if (!existing || existing[2] < radius) cells.set(cell, [px, py, radius]);
      }
    });
    return panels;
  }

  function matchRadius(cells, x, y) {
    if (!cells) return DEFAULT_RADIUS;
    var cx = Math.floor(x / DEDUPE_CELL);
    var cy = Math.floor(y / DEDUPE_CELL);
    var best = 0;
    for (var ox = -1; ox <= 1; ox++) {
      for (var oy = -1; oy <= 1; oy++) {
        var hit = cells.get((cx + ox) * 100000 + (cy + oy));
        if (hit && Math.abs(hit[0] - x) < 2 && Math.abs(hit[1] - y) < 2 && hit[2] > best) best = hit[2];
      }
    }
    return best || DEFAULT_RADIUS;
  }

  function annotationCoord(axis, value) {
    return axis.type === 'log' ? Math.log10(value) : value;
  }

  function fontFor(layer, full) {
    var font = layer.font || {};
    var base = full.font || {};
    return {
      size: font.size || base.size || 12,
      family: font.family || base.family || 'sans-serif',
      weight: font.weight || base.weight || 'normal',
      style: font.style || base.style || 'normal'
    };
  }

  function collectLabels(gd, state, cfg) {
    var full = gd._fullLayout;
    var frame = activeFrame(gd, state, cfg);
    var ctx = measureContext();
    var obstacles = {};
    var useObstacles = cfg.layers.some(function (l) { return l.solver.avoid_points; });
    var cells = useObstacles ? collectObstacles(gd) : {};
    var panels = {};

    cfg.layers.forEach(function (layer, layerIndex) {
      var font = fontFor(layer, full);
      var box = layer.label || {};
      var chrome = 2 * ((box.borderpad == null ? 1 : box.borderpad) +
                        (box.borderwidth == null ? 1 : box.borderwidth));
      var solver = layer.solver;

      for (var i = 0; i < layer.text.length; i++) {
        if (at(layer.visible, i) === false) continue;
        var labelFrame = at(layer.frame, i);
        if (labelFrame != null && frame != null && String(labelFrame) !== frame) continue;
        var trace = at(layer.trace, i);
        if (trace != null && traceHidden(gd, trace)) continue;

        var xref = at(layer.xref, i);
        var yref = at(layer.yref, i);
        var xa = full[axisName(xref)];
        var ya = full[axisName(yref)];
        if (!xa || !ya || !xa.d2p || !ya.d2p) continue;

        var xValue = at(layer.x, i);
        var yValue = at(layer.y, i);
        var relX = xa.d2p(xValue);
        var relY = ya.d2p(yValue);
        if (!(relX >= 0 && relX <= xa._length && relY >= 0 && relY <= ya._length)) continue;

        var key = panelKey(xa, ya);
        var panel = panels[key];
        if (!panel) {
          panel = panels[key] = {
            key: key,
            bounds: {
              x0: xa._offset,
              x1: xa._offset + xa._length,
              y0: ya._offset,
              y1: ya._offset + ya._length
            },
            entries: []
          };
        }

        var text = at(layer.text, i);
        var size = measure(ctx, text, font);
        var px = xa._offset + relX;
        var py = ya._offset + relY;
        var id = layerIndex + '-' + i;
        var warm = state.previous[id];
        var radius = matchRadius(cells[key], px, py);

        panel.entries.push({
          id: id,
          layer: layer,
          text: text,
          xa: xa,
          ya: ya,
          xref: xref,
          yref: yref,
          xValue: xValue,
          yValue: yValue,
          halfBoxX: (size.width + chrome) / 2,
          halfBoxY: (size.height + chrome) / 2,
          spec: {
            x: px,
            y: py,
            width: size.width + chrome + 2 * solver.box_padding,
            height: size.height + chrome + 2 * solver.box_padding,
            priority: at(layer.priority, i),
            maxOverlaps: solver.max_overlaps == null ? Infinity : solver.max_overlaps,
            direction: solver.direction,
            pull: solver.force_pull,
            push: solver.force,
            pointPadding: solver.point_padding,
            radius: radius,
            startDx: warm ? warm[0] : undefined,
            startDy: warm ? warm[1] : undefined
          }
        });
      }
    });

    Object.keys(panels).forEach(function (key) {
      var list = cells[key] ? Array.from(cells[key].values()) : [];
      obstacles[key] = {
        x: list.map(function (o) { return o[0]; }),
        y: list.map(function (o) { return o[1]; }),
        r: list.map(function (o) { return o[2]; })
      };
    });
    return { panels: panels, obstacles: obstacles };
  }

  // Applies each call's max_labels to that call's labels in this panel.
  function limitPerLayer(entries) {
    var byLayer = new Map();
    entries.forEach(function (entry, index) {
      if (!byLayer.has(entry.layer)) byLayer.set(entry.layer, []);
      byLayer.get(entry.layer).push({ entry: entry, index: index });
    });

    var kept = [];
    byLayer.forEach(function (items, layer) {
      var limit = layer.solver.max_labels;
      if (limit == null || items.length <= limit) {
        kept = kept.concat(items);
        return;
      }
      kept = kept.concat(items.slice().sort(function (a, b) {
        var pa = Number.isFinite(a.entry.spec.priority) ? a.entry.spec.priority : 0;
        var pb = Number.isFinite(b.entry.spec.priority) ? b.entry.spec.priority : 0;
        return pb - pa || a.index - b.index;
      }).slice(0, limit));
    });
    return kept
      .sort(function (a, b) { return a.index - b.index; })
      .map(function (item) { return item.entry; });
  }

  // Calls sharing a panel are solved together, so these limits apply to the
  // whole solve: the most generous iteration and time limits win.
  function solveOptions(entries, exact) {
    var iter = 0;
    var time = 0;
    var seed = null;
    entries.forEach(function (entry) {
      var solver = entry.layer.solver;
      iter = Math.max(iter, solver.max_iter);
      time = Math.max(time, solver.max_time_ms);
      if (seed == null) seed = solver.seed;
    });
    return { maxIter: iter, maxTimeMs: exact ? Infinity : time, seed: seed };
  }

  function buildAnnotation(entry, x, y, radius) {
    var layer = entry.layer;
    var segment = layer.segment || {};
    var dx = x - entry.spec.x;
    var dy = y - entry.spec.y;
    var gapX = Math.abs(dx) - entry.halfBoxX;
    var gapY = Math.abs(dy) - entry.halfBoxY;
    var gap = Math.hypot(Math.max(gapX, 0), Math.max(gapY, 0));
    var showSegment = gap >= layer.solver.min_segment_length;

    var annotation = {
      name: NAME_PREFIX + entry.id,
      x: annotationCoord(entry.xa, entry.xValue),
      y: annotationCoord(entry.ya, entry.yValue),
      xref: entry.xref,
      yref: entry.yref,
      axref: 'pixel',
      ayref: 'pixel',
      ax: Math.round(dx * 10) / 10,
      ay: Math.round(dy * 10) / 10,
      text: entry.text,
      xanchor: 'center',
      yanchor: 'middle',
      showarrow: true,
      arrowhead: segment.arrowhead || 0,
      arrowsize: segment.arrowsize || 1,
      arrowwidth: segment.width == null ? 1 : segment.width,
      arrowcolor: showSegment ? (segment.color || 'rgba(90,90,90,0.7)') : 'rgba(0,0,0,0)',
      standoff: radius
    };
    if (layer.font) annotation.font = layer.font;
    if (layer.label) {
      ['bgcolor', 'bordercolor', 'borderwidth', 'borderpad'].forEach(function (key) {
        if (layer.label[key] != null) annotation[key] = layer.label[key];
      });
    }
    return annotation;
  }

  function computeAnnotations(gd, state, cfg, exact) {
    var collected = collectLabels(gd, state, cfg);
    var annotations = [];
    var previous = {};

    Object.keys(collected.panels).sort().forEach(function (key) {
      var panel = collected.panels[key];
      var entries = limitPerLayer(panel.entries);
      if (!entries.length) return;

      var result = Solver.solve({
        labels: entries.map(function (e) { return e.spec; }),
        bounds: panel.bounds,
        obstacles: collected.obstacles[key],
        options: solveOptions(entries, exact)
      });

      var hidden = new Uint8Array(entries.length);
      var dropping = entries.some(function (e) { return e.layer.solver.drop_unresolved; });
      if (dropping) markUnresolved(entries, result, hidden);

      entries.forEach(function (entry, i) {
        if (!result.kept[i] || hidden[i]) return;
        previous[entry.id] = [result.x[i] - entry.spec.x, result.y[i] - entry.spec.y];
        annotations.push(buildAnnotation(entry, result.x[i], result.y[i], entry.spec.radius));
      });
    });

    state.previous = previous;
    return annotations;
  }

  // Hides labels that still collide, keeping the highest priority of each clash.
  function markUnresolved(entries, result, hidden) {
    var order = entries
      .map(function (e, i) { return i; })
      .filter(function (i) { return result.kept[i]; })
      .sort(function (a, b) {
        var pa = entries[a].spec.priority || 0;
        var pb = entries[b].spec.priority || 0;
        return pb - pa || a - b;
      });
    var placed = [];
    order.forEach(function (i) {
      var e = entries[i];
      var clash = !e.layer.solver.drop_unresolved ? false : placed.some(function (j) {
        var o = entries[j];
        return Math.abs(result.x[i] - result.x[j]) * 2 < e.spec.width + o.spec.width &&
               Math.abs(result.y[i] - result.y[j]) * 2 < e.spec.height + o.spec.height;
      });
      if (clash) hidden[i] = 1;
      else placed.push(i);
    });
  }

  function signature(annotations) {
    return annotations.map(function (a) {
      return [a.name, a.ax, a.ay, a.x, a.y, a.arrowcolor].join(':');
    }).join(';');
  }

  // Annotations extend autoranged axes, and a changed range would invalidate
  // the solve that produced them. Freezing the current range breaks that loop.
  function pinnedRanges(gd, cfg) {
    var full = gd._fullLayout;
    var update = {};
    touchedAxes(cfg).forEach(function (ref) {
      var name = axisName(ref);
      var axis = full[name];
      if (axis && axis.autorange) update[name + '.range'] = axis.range.slice();
    });
    return update;
  }

  function apply(gd, cfg, annotations) {
    var kept = ((gd.layout && gd.layout.annotations) || []).filter(function (a) { return !isOurs(a); });
    var update = pinnedRanges(gd, cfg);
    update.annotations = kept.concat(annotations);
    return root.Plotly.relayout(gd, update);
  }

  function settle(gd, state, runParts) {
    state.applying = false;
    var cfg = getConfig(gd);
    if (!cfg || !gd._fullLayout) return;
    var parts = captureParts(gd, state, cfg);
    var unchanged = runParts && parts.ranges === runParts.ranges &&
      parts.size === runParts.size && parts.frame === runParts.frame &&
      parts.traces === runParts.traces && parts.config === runParts.config;
    state.parts = parts;
    if (!unchanged && state.chained < MAX_CHAINED_RUNS) {
      state.chained++;
      schedule(gd, state, 'render');
    }
  }

  function run(gd, state, exact) {
    if (state.applying) return state.promise;
    var cfg = getConfig(gd);
    if (!cfg || !gd._fullLayout) return Promise.resolve();

    var runParts = captureParts(gd, state, cfg);
    var annotations;
    try {
      annotations = computeAnnotations(gd, state, cfg, exact);
    } catch (error) {
      console.error('repelly: failed to place labels', error);
      return Promise.resolve();
    }

    var sig = signature(annotations);
    var current = countOurs(gd);
    if (sig === state.signature && current === annotations.length) {
      state.parts = runParts;
      return Promise.resolve();
    }

    state.signature = sig;
    state.applying = true;
    state.promise = Promise.resolve(apply(gd, cfg, annotations)).then(
      function () { settle(gd, state, runParts); },
      function (error) {
        state.applying = false;
        console.error('repelly: failed to apply labels', error);
      }
    );
    return state.promise;
  }

  function schedule(gd, state, trigger) {
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(function () {
      state.timer = null;
      run(gd, state, false);
    }, DEBOUNCE[trigger] || 0);
  }

  function removeLabels(gd, state) {
    state.parts = null;
    state.signature = null;
    state.previous = {};
    if (!countOurs(gd)) return;
    var kept = gd.layout.annotations.filter(function (a) { return !isOurs(a); });
    state.applying = true;
    Promise.resolve(root.Plotly.relayout(gd, { annotations: kept })).then(
      function () { state.applying = false; },
      function () { state.applying = false; }
    );
  }

  function evaluate(gd, state) {
    if (state.applying || !gd._fullLayout) return;
    var cfg = getConfig(gd);
    if (!cfg) {
      if (state.parts || countOurs(gd)) removeLabels(gd, state);
      return;
    }

    var parts = captureParts(gd, state, cfg);
    var prev = state.parts;
    var trigger = null;
    if (!prev || prev.config !== parts.config || prev.count !== parts.count || prev.traces !== parts.traces) {
      trigger = 'render';
      if (prev && prev.config !== parts.config) {
        state.previous = {};
        state.frame = null;
        parts.frame = String(activeFrame(gd, state, cfg));
      }
    } else if (prev.frame !== parts.frame) {
      trigger = 'frame';
    } else if (prev.size !== parts.size) {
      trigger = 'resize';
    } else if (prev.ranges !== parts.ranges) {
      trigger = 'zoom';
    }
    if (!trigger) return;

    state.chained = 0;
    if (trigger !== 'render' && (cfg.on || []).indexOf(trigger) === -1) {
      state.parts = parts;
      return;
    }
    schedule(gd, state, trigger);
  }

  function attach(gd) {
    if (!gd || typeof gd.on !== 'function') return null;
    if (gd.__repelly && gd.__repelly.emitter === gd._ev) {
      evaluate(gd, gd.__repelly);
      return gd.__repelly;
    }

    var state = {
      emitter: gd._ev,
      parts: null,
      signature: null,
      previous: {},
      applying: false,
      promise: Promise.resolve(),
      timer: null,
      chained: 0,
      frame: null
    };
    gd.__repelly = state;

    var check = function () { evaluate(gd, state); };
    ['plotly_afterplot', 'plotly_relayout', 'plotly_restyle', 'plotly_update', 'plotly_redraw',
     'plotly_animated'].forEach(function (name) { gd.on(name, check); });
    gd.on('plotly_animatingframe', function (event) {
      if (event && event.name != null) state.frame = String(event.name);
      check();
    });

    evaluate(gd, state);
    return state;
  }

  // Solves immediately, without the time budget, and reports the outcome.
  // Static export uses this to read positions out of a headless browser.
  function solveNow(gd) {
    var state = attach(gd);
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = null;
    }
    return Promise.resolve(state.promise)
      .then(function () { return run(gd, state, true); })
      .then(function () { return state.promise; })
      .then(function () {
        var ranges = {};
        var cfg = getConfig(gd);
        if (cfg) {
          touchedAxes(cfg).forEach(function (ref) {
            var name = axisName(ref);
            if (gd._fullLayout[name]) ranges[name] = gd._fullLayout[name].range.slice();
          });
        }
        return { annotations: ((gd.layout && gd.layout.annotations) || []).filter(isOurs), ranges: ranges };
      });
  }

  function scanPage() {
    var plots = document.querySelectorAll('.js-plotly-plot');
    for (var i = 0; i < plots.length; i++) attach(plots[i]);
  }

  // Watches for Plotly graphs appearing on the page; used by Dash integration,
  // where graphs are created and replaced by callbacks at any time.
  function autoAttach() {
    if (root.__repellyObserver) return;
    var pending = null;
    root.__repellyObserver = new MutationObserver(function () {
      if (pending) return;
      pending = setTimeout(function () {
        pending = null;
        scanPage();
      }, 50);
    });
    root.__repellyObserver.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class']
    });
    scanPage();
  }

  root.repelly = {
    version: VERSION,
    attach: attach,
    autoAttach: autoAttach,
    solveNow: solveNow
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
