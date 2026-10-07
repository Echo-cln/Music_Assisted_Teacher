from app.services.lesson_service import _device_action, _extract_classroom_setup, _low_device_option, _sync_objective_evidence, _validate_saved_preview, _validated_content


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


def test_fast_mode_keeps_full_contract_and_requires_song_specific_evidence():
    from app.services.ai_provider import _build_messages

    base = _base()
    base["generation_context"] = {
        "selected_song_from_database": {
            "name": "测试歌", "mood": "欢快", "song_type": "童谣", "mode": "五声音阶", "range_note": "c1-c2", "rhythm_score": 4,
        },
        "class_profile": {"rhythm_level": "首拍容易不稳"},
    }
    prompt = _build_messages(base, "", generation_strategy="fast")[0]["content"]
    assert "唯一差别是生成速度" in prompt
    assert "至少两项明确事实" in prompt
    assert "压缩篇幅" not in prompt


def test_saving_rendered_preview_keeps_structured_theory_and_mistake_fields():
    preview = _base()
    preview["theory_explanation"] = {"term": "切分节奏", "script": "先拍出强弱，再把弱拍提前唱出。"}
    preview["mistake_practice"] = {"problem": "句首抢拍", "correction": "先默数一小节，再从强拍进入。"}
    saved = _validate_saved_preview(preview)
    assert saved["theory_explanation"] == preview["theory_explanation"]
    assert saved["mistake_practice"] == preview["mistake_practice"]


def test_device_condition_is_removed_from_teacher_copy_and_kept_as_structured_context():
    setup, requirements = _extract_classroom_setup("强调节奏练习\n[课堂设备条件：无电子设备（教师清唱与身体声势）]")
    assert setup.startswith("无电子设备")
    assert requirements == "强调节奏练习"


def test_low_device_alternative_is_specific_to_each_lesson_stage():
    option = _low_device_option("分句学唱", "无电子设备（教师清唱与身体声势）")
    assert "教师先唱短句" in option
    assert "哼鸣回声模唱" in option


def test_lesson_contract_preserves_local_evidence_and_device_alternatives():
    base = _base()
    base["timeline"][0]["look_for"] = "观察学生能否跟随强拍起唱。"
    base["timeline"][0]["low_device_option"] = "教师清唱，学生拍手保持恒拍。"
    base["objective_evidence"] = [{"objective": "旧目标", "evidence": "观察首拍"}]
    raw = '''{"title":"生成课","objectives":["学生跟随示范完成两次回唱"],"key_points":"保持首拍","difficulties":"长音收尾","preparation":"清唱示范","timeline":[{"teacher":"教师示范后停顿两拍。","students":"两人互换回唱。"}],"theory_explanation":{"term":"节拍","script":"强拍像走路时先落下的一步。"},"mistake_practice":{"problem":"抢拍","correction":"先拍两轮再唱。"},"differentiation":["跟唱","领唱"],"assessment":"记录起音是否稳定。"}'''
    result = _validated_content(raw, base)
    assert result["timeline"][0]["look_for"] == base["timeline"][0]["look_for"]
    assert result["timeline"][0]["low_device_option"] == base["timeline"][0]["low_device_option"]
    assert result["objective_evidence"][0]["objective"] == result["objectives"][0]



def test_observation_evidence_stays_aligned_when_model_changes_objective_count():
    content = {"objectives": ["目标一", "目标二", "目标三", "目标四"]}
    base = {"objective_evidence": [{"objective": "旧目标", "evidence": "旧观察依据"}]}
    _sync_objective_evidence(content, base)
    assert [item["objective"] for item in content["objective_evidence"]] == content["objectives"]
    assert len(content["objective_evidence"]) == len(content["objectives"])
    assert all(item["evidence"] for item in content["objective_evidence"])


def test_device_selection_changes_visible_stage_instruction():
    stage = "分句学唱"
    no_device = _device_action(stage, "无电子设备（教师清唱与身体声势）")
    phone = _device_action(stage, "手机与手机扬声器")
    projector = _device_action(stage, "电脑、投影与音箱")
    computer = _device_action(stage, "电脑与音箱")
    assert len({no_device, phone, projector, computer}) == 4
    assert "教师逐句范唱" in no_device
    assert "手机按乐句播放" in phone
    assert "投影当前歌词句" in projector
    assert "电脑分句播放" in computer
