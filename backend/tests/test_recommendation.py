from app.services.recommendation_service import _number


def test_chinese_grade_number():
    assert _number("三年级") == 3
    assert _number("6年级") == 6


def test_unknown_grade_has_default():
    assert _number("通用") == 3
