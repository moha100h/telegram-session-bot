"""
Transaction verifier — checks TX hash link for:
- Real token (not fake/scam)
- Correct destination address
- Amount matches expected
- Transaction confirmed

Supported networks:
  usdt_trc / trx  → TronScan API
  usdt_bep        → BscScan API
  ton             → TonAPI
"""
import re
import aiohttp
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("tx_verifier")

REAL_CONTRACTS = {
    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": "USDT",
    "0x55d398326f99059ff775485246999027b3197955": "USDT",
}

@dataclass
class TxResult:
    ok: bool
    confirmed: bool
    amount: float
    currency: str
    to_address: str
    from_address: str
    is_real_token: bool
    error: str = ""
    explorer_url: str = ""


def extract_txid(link: str, network: str) -> Optional[str]:
    link = link.strip()
    if re.match(r'^[0-9a-fA-F]{64}$', link):
        return link
    if re.match(r'^0x[0-9a-fA-F]{64}$', link):
        return link
    m = re.search(r'tronscan\.org/#/transaction/([0-9a-fA-F]{64})', link)
    if m: return m.group(1)
    m = re.search(r'bscscan\.com/tx/(0x[0-9a-fA-F]{64})', link)
    if m: return m.group(1)
    m = re.search(r'(?:tonscan\.org|tonviewer\.com|explorer\.toncoin\.org)/transaction/([A-Za-z0-9+/=_-]{40,})', link)
    if m: return m.group(1)
    m = re.search(r'tonapi\.io/[^/]+/([A-Za-z0-9+/=_-]{40,})', link)
    if m: return m.group(1)
    return None


async def verify_tron(txid: str, expected_addr: str, coin_key: str) -> TxResult:
    url      = f"https://apilist.tronscanapi.com/api/transaction-info?hash={txid}"
    explorer = f"https://tronscan.org/#/transaction/{txid}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return TxResult(False, False, 0, "", "", "", False,
                                    f"TronScan API error: {r.status}", explorer)
                data = await r.json()

        confirmed     = data.get("confirmed", False)
        contract_type = data.get("contractType", 0)

        if coin_key == "trx":
            if contract_type != 1:
                return TxResult(False, confirmed, 0, "TRX", "", "", False,
                                "این تراکنش انتقال TRX نیست.", explorer)
            cd       = data.get("contractData", {})
            to_addr  = cd.get("to_address", "")
            amount   = float(cd.get("amount", 0)) / 1_000_000
            currency = "TRX"
            is_real  = True
        else:
            if contract_type != 31:
                return TxResult(False, confirmed, 0, "USDT", "", "", False,
                                "این تراکنش انتقال TRC20 نیست.", explorer)
            trc20    = (data.get("trc20TransferInfo") or [{}])[0]
            contract = trc20.get("contract_address", "")
            to_addr  = trc20.get("to_address", "")
            amount   = float(trc20.get("amount_str", "0")) / 1_000_000
            currency = trc20.get("symbol", "USDT")
            is_real  = contract.upper() == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t".upper()
            if not is_real:
                return TxResult(False, confirmed, amount, currency, to_addr, "", False,
                                f"توکن جعلی! قرارداد: {contract}", explorer)

        from_addr   = data.get("ownerAddress", "")
        addr_match  = to_addr.lower() == expected_addr.lower()
        return TxResult(
            ok           = confirmed and addr_match and is_real,
            confirmed    = confirmed,
            amount       = amount,
            currency     = currency,
            to_address   = to_addr,
            from_address = from_addr,
            is_real_token= is_real,
            error        = "" if (confirmed and addr_match) else (
                "آدرس مقصد مطابقت ندارد." if not addr_match else "تراکنش هنوز تایید نشده."
            ),
            explorer_url = explorer
        )
    except Exception as e:
        logger.exception(f"verify_tron error: {e}")
        return TxResult(False, False, 0, "", "", "", False, f"خطا در بررسی: {e}", explorer)


