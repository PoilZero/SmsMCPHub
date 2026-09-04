---
name: smsmcphub
description: Use when a user asks to find, inspect, or organize SMS messages, verification codes, login OTPs, or recent alerts, or asks to install, configure, or test SmsMCPHub; automatically route the request to the connected SmsMCPHub MCP tools and guide local setup when they are unavailable.
---

# SmsMCPHub

SmsMCPHub is a read-only SMS access layer. It receives messages from a configured
phone or cloud provider, normalizes them, and exposes them through four MCP
tools. This skill makes the capability discoverable without requiring the user
to name an MCP server or tool.

## Operating modes

### Use mode

When the SmsMCPHub tools are available in the current agent session:

- Treat requests about SMS, verification codes, one-time passwords, login codes,
  delivery alerts, sender history, or message conversations as requests for
  SmsMCPHub data.
- Select the appropriate tool from the routing rules below and call it
  automatically. Do not ask the user to repeat the request with an MCP tool name.
- Never fabricate a code or claim that a message was received when the query
  returned no match. State that no matching message was found and, when useful,
  broaden the search once.
- Return only the minimum sensitive content needed for the user's request. Mask
  phone numbers unless the full number is relevant.

### Install mode

If the user asks to install, configure, or enable SmsMCPHub and the server or
skill is not available:

1. Locate or clone the SmsMCPHub project, then install its locked dependencies
   with `uv sync --extra dev`.
2. Create `.env` from `.env.example` only when `.env` does not already exist; do
   not overwrite local secrets or database settings.
3. Bind to `127.0.0.1` when the provider runs on the same computer. Bind to
   `0.0.0.0` when a phone on the private LAN must reach the service. Detect and
   report the computer's usable LAN address in the latter case.
4. Start the server, verify `GET /healthz`, and report the exact Webhook and MCP
   URLs. Do not expose the service to the public internet or create a tunnel
   unless the user explicitly chooses that exposure.
5. Register the Streamable HTTP MCP endpoint with the active agent client. For
   Codex use `codex mcp add smsmcphub --url <MCP_URL>`; for Claude Code use
   `claude mcp add --transport http smsmcphub <MCP_URL>`. If a server with that
   name already exists, inspect it before changing it.
6. Install this skill into the agent's skill directory when requested or when
   the skill is being installed as part of SmsMCPHub setup. Keep implicit
   invocation enabled.
7. Guide the user to configure the Provider's HTTP Webhook with `POST` and the
   reported Webhook URL. Start with an empty custom parameter/template so the
   provider's default payload can be validated first. Ask the user to trigger a
   provider test, then verify the resulting message through MCP.

Read [references/installation.md](references/installation.md) for platform
commands, firewall scope, environment variables, and recovery steps. Use the
bundled `scripts/install.ps1` for a deterministic Windows setup when the project
path and requested exposure are known.

## Tool routing

| User intent | Tool | Selection rules |
|---|---|---|
| Newest/current SMS, verification code, OTP, login code, recent alert | `sms_latest` | Use first. Pass a recent `within_minutes` window; pass a service or sender keyword when one is provided. |
| SMS history, multiple messages, date range, sender/recipient/keyword filter | `sms_search` | Use for explicit lists and history. Also use as a broader fallback after `sms_latest` returns no match. |
| Details for a known message ID or complete metadata | `sms_get` | Call only when the user references a message ID or needs full message fields. |
| Conversation, thread, contact, or peer overview | `sms_conversations` | Return conversation summaries; fetch a specific message only if needed. |

### Query behavior

- Interpret “just now”, “recently”, or an unspecified verification-code request
  as a short recent window, normally 10 minutes. Respect an explicit time range.
- For a verification-code request, call `sms_latest` with a relevant keyword
  such as `verification`, `验证码`, `OTP`, or `code`. If a service name is
  supplied, use it as an additional keyword or perform a targeted
  `sms_search` fallback when the first query is empty.
- If several candidates match, prefer the newest message and mention the
  timestamp; ask a concise clarification only when the candidates are genuinely
  ambiguous.
- Use `sms_search` without a keyword for a request for recent SMS generally. Cap
  results at a practical limit and use the returned cursor for pagination.
- `sms_latest` and `sms_search` return compact summaries. Use `sms_get` for
  provider metadata, the complete canonical record, or debugging details.

## Capability boundaries

SmsMCPHub v1 exposes read-only SMS operations. It does not send SMS, log into
third-party apps, publish content, or perform other side effects. If a request
combines SMS verification with another connected capability, first retrieve the
code with SmsMCPHub, then use the other capability only when it is available and
the user has supplied the required information and authorization.

Do not expose secrets, raw payloads, or full message histories unnecessarily.
Keep provider credentials in local environment variables or ignored `.env`
files, never in prompts or tracked files.
