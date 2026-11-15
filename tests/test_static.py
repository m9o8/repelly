# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Tests for static export that need no browser."""

from __future__ import annotations

import subprocess

import pytest

import repelly
from repelly import _static


def test_result_is_unescaped_like_the_dom_dump():
    dom = (
        '<html><body><pre id="repelly-result">'
        '{"text": "a&nbsp;b &amp; &lt;i&gt;c&lt;/i&gt; \\"d\\""}'
        "</pre></body></html>"
    )
    assert _static._parse_result(dom) == {"text": 'a b & <i>c</i> "d"'}


def test_missing_result_is_reported_as_none():
    assert _static._parse_result("<html><body></body></html>") is None


def test_browser_timeout_raises_a_clear_error(monkeypatch):
    def slow(*args, timeout, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout)

    monkeypatch.setattr(_static, "find_browser", lambda explicit: "chrome")
    monkeypatch.setattr(_static.subprocess, "run", slow)
    with pytest.raises(RuntimeError, match="did not finish placing labels"):
        _static._run_headless("<html></html>", None)


def test_a_broken_choreographer_falls_back_to_the_path(monkeypatch):
    chromium = pytest.importorskip("choreographer.browsers.chromium").Chromium

    def changed(*args, **kwargs):
        raise TypeError("unexpected keyword argument 'skip_local'")

    monkeypatch.delenv("BROWSER_PATH", raising=False)
    monkeypatch.setattr(chromium, "find_browser", changed)
    monkeypatch.setattr(_static.shutil, "which", lambda name: f"/bin/{name}")
    assert _static.find_browser() == "/bin/google-chrome"


def test_missing_browser_error_is_public(monkeypatch):
    monkeypatch.delenv("BROWSER_PATH", raising=False)
    monkeypatch.setattr(_static, "_browser_from_choreographer", lambda: None)
    monkeypatch.setattr(_static.shutil, "which", lambda name: None)
    with pytest.raises(repelly.ChromeNotFoundError):
        _static.find_browser()
