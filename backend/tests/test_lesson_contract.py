from app.services.lesson_service import _validated_content


def _base():
    return {
        "title": "骨架课", "summary": {"class_name": "三年级"},
        "objectives": ["目标一"], "key_points": "重点", "difficulties": "难点", "preparation": "准备",
        "timeline": [{"minutes": 5, "stage": "导入", "teacher": "骨架教师", "students": "骨架学生"}],
        "theory_explanation": {"term": "节拍", "script": "骨架解释"},
        "mistake_practice": {"problem": "抢拍", "correction": "先拍后唱"},
        "differentiation": ["基础层"], "assessment": "骨架评价",
    }


def test_assessment_object_is_normalized_to_editable_text():
    raw = '''{
      "title":"生成课","objectives":["完成回声模唱"],"key_points":"稳住首拍","difficulties":"长音保持","preparation":"钢琴和节奏卡",
      "timeline":[{"teacher":"给 C 音后示范两拍，听学生起唱。","students":"两人一组回唱并互评。"}],
      "theory_explanation":{"term":"节拍","script":"像走路一样强弱交替。"},
      "mistake_practice":{"problem":"句首抢拍","correction":"先拍四拍再唱。"},
      "differentiation":["基础层跟唱","进阶层领唱"],
      "assessment":{"evidence":"唱准首拍","peer":"同伴勾选","next":"记录长音"}
    }'''
    result = _validated_content(raw, _base())
    assert isinstance(result["assessment"], str)
    assert "唱准首拍" in result["assessment"]
    assert result["timeline"][0]["stage"] == "导入"


def test_string_explanation_and_newline_lists_are_normalized():
    raw = '''{"title":"生成课","objectives":"跟唱主旋律\\n保持首拍","key_points":"重点","difficulties":"难点","preparation":"准备","timeline":[{"teacher":"教师示范","students":"学生回唱"}],"theory_explanation":"节拍像走路","mistake_practice":"先拍再唱","differentiation":"基础跟唱；进阶领唱","assessment":["互评首拍","教师记录长音"]}'''
    result = _validated_content(raw, _base())
    assert result["theory_explanation"]["script"] == "节拍像走路"
    assert result["mistake_practice"]["correction"] == "先拍再唱"
    assert len(result["objectives"]) == 2
