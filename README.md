<p align="center">
  <a href="https://computescreener.com"><img src="docs/logo.png" alt="Compute Screener logo" width="88" height="88"></a>
</p>

<h1 align="center">Compute Screener</h1>

<p align="center">
  <b>Free daily price indices for renting GPUs and for AI model tokens.</b><br>
  <a href="https://computescreener.com"><b>computescreener.com</b></a>
</p>

<p align="center">
  <a href="https://computescreener.com"><img src="docs/screenshot.png" alt="Compute Screener: rental prices of B300, B200, H200, H100, RTX PRO 6000 and A100 in USD per GPU-hour, with 1-day, 1-week and 1-month changes" width="800"></a>
</p>

## What it tracks

- **GPU rental prices:** a daily index in USD per GPU-hour for **H100, H200, A100, B200, B300 and RTX PRO 6000**. It is built from the posted on-demand prices of 20 sources (cloud rate cards and GPU marketplaces), standardized to one benchmark contract (on-demand, 8-GPU node, US), and updated every 2 to 3 hours. With 1-day, 1-week and 1-month changes, each provider's average price, and the prices of GPU rental contracts on the exchanges that list them.
- **AI token prices:** a daily index in USD per 1M tokens (3 input : 1 output) for **Anthropic, OpenAI, Google, xAI, Meta, Moonshot AI, Alibaba, DeepSeek, Z.ai and Xiaomi**, with each company's models and their posted prices.

How every price is collected, filtered and combined: [methodology](https://computescreener.com/methodology).

## Use it

| Where | How |
| --- | --- |
| Website | [computescreener.com](https://computescreener.com) |
| Claude, ChatGPT and other AI apps (MCP) | Add the connector `https://computescreener.com/mcp`. No account or API key. Setup: [computescreener.com/connect](https://computescreener.com/connect) |
| Daily CSV (this repo) | [data/](data): every GPU's and company's daily index, provider averages and model prices, updated every day |
| Data files (JSON) | [index.json](https://computescreener.com/data/index.json) (latest GPU prices) · [series.json](https://computescreener.com/data/series.json) (GPU history) · [tokens.json](https://computescreener.com/data/tokens.json) · [token_series.json](https://computescreener.com/data/token_series.json) |

The connector is listed in Claude's connector directory and in the official MCP Registry as `com.computescreener/compute-screener`.

## This repository

`data/` holds the daily CSV copies (see [data/README.md](data/README.md)), refreshed by a scheduled workflow. `dist/`
holds a minified build of the website's pages, for reference. The price pipeline and the connector are not published.

## Licence

- **Data:** [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Reuse it, including commercially, with credit to "Compute Screener (computescreener.com)". See the [terms](https://computescreener.com/terms).
- **Code:** © 2026 Compute Screener. All rights reserved: no licence is granted to copy, modify or redistribute it. See [LICENSE](LICENSE).

Prices are information, not investment advice.

## Contact

[computescreener.com/support](https://computescreener.com/support) · [@RenshuBTC](https://x.com/RenshuBTC) on X
