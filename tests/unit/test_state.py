from maya_agent.sidecar.state import CrossIntentMemory


def test_memory_drops_oldest_at_capacity():
    m = CrossIntentMemory(max_entries=2)
    m.add("a", "A")
    m.add("b", "B")
    m.add("c", "C")
    assert m.as_list() == [("b", "B"), ("c", "C")]


def test_memory_clear():
    m = CrossIntentMemory()
    m.add("x", "X")
    m.clear()
    assert m.as_list() == []
