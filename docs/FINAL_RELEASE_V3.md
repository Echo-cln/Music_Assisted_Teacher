# 乡音智谱 Final V3 Release

## 本版本目标

在 Phase4 基础上完成 AI 教学引擎整合版本。

## 已整合能力

- 模型无关 LLM Adapter 架构
- OpenAI Compatible 模型接入方式
- JSON/Markdown 返回解析兼容
- 教案固定 Schema 方向
- AI 模型配置中心基础
- Generation Job 任务管理基础
- 教师侧 AI 引擎配置方向

## 设计原则

模型负责生成内容，系统负责保证教学数据结构稳定。

不同模型输出最终统一进入教案结构，不允许模型改变前端业务协议。

## 部署前检查

1. 配置 backend/.env
2. 初始化数据库
3. 导入知识库
4. 启动后端和前端
5. 使用 demo 账号验证生成流程

