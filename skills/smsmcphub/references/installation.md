# SmsMCPHub installation reference

Use this reference only during installation, configuration, or troubleshooting.

## Project setup

From a cloned project directory:

```powershell
uv sync --extra dev
Copy-Item .env.example .env
uv run smsmcphub
```

On macOS or Linux, use the same `uv` commands in a shell. The application
creates `data/smsmcphub.db` on first start. The `.env` file and database are
local-only and must never be committed.

## Binding and URLs

- Same-computer provider and agent: bind to `127.0.0.1`; use
  `http://127.0.0.1:8000/mcp` and the loopback Webhook URL.
- Phone on the same private LAN: bind to `0.0.0.0`; use the computer's LAN IP
  in the phone Webhook URL, for example
  `http://<COMPUTER_LAN_IP>:8000/api/v1/providers/smsforwarder/webhook`.
- If the computer has several network adapters, choose the Wi-Fi adapter's
  address. The Windows installer prefers interfaces named Wi-Fi/WLAN/Wireless;
  pass `-NetworkInterface <name>` when selection is ambiguous.
- Public access: stop and ask the user to choose a tunnel, reverse proxy, or
  other exposure method. Do not select one implicitly.

The phone and computer must be on the same reachable Wi-Fi segment. If a local
firewall blocks the port, explain the exact interface and private subnet before
requesting permission to add a narrowly scoped rule.

## Provider first test

Configure the Provider's HTTP Webhook as:

```text
Method: POST
URL: http://<COMPUTER_LAN_IP>:8000/api/v1/providers/smsforwarder/webhook
Custom parameters/template: empty
```

Enable the received-SMS rule and run the Provider's test action. A successful
response is a JSON object with `accepted: true`. Then call `sms_latest` or
`sms_search` through MCP to confirm persistence.

## Environment variables

The application reads `.env` without overwriting already-exported values:

```text
SMSMCPHUB_HOST=0.0.0.0
SMSMCPHUB_PORT=8000
SMSMCPHUB_DATABASE_PATH=./data/smsmcphub.db
SMSMCPHUB_MCP_TOKEN=
SMSFORWARDER_SECRET=
SMSFORWARDER_REQUIRE_SIGNATURE=false
```

Set `SMSFORWARDER_SECRET` only after the unsigned Webhook path works. Set
`SMSMCPHUB_MCP_TOKEN` before registering a bearer token in the agent client.
