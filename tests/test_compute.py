# flake8: noqa
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # noqa: E402

import pytest
from backend import (
    compute_component_score,
    compute_component_weight,
    Component,
    Material,
)


def test_compute_component_score_atomic():
    mat = Material(id=1, name="Steel", co2_value=2.0)
    comp = Component(id=1, is_atomic=True, weight=3.0, material=mat)
    score = compute_component_score(comp, None)
    assert score == 6.0


def test_compute_component_score_hierarchy():
    mat = Material(id=1, name="Steel", co2_value=5.0)
    child = Component(id=2, name="child", is_atomic=True, weight=1.0, material=mat)
    root = Component(
        id=3,
        name="root",
        is_atomic=False,
        weight=None,
        reusable=False,
        connection_strength=95,
    )
    root.children.append(child)
    child.parent = root
    compute_component_weight(root)
    assert root.weight == pytest.approx(child.weight)
    score = compute_component_score(root, None)
    assert pytest.approx(score) == 4.75


def test_compute_component_weight_propagates():
    mat = Material(id=1, name="Steel", co2_value=1.0)
    c1 = Component(id=1, name="c1", is_atomic=True, weight=1.5, material=mat)
    c2 = Component(id=2, name="c2", is_atomic=True, weight=2.5, material=mat)
    parent = Component(id=3, name="p", is_atomic=False, weight=None)
    parent.children.extend([c1, c2])
    c1.parent = parent
    c2.parent = parent

    compute_component_weight(parent)
    assert parent.weight == pytest.approx(c1.weight + c2.weight)
