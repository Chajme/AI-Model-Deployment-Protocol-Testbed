import pytest

from common.stats import quartiles, to_number


def test_quartiles_odd_count():
    assert quartiles([5, 1, 3, 2, 4]) == (2.0, 3.0, 4.0)


def test_quartiles_even_count_interpolates():
    q1, median, q3 = quartiles([1, 2, 3, 4])
    assert median == pytest.approx(2.5)
    assert q1 == pytest.approx(1.75)
    assert q3 == pytest.approx(3.25)


def test_quartiles_single_value_and_empty():
    assert quartiles([7.0]) == (7.0, 7.0, 7.0)
    assert quartiles([]) is None
    assert quartiles([None, None]) is None


def test_quartiles_stay_inside_range_for_small_n():
    q1, _, q3 = quartiles([10, 20])
    assert 10 <= q1 <= q3 <= 20


@pytest.mark.parametrize("text, expected", [
    ("3.81", 3.81), ("0.26%", 0.26), ("28.6 MB", 28.6), (" 1 ", 1.0),
    ("X", None), ("", None), (None, None), ("True", None),
])
def test_to_number(text, expected):
    assert to_number(text) == expected
