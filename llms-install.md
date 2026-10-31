# Installing the Compute Screener MCP server

Compute Screener is a hosted, read-only MCP server: nothing to download, build or run, and no account, API key or
sign-in. It answers what compute costs: GPU rental prices per hour (H100, H200, B200 and the others, each provider's
prices and the daily price indices), AI model API prices per 1M tokens, and how those prices changed.

- Endpoint: `https://computescreener.com/mcp`
- Transport: Streamable HTTP

## Cline

Add it under **MCP Servers → Remote Servers** (name `compute-screener`, URL `https://computescreener.com/mcp`,
transport Streamable HTTP), or add this to `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "compute-screener": {
      "type": "streamableHttp",
      "url": "https://computescreener.com/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

## Other apps

- Claude Code: `claude mcp add --transport http compute-screener https://computescreener.com/mcp`
- Gemini CLI: `gemini extensions install https://github.com/renshuBTC/compute-screener`
- Claude, ChatGPT and other apps: add `https://computescreener.com/mcp` as a custom connector
  ([setup for each app](https://computescreener.com/connect)).

To check it works, ask: "What does an H100 cost to rent per hour today?"
