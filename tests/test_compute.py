# flake8: noqa
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # noqa: E402

import pytest
from backend import compute_component_score, Component, Material


def test_compute_component_score_atomic():
    mat = Material(
        id=1,
        name="Steel",
        total_gwp=2.0,
        is_dangerous=False,
        plast_fam="A",
        system_ability=2,
        sortability=1,
    )
    comp = Component(id=1, is_atomic=True, weight=3.0, material=mat)
    score = compute_component_score(comp)
    assert score == 1.0


def test_compute_component_score_hierarchy():
    mat = Material(
        id=1,
        name="Steel",
        total_gwp=5.0,
        is_dangerous=False,
        plast_fam="A",
        system_ability=2,
        sortability=1,
    )
    child = Component(id=2, name="child", is_atomic=True, weight=1.0, material=mat)
    root = Component(
        id=3,
        name="root",
        is_atomic=False,
        weight=2.0,
        reusable=False,
        connection_type=1,
    )
    root.children.append(child)
    child.parent = root
    score = compute_component_score(root)
    assert score == 1.0
