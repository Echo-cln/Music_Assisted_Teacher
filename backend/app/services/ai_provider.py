"""模型无关的教案生成层。

规则层只提供数据库事实和课时约束。快速、深度两种模式使用不同的
教学写作任务，避免把同一份固定文案换一个模式名称返回给教师。
"""

import json
import time
from collections.abc import Iterator

from app.services.llm.factory import get_adapter
from app.core.config import get_settings


def _retry_stream(messages: list[dict], model: str | None = None, generation_strategy: str = "deep") -> Iterator[str]:
    """对可恢复的网络或服务错误进行有限重试。"""
    last_error: Exception | None = None
    # 一次深度请求允许完整生成。失败立即持久化错误，避免重试把等待时间翻倍。
    for delay in (0,):
        try:
            if delay:
                time.sleep(delay)
            yield from get_adapter(model, generation_strategy=generation_strategy).stream(messages, generation_strategy=generation_strategy)
            return
        except Exception as exc:  # 调用端需要最后一个真实错误用于任务状态展示
            last_error = exc
    assert last_error is not None
    raise last_error


def _build_messages(base: dict, instruction: str, *, adjustment: bool = False, generation_strategy: str = "deep") -> list[dict]:
    """按生成策略构造不同的教学任务，而非只改一句模式说明。"""
    lesson = {key: value for key, value in base.items() if key != "generation_context"}
    evidence = base.get("generation_context", {})
    contract = """
【严格输出协议】只输出一个 JSON 对象，不要包装字段或 Markdown。必须包含 title、objectives（字符串数组）、key_points（字符串）、difficulties（字符串）、preparation（字符串）、timeline（对象数组）、theory_explanation（含 term、script）、mistake_practice（含 problem、correction）、differentiation（字符串数组）、assessment（字符串）。
timeline 项数必须等于输入 lesson；每项只含 teacher 与 students 两个非空字符串。不要输出 summary、minutes、stage、generation_context。设备与班级差异约束：lesson.classroom_setup 是设备白名单，只能使用其中明确列出的设备；没有外接音箱、投影或乐器时不得默认其存在；写有无电子设备时必须提供清唱、哼鸣或身体声势方案。evidence.class_profile.common_problems 与 teacher_notes 是群体层面的差异，应转成基础支持、核心任务和拓展任务，禁止编造个人情况。\n总正文控制在 3600 个汉字以内，JSON 结束后立即停止。
"""
    if adjustment:
        system_prompt = """
你是一名具有多年乡村小学音乐教学经验的优秀音乐教研员。根据教师的调整要求修改现有教案。
只输出一个合法 JSON 对象，不要 Markdown、不要解释、不要 generation_context。
保留 timeline 项数；每项的 minutes、stage 由后端保留，模型不要输出。
只能依据输入资料，不得编造歌词、简谱或地方文化事实。请把修改真正落实到目标、流程、话术和评价中。
""" + contract
    elif generation_strategy == "fast":
        system_prompt = """
你是一名乡村小学音乐教研员。现在执行“快速成课”任务：使用更快的模型，在给定事实与课时框架内生成一份完整、细致、可立即上课的音乐教案。

只输出一个合法 JSON 对象：不要 Markdown、不要解释、不要 generation_context。

【快速模式的唯一差别是生成速度】
1. 内容完整度、活动数量、课堂话术质量、个性化程度必须与深度模式相同；不得为了“快速”删减篇幅、字段、教学环节或细节。
2. 快速来自更快的模型和较短的服务等待路径，不来自模板套用。必须从 evidence.selected_song_from_database 中选至少两项明确事实（如歌曲情绪、体裁、调式、音域、节奏难度、地区）并在目标、课堂流程或练习中落实为具体动作；同时至少落实一项班级画像事实。
3. 同一地区的不同歌曲不能得到只替换歌名的同构教案。歌曲事实不足时，明确依照现有资料安排活动，不得编造歌词、简谱或地方文化事实。
4. 每个 timeline.teacher 与 timeline.students 都要写清动作、任务、观察点和可直接使用的课堂语言；目标、重难点、乐理、易错纠正、分层和评价都必须完整保留。
""" + contract
    else:
        # 深度模式是一次完整的“诊断→决策→落地”生成，而不是快速骨架的扩写版。
        system_prompt = """
你是一名具有多年乡村小学音乐教学经验的优秀音乐教研员。
根据班级画像、歌曲资料、知识库和教师补充要求，写出一份能直接带进课堂的教案。先选定一个最需要优先解决的学习问题，再把决定落实到目标、活动和评价中。classroom_setup 是本节可用设备白名单，只能安排其中明确出现的设备；未勾选投影、音箱或乐器时，不得假设存在。

只输出合法 JSON，不要解释或推理过程。不得删除、合并、减少、调换 timeline 数组中的课堂环节；minutes 和 stage 由后端保留。

【每个课堂环节必须可执行】
timeline 每一项的 teacher 与 students 均需与该项 stage 和 minutes 对应：
- teacher：写清启动指令、示范/组织动作、观察点和一个可直接说出口的短句；必要时写出学生卡住后的即时支架；
- students：写清个人/小组任务、产出或回应方式，以及互听/展示的依据；
- 一项只解决该阶段的一个核心任务。不得在所有环节重复“分组合作”“老师引导”“学生积极参与”等套话。
可使用模唱、分句、律动、分组、互听、拍手或桌面节奏，但必须说明为何适合当前班级，而不是罗列方法。

【教案其余字段的质量标准】
1. objectives、key_points、difficulties、preparation 必须对应当前班级的音准、节奏、合作和课堂偏好；目标必须可观察、可判断，不能只写“感受音乐”。
2. theory_explanation 只解释本课真正需要的一个知识点，用小学生听得懂的比喻、教师口语和一个可操作的小验证，不写教材式定义。
3. mistake_practice 按“错误表现 → 可能原因 → 立刻纠正动作 → 教师提示语”写，并优先使用知识库给出的易错点。
4. differentiation 明确基础、一般、进阶三类学生各自任务和教师支持，不能只是“多鼓励”“提高难度”。
5. assessment 给出学生能拿出来的证据、一次自评/互评方式和教师下一课要记录的具体信息。
7. 班级画像中的 common_problems 与 teacher_notes 表示群体层面的差异。把实际出现的音准、节奏、开口意愿、合作或注意力差异分别转成基础支持、核心任务、拓展任务；不臆测个人情况，也不只写“因材施教”。
8. classroom_setup 是设备白名单：各环节动作只可使用明确列出的设备；若写有“无电子设备”，安排清唱、哼鸣、拍手、跺脚或桌面声势，不得要求播放或投影。
6. teacher_requirements 是最高优先级：教师已有明确要求时，必须至少落实到两个相关环节或字段中。

【事实边界】
只能依据提供的歌曲资料、班级画像、知识库和教案骨架；禁止编造歌词、简谱或不存在的地方文化事实。
最终应是一份经过教学诊断和课堂决策的真实小学音乐教案：信息具体、有取舍、可执行，但不堆砌长段文字，更不是论文、理论分析或快速模式的扩写。
""" + contract

    user_payload = {
        "lesson": lesson,
        "evidence": evidence,
        "teacher_instruction": instruction,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def stream_lesson_json(base: dict, model: str | None = None, generation_strategy: str = "deep") -> Iterator[str]:
    instruction = (
        "快速模型生成一份内容完整、细节充分且按歌曲与班级个性化的课堂教案。"
        if generation_strategy == "fast"
        else "深度增强完整音乐教学方案，补足教师决策、课堂话术、学生任务与评价依据。"
    )
    selected_model = model or (get_settings().ai_fast_model if generation_strategy == "fast" else get_settings().ai_model)
    yield from _retry_stream(
        _build_messages(base, instruction, generation_strategy=generation_strategy),
        selected_model,
        generation_strategy,
    )


def stream_adjusted_lesson_json(
    content: dict, instruction: str, model: str | None = None
) -> Iterator[str]:
    yield from _retry_stream(_build_messages(content, instruction, adjustment=True), model)


def extract_lesson_brief(prompt: str, class_profile: dict | None = None) -> dict:
    """Extract explicit teacher constraints into a small reviewable draft."""
    system_prompt = """
你是小学音乐备课条件整理助手。把教师的自然语言整理成可核对的 JSON，不生成教案。
只输出 JSON 对象，字段固定为：
class_name（班级名称或 null）、song_name（歌曲名或 null）、duration_minutes（20到90之间的整数或 null）、
activity_preference（课堂偏好或 null）、region_element（教师明确提出的地区/文化元素或 null）、
equipment_constraints（教师明确说到的设备与限制数组；没有提及则空数组）、
teacher_requirements（其余明确的课堂要求，字符串）。
不得猜测教师没有说的歌曲、年级、课时、设备或地域元素。把“没投影”“没有音箱”等限制原样保留在设备约束里。
"""
    payload = {
        "teacher_message": prompt,
        "selected_class_profile": class_profile or {},
    }
    model = get_settings().ai_fast_model
    raw = "".join(_retry_stream(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        model,
        "fast",
    )).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start = raw.find("{")
    if start < 0:
        raise ValueError("模型未返回备课条件 JSON")
    try:
        result, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"备课条件格式无法解析：{exc.msg}") from exc
    if not isinstance(result, dict):
        raise ValueError("备课条件返回格式不是对象")
    result.setdefault("class_name", None)
    result.setdefault("song_name", None)
    result.setdefault("duration_minutes", None)
    result.setdefault("activity_preference", None)
    result.setdefault("region_element", None)
    result.setdefault("equipment_constraints", [])
    result.setdefault("teacher_requirements", "")
    if not isinstance(result["equipment_constraints"], list):
        result["equipment_constraints"] = [str(result["equipment_constraints"])]
    result["equipment_constraints"] = [str(value).strip() for value in result["equipment_constraints"] if str(value).strip()]
    if result["duration_minutes"] is not None:
        try:
            result["duration_minutes"] = max(20, min(90, int(result["duration_minutes"])))
        except (TypeError, ValueError):
            result["duration_minutes"] = None
    return result