async def verify_bsc(txid: str, expected_addr: str) -> TxResult:
    explorer = f"https://bscscan.com/tx/{txid}"
    url      = f"https://api.bscscan.com/api?module=proxy&action=eth_getTransactionByHash&txhash={txid}&apikey=YourApiKeyToken"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.get(url) as r:
                data = await r.json()
        tx = data.get("result") or {}
        if not tx:
            return TxResult(False, False, 0, "USDT", "", "", False, "تراکنش یافت نشد.", explorer)
        input_data  = tx.get("input", "")
        to_addr_raw = ""
        amount      = 0.0
        is_real     = False
        if input_data.startswith("0xa9059cbb") and len(input_data) >= 138:
            to_addr_raw = "0x" + input_data[34:74]
            amount      = (int(input_data[74:138], 16) if len(input_data) >= 138 else 0) / 1e18
            contract    = tx.get("to", "").lower()
            is_real     = contract == "0x55d398326f99059ff775485246999027b3197955"
            if not is_real:
                return TxResult(False, False, amount, "USDT", to_addr_raw, tx.get("from",""), False,
                                f"توکن جعلی! قرارداد: {contract}", explorer)
        addr_match = to_addr_raw.lower() == expected_addr.lower()
        url2 = f"https://api.bscscan.com/api?module=proxy&action=eth_getTransactionReceipt&txhash={txid}&apikey=YourApiKeyToken"
        confirmed = False
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.get(url2) as r2:
                d2      = await r2.json()
                receipt = d2.get("result") or {}
                if receipt:
                    confirmed = receipt.get("status", "0x0") == "0x1"
        return TxResult(
            ok           = confirmed and addr_match and is_real,
            confirmed    = confirmed,
            amount       = amount,
            currency     = "USDT",
            to_address   = to_addr_raw,
            from_address = tx.get("from", ""),
            is_real_token= is_real,
            error        = "" if (confirmed and addr_match) else (
                "آدرس مقصد مطابقت ندارد." if not addr_match else "تراکنش هنوز تایید نشده."
            ),
            explorer_url = explorer
        )
    except Exception as e:
        logger.exception(f"verify_bsc error: {e}")
        return TxResult(False, False, 0, "USDT", "", "", False, f"خطا در بررسی: {e}", explorer)


async def verify_ton(txid: str, expected_addr: str) -> TxResult:
    explorer = f"https://tonscan.org/tx/{txid}"
    url      = f"https://tonapi.io/v2/blockchain/transactions/{txid}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.get(url, headers={"Accept": "application/json"}) as r:
                if r.status != 200:
                    return TxResult(False, False, 0, "TON", "", "", False,
                                    f"TonAPI error: {r.status}", explorer)
                data = await r.json()
        success   = data.get("success", False)
        in_msg    = data.get("in_msg", {})
        to_addr   = in_msg.get("destination", {}).get("address", "")
        from_addr = in_msg.get("source", {}).get("address", "")
        value     = float(in_msg.get("value", 0)) / 1e9
        addr_match = to_addr.lower() == expected_addr.lower()
        return TxResult(
            ok           = success and addr_match,
            confirmed    = success,
            amount       = value,
            currency     = "TON",
            to_address   = to_addr,
            from_address = from_addr,
            is_real_token= True,
            error        = "" if (success and addr_match) else (
                "آدرس مقصد مطابقت ندارد." if not addr_match else "تراکنش ناموفق یا تایید نشده."
            ),
            explorer_url = explorer
        )
    except Exception as e:
        logger.exception(f"verify_ton error: {e}")
        return TxResult(False, False, 0, "TON", "", "", False, f"خطا در بررسی: {e}", explorer)


async def verify_tx(link: str, coin_key: str, expected_addr: str, expected_usd: float = 0) -> TxResult:
    txid = extract_txid(link, coin_key)
    if not txid:
        return TxResult(False, False, 0, "", "", "", False,
                        "لینک یا هش تراکنش معتبر نیست. لطفاً لینک کامل از explorer ارسال کنید.")
    if coin_key in ("usdt_trc", "trx"):
        return await verify_tron(txid, expected_addr, coin_key)
    elif coin_key == "usdt_bep":
        return await verify_bsc(txid, expected_addr)
    elif coin_key == "ton":
        return await verify_ton(txid, expected_addr)
    else:
        return TxResult(False, False, 0, "", "", "", False, f"شبکه {coin_key} پشتیبانی نمیشه.")
