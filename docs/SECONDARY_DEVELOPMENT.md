# 宝拓小说二次开发指南

本文给出一个“从拉代码到改业务”的最短路径，重点是常见二开改造点与代码落点。

## 1. 本地启动（推荐先跑通）

```bash
# 在仓库根目录
cp .env.example .env

# 后端
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
# 新开一个终端，前端
cd frontend
npm install
npm run dev
```

默认地址：
- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

## 2. 目录速览（改功能时最常用）

- `backend/app/api/routers/`：HTTP 路由入口（先看这里找接口）
- `backend/app/services/`：核心业务逻辑（AI 流程、生成链路、规则）
- `backend/app/models/`：SQLAlchemy ORM 模型
- `backend/app/schemas/`：Pydantic 请求/响应结构
- `backend/app/db/`：数据库初始化、连接会话
- `backend/db/migrations/`：SQL 迁移脚本
- `frontend/src/api/`：前端接口封装
- `frontend/src/stores/`：Pinia 状态
- `frontend/src/views/` 和 `frontend/src/components/`：页面与组件

## 3. 一条完整二开链路（后端 + 前端）

以“新增一个项目配置字段”举例，建议按顺序改：

1. `backend/app/models/` 增加字段（数据库层）
2. `backend/app/schemas/` 暴露字段（API 契约）
3. `backend/app/services/` 写业务读写逻辑
4. `backend/app/api/routers/` 新增或扩展接口
5. `frontend/src/api/` 增加请求函数和类型
6. `frontend/src/stores/` 接入状态管理
7. `frontend/src/views/` / `components/` 完成页面交互

## 4. 数据库变更建议

新增字段/表时，至少做三件事：

1. 更新 `backend/app/models/` 中对应模型
2. 在 `backend/db/migrations/` 增加 SQL 迁移脚本
3. 如需兼容旧库，补充 `backend/app/db/init_db.py` 的兜底升级逻辑

项目同时支持 SQLite/MySQL，建表语句尽量避免只在单一数据库可用的语法。

## 5. 前端接口约定

- 统一入口在 `frontend/src/api/novel.ts`、`admin.ts`、`llm.ts`
- 开发环境默认请求 `http://127.0.0.1:8000`
- 生产环境默认走相对路径 `/api/...`
- 鉴权 token 在 `frontend/src/stores/auth.ts` 统一处理

## 6. Docker 二开调试

根目录执行：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

如果要在容器内启用 MySQL（本项目内置 profile）：

```bash
DB_PROVIDER=mysql docker compose -f deploy/docker-compose.yml --profile mysql up -d
```

## 7. 常见排查

- 报 `401`：先检查前端 `localStorage` 的 token 是否过期
- 报“未配置默认 LLM API Key”：检查 `.env` 的 `OPENAI_API_KEY`
- 报 JSON 解析错误：优先检查 Prompt 与模型是否稳定返回结构化内容
- 数据库字段不存在：确认迁移脚本已执行，且 `init_db` 兼容逻辑已覆盖旧库
