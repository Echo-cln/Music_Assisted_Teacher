# 本机混音人声分离

## 为什么要换

当前逐音评测把“参考混音是否可用”交给 Demucs 的 `htdemucs` 二轨模式。若人声没有分离干净，后续基频和 DTW 无法得到可信参考。本次为混音参考增加了 Audio Separator / BS-RoFormer 路径；已安装时优先使用它，未安装时保留原有 Demucs 路径。分离失败会记录模型与进程错误，并停止逐音评分，不会用混音直接冒充人声。

## Windows 安装

从项目根目录双击 `setup_audio_separator.bat`。该脚本会在 `.audio-separator-venv` 建立单独的 Python 环境，不改主项目的 `.venv`，避免 torch / NumPy 依赖影响 FastAPI、librosa 和现有测试。

默认模型为 `model_bs_roformer_ep_317_sdr_12.9755.ckpt`。首次用混音做人声分离时，模型会自动下载并缓存；因此首次处理需要联网，CPU 也可能耗时较久。后续会复用模型文件。

## 可选配置

可在 `backend/.env` 指定：

```dotenv
AUDIO_SEPARATOR_MODEL=model_bs_roformer_ep_317_sdr_12.9755.ckpt
# 如果可执行文件不在项目根目录 .audio-separator-venv 中，再填完整路径：
# AUDIO_SEPARATOR_COMMAND=E:\\audio-separator-venv\\Scripts\\audio-separator.exe
```

一般不需要填写 `AUDIO_SEPARATOR_COMMAND`，后端会自动检查项目根目录的隔离环境。

## 测试与判断

1. 安装后重启 `run.bat` 启动的后端。
2. 在音频分析页选择“单人练唱逐音评测”与“原唱 / 伴奏混音”，上传混音参考及练唱录音。
3. 首次运行等待权重下载；任务状态完成后，结果应显示“RoFormer/UVR 已分离参考人声”，并出现红色参考波形和蓝色练唱波形。
4. 若分离失败，结果显示不可评分原因；后端终端会记录 `audio_separator_failed` 的详细模型/设备日志。

`audio-separator` 的 Python 包仓库采用 MIT 许可证，并对 UVR 贡献者要求署名；每个预训练权重仍应按其来源和许可单独确认。本项目不会把模型权重打包进仓库。

## 上游资料

- [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator)：Python API、RoFormer/MDX/VR/Demucs 模型、CPU 安装方式。
- [BS-RoFormer 模型清单与使用示例](https://github.com/nomadkaraoke/python-audio-separator#as-a-dependency-in-a-python-project)。
- [Demucs 上游说明](https://github.com/facebookresearch/demucs)：上游明确说明该仓库已不再维护，因此当前只保留为未安装新分离器时的旧路径。

混音分离的效果受伴奏密度、混响、人声叠唱、压缩和母带处理影响；单次接入不能保证每首商业母带都分离成功。要确认你这条录音是否改善，需要在你的 Windows 机器安装模型后跑真实样本。
