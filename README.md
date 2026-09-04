# SmsMCPHub

<p align="right"><a href="#english">English</a> | <a href="#中文">中文</a></p>

<a id="english"></a>

## English

> SmsMCPHub enables MCP-compatible agent frameworks—such as Codex and Claude Code—to send and receive mobile SMS messages via MCP, thereby fully automating workflows that rely on SMS. It utilizes SQLite for data persistence and employs FastMCP to provide a unified query interface.

SmsMCPHub is a decoupled SMS ingestion gateway for agents. It accepts messages
from phone-side or cloud forwarding providers such as
[SmsForwarder](https://github.com/pppscn/SmsForwarder), normalizes them into a
stable message model, stores them in SQLite, and exposes read-only query tools
through FastMCP.

### Quick start

#### 1. Install the agent skill

The only required manual installation step is to install the `smsmcphub` skill.
It teaches the agent the available SMS capabilities and can then deploy the
server, register MCP, detect the LAN address, and guide Provider setup.

Requirements: a Codex-compatible client and Git. Clone the repository if it is
not already present, then copy the skill into the Codex user skill directory:

```powershell
git clone https://github.com/PoilZero/SmsMCPHub.git
cd SmsMCPHub
Copy-Item -Recurse -Force .\skills\smsmcphub `
  "$env:USERPROFILE\.codex\skills\smsmcphub"
```

Restart Codex or start a new session, then ask the agent to install and configure
SmsMCPHub. Do not manually start the server or register MCP unless the skill
reports a setup problem.

#### 2. Let the skill configure the server and Provider

Ask the agent for a local setup, for example:

```text
Install and configure SmsMCPHub for a phone on my private Wi-Fi network.
```

The skill will install the locked dependencies, create `.env` only when needed,
start the server, verify `/healthz`, register the Streamable HTTP MCP endpoint,
report the exact LAN URLs, and guide the SmsForwarder Webhook configuration.

When prompted for the phone Provider, use its HTTP Webhook channel:

Install or open [SmsForwarder](https://github.com/pppscn/SmsForwarder), then add
an HTTP Webhook forwarding channel. In the SmsForwarder UI, these fields may be
named `WebServer`, `Webhook URL`, `WebParams`, or similar:

The provider's reference is the [SmsForwarder Webhook guide](https://github.com/pppscn/SmsForwarder/wiki/%E9%99%84%E5%BD%951%EF%BC%9A%E5%90%91webhook%E5%8F%91%E9%80%81post-get-put-patch%E8%AF%B7%E6%B1%82).

```text
Method:  POST
URL:     http://<COMPUTER_LAN_IP>:8000/api/v1/providers/smsforwarder/webhook
WebParams: leave empty for the first test
```

Create or enable a rule for received SMS messages and select this Webhook
channel. Keep the phone and computer on the same Wi-Fi network. The skill will
provide the actual LAN IP and final URL for this step.

With empty `WebParams`, SmsForwarder sends its default form fields `from`,
`content`, `timestamp`, and optional `sign`. SmsMCPHub parses these fields
directly. SmsForwarder can also send a custom JSON template; the adapter accepts
common aliases and configurable JSON paths.

For a protected setup, configure the same secret in SmsForwarder and restart
SmsMCPHub with:

```powershell
$env:SMSFORWARDER_SECRET = "replace-with-the-same-secret"
uv run smsmcphub
```

SmsMCPHub then validates SmsForwarder's HMAC-SHA256 timestamp signature. Use
HTTPS or a private network/VPN for anything beyond a local test.

#### 3. Verify the service and the message path

Check the service from the computer:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

Check the same URL from the phone browser using the computer LAN address:

```text
http://<COMPUTER_LAN_IP>:8000/healthz
```

You can simulate SmsForwarder before sending a real SMS:

```powershell
$body = @{
  from = "10086"
  content = "SmsMCPHub test 123456"
}

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/providers/smsforwarder/webhook" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body $body
```

Expected response:

```json
{
  "accepted": true,
  "message_ids": ["msg_..."],
  "duplicates": 0
}
```

After sending a real SMS, query the HTTP API:

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/messages?keyword=SmsMCPHub" |
  ConvertTo-Json -Depth 8
```

Run the MCP smoke test from the project directory:

```powershell
@'
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools])
        result = await client.call_tool(
            "sms_search",
            {"keyword": "SmsMCPHub", "limit": 10},
        )
        print(result.content[0].text)
        print(result.data)

asyncio.run(main())
'@ | uv run python -
```

The tool list should contain:

```text
sms_search
sms_get
sms_latest
sms_conversations
```

#### 4. Verify MCP or use the manual fallback

The skill normally registers MCP automatically. The server uses Streamable HTTP
at `/mcp`. On the same computer, use
`127.0.0.1`; from another agent host on the LAN, use the computer's LAN IP.

If the skill cannot register the client, use the manual commands below.

**Codex CLI / Codex app / IDE extension**

Reference: [Codex MCP documentation](https://developers.openai.com/codex/mcp).

Add the server with the Codex CLI:

```powershell
codex mcp add smsmcphub --url http://127.0.0.1:8000/mcp
codex mcp list
```

The equivalent `config.toml` entry is:

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
```

If `SMSMCPHUB_MCP_TOKEN` is configured on the server, use a bearer token
environment variable instead of putting the token directly in the file:

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
bearer_token_env_var = "SMSMCPHUB_MCP_TOKEN"
```

Codex reads this configuration from `~/.codex/config.toml`; a trusted project
may also use a project-scoped `.codex/config.toml`. After adding the server,
restart the Codex client or use `/mcp` to inspect the active tools.

**Claude Code (`cc`)**

Reference: [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

```powershell
claude mcp add --transport http smsmcphub http://127.0.0.1:8000/mcp
claude mcp list
```

Inside a Claude Code session, use `/mcp` to check the connection and tool list.
For a project-scoped configuration:

```powershell
claude mcp add --transport http --scope project `
  smsmcphub http://127.0.0.1:8000/mcp
```

The project configuration is stored in `.mcp.json`:

```json
{
  "mcpServers": {
    "smsmcphub": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

With MCP authentication enabled, add an Authorization header through Claude
Code's `--header` option instead of committing the token to `.mcp.json`.

### Core architecture

```text
SmsForwarder / phone or cloud provider
                    |
                    | HTTP Webhook
                    v
              FastAPI Ingress
                    |
                    v
             Provider Adapter
                    |
                    v
          Canonical Message Model
                    |
                    v
                SQLite Store
                    |
          +---------+----------+
          |                    |
          v                    v
     HTTP API             FastMCP Server
                               |
                               v
                 SmsMCPHub Agent Skill (optional)
                               |
                               v
                             Agent
```

The inbound path and the agent path share the domain service but not provider
protocol details:

- **FastAPI Ingress** receives the raw request, verifies the provider, and
  returns an acknowledgement only after the message has been persisted.
- **Provider Adapter** validates and parses provider-specific form or JSON
  payloads. The SmsForwarder adapter supports default form fields, custom JSON,
  aliases, simple JSON paths, and HMAC-SHA256 signatures.
- **Canonical Message Model** gives every source the same fields: sender,
  recipient, body, receive time, source, conversation, status, metadata, and
  deduplication key.
- **Message Service** normalizes phone numbers, creates conversation IDs,
  applies idempotency, and provides the shared query operations.
- **SQLite Repository** stores messages with indexes for time, sender,
  recipient, and conversation queries. Repeated provider events are accepted as
  idempotent successes.
- **FastMCP Server** exposes only the stable domain contract and does not know
  SmsForwarder's raw field names.
- **SmsMCPHub Agent Skill** adds intent routing and setup guidance. It is
  optional: the MCP server remains usable directly by any compatible client.

### MCP tools

| Tool | Purpose | Main inputs |
|---|---|---|
| `sms_search` | Search messages with filters and pagination | sender, recipient, keyword, time range, status, limit, cursor |
| `sms_get` | Fetch one complete message | message ID |
| `sms_latest` | Return the newest matching message | sender, keyword, time window |
| `sms_conversations` | List conversation summaries | limit, cursor |

Search and latest results return compact message summaries to keep agent context
small. `sms_get` returns the complete canonical message, including metadata.
MVP v1 intentionally exposes read-only operations; sending, replying, deleting,
and long-lived watches are not enabled.

### HTTP API

```text
GET  /healthz
POST /api/v1/providers/{provider_id}/webhook
GET  /api/v1/messages/{message_id}
GET  /api/v1/messages
POST /mcp   (Streamable HTTP MCP endpoint)
```

The default provider ID is `smsforwarder`, so the standard Webhook URL is:

```text
http://<COMPUTER_LAN_IP>:8000/api/v1/providers/smsforwarder/webhook
```

### Implementation and tests

The implementation is a modular monolith built with:

- Python 3.11+
- FastAPI and Uvicorn for HTTP
- FastMCP Streamable HTTP for agent access
- Pydantic for validated domain and tool schemas
- SQLite with Python's standard `sqlite3` driver
- `uv` for reproducible environments and locked dependencies

Run the checks with:

```powershell
uv run pytest -q
uv run ruff check src tests
uv run python -m compileall -q src tests
```

The test suite covers SmsForwarder form and JSON payloads, field mapping,
signature validation, replay rejection, idempotent ingestion, pagination,
conversation aggregation, FastAPI endpoints, MCP discovery, structured results,
and MCP token protection.

### Security notes

The default development setup has no provider secret and no MCP token so that a
same-network smoke test is easy. Before exposing the service outside a trusted
LAN, configure `SMSFORWARDER_SECRET` and `SMSMCPHUB_MCP_TOKEN`, use HTTPS or a
VPN, restrict the firewall, and keep raw payload storage disabled unless it is
needed for debugging.

<p align="right"><a href="#english">Back to language switch</a> | <a href="#中文">中文</a></p>

<a id="中文"></a>

## 中文

> SmsMCPHub 让Codex、Claude Code 等任意支持MCP的Agent框架通过MCP收发移动设备的短信消息等，以全自动各种需要短信的工作流。通过SQLite持久化，并使用FastMCP提供统一查询接口。

SmsMCPHub 是一个面向 Agent 的解耦短信接入网关。它兼容
[SmsForwarder](https://github.com/pppscn/SmsForwarder) 等手机端或云端转发
服务，将消息转换为稳定的统一模型，保存到 SQLite，并通过 FastMCP 提供只
读查询工具。

### 快速使用

#### 1. 安装 Agent Skill

用户唯一需要手动安装的是 `smsmcphub` Skill。它会告诉 Agent 有哪些短信能
力，并在后续自动部署 Server、注册 MCP、探测局域网 IP 和引导 Provider 配置。

依赖：支持 Codex Skill 的 Agent 和 Git。仓库不存在时先克隆，然后将 Skill 复制
到当前 Codex 用户目录：

```powershell
git clone https://github.com/PoilZero/SmsMCPHub.git
cd SmsMCPHub
Copy-Item -Recurse -Force .\skills\smsmcphub `
  "$env:USERPROFILE\.codex\skills\smsmcphub"
```

重启 Codex 或新建会话，然后直接让 Agent 安装和配置 SmsMCPHub。除非 Skill 报告
问题，否则不需要手动启动 Server 或注册 MCP。

#### 2. 让 Skill 配置 Server 和 Provider

可以这样向 Agent 发起安装请求：

```text
请为同一 Wi-Fi 下的手机安装并配置 SmsMCPHub。
```

Skill 会安装锁定依赖、在需要时创建 `.env`、启动 Server、检查 `/healthz`、注册
Streamable HTTP MCP、输出准确的局域网 URL，并引导 SmsForwarder Webhook 配置。

Agent 要求配置手机 Provider 时，选择 HTTP Webhook：

安装或打开 [SmsForwarder](https://github.com/pppscn/SmsForwarder)，新增
HTTP Webhook 转发通道。不同版本的界面可能叫 `WebServer`、`Webhook URL`、
`WebParams` 或类似名称：

官方配置参考：[SmsForwarder Webhook 文档](https://github.com/pppscn/SmsForwarder/wiki/%E9%99%84%E5%BD%951%EF%BC%9A%E5%90%91webhook%E5%8F%91%E9%80%81post-get-put-patch%E8%AF%B7%E6%B1%82)。

```text
请求方式：POST
URL：     http://<电脑局域网IP>:8000/api/v1/providers/smsforwarder/webhook
WebParams：第一次测试时留空
```

新增或启用“接收短信”转发规则，并选择这个 Webhook 通道。手机和电脑必须连
接同一个 Wi-Fi。具体局域网 IP 和最终 URL 由 Skill 输出。

当 `WebParams` 留空时，SmsForwarder 默认发送表单字段 `from`、`content`、
`timestamp` 和可选的 `sign`。SmsMCPHub 已经直接兼容这些字段。SmsForwarder
也支持自定义 JSON 模板，适配器同时支持常见字段别名和可配置的简单 JSON 路径。

如果需要启用签名，请在 SmsForwarder 中配置 secret，并使用相同的 secret 重启
SmsMCPHub：

```powershell
$env:SMSFORWARDER_SECRET = "替换为相同的密钥"
uv run smsmcphub
```

SmsMCPHub 会校验 SmsForwarder 的 HMAC-SHA256 时间戳签名。除本地测试外，建议使
用 HTTPS 或私有网络/VPN。

#### 3. 验证服务和消息链路

在电脑上检查服务：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

预期返回：

```json
{"status":"ok"}
```

在手机浏览器中使用电脑局域网 IP 打开相同地址：

```text
http://<电脑局域网IP>:8000/healthz
```

发送真实短信前，可以先模拟 SmsForwarder：

```powershell
$body = @{
  from = "10086"
  content = "SmsMCPHub test 123456"
}

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/providers/smsforwarder/webhook" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body $body
```

预期返回：

```json
{
  "accepted": true,
  "message_ids": ["msg_..."],
  "duplicates": 0
}
```

发送真实短信后，可以通过 HTTP API 查询：

```powershell
Invoke-RestMethod `
  "http://127.0.0.1:8000/api/v1/messages?keyword=SmsMCPHub" |
  ConvertTo-Json -Depth 8
```

在项目目录运行 MCP 冒烟测试：

```powershell
@'
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        tools = await client.list_tools()
        print([tool.name for tool in tools])
        result = await client.call_tool(
            "sms_search",
            {"keyword": "SmsMCPHub", "limit": 10},
        )
        print(result.content[0].text)
        print(result.data)

asyncio.run(main())
'@ | uv run python -
```

工具列表应包含：

```text
sms_search
sms_get
sms_latest
sms_conversations
```

#### 4. 验证 MCP 或使用手动兜底

Skill 通常会自动注册 MCP。服务使用 `/mcp` 提供 Streamable HTTP。Agent 和服务在
同一台电脑时使用
`127.0.0.1`；如果 Agent 在局域网另一台机器上运行，则使用电脑的局域网 IP。

只有 Skill 无法注册客户端时，才使用下面的手动命令。

**Codex CLI / Codex 应用 / IDE 扩展**

官方参考：[Codex MCP 文档](https://developers.openai.com/codex/mcp)。

使用 Codex CLI 添加：

```powershell
codex mcp add smsmcphub --url http://127.0.0.1:8000/mcp
codex mcp list
```

等价的 `config.toml` 配置：

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
```

如果服务端配置了 `SMSMCPHUB_MCP_TOKEN`，使用环境变量传递 Bearer Token，不要
把 token 直接写进配置文件：

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
bearer_token_env_var = "SMSMCPHUB_MCP_TOKEN"
```

Codex 默认从 `~/.codex/config.toml` 读取配置；受信任的项目也可以使用项目级
`.codex/config.toml`。添加后重启 Codex，或使用 `/mcp` 查看已连接的工具。

**Claude Code（`cc`）**

官方参考：[Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)。

```powershell
claude mcp add --transport http smsmcphub http://127.0.0.1:8000/mcp
claude mcp list
```

在 Claude Code 会话中使用 `/mcp` 检查连接和工具列表。项目级配置可以这样添加：

```powershell
claude mcp add --transport http --scope project `
  smsmcphub http://127.0.0.1:8000/mcp
```

项目级配置会保存到 `.mcp.json`：

```json
{
  "mcpServers": {
    "smsmcphub": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

启用 MCP 鉴权后，使用 Claude Code 的 `--header` 选项传递 Authorization，不要
把 token 提交到 `.mcp.json`。

### 核心架构

```text
SmsForwarder / 手机或云端 Provider
                    |
                    | HTTP Webhook
                    v
              FastAPI 接入层
                    |
                    v
              Provider 适配器
                    |
                    v
                统一消息模型
                    |
                    v
                  SQLite
                    |
          +---------+----------+
          |                    |
          v                    v
       HTTP API             FastMCP Server
                               |
                               v
                 SmsMCPHub Agent Skill（可选）
                               |
                               v
                             Agent
```

接收链路和 Agent 链路共享领域服务，但不共享 Provider 的原始协议细节：

- **FastAPI 接入层**接收原始请求、完成 Provider 校验，并在消息持久化成功后返回
  确认响应。
- **Provider 适配器**负责解析 Provider 特有的表单或 JSON。SmsForwarder 适配器支
  持默认表单、自定义 JSON、字段别名、简单 JSON 路径和 HMAC-SHA256 签名。
- **统一消息模型**为所有来源提供相同字段：发送人、接收人、正文、接收时间、来
  源、会话、状态、元数据和幂等键。
- **Message Service**负责号码规范化、会话 ID、幂等处理和统一查询操作。
- **SQLite Repository**保存消息，并为时间、发送人、接收人和会话查询建立索引。
  重复 Provider 事件按幂等成功处理。
- **FastMCP Server**只暴露稳定的领域契约，不了解 SmsForwarder 的原始字段名。
- **SmsMCPHub Agent Skill**提供意图路由和安装配置引导。它是可选层，任何兼容 MCP
  的客户端仍然可以直接使用 Server。

### MCP 工具

| 工具 | 用途 | 主要输入 |
|---|---|---|
| `sms_search` | 按条件分页搜索短信 | sender、recipient、keyword、时间范围、status、limit、cursor |
| `sms_get` | 获取一条完整短信 | message ID |
| `sms_latest` | 获取时间窗口内最新匹配短信 | sender、keyword、时间窗口 |
| `sms_conversations` | 列出会话摘要 | limit、cursor |

`sms_search` 和 `sms_latest` 返回精简消息摘要，减少 Agent 上下文占用；需要完整
字段时使用 `sms_get`。MVP v1 只提供只读能力，暂不支持发送、回复、删除和长期
监听。

### HTTP API

```text
GET  /healthz
POST /api/v1/providers/{provider_id}/webhook
GET  /api/v1/messages/{message_id}
GET  /api/v1/messages
POST /mcp   (Streamable HTTP MCP endpoint)
```

默认 Provider ID 是 `smsforwarder`，所以标准 Webhook 地址是：

```text
http://<电脑局域网IP>:8000/api/v1/providers/smsforwarder/webhook
```

### 实现和测试

项目采用模块化单体，技术栈为：

- Python 3.11+
- FastAPI 和 Uvicorn 提供 HTTP 服务
- FastMCP Streamable HTTP 提供 Agent 接入
- Pydantic 提供领域模型和工具 Schema 校验
- Python 标准库 `sqlite3` 驱动 SQLite
- `uv` 管理可复现环境和锁定依赖

运行检查：

```powershell
uv run pytest -q
uv run ruff check src tests
uv run python -m compileall -q src tests
```

测试覆盖 SmsForwarder 表单和 JSON、字段映射、签名校验、重放拒绝、幂等入库、分
页、会话聚合、FastAPI 接口、MCP 工具发现、结构化结果和 MCP Token 鉴权。

### 安全说明

默认开发配置不启用 Provider secret 和 MCP Token，便于同一网络下快速测试。对外
暴露服务前，请配置 `SMSFORWARDER_SECRET` 和 `SMSMCPHUB_MCP_TOKEN`，使用 HTTPS
或 VPN，限制防火墙范围，并保持原始 payload 保存关闭，除非确实需要排查问题。

<p align="right"><a href="#english">English</a> | <a href="#中文">返回顶部</a></p>
