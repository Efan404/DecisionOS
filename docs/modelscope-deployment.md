# ModelScope 部署文档

## 概述

本文档记录 DecisionOS 在魔搭创空间（ModelScope Docker Studio）的部署配置。

## 分支

- **GitHub 分支**: `dev/modelscope`
- **ModelScope 仓库**: https://www.modelscope.cn/studios/efan404/Decision-OS

## 部署步骤

### 1. 推送代码到 ModelScope

```bash
# 克隆 ModelScope 仓库
git clone http://oauth2:<TOKEN>@www.modelscope.cn/studios/efan404/Decision-OS.git

# 复制项目文件（从 GitHub dev/modelscope 分支）
cp -r /path/to/pm-cursor/backend /path/to/pm-cursor/frontend .
cp /path/to/pm-cursor/Dockerfile .
cp /path/to/pm-cursor/supervisord.conf .
cp /path/to/pm-cursor/ms_deploy.json .
cp /path/to/pm-cursor/package.json /path/to/pm-cursor/pnpm-lock.yaml .
cp /path/to/pm-cursor/next.config.mjs /path/to/pm-cursor/postcss.config.mjs .

# 提交并推送
git add .
git commit -m "Add DecisionOS"
git push
```

### 2. 配置文件

#### ms_deploy.json

```json
{
  "$schema": "https://modelscope.cn/api/v1/studios/deploy_schema.json",
  "sdk_type": "docker",
  "resource_configuration": "platform/2v-cpu-16g-mem",
  "port": 7860,
  "environment_variables": [
    {
      "name": "DECISIONOS_SEED_ADMIN_USERNAME",
      "value": "admin"
    },
    {
      "name": "DECISIONOS_SEED_ADMIN_PASSWORD",
      "value": "admin123"
    }
  ]
}
```

### 3. 环境变量

在 ModelScope 创空间设置页面配置：

| 变量名                         | 值       | 必填                      |
| ------------------------------ | -------- | ------------------------- |
| DECISIONOS_SEED_ADMIN_USERNAME | admin    | 是                        |
| DECISIONOS_SEED_ADMIN_PASSWORD | admin123 | 是                        |
| LLM_MODE                       | mock     | 建议（避免 LLM 调用错误） |

### 4. 部署

1. 访问 https://www.modelscope.cn/studios/efan404/Decision-OS
2. 进入「设置」页面
3. 配置环境变量
4. 点击「上线」或「重新部署」

## 已知问题

### 1. LLM 调用错误 (500 Internal Server Error)

**错误信息:**

```
pydantic_core._pydantic_core.ValidationError: 14 validation errors for ScopeOutput
in_scope.0 Input should be a valid dictionary or instance of InScopeItem [type=model_type, input_value='AI-driven bug prediction', input_type=str]
```

**原因:** LLM 返回的是字符串，但 Pydantic 期望对象格式。

**临时解决方案:** 设置环境变量 `LLM_MODE=mock`

### 2. Authorization Header 被占用

**问题:** 魔搭平台占用 `Authorization` HTTP Header。

**解决方案:** 代码已修改为使用 `X-App-Token` 自定义 Header。

## 文件变更

### 新增文件

- `Dockerfile` - 单容器构建配置
- `supervisord.conf` - 进程管理配置
- `ms_deploy.json` - ModelScope 部署配置

### 修改文件

| 文件                         | 变更                        |
| ---------------------------- | --------------------------- |
| `backend/app/core/auth.py`   | 使用 `X-App-Token` Header   |
| `backend/app/routes/auth.py` | logout 使用 `X-App-Token`   |
| `frontend/lib/api.ts`        | 发送 `X-App-Token` Header   |
| `next.config.mjs`            | 添加 `output: 'standalone'` |

## 本地测试

```bash
# 构建
docker build -t decisionos .

# 运行
docker run -d -p 7860:7860 \
  -e DECISIONOS_SEED_ADMIN_USERNAME=admin \
  -e DECISIONOS_SEED_ADMIN_PASSWORD=admin123 \
  -e LLM_MODE=mock \
  decisionos

# 访问
open http://localhost:7860
```

## 架构

```
浏览器 → 7860 (Next.js) → rewrite /api-proxy/* → 8000 (FastAPI)
```

- Next.js 监听 7860 端口（对外）
- FastAPI/uvicorn 监听 8000 端口（内部）
- Next.js 作为反向代理转发 API 请求

## 端口说明

| 端口 | 用途                        |
| ---- | --------------------------- |
| 7860 | 对外暴露（ModelScope 要求） |
| 8000 | FastAPI 内部                |
| 8080 | 禁用（平台占用）            |

## Supervisor 进程管理

由于单容器需要同时运行 Next.js 和 FastAPI，使用 `supervisord` 作为进程管理器。

### supervisord.conf 配置

```ini
[supervisord]
nodaemon=true
loglevel=info
logfile=/dev/null
logfile_maxbytes=0

[program:uvicorn]
command=uvicorn app.main:app --host 127.0.0.1 --port 8000
directory=/home/user/app/backend
autostart=true
autorestart=true
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0

[program:nextjs]
command=node server.js
directory=/home/user/app/frontend
environment=PORT="7860",HOSTNAME="0.0.0.0"
autostart=true
autorestart=true
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0
```

### 工作原理

1. **supervisord** 作为 PID 1 启动
2. **uvicorn** 进程：运行 FastAPI 后端，监听 127.0.0.1:8000
3. **nextjs** 进程：运行 Next.js 服务，监听 0.0.0.0:7860
4. Next.js 通过内部 rewrite 将 `/api-proxy/*` 请求转发到 uvicorn
5. 所有日志输出到 stdout/stderr，供 `docker logs` 捕获

### 关键点

- `nodaemon=true`：supervisord 必须运行在前台（PID 1）
- `autostart=true` + `autorestart=true`：进程崩溃自动重启
- `directory` 指定正确的工作目录
- Next.js 使用 `environment` 设置 PORT 和 HOSTNAME

## 相关文档

- [魔搭创空间快速部署](https://modelscope.cn/docs/studio/Deploy_QuickStart)
- [Docker 创空间介绍](https://modelscope.cn/docs/studio/Docker_Studio_Intro)
