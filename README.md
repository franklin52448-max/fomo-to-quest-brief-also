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

Run on a real Robinhood Chain address:

```bash
python3 relay_brief.py <REAL_ADDRESS> --out example_output.md
python3 relay_brief.py <REAL_ADDRESS> --json --out example_output.json
```

**Address used:** `<REAL_ADDRESS>`

**Sample output:**

```
<paste example_output.md here>
```
