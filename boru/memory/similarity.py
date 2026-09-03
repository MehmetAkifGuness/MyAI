import math
from collections.abc import Sequence


def cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if len(left) != len(right) or not left:
        return 0.0

    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(left, right)
    )

    left_norm = math.sqrt(
        sum(value * value for value in left)
    )

    right_norm = math.sqrt(
        sum(value * value for value in right)
    )

    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0

    similarity = dot_product / (left_norm * right_norm)

    return max(
        -1.0,
        min(1.0, similarity),
    )