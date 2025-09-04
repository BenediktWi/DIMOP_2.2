import frontend


def test_build_graphviz_source():
    components = [
        {"id": 1, "name": "Root", "level": 0, "parent_id": None},
        {"id": 2, "name": "Child", "level": 1, "parent_id": 1},
    ]
    src = frontend.build_graphviz_source(components)
    assert '1 [label="Root' in src
    assert '2 [label="Child' in src
    assert '1 -> 2' in src
