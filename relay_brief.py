#!/usr/bin/env python3
"""
relay_brief.py - read-only Robinhood Chain research brief generator.

Input : a Robinhood Chain (chain id 4663) token or wallet/contract address
Data  : public RPC (eth_chainId, eth_getCode) + public Blockscout REST API v2
        (free Blockscout API key via BLOCKSCOUT_API_KEY env var; no key is stored in code)
Output: short markdown brief (default) or JSON (--json) that includes a
        ready-to-post Relay Tech research bounty draft.

Read-only: no keys, no signing, no trading, no private APIs, no login.
Python 3.8+, standard library only.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from collections import Counter
from datetime import datetime, timezone

RPC_URL = os.environ.get("RH_RPC_URL", "https://rpc.mainnet.chain.robinhood.com")
API_KEY = os.environ.get("BLOCKSCOUT_API_KEY", "")  # free key from https://dev.blockscout.com
_default_api = ("https://api.blockscout.com/4663/api/v2" if API_KEY
                else "https://robinhoodchain.blockscout.com/api/v2")
API_URL = os.environ.get("RH_API_URL", _default_api).rstrip("/")
EXPLORER = os.environ.get("RH_EXPLORER", "https://robinhoodchain.blockscout.com").rstrip("/")
CHAIN_ID = 4663
UA = {
    "User-Agent": os.environ.get(
        "RH_UA",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 relay-brief/1.0"),
    "Accept": "application/json",
}


# ---------- tiny HTTP layer ----------
def _http(url, data=None, tries=4):
    hdrs = dict(UA)
    if data is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 403:
                raise SystemExit(f"HTTP 403 from {url}\nThe endpoint blocked this request (bot/IP filter). "
                                 "Blockscout now expects a free API key: get one at https://dev.blockscout.com "
                                 "then run:  export BLOCKSCOUT_API_KEY=proapi_xxx")
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(1.5 * (i + 1))
                continue
            raise
        except urllib.error.URLError:
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
                continue
            raise


def rpc(method, params):
    res = _http(RPC_URL, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return (res or {}).get("result")


def api(path, **params):
    if API_KEY:
        params["apikey"] = API_KEY
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return _http(f"{API_URL}{path}" + (f"?{q}" if q else ""))


def paged(path, limit):
    """Follow Blockscout next_page_params until `limit` items are collected."""
    items, params = [], {}
    while len(items) < limit:
        page = api(path, **params)
        if not page:
            break
        items += page.get("items", [])
        nxt = page.get("next_page_params")
        if not nxt:
            break
        params = {k: v for k, v in nxt.items() if v is not None}
    return items[:limit]


# ---------- helpers ----------
def ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def wei_to_eth(v):
    try:
        return int(v) / 1e18
    except (TypeError, ValueError):
        return 0.0


def short(a):
    return f"{a[:6]}…{a[-4:]}" if a and len(a) > 12 else (a or "?")


def addr_of(x):
    return (x or {}).get("hash") or ""


def label(x):
    x = x or {}
    return x.get("name") or x.get("ens_domain_name") or short(x.get("hash"))


def valid_address(a):
    return isinstance(a, str) and len(a) == 42 and a.startswith("0x") and all(
        c in "0123456789abcdefABCDEF" for c in a[2:])


# ---------- collection ----------
def collect(address, rules):
    d = {"address": address, "explorer_url": f"{EXPLORER}/address/{address}"}
    cid = rpc("eth_chainId", [])
    d["rpc_chain_id"] = int(cid, 16) if cid else None
    if d["rpc_chain_id"] != CHAIN_ID:
        raise SystemExit(f"RPC chain id is {d['rpc_chain_id']}, expected {CHAIN_ID}. Check RH_RPC_URL.")
    code = rpc("eth_getCode", [address, "latest"]) or "0x"
    d["is_contract"] = code not in ("0x", "0x0")
    d["info"] = api(f"/addresses/{address}") or {}
    d["counters"] = api(f"/addresses/{address}/counters") or {}
    d["token"] = api(f"/tokens/{address}") if d["is_contract"] else None
    d["txs"] = paged(f"/addresses/{address}/transactions", rules["recent_tx_limit"])
    d["transfers"] = paged(f"/addresses/{address}/token-transfers", rules["recent_transfer_limit"])
    d["holders"] = paged(f"/tokens/{address}/holders", 50) if d["token"] else []
    return d


# ---------- analysis ----------
def analyse(d, rules):
    now = datetime.now(timezone.utc)
    sig, flags = {}, []
    txs, xfers = d["txs"], d["transfers"]
    times = sorted(t for t in (ts(x.get("timestamp")) for x in txs) if t)

    c = d["counters"]
    sig["total_transactions"] = int(c.get("transactions_count") or 0)
    sig["total_token_transfers"] = int(c.get("token_transfers_count") or 0)
    sig["balance_eth"] = round(wei_to_eth(d["info"].get("coin_balance")), 6)
    sig["sampled_txs"] = len(txs)

    if times:
        span_days = max((times[-1] - times[0]).total_seconds() / 86400, 1 / 24)
        sig["sample_first_tx"], sig["sample_last_tx"] = times[0].isoformat(), times[-1].isoformat()
        sig["txs_per_day_in_sample"] = round(len(times) / span_days, 2)
        idle = (now - times[-1]).days
        sig["days_since_last_tx"] = idle
        if idle >= rules["dormant_days"]:
            flags.append(f"Dormant: last transaction {idle} days ago.")
        # burst detection: sliding window
        w, best, j = rules["burst_window_minutes"] * 60, 0, 0
        for i in range(len(times)):
            while (times[i] - times[j]).total_seconds() > w:
                j += 1
            best = max(best, i - j + 1)
        sig["max_txs_in_burst_window"] = best
        if best >= rules["burst_min_txs"]:
            flags.append(f"Burst: {best} txs within {rules['burst_window_minutes']} minutes.")
        # age (only meaningful if the sample reaches the beginning)
        if len(txs) < rules["recent_tx_limit"] and (now - times[0]).days <= rules["new_address_days"]:
            flags.append(f"New address: first activity {(now - times[0]).days} day(s) ago.")

    failed = sum(1 for t in txs if t.get("status") == "error")
    sig["failed_tx_ratio"] = round(failed / len(txs), 3) if txs else 0
    if txs and sig["failed_tx_ratio"] >= rules["high_failure_ratio"]:
        flags.append(f"High failure rate: {failed}/{len(txs)} sampled txs failed.")

    # counterparties & methods
    cp, methods, big = Counter(), Counter(), []
    for t in txs:
        other = t.get("to") if addr_of(t.get("from")).lower() == d["address"].lower() else t.get("from")
        if other:
            cp[(addr_of(other), label(other), bool(other.get("is_contract")))] += 1
        if t.get("method"):
            methods[t["method"]] += 1
        v = wei_to_eth(t.get("value"))
        if v >= rules["large_value_eth"]:
            big.append({"hash": t.get("hash"), "eth": round(v, 4), "time": t.get("timestamp")})
    sig["unique_counterparties"] = len(cp)
    sig["top_counterparties"] = [
        {"address": a, "label": l, "is_contract": ic, "tx_count": n} for (a, l, ic), n in cp.most_common(5)]
    sig["top_methods"] = [{"method": m, "count": n} for m, n in methods.most_common(5)]
    sig["large_value_txs"] = big[:5]
    if big:
        flags.append(f"{len(big)} sampled tx(s) moved >= {rules['large_value_eth']} ETH.")
    if len(txs) >= 30 and len(cp) < rules["min_unique_counterparties_for_organic"]:
        flags.append(f"Few counterparties ({len(cp)}) for {len(txs)} txs - may be bot or self-dealing.")

    # token transfers
    kinds = Counter(x.get("type") for x in xfers)
    sig["transfer_types"] = dict(kinds)
    tokens = Counter((x.get("token") or {}).get("symbol") or short(addr_of(x.get("token"))) for x in xfers)
    sig["top_tokens_touched"] = [{"token": k, "transfers": v} for k, v in tokens.most_common(5)]
    if kinds.get("token_minting") or kinds.get("token_burning"):
        flags.append(f"Mint/burn activity in sample: {kinds.get('token_minting', 0)} mints, {kinds.get('token_burning', 0)} burns.")

    # token specific
    tk = d["token"]
    if tk:
        dec = int(tk.get("decimals") or 0)
        supply = int(tk.get("total_supply") or 0)
        sig["token"] = {
            "name": tk.get("name"), "symbol": tk.get("symbol"), "type": tk.get("type"),
            "decimals": dec, "total_supply": supply / (10 ** dec) if supply else None,
            "holders_count": tk.get("holders_count") or tk.get("holders"),
        }
        vals = sorted((int(h.get("value") or 0) for h in d["holders"]), reverse=True)
        if supply and vals:
            t1, t10 = vals[0] / supply * 100, sum(vals[:10]) / supply * 100
            sig["token"]["top1_holder_pct"], sig["token"]["top10_holders_pct"] = round(t1, 2), round(t10, 2)
            sig["token"]["top_holders"] = [
                {"address": addr_of(h.get("address")), "label": label(h.get("address")),
                 "pct": round(int(h.get("value") or 0) / supply * 100, 2)} for h in d["holders"][:5]]
            if t1 >= rules["holder_top1_pct"]:
                flags.append(f"Concentration: top holder owns {t1:.1f}% of supply.")
            if t10 >= rules["holder_top10_pct"]:
                flags.append(f"Concentration: top 10 holders own {t10:.1f}% of supply.")
    if d["is_contract"]:
        sig["verified_contract"] = bool(d["info"].get("is_verified"))
        if not sig["verified_contract"]:
            flags.append("Contract source is NOT verified on Blockscout.")
        if d["info"].get("creator_address_hash"):
            sig["creator"] = d["info"]["creator_address_hash"]
    if not txs and not xfers:
        flags.append("No activity found for this address.")
    return sig, flags


# ---------- output ----------
def bounty_draft(d, sig, flags, rules):
    kind = "token" if d["token"] else ("contract" if d["is_contract"] else "wallet")
    name = (sig.get("token") or {}).get("symbol") or short(d["address"])
    return {
        "title": f"Deep-dive research on {kind} {name} (Robinhood Chain)",
        "description": (
            f"Investigate {kind} {d['address']} on Robinhood Chain. Automated screen flagged: "
            + ("; ".join(flags) if flags else "no automated flags")
            + ". Deliver a verified written report with sources (explorer links)."),
        "deliverables": [
            "Who deployed/controls it and how funds flow in and out",
            "Explanation of each flagged signal: real risk or benign",
            "Counterparty / holder cluster analysis",
            "Clear verdict with evidence links"],
        "reward_usdg": rules["bounty_reward_usdg"],
        "reference": d["explorer_url"],
    }


def to_markdown(d, sig, flags):
    L = [f"# Research brief: {(sig.get('token') or {}).get('symbol') or short(d['address'])}",
         f"`{d['address']}` - {'token' if d['token'] else 'contract' if d['is_contract'] else 'wallet'} - "
         f"Robinhood Chain ({CHAIN_ID})", d["explorer_url"], ""]
    L.append("## Flags")
    L += [f"- {f}" for f in flags] or ["- none"]
    L += ["", "## Key metrics",
          f"- Balance: {sig['balance_eth']} ETH",
          f"- Lifetime txs: {sig['total_transactions']} | token transfers: {sig['total_token_transfers']}",
          f"- Sample: {sig['sampled_txs']} latest txs, {sig.get('txs_per_day_in_sample', 'n/a')} tx/day, "
          f"last tx {sig.get('days_since_last_tx', 'n/a')} day(s) ago",
          f"- Failed tx ratio: {sig['failed_tx_ratio']:.0%} | unique counterparties: {sig['unique_counterparties']}"]
    if "token" in sig:
        t = sig["token"]
        L += ["", "## Token", f"- {t['name']} ({t['symbol']}), {t['type']}, supply {t['total_supply']}, holders {t['holders_count']}"]
        if "top1_holder_pct" in t:
            L.append(f"- Top holder {t['top1_holder_pct']}% | top 10 {t['top10_holders_pct']}%")
    if sig["top_counterparties"]:
        L += ["", "## Top counterparties"]
        L += [f"- {c['label']} ({'contract' if c['is_contract'] else 'EOA'}) x{c['tx_count']}" for c in sig["top_counterparties"]]
    if sig["top_methods"]:
        L += ["", "## Top contract methods", ", ".join(f"{m['method']} x{m['count']}" for m in sig["top_methods"])]
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser(description="Read-only Robinhood Chain research brief")
    p.add_argument("address")
    p.add_argument("--json", action="store_true", help="JSON output (includes bounty draft)")
    p.add_argument("--rules", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.json"))
    p.add_argument("--out", help="write output to file")
    a = p.parse_args()
    if not valid_address(a.address):
        sys.exit("Invalid address: expected 0x + 40 hex chars")
    with open(a.rules) as f:
        rules = json.load(f)
    d = collect(a.address, rules)
    sig, flags = analyse(d, rules)
    if a.json:
        out = json.dumps({"address": a.address, "chain_id": CHAIN_ID,
                          "generated_at": datetime.now(timezone.utc).isoformat(),
                          "kind": "token" if d["token"] else "contract" if d["is_contract"] else "wallet",
                          "flags": flags, "signals": sig,
                          "bounty_draft": bounty_draft(d, sig, flags, rules)}, indent=2)
    else:
        out = to_markdown(d, sig, flags)
    if a.out:
        open(a.out, "w").write(out)
    print(out)


if __name__ == "__main__":
    main()
