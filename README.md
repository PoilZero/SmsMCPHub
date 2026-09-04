# SmsMCPHub

<p align="right"><a href="#english">English</a> | <a href="#中文">中文</a></p>

<a id="english"></a>

## English

> SmsMCPHub enables MCP-compatible agent frameworks—such as Codex and Claude Code—to send and receive mobile SMS messages via MCP, thereby fully automating workflows that rely on SMS. It utilizes SQLite for data persistence and employs FastMCP to provide a unified query interface.

SmsMCPHub is a decoupled SMS gateway for agents. It accepts messages from
phone-side or cloud providers such as
[SmsForwarder](https://github.com/pppscn/SmsForwarder), normalizes them, stores
them in SQLite, and exposes read-only query tools through FastMCP.

## Quick start

### 1. Install the Skill

The only required manual step is to install the `smsmcphub` Skill. It teaches
the agent what SmsMCPHub can do and how to use it without requiring users to
name an MCP server or tool.

```powershell
git clone https://github.com/PoilZero/SmsMCPHub.git
cd SmsMCPHub
Copy-Item -Recurse -Force .\skills\smsmcphub `
  "$env:USERPROFILE\.codex\skills\smsmcphub"
```

Restart Codex or start a new session after installation.

### 2. Ask the Skill to configure everything

Tell the agent what kind of deployment you want, for example:

```text
Install and configure SmsMCPHub for a phone on my private Wi-Fi network.
```

The Skill will guide the complete setup: install the Server dependencies, create
local configuration when needed, choose loopback or private-LAN exposure,
detect the usable address, start and health-check the Server, register MCP with
the active agent client, and guide the Provider Webhook setup. Public exposure
is never enabled without an explicit user choice.

Follow the Skill's prompts on the phone Provider and send a test message when it
asks you to verify the connection.

### 3. Use the Skill naturally

After setup, ask for the result directly. You do not need to mention MCP,
SmsMCPHub, or a tool name:

```text
查一下最近的验证码
```

```text
Find the latest login code received by SMS.
```

The Skill helps the agent select the appropriate read-only operation based on
the request. It does not restrict the request to any particular website,
platform, sender, or business workflow.

## Core architecture

```text
Phone or cloud Provider
          |
          | HTTP Webhook / future adapters
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
          v
      FastMCP Server
          |
          v
 Agent + optional SmsMCPHub Skill
```

The project is a modular monolith. FastAPI receives and validates Provider
payloads, the adapter converts them to the canonical message model, and the
shared service persists and queries messages. FastMCP exposes only the stable
domain contract, so Provider-specific field names do not leak into agent
requests. The optional Skill adds intent routing and installation guidance.

## MCP capabilities

| Tool | Use it for |
|---|---|
| `sms_latest` | The newest/current SMS, verification codes, OTPs, login codes, or recent alerts |
| `sms_search` | SMS history, multiple messages, time ranges, sender/recipient filters, or keyword searches |
| `sms_get` | Complete details and metadata for a known message ID |
| `sms_conversations` | Conversation, contact, or thread summaries |

All current tools are read-only. The Server does not send SMS, log into other
apps, publish content, or perform external side effects.

## Implementation and tests

- Python 3.11+
- FastAPI and Uvicorn
- FastMCP Streamable HTTP
- Pydantic
- SQLite via Python's standard `sqlite3` driver
- `uv` with a committed lock file

Run the checks from the project directory:

```powershell
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
```

The tests cover SmsForwarder form and JSON payloads, mapping, signatures,
idempotent ingestion, pagination, conversations, FastAPI endpoints, MCP
discovery, structured results, and authentication.

## Appendix: manual reference

The normal user path is Skill-first. This appendix is for manual installation,
debugging, and clients that cannot be configured by the Skill.

### A. Manual Server installation and startup

Requirements: Python 3.11+ and
[uv](https://docs.astral.sh/uv/getting-started/installation/).

```powershell
cd SmsMCPHub
uv sync --extra dev
Copy-Item .env.example .env
uv run smsmcphub
```

The default Server listens on `0.0.0.0:8000`. The database is created at
`data/smsmcphub.db`; `.env`, logs, and database files are local-only.

### B. Manual SmsForwarder configuration

Install or open [SmsForwarder](https://github.com/pppscn/SmsForwarder), then
add an HTTP Webhook forwarding channel. The UI may call these fields
`WebServer`, `Webhook URL`, `WebParams`, or similar.

Official reference: [SmsForwarder Webhook guide](https://github.com/pppscn/SmsForwarder/wiki/%E9%99%84%E5%BD%951%3A%E5%90%91webhook%E5%8F%91%E9%80%81post-get-put-patch%E8%AF%B7%E6%B1%82).

```text
Method:  POST
URL:     http://<COMPUTER_LAN_IP>:8000/api/v1/providers/smsforwarder/webhook
WebParams: leave empty for the first test
```

Enable a received-SMS forwarding rule and select this Webhook channel. The
phone and computer must be on the same reachable Wi-Fi network.

With empty `WebParams`, SmsForwarder sends the default form fields `from`,
`content`, `timestamp`, and optional `sign`. The adapter also accepts custom
JSON templates, common aliases, and simple JSON path mappings.

To enable SmsForwarder signature validation, set the same secret in both
systems before starting the Server:

```powershell
$env:SMSFORWARDER_SECRET = "replace-with-the-same-secret"
uv run smsmcphub
```

### C. Manual verification

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

Expected:

```json
{"status":"ok"}
```

Simulate SmsForwarder:

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

Expected:

```json
{
  "accepted": true,
  "message_ids": ["msg_..."],
  "duplicates": 0
}
```

### D. Manual MCP client configuration

The MCP endpoint is Streamable HTTP at `/mcp`. Use `127.0.0.1` when the Agent
and Server share a computer; otherwise use the Server computer's private-LAN
address.

#### Codex CLI / app / IDE extension

Official reference: [Codex MCP documentation](https://developers.openai.com/codex/mcp).

```powershell
codex mcp add smsmcphub --url http://127.0.0.1:8000/mcp
codex mcp list
```

Equivalent `config.toml`:

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
```

With MCP Token authentication:

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
bearer_token_env_var = "SMSMCPHUB_MCP_TOKEN"
```

Restart Codex or use `/mcp` to inspect the active server and tools.

#### Claude Code (`cc`)

Official reference: [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

```powershell
claude mcp add --transport http smsmcphub http://127.0.0.1:8000/mcp
claude mcp list
```

For a project-scoped server:

```powershell
claude mcp add --transport http --scope project `
  smsmcphub http://127.0.0.1:8000/mcp
```

The resulting `.mcp.json` entry is:

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

Use `/mcp` inside Claude Code to check the connection.

### E. Manual Windows setup helper

The repository includes a deterministic helper for users who need to run the
manual setup from PowerShell:

```powershell
.\skills\smsmcphub\scripts\install.ps1 `
  -ProjectPath . -Exposure lan -ConfigureCodex -InstallSkill -Start
```

Use `-Exposure loopback` when the phone does not need LAN access. When multiple
network adapters are present, pass `-NetworkInterface <WLAN_INTERFACE>` so the
phone URL uses the Wi-Fi address. The helper never configures public exposure
and never overwrites an existing `.env`.

<p align="right"><a href="#english">Back to language switch</a> | <a href="#中文">中文</a></p>

<a id="中文"></a>

## 中文

> SmsMCPHub 让Codex、Claude Code 等任意支持MCP的Agent框架通过MCP收发移动设备的短信消息等，以全自动各种需要短信的工作流。通过SQLite持久化，并使用FastMCP提供统一查询接口。

SmsMCPHub 是一个解耦的短信接入网关，兼容
[SmsForwarder](https://github.com/pppscn/SmsForwarder) 等手机端或云端转发服务。
它使用 FastAPI 接收并标准化短信，使用 SQLite 持久化，再通过 FastMCP 提供只读
查询工具。

## 快速使用

### 1. 安装 Skill

用户唯一需要手动安装的是 `smsmcphub` Skill。它会告诉 Agent SmsMCPHub 有哪些
能力，以及如何在用户不指定 MCP 或工具名称时自动使用这些能力。

```powershell
git clone https://github.com/PoilZero/SmsMCPHub.git
cd SmsMCPHub
Copy-Item -Recurse -Force .\skills\smsmcphub `
  "$env:USERPROFILE\.codex\skills\smsmcphub"
```

安装后重启 Codex 或新建会话。

### 2. 让 Skill 自动完成配置

直接告诉 Agent 你的部署需求，例如：

```text
请为同一 Wi-Fi 下的手机安装并配置 SmsMCPHub。
```

Skill 会引导完成完整配置：安装 Server 依赖、按需创建本地配置、选择本机或私有
局域网暴露方式、探测可用地址、启动并检查 Server、注册 MCP，以及引导配置手机
Provider 的 Webhook。没有得到用户明确选择时，不会配置公网访问。

按照 Skill 的提示在手机 Provider 中完成配置，并在要求测试时发送一条测试短信。

### 3. 直接使用 Skill

配置完成后直接描述需求，不需要提到 MCP、SmsMCPHub 或工具名称：

```text
查一下最近的验证码
```

```text
查找最近收到的登录短信
```

Skill 会帮助 Agent 根据用户意图自动选择合适的只读操作，不限定快手、小红书或任
何特定网站、平台、发送人和业务流程。

## 核心架构

```text
手机或云端 Provider
          |
          | HTTP Webhook / 后续适配器
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
          v
       FastMCP Server
          |
          v
 Agent + 可选 SmsMCPHub Skill
```

项目采用模块化单体。FastAPI 接收并校验 Provider 报文，适配器将其转换为统一消
息模型，共享服务负责持久化和查询。FastMCP 只暴露稳定的领域契约，不让 Provider
特有字段进入 Agent 请求。可选 Skill 负责意图路由和安装引导。

## MCP 能力

| 工具 | 使用场景 |
|---|---|
| `sms_latest` | 最新短信、验证码、OTP、登录码和近期提醒 |
| `sms_search` | 短信历史、多条消息、时间范围、发送人/接收人筛选和关键词搜索 |
| `sms_get` | 根据消息 ID 查看完整详情和元数据 |
| `sms_conversations` | 会话、联系人或消息线程概览 |

当前所有工具都是只读的。Server 不发送短信、不登录其他应用、不发布内容，也不执
行其他外部副作用。

## 实现和测试

- Python 3.11+
- FastAPI 和 Uvicorn
- FastMCP Streamable HTTP
- Pydantic
- Python 标准库 `sqlite3` 驱动 SQLite
- `uv` 和提交到仓库的锁定文件

在项目目录执行：

```powershell
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
```

测试覆盖 SmsForwarder 表单和 JSON、字段映射、签名、幂等入库、分页、会话、
FastAPI 接口、MCP 发现、结构化结果和鉴权。

## 附录：手动参考

正常用户路径是 Skill-first。下面内容用于手动安装、故障排查，以及 Skill 无法配
置客户端时的备用操作。

### A. 手动安装和启动 Server

依赖：Python 3.11+ 和
[uv](https://docs.astral.sh/uv/getting-started/installation/)。

```powershell
cd SmsMCPHub
uv sync --extra dev
Copy-Item .env.example .env
uv run smsmcphub
```

Server 默认监听 `0.0.0.0:8000`。数据库会自动创建到 `data/smsmcphub.db`；`.env`、
日志和数据库只保存在本地。

### B. 手动配置 SmsForwarder

安装或打开 [SmsForwarder](https://github.com/pppscn/SmsForwarder)，新增 HTTP
Webhook 转发通道。不同版本界面可能叫 `WebServer`、`Webhook URL`、`WebParams`
或类似名称。

官方参考：[SmsForwarder Webhook 文档](https://github.com/pppscn/SmsForwarder/wiki/%E9%99%84%E5%BD%951%3A%E5%90%91webhook%E5%8F%91%E9%80%81post-get-put-patch%E8%AF%B7%E6%B1%82)。

```text
请求方式：POST
URL：     http://<电脑局域网IP>:8000/api/v1/providers/smsforwarder/webhook
WebParams：第一次测试时留空
```

启用“接收短信”转发规则并选择该 Webhook 通道。手机和电脑必须在同一个可达的
Wi-Fi 网络中。

当 `WebParams` 留空时，SmsForwarder 默认发送表单字段 `from`、`content`、
`timestamp` 和可选的 `sign`。适配器也支持自定义 JSON 模板、常见字段别名和简单
JSON 路径映射。

如果要启用 SmsForwarder 签名校验，请在两边配置相同 secret 后再启动 Server：

```powershell
$env:SMSFORWARDER_SECRET = "替换为相同的密钥"
uv run smsmcphub
```

### C. 手动验证

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
```

预期：

```json
{"status":"ok"}
```

模拟 SmsForwarder：

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

预期：

```json
{
  "accepted": true,
  "message_ids": ["msg_..."],
  "duplicates": 0
}
```

### D. 手动配置 MCP 客户端

MCP 地址是 `/mcp` 的 Streamable HTTP。Agent 和 Server 在同一台电脑时使用
`127.0.0.1`；否则使用 Server 所在电脑的私有局域网 IP。

#### Codex CLI / 应用 / IDE 扩展

官方参考：[Codex MCP 文档](https://developers.openai.com/codex/mcp)。

```powershell
codex mcp add smsmcphub --url http://127.0.0.1:8000/mcp
codex mcp list
```

等价的 `config.toml`：

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
```

启用 MCP Token 时：

```toml
[mcp_servers.smsmcphub]
url = "http://127.0.0.1:8000/mcp"
bearer_token_env_var = "SMSMCPHUB_MCP_TOKEN"
```

重启 Codex 或使用 `/mcp` 查看连接和工具。

#### Claude Code（`cc`）

官方参考：[Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)。

```powershell
claude mcp add --transport http smsmcphub http://127.0.0.1:8000/mcp
claude mcp list
```

项目级 Server：

```powershell
claude mcp add --transport http --scope project `
  smsmcphub http://127.0.0.1:8000/mcp
```

生成的 `.mcp.json` 配置：

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

在 Claude Code 中使用 `/mcp` 检查连接。

### E. Windows 手动安装脚本

仓库提供了一个 PowerShell 辅助脚本，可用于手动执行完整配置：

```powershell
.\skills\smsmcphub\scripts\install.ps1 `
  -ProjectPath . -Exposure lan -ConfigureCodex -InstallSkill -Start
```

手机不需要局域网访问时使用 `-Exposure loopback`。电脑有多个网卡时，增加
`-NetworkInterface <WLAN网卡名称>`，确保手机 URL 使用 Wi-Fi 地址。脚本不会配置
公网暴露，也不会覆盖已有 `.env`。

<p align="right"><a href="#english">English</a> | <a href="#中文">返回顶部</a></p>
