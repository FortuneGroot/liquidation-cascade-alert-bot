# Liquidation Cascade Alert Bot

A real-time crypto market monitor that streams **forced-liquidation events from Binance and Bybit over WebSockets**, aggregates them into rolling five-minute "cascades," confirms each one against BingX price and volume data, and posts only the few events per day that clear every filter to Discord.

Built for the Fortune & Finance trading-education community. Read-only: it does not trade, connect to member accounts, or require any paid data subscription.

## The problem it solves

Liquidation feeds are extremely noisy — thousands of small events per hour. Channels that repost them become spam that members mute. The useful signal is the rare *cascade*: a burst of same-direction liquidations that actually moved price. This bot is built around **noise control** first:

An alert is sent only when **all** of these pass:

1. Dominant-side liquidations exceed the coin's USD threshold (e.g. $8M for BTC, $5M for ETH, $1M default).
2. At least *N* events occurred inside the five-minute window.
3. One direction accounts for at least 72% of liquidated value.
4. BingX price moved meaningfully **in the expected direction** (≥ 0.65% by default).
5. BingX volume is elevated versus its recent baseline (≥ 1.35×).
6. The symbol is outside its 30-minute cooldown.
7. The server-wide daily budget (default: 4 alerts per UTC day) is not exhausted.

Every threshold is configurable in `config.json`. Budget and cooldown state are persisted so a restart cannot reset the daily limit.

## Key features

- Concurrent WebSocket consumers for Binance USD-M Futures (`!forceOrder@arr`) and Bybit v5 linear liquidations, feeding a shared bounded `asyncio.Queue`.
- Rolling-window cascade aggregation per symbol (25 symbols configured by default).
- Two-stage gating: a cheap pre-qualification on liquidation data, then a BingX REST lookup for price/volume confirmation only when needed (with per-symbol evaluation throttling).
- Persistent alert budget and cooldown (`data/alert_state.json`).
- Scheduled summaries every four hours that never mention a role.
- Discord delivery via the authenticated HTTP API with **allowed-mentions explicitly disabled** (cannot ping `@everyone`); optional opt-in alert role.
- Read-only live probes (`tools/live_probe.py`, `tools/live_stream_probe.py`) for checking exchange connectivity.
- Dockerfile for server deployment.

## Technologies

- **Python 3.11+**, `asyncio`
- **aiohttp** (WebSocket clients, REST, and the Discord HTTP API — no discord.py dependency)
- Binance Futures WebSocket, Bybit v5 WebSocket, BingX public REST API
- Docker
- `unittest` test suite

## How it works

```text
Binance WS ─┐
            ├─► asyncio.Queue ─► CascadeAggregator (5-min window)
Bybit WS  ──┘                         │
                                      ▼
                         AlertGate.prequalifies()  (size, count, dominance, cooldown, budget)
                                      │
                                      ▼
                         BingX market context (price move + volume ratio)
                                      │
                                      ▼
                         AlertGate.qualifies_with_context() ─► Discord embed
```

```text
liquidation_bot/
├─ binance.py / bybit.py   WebSocket streams → normalized liquidation events
├─ aggregator.py           Rolling per-symbol cascade windows and daily snapshot
├─ filters.py              AlertGate: thresholds, cooldowns, persistent daily budget
├─ bingx.py                Price/volume context from public candles
├─ discord.py              Discord REST client, channel validation, embeds
├─ config.py               Settings from .env + config.json with validation
└─ app.py                  Orchestration and summary scheduler
```

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env              # bot token + channel IDs
Copy-Item config.example.json config.json
python run.py
```

The Discord bot needs only View Channel, Send Messages, Embed Links, and Read Message History. No privileged intents and no Administrator permission.

Docker:

```powershell
docker build -t liquidation-cascade .
docker run -d --restart unless-stopped --env-file .env -v "${PWD}/config.json:/app/config.json:ro" liquidation-cascade
```

## Testing and current status

```powershell
python -m unittest discover -s tests -v
```

**Verified (October 2026):** 5 tests pass (Python 3.12). They cover the Binance and Bybit message parsers (including each exchange's side convention), cascade aggregation and gating, rejection when price moved the wrong way, and daily-budget persistence across a restart.

**Not verified in this review:** the live WebSocket probes and a live Discord run were not executed while preparing this repository. Test coverage is focused on the core logic rather than end-to-end behavior.

## Accuracy statement

Alerts name Binance and Bybit as sources because those free feeds represent those exchanges, not the whole market. The bot does not estimate hidden liquidations or claim market-wide completeness.

## Business application

- Market-intelligence alerts for trading communities and research desks.
- The architecture — multiple real-time streams merged, windowed, enriched with a second data source, and rate-limited before notifying people — is the same pattern used for fraud alerts, infrastructure monitoring, and any "only page a human when it matters" system.

## Development approach

Built by George ([@FortuneGroot](https://github.com/FortuneGroot)) using AI-assisted development (OpenAI Codex and other AI coding tools). George designed the alerting policy — which conditions define a meaningful cascade, the per-coin thresholds, the daily budget, and the no-mass-mention rule — drawing on nine years of trading experience. He directed the implementation and validated it with the test suite. The AI tools generated much of the code under that direction.

## License

Copyright © 2026 George (FortuneGroot). All rights reserved. This code is published for portfolio review; contact me before reusing it.
