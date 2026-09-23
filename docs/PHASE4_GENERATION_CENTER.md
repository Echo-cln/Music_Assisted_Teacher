# Phase4 Generation Center

本阶段增强生成任务可追踪性。

## 新增

- GenerationJob记录实际使用模型
- GenerationJob记录生成策略
- 前端可展示任务来源与配置

## 设计原则

模型选择与业务教案结构解耦，生成结果仍进入固定Lesson Schema。
