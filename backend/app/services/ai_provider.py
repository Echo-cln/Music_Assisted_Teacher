"""模型无关的教案生成层。

规则层只提供数据库事实和课时约束。快速、深度两种模式使用不同的
教学写作任务，避免把同一份固定文案换一个模式名称返回给教师。
"""

import json
import ast
import re
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


def reply_to_lesson_dialogue(message: str, history: list[dict], context: dict) -> str:
    """Answer teacher questions in the lesson-planning conversation without mutating a lesson."""
    text = str(message or "").strip()
    asks_mode = (
        "模式" in text
        and any(word in text for word in ("还有", "什么", "哪些", "几种", "区别", "可以选"))
        and not any(word in text for word in ("调式", "调性", "曲式", "音阶"))
    )
    names_planning_mode = any(word in text for word in ("快速模式", "深度模式", "表单备课", "对话备课"))
    is_mode_question = asks_mode or (
        names_planning_mode and any(word in text for word in ("区别", "还有", "是什么", "怎么选"))
    )
    if is_mode_question:
        return (
            "目前教案生成有快速和深度两种，差别是生成所需时间，教案的内容完整度不应因此缩水。"
            "“表单备课”和“对话备课”是两种输入方式，不是额外的生成模式；对话备课可以直接问答、生成后继续提出修改。"
        )

    safe_history = []
    for item in (history or [])[-8:]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if content:
            safe_history.append({"role": item["role"], "content": content[:1200]})
    safe_context = context if isinstance(context, dict) else {}
    system_prompt = """你是教师身边一位亲切、靠谱的音乐教学搭档。这里是自然对话，不是客服工单或固定问答流程。本次调用只回答当前问题，不生成、保存或改写教案。

先听懂对方真正想问什么，再直接回应。教师聊到与教学无关的话题、随口提问或暂时换了话题都很正常：像熟悉的同事一样回答，不要责备、拒绝得生硬，也不要每次都把话题拽回备课。若问题需要实时信息而当前没有查到，坦率、简短地说明现在缺少什么，并给出自然的下一步；不要说“我不会用模型猜”，不要编造事实。

语气温和、清楚、自然，不要过度热情或使用幼稚的语气词。避免客服腔、训导口吻、模板化开场和重复道歉。问题简单就简短回答；复杂问题再解释。用户表达不满时先承认具体困扰，再处理问题，不要辩解。不要把每条消息都变成待办清单或追问；只有缺少关键信息时才问一个必要的问题。

理解连续上下文：短回复（包括数字、城市名）要承接上一轮的问题；若仍有歧义，再用一句话确认。用户纠正信息时，以最新说明为准，简短回应并修正。不要把普通问题误判为教案修改，也不要声称已经修改、生成或保存。

项目里的历史教案、课堂反馈、歌曲、资源、音频和编曲是数据库事实，只能引用本轮上下文明确提供的资料，尽量说清记录名称或日期；没检索到就自然说明没找到，不能编造来源、学生表现或分析结论。通用知识可以正常回答，不受项目检索结果限制。

例子：
教师：“天气怎么样？”——自然地问“你想查哪个城市？告诉我地名，我帮你看。”
教师：“我今天有点累。”——先回应关心，不要追问班级或切回教案。
教师：“为什么冬天唱歌前要做热身？”——直接用通俗语言回答，可简要说明嗓音和呼吸准备。

通常使用简洁中文，不要每轮列清单，不要重复教案全文，不输出 JSON 或 Markdown 表格。"""
    messages = [
        {"role": "system", "content": system_prompt},
        *safe_history,
        {
            "role": "user",
            "content": json.dumps(
                {"本轮问题": text, "当前备课上下文": safe_context},
                ensure_ascii=False,
            ),
        },
    ]
    answer = "".join(_retry_stream(messages, get_settings().ai_fast_model, "fast")).strip()
    answer = answer.strip(" \t\r\n\"'“”")
    if not answer:
        raise ValueError("对话模型没有返回回答正文")
    answer = _naturalize_dialogue_answer(answer)
    return answer[:1200]


def _naturalize_dialogue_answer(answer: str) -> str:
    """Remove accidental object dumps from model prose without inventing missing facts."""
    text = re.sub(r"^```(?:json|python)?\s*|\s*```$", "", str(answer or "").strip(), flags=re.IGNORECASE)
    labels = {
        "class_name": "班级", "song_name": "歌曲", "duration_minutes": "课时",
        "summary": "摘要", "teacher_requirements": "备课要求", "activity_preference": "课堂偏好",
        "equipment_constraints": "设备条件", "region_element": "地区元素",
    }

    def describe(value):
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                label = labels.get(str(key))
                if label and item not in (None, "", [], {}):
                    if isinstance(item, list):
                        item = "、".join(str(part) for part in item if not isinstance(part, (dict, list)))
                    if not isinstance(item, (dict, list)):
                        parts.append(f"{label}：{item}")
            return "；".join(parts) or "相关资料已列在下方来源中。"
        if isinstance(value, list):
            return "；".join(str(item) for item in value if isinstance(item, (str, int, float))) or "相关资料已列在下方来源中。"
        return str(value).strip()

    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = None
    if isinstance(parsed, (dict, list)):
        if isinstance(parsed, dict):
            for key in ("reply", "answer", "message", "response", "text", "content"):
                if isinstance(parsed.get(key), str) and parsed[key].strip():
                    return parsed[key].strip()
        return describe(parsed)

    # Some providers prepend a sentence and then accidentally paste a Python dict.
    # Scan balanced braces so nested JSON/Python objects are handled as one unit.
    output = []
    cursor = 0
    while cursor < len(text):
        start = text.find("{", cursor)
        if start < 0:
            output.append(text[cursor:])
            break
        output.append(text[cursor:start])
        depth, quote, escaped, end = 0, None, False, None
        for index in range(start, min(len(text), start + 4000)):
            char = text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            output.append(text[start])
            cursor = start + 1
            continue
        raw = text[start:end]
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            try:
                value = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                output.append(raw)
            else:
                output.append(describe(value) if isinstance(value, (dict, list)) else raw)
        else:
            output.append(describe(value) if isinstance(value, (dict, list)) else raw)
        cursor = end
    text = "".join(output)
    text = re.sub(r"\s+", " ", text).strip(" ：:，,；;")
    return text or "我找到了一些相关内容，已经整理在下方来源里。你可以告诉我想先看哪一条。"
