# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Public functions that add repelling labels to a figure."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import numbers
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import plotly.graph_objects as go

from repelly._figure import RepelFigure, as_repel_figure

META_KEY = "repelly"
SCHEMA_VERSION = 1
EVENTS = ("render", "zoom", "resize", "frame")
SUPPORTED_TRACES = ("scatter", "scattergl")
DIRECTIONS = ("both", "x", "y")
TRACE_COLOR = "trace"

_DEFAULT_SEGMENT = {"color": "rgba(90,90,90,0.7)", "width": 1}
_DEFAULT_LABEL = {
    "bgcolor": "rgba(255,255,255,0.9)",
    "bordercolor": "rgba(0,0,0,0.3)",
    "borderwidth": 1,
    "borderpad": 3,
}


def add_text_repel(
    fig: go.Figure,
    x: Any = None,
    y: Any = None,
    text: Any = None,
    *,
    row: int | None = None,
    col: int | None = None,
    secondary_y: bool | None = None,
    xref: str | None = None,
    yref: str | None = None,
    selector: Any = None,
    frame: Any = None,
    priority: Any = None,
    visible: Any = None,
    force: float = 1.0,
    force_pull: float = 1.0,
    box_padding: float = 2.0,
    point_padding: float = 2.0,
    direction: Any = "both",
    color: Any = None,
    max_iter: int = 400,
    max_time_ms: float = 40.0,
    max_overlaps: int | None = 10,
    max_labels: int | None = None,
    seed: int = 42,
    min_segment_length: float = 6.0,
    avoid_points: bool = True,
    drop_unresolved: bool = False,
    font: Mapping[str, Any] | None = None,
    segment: Mapping[str, Any] | None = None,
    on: str | Iterable[str] = EVENTS,
) -> RepelFigure:
    """Return a copy of ``fig`` with repelling text labels added.

    Labels are positioned in the browser and re-solved as the viewport changes.
    The returned figure must be kept: its ``show``, ``to_html``, ``write_html``,
    ``to_image`` and ``write_image`` methods carry the label behaviour.

    Coordinates come from one of two places:

    * Explicit: pass ``x``, ``y`` and ``text``. Use ``row``/``col`` or
      ``xref``/``yref`` to target a subplot.
    * From traces: omit ``x`` and ``y`` to label the points of existing scatter
      traces, which is what you want for ``plotly.express`` facets and
      animations. Labels hide along with their trace. ``text`` then defaults to
      each trace's ``text`` (or ``hovertext``), and may be a function of the
      trace. ``selector``, ``row`` and ``col`` narrow down the traces.

    Parameters
    ----------
    fig:
        The figure to label. It is not modified.
    x, y:
        Label anchors in data coordinates.
    text:
        Label strings. Empty or missing entries get no label.
    row, col, secondary_y, xref, yref:
        Target subplot. Defaults to the primary ``x``/``y`` axes.
    selector:
        Trace filter, as for ``Figure.select_traces``, in from-traces mode.
    frame:
        Animation frame name for each label, in explicit mode. From-traces mode
        reads ``fig.frames`` instead.
    priority:
        Higher values are kept first when labels are culled. A sequence, or in
        from-traces mode a function of the trace.
    visible:
        Boolean mask of labels to show. Hidden points still repel other labels.
        A sequence, or in from-traces mode a function of the trace.
    force:
        How strongly overlapping labels separate, from 0.05 up to 1.
    force_pull:
        How strongly labels are drawn back towards their anchors.
    box_padding, point_padding:
        Gaps in pixels around each label box and around each point.
    direction:
        Axes labels may move along: ``"both"``, ``"x"`` or ``"y"``. One value, a
        sequence with one per label, or in from-traces mode a function of the
        trace.
    color:
        Text colour, overriding ``font["color"]``. One colour, a sequence with
        one per label, or in from-traces mode a function of the trace. In
        from-traces mode, ``"trace"`` uses each point's marker colour.
    max_iter, max_time_ms:
        Iteration and time limits for one solve. Calls sharing a subplot are
        solved together, using the largest limits among them.
    max_overlaps:
        Drop a label that starts on top of more than this many higher-priority
        labels. ``None`` keeps every label. Applies to this call's labels.
    max_labels:
        Show at most this many of this call's labels per subplot, by priority.
    seed:
        Random seed, which makes placement reproducible. Calls sharing a
        subplot use the seed of the first call.
    min_segment_length:
        Hide the connector when the label is closer than this many pixels.
    avoid_points:
        Keep labels off every marker in the subplot, labelled or not.
    drop_unresolved:
        Hide labels that still overlap another label after solving.
    font:
        Plotly annotation font, for example ``{"size": 13, "color": "navy"}``.
    segment:
        Connector style: ``color``, ``width``, ``arrowhead``, ``arrowsize``.
    on:
        Events that re-solve: any of ``"render"``, ``"zoom"``, ``"resize"``,
        ``"frame"``. The first render is always solved.
    """
    return _add_layer(
        fig,
        x,
        y,
        text,
        label=None,
        row=row,
        col=col,
        secondary_y=secondary_y,
        xref=xref,
        yref=yref,
        selector=selector,
        frame=frame,
        priority=priority,
        visible=visible,
        force=force,
        force_pull=force_pull,
        box_padding=box_padding,
        point_padding=point_padding,
        direction=direction,
        color=color,
        max_iter=max_iter,
        max_time_ms=max_time_ms,
        max_overlaps=max_overlaps,
        max_labels=max_labels,
        seed=seed,
        min_segment_length=min_segment_length,
        avoid_points=avoid_points,
        drop_unresolved=drop_unresolved,
        font=font,
        segment=segment,
        on=on,
    )


