# Compute Screener data (CSV)

Daily copies of the price indices published on [computescreener.com](https://computescreener.com), updated
automatically every day. Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Credit
"Compute Screener (computescreener.com)". How every value is calculated: [methodology](https://computescreener.com/methodology).

| File | One row per | Columns |
| --- | --- | --- |
| [gpu_index_daily.csv](gpu_index_daily.csv) | GPU and day | `date` (US Central day), `gpu`, `usd_per_gpu_hour`, `final` (false for today's provisional value), `weekly_history` (weekly values before the daily index began), `restated` |
| [gpu_providers_latest.csv](gpu_providers_latest.csv) | GPU and provider, latest | `gpu`, `provider`, `average_usd_per_gpu_hour` (standardized to the GPU's benchmark contract), `prices`, `status`, `read_at` |
| [token_index_daily.csv](token_index_daily.csv) | AI company and day | `date` (UTC day), `company`, `usd_per_1m_tokens` (3 input : 1 output blend, usage-weighted across the company's models), `final`, `rebuilt_history` (values rebuilt from earlier posted prices) |
| [token_models_latest.csv](token_models_latest.csv) | Model, latest day | `date`, `company`, `model`, `usd_per_1m_input`, `usd_per_1m_output`, `usd_per_1m_blended`, `share_of_company_tokens` |

`updated.txt` gives the time of the data each copy was taken from.

GPU indices: an on-demand, 8-GPU, US benchmark contract per GPU, from the posted prices of cloud providers and
GPU marketplaces. Token indices: each company's posted API prices, weighted by its models' usage. Sources the data
builds on keep their own terms: OpenRouter rankings (CC BY 4.0) for token usage, and for GPU history before
23 October 2026, SkyPilot's price catalog (Apache-2.0) and GetDeploying (CC BY 4.0).

Prices are information, not investment advice.
