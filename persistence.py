# ═══════════════════════════════════════════════════════════════════
# persistence.py - Data loading/saving with migration
# ═══════════════════════════════════════════════════════════════════

import json
import pathlib
import datetime as dt
from dataclasses import asdict
from typing import List

from models import Trade, Leg, Risk, CommissionFees
from utils import to_decimal
from config import load_config

BOOK = pathlib.Path("trades.json")
INBOX = pathlib.Path("inbox")
ARCHIVE = pathlib.Path("archive")

INBOX.mkdir(exist_ok=True)
ARCHIVE.mkdir(exist_ok=True)

def make_leg(d: dict, cfg: dict) -> Leg:
    """Create a Leg from dictionary data with proper CommissionFees objects"""
    entry_costs = d.get("entry_costs", {})
    if isinstance(entry_costs, dict):
        entry_costs = CommissionFees(
            commission=to_decimal(entry_costs.get("commission", "0")),
            exchange_fees=to_decimal(entry_costs.get("exchange_fees", "0")),
            regulatory_fees=to_decimal(entry_costs.get("regulatory_fees", "0"))
        )
    elif entry_costs is None:
        entry_costs = CommissionFees()
    
    exit_costs = d.get("exit_costs")
    if isinstance(exit_costs, dict):
        exit_costs = CommissionFees(
            commission=to_decimal(exit_costs.get("commission", "0")),
            exchange_fees=to_decimal(exit_costs.get("exchange_fees", "0")),
            regulatory_fees=to_decimal(exit_costs.get("regulatory_fees", "0"))
        )
    
    return Leg(
        symbol=d["symbol"],
        side=d["side"],
        qty=d["qty"],
        entry=to_decimal(d["entry"]),
        exit=to_decimal(d.get("exit")),
        multiplier=d.get("multiplier", cfg["multipliers"].get(d["symbol"].split("_")[0], 1)),
        entry_costs=entry_costs,
        exit_costs=exit_costs
    )

def load_book() -> List[Trade]:
    """Load trades from the JSON file with data migration"""
    if not BOOK.exists():
        return []
    
    cfg = load_config()
    raw = json.load(BOOK.open())
    fixed: List[Trade] = []
    
    for t in raw:
        # Handle legacy format conversion
        if "legs" not in t:
            symbol = t.pop("instr")
            mult = cfg["multipliers"].get(symbol.split("_")[0], 1)
            t["legs"] = [{
                "symbol": symbol,
                "side": t.pop("side", "BUY"),
                "qty": t.pop("qty", 1),
                "entry": to_decimal(t.pop("price")),
                "exit": to_decimal(t.pop("exit_price", None)),
                "multiplier": mult,
                "entry_costs": {},
                "exit_costs": None
            }]
            t.pop("pnl", None)
            t["typ"] = t.get("typ", "FUTURE" if "_" not in symbol else "OPTION")
        
        for leg in t["legs"]:
            leg["entry"] = to_decimal(leg["entry"])
            leg["exit"] = to_decimal(leg.get("exit"))
            if "entry_costs" not in leg:
                leg["entry_costs"] = {}
            if "exit_costs" not in leg:
                leg["exit_costs"] = None
        
        allowed = {
            "id", "ts", "typ", "strat", "risk", "status", "pnl",
            "pnl_2h", "pnl_2h_recorded", "pnl_2h_timestamp", "original_qty"
        }
        core = {k: v for k, v in t.items() if k in allowed}
        
        if core.get("risk") and not isinstance(core["risk"], Risk):
            core["risk"] = Risk(**core["risk"])
        
        if isinstance(core.get("pnl"), str):
            core["pnl"] = to_decimal(core["pnl"])
        if isinstance(core.get("pnl_2h"), str):
            core["pnl_2h"] = to_decimal(core["pnl_2h"])
        
        trade = Trade(**core, legs=[make_leg(l, cfg) for l in t["legs"]])
        fixed.append(trade)
    
    return fixed

def save_book(book: List[Trade]):
    """Save trades to the JSON file"""
    def serialize_commission_fees(obj):
        if isinstance(obj, CommissionFees):
            return {
                "commission": str(obj.commission),
                "exchange_fees": str(obj.exchange_fees),
                "regulatory_fees": str(obj.regulatory_fees)
            }
        if isinstance(obj, (dt.datetime, dt.date)):
            return obj.isoformat()
        return str(obj)
    
    data = []
    for trade in book:
        trade_dict = asdict(trade)
        data.append(trade_dict)
    
    BOOK.write_text(json.dumps(data, default=serialize_commission_fees, indent=2))

def write_single_trade_file(tr: Trade):
    """Write a single trade to the inbox directory"""
    fn = f"{dt.datetime.now():%y%m%d}-{tr.id}.trade.json"
    
    def serialize_commission_fees(obj):
        if isinstance(obj, CommissionFees):
            return {
                "commission": str(obj.commission),
                "exchange_fees": str(obj.exchange_fees),
                "regulatory_fees": str(obj.regulatory_fees)
            }
        return str(obj)
    
    trade_dict = asdict(tr)
    INBOX.joinpath(fn).write_text(json.dumps(trade_dict, default=serialize_commission_fees, indent=2))

def import_inbox_files(book: List[Trade]) -> int:
    """Import trade files from inbox and return number of trades added"""
    cfg = load_config()
    seen = {t.id for t in book}
    total_added = 0
    
    for fp in INBOX.glob("*.json"):
        payload = json.loads(fp.read_text())
        raws = payload if isinstance(payload, list) else [payload]
        added = 0
        
        for raw in raws:
            if raw.get("risk") and not isinstance(raw["risk"], Risk):
                raw["risk"] = Risk(**raw["risk"])
            raw["legs"] = [make_leg(l, cfg) for l in raw["legs"]]
            tr = Trade(**raw)
            
            if tr.id not in seen:
                book.append(tr)
                seen.add(tr.id)
                added += 1
        
        fp.rename(ARCHIVE / fp.name)
        if added > 0:
            print(f"📁 Imported {added} trade(s) from {fp.name}")
        total_added += added
    
    return total_added