def add_label_repel(
    fig: go.Figure,
    x: Any = None,
    y: Any = None,
    text: Any = None,
    *,
    label: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> RepelFigure:
    """Like :func:`add_text_repel`, with labels drawn on a filled box.

    ``label`` overrides the box style with any of ``bgcolor``, ``bordercolor``,
    ``borderwidth`` and ``borderpad``.
    """
    unknown = set(label or ()) - set(_DEFAULT_LABEL)
    if unknown:
        raise ValueError(f"unknown label style keys: {sorted(unknown)}")
    style = {**_DEFAULT_LABEL, **dict(label or {})}
    return _add_layer(fig, x, y, text, label=style, **kwargs)


def _add_layer(
    fig: go.Figure,
    x: Any,
    y: Any,
    text: Any,
    *,
    label: Mapping[str, Any] | None,
    row: int | None = None,
    col: int | None = None,
    secondary_y: bool | None = None,
    xref: str | None = None,
    yref: str | None = None,
    selector: Any = None,
    frame: Any = None,
    priority: Any = None,
    visible: Any = None,
    direction: Any = "both",
    color: Any = None,
    font: Mapping[str, Any] | None = None,
    segment: Mapping[str, Any] | None = None,
    on: str | Iterable[str] = EVENTS,
    **solver: Any,
) -> RepelFigure:
    if not isinstance(fig, go.Figure):
        raise TypeError(f"fig must be a plotly Figure, got {type(fig).__name__}")
    if (x is None) != (y is None):
        raise ValueError("pass both x and y, or neither to label existing traces")

    events = _validate_events(on)
    solver = _validate_solver(solver)
    result = as_repel_figure(fig, copy=True)

    if x is None:
        if frame is not None:
            raise ValueError("frame is read from fig.frames when labelling traces")
        if xref is not None or yref is not None or secondary_y is not None:
            raise ValueError("xref, yref and secondary_y need explicit x and y")
        columns = _columns_from_traces(
            result, text, priority, visible, direction, color, selector, row, col
        )
    else:
        if selector is not None:
            raise ValueError("selector only applies when x and y are omitted")
        if text is None:
            raise ValueError("text is required when x and y are given")
        refs = _resolve_refs(result, row, col, secondary_y, xref, yref)
        columns = _columns_from_arrays(
            x, y, text, refs, frame, priority, visible, direction, color
        )

    layer = _build_layer(_drop_unlabelled(columns), label, font, segment, solver)
    _store_layer(result, layer, events)
    return result


def _validate_events(on: str | Iterable[str]) -> list[str]:
    events = [on] if isinstance(on, str) else list(on)
    bad = [event for event in events if event not in EVENTS]
    if bad:
        raise ValueError(f"unknown events {bad}; choose from {list(EVENTS)}")
    return events


def _validate_solver(solver: dict[str, Any]) -> dict[str, Any]:
    known = {
        "force": 1.0,
        "force_pull": 1.0,
        "box_padding": 2.0,
        "point_padding": 2.0,
        "max_iter": 400,
        "max_time_ms": 40.0,
        "max_overlaps": 10,
        "max_labels": None,
        "seed": 42,
        "min_segment_length": 6.0,
        "avoid_points": True,
        "drop_unresolved": False,
    }
    unknown = set(solver) - set(known)
    if unknown:
        raise TypeError(f"unexpected keyword arguments: {sorted(unknown)}")
    merged = {**known, **solver}

    for name in (
        "force",
        "force_pull",
        "box_padding",
        "point_padding",
        "max_time_ms",
        "min_segment_length",
    ):
        value = merged[name]
        if not _is_real(value) or value < 0:
            raise ValueError(f"{name} must be a non-negative number")
    if not isinstance(merged["max_iter"], numbers.Integral) or merged["max_iter"] < 1:
        raise ValueError("max_iter must be a positive integer")
    if not isinstance(merged["seed"], numbers.Integral):
        raise ValueError("seed must be an integer")
    for name, minimum in (("max_overlaps", 0), ("max_labels", 1)):
        value = merged[name]
        if value is not None and (
            not isinstance(value, numbers.Integral) or value < minimum
        ):
            raise ValueError(f"{name} must be None or an integer >= {minimum}")
    return {key: _to_native(value) for key, value in merged.items()}


def _is_real(value: Any) -> bool:
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _resolve_refs(
    fig: go.Figure,
    row: int | None,
    col: int | None,
    secondary_y: bool | None,
    xref: str | None,
    yref: str | None,
) -> tuple[str, str]:
    if (row is None) != (col is None):
        raise ValueError("row and col must be given together")
    if row is not None:
        if xref is not None or yref is not None:
            raise ValueError("use either row/col or xref/yref, not both")
        subplot = fig.get_subplot(row, col, secondary_y=bool(secondary_y))
        if not hasattr(subplot, "xaxis") or not hasattr(subplot, "yaxis"):
            raise ValueError(f"subplot ({row}, {col}) is not a cartesian x/y subplot")
        return _axis_ref(subplot.xaxis.plotly_name), _axis_ref(
            subplot.yaxis.plotly_name
        )
    if secondary_y is not None:
        raise ValueError("secondary_y requires row and col")

    resolved = (xref or "x", yref or "y")
    for ref, letter in zip(resolved, "xy", strict=True):
        if not ref.startswith(letter) or not (ref[1:] == "" or ref[1:].isdigit()):
            raise ValueError(f"invalid {letter}ref {ref!r}")
    return resolved


def _axis_ref(plotly_name: str) -> str:
    return plotly_name.replace("axis", "")


def _to_list(values: Any, name: str) -> list[Any]:
    if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Iterable):
        raise TypeError(f"{name} must be a sequence, got {type(values).__name__}")
    dtype = getattr(values, "dtype", None)
    if (
        type(values).__module__.startswith("numpy")
        and getattr(dtype, "kind", "") == "M"
    ):
        values = values.astype("datetime64[us]")
    return list(values.tolist() if hasattr(values, "tolist") else values)


