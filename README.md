# Antigravity Proxy Connector for OpenWebUI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![OpenWebUI](https://img.shields.io/badge/OpenWebUI-Compatible-blue)](https://openwebui.com)
[![Python](https://img.shields.io/badge/Python-3.8%2B-green)](https://python.org)

A **Pipe / Function** for [OpenWebUI](https://openwebui.com) that connects to the [Antigravity Claude Proxy](https://github.com/badrisnarayanan/antigravity-claude-proxy), bringing **Claude and Gemini models** — including thinking/reasoning variants — directly into your OpenWebUI chat interface.

```
┌─────────────────┐     ┌─────────────────────────┐     ┌──────────────────────────┐
│   OpenWebUI     │────▶│  Antigravity Proxy       │────▶│  Antigravity Cloud Code  │
│  (This Plugin)  │     │  (localhost:8080)         │     │  (Google Cloud APIs)     │
└─────────────────┘     └─────────────────────────┘     └──────────────────────────┘
```

---

> **⚠️ Terms of Service Warning**
> The Antigravity Proxy uses Google's Cloud Code APIs via unofficial means. Google has issued ToS violations and account bans for some users. **Use a burner Google account — do not use your primary account.** You assume all risks. See the [upstream safety notices](https://github.com/badrisnarayanan/antigravity-claude-proxy/blob/main/docs/safety-notices.md) for full details.

---

## Features

- 🤖 **Multi-model support** — Claude (including Opus, Sonnet, Haiku) and Gemini models in one place
- 🧠 **Thinking / Reasoning tokens** — Streaming `<think>` blocks for supported models (e.g. `claude-*-thinking`, `gemini-3+`)
- 🖼️ **Vision / multimodal** — Image inputs forwarded correctly to the proxy
- 🔧 **Tool / function calling** — OpenAI-to-Anthropic tool format conversion built-in
- 📡 **Streaming support** — Real-time token streaming via SSE
- ⚙️ **Configurable valves** — Proxy URL, API key, timeouts, model prefix, and thinking toggle — all tunable from the OpenWebUI UI

---

## Prerequisites

### 1. OpenWebUI

You need a running instance of [OpenWebUI](https://github.com/open-webui/open-webui).

```bash
# Quick start with Docker
docker run -d -p 3000:8080 --name openwebui ghcr.io/open-webui/open-webui:main
```

### 2. Antigravity Claude Proxy ⚡ (Required)

This connector **depends on the Antigravity Claude Proxy** running locally (or on a reachable host). The proxy handles authentication with Antigravity's Cloud Code and exposes an Anthropic-compatible API.

**Install and start the proxy:**

```bash
# Option A — Run directly with npx (no install needed)
npx antigravity-claude-proxy@latest start

# Option B — Install globally
npm install -g antigravity-claude-proxy@latest
antigravity-claude-proxy start

# Option C — Clone and run
git clone https://github.com/badrisnarayanan/antigravity-claude-proxy.git
cd antigravity-claude-proxy
npm install
npm start
```

> **Node.js 18 or later is required** for the proxy.

**Link a Google account** (required to actually call models):

After starting the proxy, open `http://localhost:8080` in your browser, go to the **Accounts** tab, and click **Add Account** to complete Google OAuth.

> For headless / remote servers, use: `antigravity-claude-proxy accounts add --no-browser`

**Verify the proxy is running:**

```bash
curl http://localhost:8080/health
curl http://localhost:8080/v1/models
```

For full proxy documentation, visit the [antigravity-claude-proxy repo](https://github.com/badrisnarayanan/antigravity-claude-proxy).

---

## Installation

### Step 1 — Add the Function to OpenWebUI

1. Open your OpenWebUI instance in a browser.
2. Navigate to **Workspace** → **Functions** → **+ Add Function** (or **Import**).
3. Paste the contents of [`antigravity_pipe.py`](./antigravity_pipe.py) into the editor.
4. Click **Save**.

### Step 2 — Configure the Valves

After saving, click the ⚙️ **gear icon** next to the function to open the Valves configuration panel:

| Valve | Default | Description |
|---|---|---|
| `PROXY_BASE_URL` | `http://localhost:8080` | Base URL of your running Antigravity Proxy |
| `API_KEY` | `test` | API key for the proxy (use `test` unless you set a custom key) |
| `INCLUDE_THINKING` | `true` | Enable `<think>` blocks for models that support reasoning |
| `MODEL_PREFIX` | `AG-Proxy: ` | Optional display prefix for model names in OpenWebUI |
| `REQUEST_TIMEOUT` | `300` | Timeout in seconds for non-streaming requests |
| `STREAM_TIMEOUT` | `600` | Timeout in seconds for streaming requests |

### Step 3 — Enable the Pipe

1. After configuring, toggle the function **ON** using the switch next to it.
2. In a new chat, click the model selector — you should now see all models fetched from your proxy, prefixed with `AG-Proxy:` (or your custom prefix).

---

## Usage

Once installed and the proxy is running, simply select any `AG-Proxy:` model from the model picker in OpenWebUI and start chatting. Streaming, vision inputs, and thinking blocks all work out of the box.

### Thinking / Reasoning Models

For models with `thinking` in their name (e.g. `claude-opus-4-6-thinking`) or Gemini 3+ models, the pipe will automatically request reasoning tokens. These appear as collapsible `<think>` blocks in the OpenWebUI interface.

### Recommended Models

| Use Case | Model |
|---|---|
| Best quality | `claude-opus-4-6-thinking` |
| Balanced | `claude-sonnet-4-6-thinking` |
| Fast / lightweight | `claude-sonnet-4-6` |
| Gemini (large context) | `gemini-3.1-pro-high[1m]` |
| Gemini (fast) | `gemini-3-flash[1m]` |

---

## How It Works

The pipe translates between OpenWebUI's OpenAI-style message format and the Anthropic Messages API format that the Antigravity Proxy expects:

1. **Model discovery** — On load, the pipe calls `/v1/models` on the proxy and registers all available models with OpenWebUI.
2. **Message conversion** — System messages, multipart content, image URLs (base64 and remote), and tool definitions are all converted from OpenAI format to Anthropic format.
3. **Thinking support** — For capable models, `"thinking": {"type": "enabled", ...}` is injected automatically.
4. **Streaming** — SSE events from the proxy (`content_block_start`, `content_block_delta`, etc.) are parsed and yielded as a Python generator to OpenWebUI.
5. **Response assembly** — Non-streaming responses extract `text` and `thinking` blocks and format them for display, including tool call output.

---

## Troubleshooting

**Models not appearing in OpenWebUI**
- Confirm the proxy is running: `curl http://localhost:8080/health`
- Check that `PROXY_BASE_URL` in the valve matches the proxy's address.
- If OpenWebUI is inside Docker and the proxy is on the host, use `http://host.docker.internal:8080` instead of `localhost`.

**`Pipe Error: Cannot connect to Antigravity Proxy`**
- The proxy is not running or unreachable. Start it with `antigravity-claude-proxy start` (or `npx antigravity-claude-proxy@latest start`).

**Requests time out**
- Thinking models can be slow. Try increasing `REQUEST_TIMEOUT` and `STREAM_TIMEOUT` in the valves.

**Google account banned / restricted**
- This is a known risk. Refer to the [upstream safety notices](https://github.com/badrisnarayanan/antigravity-claude-proxy/blob/main/docs/safety-notices.md). Always use a burner account.

---

## Project Structure

```
antigravity-proxy-openwebui/
├── antigravity_pipe.py   # The OpenWebUI Pipe / Function
└── README.md
```

---

## Related Projects

- [antigravity-claude-proxy](https://github.com/badrisnarayanan/antigravity-claude-proxy) — The upstream proxy this connector depends on
- [OpenWebUI](https://github.com/open-webui/open-webui) — The web UI this pipe integrates with
- [opencode-antigravity-auth](https://github.com/NoeFabris/opencode-antigravity-auth) — Antigravity OAuth plugin for OpenCode

---

## Author

**Logappradeep** — [github.com/Logappradeep-M](https://github.com/Logappradeep-M)

---

## License

MIT — see [LICENSE](./LICENSE) for details.
