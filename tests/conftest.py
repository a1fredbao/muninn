"""Shared fixtures for muninn tests."""

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_workspace():
    """Temporary directory simulating a plugin workspace_dir."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def elements_data():
    """Small subset of periodic-table elements for testing."""
    return [
        {
            "num": 1,
            "sym": "H",
            "name": "氢",
            "eng": "Hydrogen",
            "period": 1,
            "group": "IA",
        },
        {
            "num": 2,
            "sym": "He",
            "name": "氦",
            "eng": "Helium",
            "period": 1,
            "group": "0",
        },
        {
            "num": 3,
            "sym": "Li",
            "name": "锂",
            "eng": "Lithium",
            "period": 2,
            "group": "IA",
        },
        {
            "num": 4,
            "sym": "Be",
            "name": "铍",
            "eng": "Beryllium",
            "period": 2,
            "group": "IIA",
        },
    ]


@pytest.fixture
def elements_workspace(tmp_workspace, elements_data):
    """Workspace dir containing elements.json."""
    path = os.path.join(tmp_workspace, "elements.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(elements_data, f, ensure_ascii=False)
    return tmp_workspace


@pytest.fixture
def mock_state_manager():
    """StateManager mock with pre-set stats."""
    mock = MagicMock()
    mock.get_stats.return_value = {
        "ac_count": 2,
        "total_count": 5,
        "total_ac_time": 10.0,
    }
    return mock


@pytest.fixture
def temp_packs_dir():
    """Temporary directory for pack storage, isolated from ~/.muninn."""
    with tempfile.TemporaryDirectory() as tmp:
        packs_dir = os.path.join(tmp, "packs")
        os.makedirs(packs_dir)
        yield packs_dir


@pytest.fixture
def temp_state_db():
    """Temporary SQLite database file for StateManager tests."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        yield db_path