def _to_native(value: Any) -> Any:
    """Convert one value to something JSON can hold, or None if it is missing."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, dt.datetime):
        return None if value != value else value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        value = value.item()
        if isinstance(value, (dt.date, dt.datetime)):
            return value.isoformat()
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        return number if math.isfinite(number) else None
    return None if value != value else value


def _to_text(value: Any) -> str:
    native = _to_native(value)
    if native is None:
        return ""
    if isinstance(native, float) and native.is_integer():
        return str(int(native))
    return str(native)


def _check_length(values: list[Any], name: str, expected: int) -> None:
    if len(values) != expected:
        raise ValueError(f"{name} has {len(values)} values, expected {expected}")


def _priority_value(value: Any) -> float:
    native = _to_native(value)
    if native is None:
        return 0.0
    if not _is_real(native):
        raise ValueError(f"priority values must be numeric, got {value!r}")
    return float(native)


def _visible_value(value: Any) -> bool:
    native = _to_native(value)
    return bool(native) if native is not None else False


def _direction_value(value: Any) -> str:
    native = _to_native(value)
    if native not in DIRECTIONS:
        raise ValueError(f"direction must be 'both', 'x' or 'y', got {value!r}")
    return native


def _color_value(value: Any) -> str | None:
    native = _to_native(value)
    if native is not None and not isinstance(native, str):
        raise ValueError(f"color values must be strings, got {value!r}")
    return native


def _columns_from_arrays(
    x: Any,
    y: Any,
    text: Any,
    refs: tuple[str, str],
    frame: Any,
    priority: Any,
    visible: Any,
    direction: Any,
    color: Any,
) -> dict[str, list[Any]]:
    xs = [_to_native(v) for v in _to_list(x, "x")]
    n = len(xs)
    ys = [_to_native(v) for v in _to_list(y, "y")]
    texts = [_to_text(v) for v in _to_list(text, "text")]
    _check_length(ys, "y", n)
    _check_length(texts, "text", n)

    columns: dict[str, list[Any]] = {
        "x": xs,
        "y": ys,
        "text": texts,
        "xref": [refs[0]] * n,
        "yref": [refs[1]] * n,
        "trace": [None] * n,
        "frame": [None] * n,
        "priority": [0.0] * n,
        "visible": [True] * n,
    }
    if isinstance(direction, str):
        columns["direction"] = [_direction_value(direction)] * n
    else:
        directions = [_direction_value(v) for v in _to_list(direction, "direction")]
        _check_length(directions, "direction", n)
        columns["direction"] = directions
    if isinstance(color, str) and color == TRACE_COLOR:
        raise ValueError("color='trace' needs labels made from traces, without x and y")
    if color is None or isinstance(color, str):
        columns["color"] = [color] * n
    else:
        colors = [_color_value(v) for v in _to_list(color, "color")]
        _check_length(colors, "color", n)
        columns["color"] = colors
    if frame is not None:
        frames = [_to_text(v) or None for v in _to_list(frame, "frame")]
        _check_length(frames, "frame", n)
        columns["frame"] = frames
    if priority is not None:
        priorities = [_priority_value(v) for v in _to_list(priority, "priority")]
        _check_length(priorities, "priority", n)
        columns["priority"] = priorities
    if visible is not None:
        mask = [_visible_value(v) for v in _to_list(visible, "visible")]
        _check_length(mask, "visible", n)
        columns["visible"] = mask
    return columns


def _select_trace_indices(
    fig: go.Figure, selector: Any, row: int | None, col: int | None
) -> list[int]:
    if (row is None) != (col is None):
        raise ValueError("row and col must be given together")
    chosen = {id(t) for t in fig.select_traces(selector=selector, row=row, col=col)}
    indices = [i for i, trace in enumerate(fig.data) if id(trace) in chosen]
    if not indices:
        raise ValueError("no traces match; pass x and y, or adjust selector/row/col")
    for i in indices:
        if fig.data[i].type not in SUPPORTED_TRACES:
            raise TypeError(
                f"trace {i} has type {fig.data[i].type!r}; "
                f"repelly can only label {list(SUPPORTED_TRACES)} traces"
            )
    return indices


def _trace_coords(trace: Any, base: Any, axis: str) -> list[Any] | None:
    values = trace[axis] if trace[axis] is not None else base[axis]
    return None if values is None else _to_list(values, axis)


def _resolve_positions(trace: Any, base: Any) -> tuple[list[Any], list[Any]]:
    xs = _trace_coords(trace, base, "x")
    ys = _trace_coords(trace, base, "y")
    if xs is None and ys is None:
        raise ValueError("cannot label a trace without x or y data")
    if xs is None:
        x0, dx = base["x0"] or 0, base["dx"] or 1
        xs = [x0 + i * dx for i in range(len(ys))]
    if ys is None:
        y0, dy = base["y0"] or 0, base["dy"] or 1
        ys = [y0 + i * dy for i in range(len(xs))]
    return xs, ys


def _per_point(
    spec: Any, trace: Any, base: Any, name: str, n: int, default: Any
) -> list[Any]:
    if spec is None:
        return [default] * n
    values = spec(trace) if isinstance(spec, Callable) else spec
    resolved = _to_list(values, name)
    _check_length(resolved, name, n)
    return resolved


def _default_text(trace: Any, base: Any, n: int) -> list[Any]:
    for attribute in ("text", "hovertext"):
        for source in (trace, base):
            value = source[attribute]
            if value is None:
                continue
            if isinstance(value, str):
                return [value] * n
            return _to_list(value, attribute)
    raise ValueError(
        "these traces have no text or hovertext; pass text=, for example "
        "text=lambda trace: trace.customdata[:, 0]"
    )


def _trace_colors(trace: Any, base: Any, n: int) -> list[Any]:
    """Return per-point marker colours, or a marker for the browser to resolve."""
    for source in (trace, base):
        value = source.marker.color
        if isinstance(value, str):
            return [value] * n
        if value is not None:
            values = _to_list(value, "marker.color")
            if len(values) == n and all(isinstance(v, str) for v in values):
                return values
            break
    return [TRACE_COLOR] * n


def _columns_from_traces(
    fig: go.Figure,
    text: Any,
    priority: Any,
    visible: Any,
    direction: Any,
    color: Any,
    selector: Any,
    row: int | None,
    col: int | None,
) -> dict[str, list[Any]]:
    for name, spec in (
        ("text", text),
        ("priority", priority),
        ("visible", visible),
        ("direction", None if isinstance(direction, str) else direction),
        ("color", None if isinstance(color, str) else color),
    ):
        if spec is not None and not callable(spec):
            raise TypeError(f"without x and y, {name} must be a function of the trace")

    indices = set(_select_trace_indices(fig, selector, row, col))
    sources: list[tuple[int, Any, str | None]] = []
    if fig.frames:
        for frame in fig.frames:
            positions = (
                frame.traces if frame.traces is not None else range(len(frame.data))
            )
            for position, trace in zip(positions, frame.data, strict=False):
                if position in indices:
                    sources.append((position, trace, frame.name))
    else:
        sources = [(i, fig.data[i], None) for i in sorted(indices)]

    columns: dict[str, list[Any]] = {
        key: []
        for key in (
            "x",
            "y",
            "text",
            "xref",
            "yref",
            "trace",
            "frame",
            "priority",
            "visible",
            "direction",
            "color",
        )
    }
    for position, trace, frame_name in sources:
        base = fig.data[position]
        xs, ys = _resolve_positions(trace, base)
        n = min(len(xs), len(ys))
        texts = (
            _default_text(trace, base, n)
            if text is None
            else _per_point(text, trace, base, "text", n, "")
        )
        _check_length(texts, "text", n)
        columns["x"].extend(_to_native(v) for v in xs[:n])
        columns["y"].extend(_to_native(v) for v in ys[:n])
        columns["text"].extend(_to_text(v) for v in texts)
        columns["xref"].extend([base.xaxis or "x"] * n)
        columns["yref"].extend([base.yaxis or "y"] * n)
        columns["trace"].extend([position] * n)
        columns["frame"].extend([frame_name] * n)
        columns["priority"].extend(
            _priority_value(v)
            for v in _per_point(priority, trace, base, "priority", n, 0.0)
        )
        columns["visible"].extend(
            _visible_value(v)
            for v in _per_point(visible, trace, base, "visible", n, True)
        )
        columns["direction"].extend(
            _direction_value(v)
            for v in (
                [direction] * n
                if isinstance(direction, str)
                else _per_point(direction, trace, base, "direction", n, "both")
            )
        )
        if isinstance(color, str) and color == TRACE_COLOR:
            columns["color"].extend(_trace_colors(trace, base, n))
        else:
            columns["color"].extend(
                _color_value(v)
                for v in (
                    [color] * n
                    if isinstance(color, str)
                    else _per_point(color, trace, base, "color", n, None)
                )
            )
    return columns


def _drop_unlabelled(columns: dict[str, list[Any]]) -> dict[str, list[Any]]:
    keep = [
        i
        for i in range(len(columns["x"]))
        if columns["x"][i] is not None
        and columns["y"][i] is not None
        and columns["text"][i] != ""
    ]
    if not keep:
        raise ValueError(
            "no labels to add: every point has an empty label or missing coordinate"
        )
    return {key: [values[i] for i in keep] for key, values in columns.items()}


def _compact(values: Sequence[Any]) -> Any:
    """Collapse a constant column to one value to keep the figure JSON small."""
    first = values[0]
    return first if all(value == first for value in values) else list(values)


def _build_layer(
    columns: dict[str, list[Any]],
    label: Mapping[str, Any] | None,
    font: Mapping[str, Any] | None,
    segment: Mapping[str, Any] | None,
    solver: dict[str, Any],
) -> dict[str, Any]:
    unknown = set(segment or ()) - {"color", "width", "arrowhead", "arrowsize"}
    if unknown:
        raise ValueError(f"unknown segment style keys: {sorted(unknown)}")

    layer: dict[str, Any] = {
        "x": columns["x"],
        "y": columns["y"],
        "text": columns["text"],
        **{
            key: _compact(columns[key])
            for key in ("xref", "yref", "trace", "frame", "priority", "visible")
        },
        "solver": {**solver, "direction": _compact(columns["direction"])},
        "segment": {**_DEFAULT_SEGMENT, **dict(segment or {})},
    }
    if any(value is not None for value in columns["color"]):
        layer["color"] = _compact(columns["color"])
    if font:
        layer["font"] = dict(font)
    if label:
        layer["label"] = dict(label)
    return layer


def _store_layer(fig: RepelFigure, layer: dict[str, Any], events: list[str]) -> None:
    meta = fig.layout.meta
    if meta is None:
        meta = {}
    elif not isinstance(meta, Mapping):
        raise ValueError(
            "layout.meta is already set to a non-dict value; repelly stores its "
            "configuration in layout.meta and needs it to be a dict"
        )

    existing = meta.get(META_KEY) or {}
    layers = [*existing.get("layers", []), layer]
    merged_events = sorted(set(existing.get("on", [])) | set(events))
    config: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "layers": layers,
        "on": merged_events,
    }

    frames = [frame.name for frame in (fig.frames or ())]
    if frames:
        config["first_frame"] = frames[0]

    canonical = json.dumps(config, sort_keys=True, default=str).encode()
    config["hash"] = hashlib.sha1(canonical, usedforsecurity=False).hexdigest()
    fig.layout.meta = {**dict(meta), META_KEY: config}
