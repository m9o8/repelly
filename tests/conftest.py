# repelly - https://github.com/m9o8/repelly
# Copyright (C) 2026 Moritz Peist
# SPDX-License-Identifier: GPL-3.0-or-later
# This program comes with ABSOLUTELY NO WARRANTY. It is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or later. See <https://www.gnu.org/licenses/>.

"""Shared fixtures for tests that drive a real browser."""

from __future__ import annotations

import pytest

from repelly._static import ChromeNotFoundError, find_browser


@pytest.fixture(scope="session")
def chrome_path():
    try:
        return find_browser()
    except ChromeNotFoundError:
        pytest.skip("no Chrome or Chromium available")


@pytest.fixture(scope="session")
def browser(chrome_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            executable_path=chrome_path, headless=True
        )
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1000, "height": 700})
    tab = context.new_page()
    tab.console_errors = []
    tab.on(
        "console",
        lambda message: (
            tab.console_errors.append(message.text) if message.type == "error" else None
        ),
    )
    tab.on("pageerror", lambda error: tab.console_errors.append(str(error)))
    yield tab
    context.close()
