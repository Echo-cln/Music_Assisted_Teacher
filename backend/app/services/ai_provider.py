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
timeline 项数必须等于输入 lesson；每项只含 teacher 与 students 两个非空字符串。不要输出 summary、minutes、stage、generation_context。总正文控制在 2500 个汉字以内，JSON 结束后立即停止。
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
你是一名乡村小学音乐教研员。现在执行“快速成课”任务：在给定事实与课时框架内，产出一份简明、完整、可立即上课的音乐教案。

只输出一个合法 JSON 对象：不要 Markdown、不要解释、不要 generation_context。

快速模式只压缩篇幅，不改变教案的教学判断、事实边界、阶段顺序、目标、活动和评价含义：
1. 每个 timeline.teacher 和 timeline.students 各写 1—2 句，直接交代动作、任务和一句可用课堂话语；避免长段落。
2. objectives、重点难点、乐理、易错纠正、分层和评价都必须保留，不能因为快速模式而省略任何一个字段或必要信息。
3. 只删除重复表述、备用方案和冗长修饰，不得将“深度模式”改成另一套教学方案。
4. 只能使用提供的歌曲、班级和知识库事实；不得编造歌词、简谱或地方文化事实。
""" + contract
    else:
        # 深度模式是一次完整的“诊断→决策→落地”生成，而不是快速骨架的扩写版。
        system_prompt = """
你是一名具有多年乡村小学音乐教学经验的优秀音乐教研员。
根据班级画像、歌曲资料、知识库和教师补充要求，写出一份能直接带进课堂的教案。先选定一个最需要优先解决的学习问题，再把决定落实到目标、活动和评价中。

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
        "快速完成一份清晰、可直接执行的课堂教案。"
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
