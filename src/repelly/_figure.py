# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""A Figure subclass whose output methods include the repelly runtime."""

from __future__ import annotations

import html
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
from plotly.io._base_renderers import (
    HtmlRenderer,
    IFrameRenderer,
    ImageRenderer,
    PlotlyRenderer,
)

from repelly._runtime import merge_post_script

_DEFAULT_IFRAME_HEIGHT = 500
_IFRAME_MARGIN = 20


class RepelFigure(go.Figure):
    """A ``go.Figure`` that renders its repelling labels wherever it is shown."""

    def to_html(self, *args: Any, **kwargs: Any) -> str:
        kwargs["post_script"] = merge_post_script(kwargs.get("post_script"))
        return super().to_html(*args, **kwargs)

    def write_html(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["post_script"] = merge_post_script(kwargs.get("post_script"))
        return super().write_html(*args, **kwargs)

    def to_image(self, *args: Any, **kwargs: Any) -> bytes:
        from repelly._static import bake

        baked = bake(self, width=kwargs.get("width"), height=kwargs.get("height"))
        return baked.to_image(*args, **kwargs)

    def write_image(self, *args: Any, **kwargs: Any) -> Any:
        from repelly._static import bake

        baked = bake(self, width=kwargs.get("width"), height=kwargs.get("height"))
        return baked.write_image(*args, **kwargs)

    def show(
        self, renderer: str | None = None, validate: bool = True, **kwargs: Any
    ) -> None:
        interactive, inline, images = _split_renderers(renderer)
        include_plotlyjs = kwargs.pop("include_plotlyjs", "cdn")

        if images:
            baked = _bake_for_display(self, kwargs)
            pio.show(baked, renderer="+".join(images), validate=validate)
        if interactive:
            options = dict(
                kwargs, post_script=merge_post_script(kwargs.get("post_script"))
            )
            pio.show(
                _plain(self),
                renderer="+".join(interactive),
                validate=validate,
                **options,
            )
        if inline:
            from IPython.display import display

            display(
                {"text/html": self._iframe_html(include_plotlyjs, kwargs)}, raw=True
            )

    def _ipython_display_(self) -> None:
        if pio.renderers.render_on_display and pio.renderers.default:
            self.show()
        else:
            print(repr(self))

    def _repr_mimebundle_(
        self,
        include: Any = None,
        exclude: Any = None,
        validate: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        interactive, inline, images = _split_renderers(None)
        bundle: dict[str, Any] = {}
        renderers = pio.renderers
        if images:
            baked = _bake_for_display(self, kwargs)
            bundle.update(
                renderers._build_mime_bundle(baked.to_dict(), "+".join(images))
            )
        if interactive:
            options = dict(
                kwargs, post_script=merge_post_script(kwargs.get("post_script"))
            )
            bundle.update(
                renderers._build_mime_bundle(
                    self.to_dict(), "+".join(interactive), **options
                )
            )
        if inline:
            bundle["text/html"] = self._iframe_html("cdn", kwargs)
        return bundle

    def _iframe_html(self, include_plotlyjs: Any, options: dict[str, Any]) -> str:
        """Return a self-contained iframe, for frontends that run Plotly themselves.

        JupyterLab and VS Code draw Plotly's own mimetype without running custom
        JavaScript, and may run inline scripts before a CDN script has loaded.
        An iframe document has its own, ordinary script loading.
        """
        page = self.to_html(
            full_html=True,
            include_plotlyjs=include_plotlyjs,
            config=options.get("config"),
            default_width=options.get("default_width", "100%"),
            default_height=options.get("default_height", "100%"),
        )
        height = (self.layout.height or _DEFAULT_IFRAME_HEIGHT) + _IFRAME_MARGIN
        return (
            f'<iframe srcdoc="{html.escape(page, quote=True)}" width="100%" '
            f'height="{height}" style="border:none" scrolling="no"></iframe>'
        )


def as_repel_figure(fig: go.Figure, *, copy: bool = False) -> RepelFigure:
    """Return ``fig`` as a :class:`RepelFigure`.

    Useful after operations that return a plain ``go.Figure``, such as
    ``go.Figure(repel_fig)``. The labels live in ``layout.meta``, so nothing is
    lost by the conversion.
    """
    if isinstance(fig, RepelFigure) and not copy:
        return fig
    return RepelFigure(fig)


def _plain(fig: go.Figure) -> go.Figure:
    return go.Figure(fig)


def _bake_for_display(fig: RepelFigure, options: dict[str, Any]) -> go.Figure:
    from repelly._static import bake

    return bake(fig, width=options.get("width"), height=options.get("height"))


def _split_renderers(renderer: str | None) -> tuple[list[str], list[str], list[str]]:
    """Sort renderer names into (accepts post_script, needs iframe, static image)."""
    names = [
        name for name in (renderer or pio.renderers.default or "").split("+") if name
    ]
    interactive: list[str] = []
    inline: list[str] = []
    images: list[str] = []
    for name in names:
        instance = pio.renderers[name]
        if isinstance(instance, PlotlyRenderer):
            inline.append(name)
        elif isinstance(instance, ImageRenderer):
            images.append(name)
        else:
            interactive.append(name)
    if inline:
        # A combination like "plotly_mimetype+notebook" offers alternatives for one
        # output. Plotly's frontends pick one; repelly's iframe is a separate display.
        interactive = [
            name
            for name in interactive
            if not isinstance(pio.renderers[name], (HtmlRenderer, IFrameRenderer))
        ]
    return interactive, inline, images
