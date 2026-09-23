# 2026-09-23 架构升级记录

## 1. 多教师账号

新增 `Teacher`、`AuthSession`；支持注册、登录、退出、`/api/auth/me`。所有个人教学数据按 `teacher_id` 隔离。

## 2. 可在页面直接扩充知识库

`/api/resources/{kind}` 增加 POST / DELETE；系统资源只读，个人资源可新增、编辑、删除，也可从系统资源复制。

## 3. AI 后台生成任务

新增 `GenerationJob` 与 `/api/generation-jobs`。生成任务不再绑定当前 DOM 页面，切换页面仍继续执行。

## 4. 生成体验优化

先展示规则生成教案骨架，再由 GLM 异步增强。全局状态卡展示可验证的处理阶段，而非模型隐藏思维链。

## 5. GLM Token 优化

`generation_context` 作为只读依据发送给模型，但不要求模型重复输出；后端在验证阶段重新挂回数据库依据。
