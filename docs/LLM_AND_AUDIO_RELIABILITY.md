# 本轮可靠性修复说明

## 深度思考生成

此前的失败由两类问题叠加造成：

1. `glm-5.3-flash` 会先产生 reasoning token。深度模式默认 `high`、正文预算仅 12288，再加上过长的隐藏四步提示，可能在正文前触发 `finish_reason=length`。
2. 后端把模型合法的对象形式 `assessment`（例如含 evidence、peer、next）当成字符串类型错误，导致完整教案也被拒绝。

本次修改：

- 深度模型默认改为 `AI_REASONING_EFFORT=low`，`AI_MAX_TOKENS=32768`；保留 GLM thinking，但优先保证返回正文。
- 压缩深度提示与输出协议：只要求 10 个字段、5 个既定流程、2500 汉字内 JSON，不再诱导模型输出冗长隐藏推理。
- 对 `assessment`、目标/分层的字符串或数组、乐理/易错练习的对象或文本进行真实内容归一化，再严格校验。缺字段、空字段、流程数量不对仍然失败，不会用规则骨架伪装成功。
- 失败状态继续保存供应商、SSE、finish reason 等非敏感诊断。

`.env` 应使用：

```ini
AI_MODEL=glm-5.3-flash
AI_REASONING_EFFORT=low
AI_MAX_TOKENS=32768
AI_FAST_MODEL=doubao-seed-2-0-mini-260428
AI_FAST_MAX_TOKENS=8192
```

若仍看到 `finish_reason=length`，请保留错误详情并将 `AI_MAX_TOKENS` 调到 `49152` 后复测；不要改为高/max reasoning effort。

## 声音与 SF2

- 每条轨道独立加载采样。坏 SF2 或 CDN 请求失败只让这一条回落为本地 WebAudio 试听，不会静音整首、多轨或电子钢琴。
- SF2 在绑定前先解析；`Cannot read properties ... [1]` 会变成明确的文件兼容提示。当前 browser parser 是 `soundfont2 0.x`，其上游明确说明并非完全符合 SF2 规范，某些包会解析错误。
- 混音原唱逐音评测依赖 Demucs。它没有安装时，系统只给一张“未给分”的卡片，说明不能可靠分离；不会再输出两个重复错误或假 0 分。

在目标电脑的项目根目录安装分离组件：

```bat
.venv\Scripts\python.exe -m pip install -r backend\requirements-audio-pro.txt
```

首次分离会下载 Demucs 权重，需要联网并等待；请用 20–40 秒的参考主唱和同旋律练唱做测试。

## 课堂整体分析

没有参考主旋律时，系统只能分析录音中的音高稳定、起音、能量和可用人声比例，不能断言“学生跑调”。报告会把最弱的实际时间段、对应数字证据和下一步排练动作放在“本次优先动作”中；每次最多三条，避免通用建议堆叠。
