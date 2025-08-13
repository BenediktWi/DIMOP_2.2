# flake8: noqa
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # noqa: E402

import pytest
from backend import compute_component_score, Component, Material


def test_compute_component_score_atomic():
    mat = Material(id=1, name="Steel", total_gwp=2.0)
    comp = Component(id=1, is_atomic=True, volume=3.0, density=1.0, material=mat)
    score = compute_component_score(comp)
    assert score == 6.0


def test_compute_component_score_hierarchy():
    mat = Material(id=1, name="Steel", total_gwp=5.0)
    child = Component(id=2, name="child", is_atomic=True, volume=1.0, density=1.0, material=mat)
    root = Component(
        id=3,
        name="root",
        is_atomic=False,
        volume=2.0,
        density=1.0,
        reusable=False,
        connection_type=1,
    )
    root.children.append(child)
    child.parent = root
    score = compute_component_score(root)
    assert pytest.approx(score) == 9.5


def test_compute_component_score_volume_density():
    mat = Material(id=1, name="Steel", total_gwp=2.0)
    comp = Component(id=1, is_atomic=True, volume=3.0, density=2.0, material=mat)
    score = compute_component_score(comp)
    assert score == 12.0


def test_compute_component_score_default_weight_non_atomic():
    mat = Material(id=1, name="Steel", total_gwp=5.0)
    child = Component(id=2, is_atomic=True, weight=1.0, material=mat)
    root = Component(
        id=3,
        name="root",
        is_atomic=False,
        reusable=False,
        connection_type=1,
        material=mat,
    )
    root.children.append(child)
    child.parent = root
    score = compute_component_score(root)
    assert pytest.approx(score) == 4.75
