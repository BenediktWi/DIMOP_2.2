import frontend


def test_build_graphviz_tree():
    components = [
        {"id": 1, "name": "Root", "level": 0, "parent_id": None},
        {"id": 2, "name": "Child", "level": 1, "parent_id": 1},
    ]
    dot = frontend.build_graphviz_tree(components)
    src = dot.source
    assert '1 [label="Root' in src
    assert '2 [label="Child' in src
    assert '1 -> 2' in src
