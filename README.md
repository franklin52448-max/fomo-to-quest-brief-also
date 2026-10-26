# relay-brief: read-only Robinhood Chain research brief

Takes a Robinhood Chain (chain ID 4663) token, contract, or wallet address, reads real public onchain data, and prints a short research brief. It can also output JSON that includes a ready-to-post Relay Tech research bounty draft.

**Read-only by design:** no wallet signing, no trading, no private keys, no private Fomo APIs, no authenticated scraping, no login. Only public endpoints are called.

## Run it

Requires Python 3.8+. No dependencies (standard library only).

```bash
python3 relay_brief.py <address>                 # markdown brief
python3 relay_brief.py <address> --json          # JSON + bounty draft
python3 relay_brief.py <address> --out brief.md  # also write to file
python3 relay_brief.py <address> --rules my_rules.json
```

**Blockscout API key (free, public):** Blockscout's API now expects a free key. Get one at https://dev.blockscout.com (no payment) and export it. It is read from the environment only and never stored in the repo:

```bash
export BLOCKSCOUT_API_KEY=proapi_xxx
```

Optional environment overrides (defaults shown):

```
RH_RPC_URL=https://rpc.mainnet.chain.robinhood.com
RH_API_URL=https://robinhoodchain.blockscout.com/api/v2
RH_EXPLORER=https://robinhoodchain.blockscout.com
```

## What it reports

- **Recent transactions:** latest N txs (default 100), tx/day, last activity, failure ratio
- **Notable contract interactions:** top counterparties (EOA vs contract) and top called methods
- **Unusual activity flags:** bursts, large-value transfers, high failure rate, new or dormant address, few counterparties, mint/burn activity, unverified contract
- **Token metrics (if the address is a token):** supply, holder count, top-1 and top-10 holder concentration
- **Bonus:** `--json` output and a `bounty_draft` object that can be posted directly as a Relay Tech research bounty

## Configurable analysis rules

All thresholds live in `rules.json` (burst window, large-value cutoff, concentration limits, dormancy days, sample size, draft bounty reward). Edit the file or pass your own with `--rules`.

## Architecture

```
address -> validate -> RPC (eth_chainId check, eth_getCode: contract or EOA)
        -> Blockscout REST v2 (address info, counters, transactions,
           token transfers, token info, holders)
        -> analyse(): signals + rule-based flags (rules.json)
        -> output: markdown brief | JSON + bounty_draft
```

- One file, standard library only, so it is easy to audit and run.
- The RPC confirms the chain ID is 4663 before anything else, so it fails fast on a wrong endpoint.
- Blockscout is the chain's official public explorer API, so no API key is needed. Requests retry with backoff on 429/5xx errors.
- Analysis is a pure function of the fetched data, so rules can change without touching the fetching code.
- Limitation: signals come from a sample of the latest transactions (size set by `recent_tx_limit`), not the full history. Lifetime totals come from the explorer counters.

## Real example

Real run on Robinhood Chain (chain ID 4663), October 26, 2026:

```bash
python relay_brief.py 0x492641F648a4986844848E0beFE66D14817bCE34 --out example_output.md
python relay_brief.py 0x492641F648a4986844848E0beFE66D14817bCE34 --json --out example_output.json
```

**Address used:** `0x492641F648a4986844848E0beFE66D14817bCE34` (Chainlink, LINK)
[View on explorer](https://robinhoodchain.blockscout.com/address/0x492641F648a4986844848E0beFE66D14817bCE34)

Full output files: [`example_output.md`](example_output.md) and [`example_output.json`](example_output.json).

**Sample output:**

```
# Research brief: LINK
`0x492641F648a4986844848E0beFE66D14817bCE34` - token - Robinhood Chain (4663)
https://robinhoodchain.blockscout.com/address/0x492641F648a4986844848E0beFE66D14817bCE34

## Flags
- Concentration: top holder owns 48.0% of supply.
- Concentration: top 10 holders own 90.4% of supply.

## Key metrics
- Balance: 0.0 ETH
- Lifetime txs: 375 | token transfers: 3
- Sample: 100 latest txs, 14.3 tx/day, last tx 0 day(s) ago
- Failed tx ratio: 0% | unique counterparties: 70

## Token
- Chainlink (LINK), ERC-20, supply 1010.1192186234115, holders 302
- Top holder 48.05% | top 10 90.42%

## Top counterparties
- 0x63c9…9964 (EOA) x6
- 0xfe1d…e76e (EOA) x5
- 0xC0b7…5d66 (contract) x4
- 0x633c…366d (EOA) x4
- 0xbE93…97D5 (EOA) x4

## Top contract methods
approve x94, transfer x6
```

**Reading it:** the token is actively used (14.3 tx/day, 70 unique counterparties, 0% failures), but supply is heavily concentrated: one holder has 48% and the top 10 hold 90%. That is the signal a researcher would follow up, which is exactly what the `bounty_draft` field in the JSON output turns into a Relay Tech research bounty.
