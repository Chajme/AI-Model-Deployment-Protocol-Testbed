"""Small statistics helpers shared by the export and the charts."""
import statistics


def quartiles(values):
    """(q1, median, q3) of the numeric values, or None when there are none.

    Uses the inclusive method (linear interpolation between data points), so
    for n = 1 all three are the single value and for small n the quartiles
    stay inside the observed range.
    """
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return data[0], data[0], data[0]
    q1, median, q3 = statistics.quantiles(data, n=4, method="inclusive")
    return q1, median, q3


def to_number(text):
    """Parse a CSV cell such as '3.81', '0.26%', '28.6 MB' -> float, else None."""
    if text is None:
        return None
    value = str(text).strip().rstrip("%").replace(" MB", "").strip()
    if value == "" or value.upper() == "X":
        return None
    try:
        return float(value)
    except ValueError:
        return None
