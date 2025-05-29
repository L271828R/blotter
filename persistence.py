# persistence.py - Data loading and saving
"""Data persistence layer for the trade blotter"""

import json
import pathlib
import datetime as dt
from dataclasses import asdict
from typing import List

from models import Trade, Leg, Risk
from utils import to_decimal
from config import load_config

# File paths
BOOK = pathlib.Path("trades.json")
INBOX = pathlib.Path("inbox")
ARCHIVE = pathlib.Path("archive")

# Ensure directories exist
INBOX.mkdir(exist_ok=True)
ARCHIVE.mkdir(exist_ok=True)

def make_leg(d: dict, cfg: dict) -> Leg:
    """Create a Leg from dictionary data"""
    return Leg(
        symbol=d["symbol"],
        side=d["side"],
        qty=d["qty"],
        entry=to_decimal(d["entry"]),
        exit=to_decimal(d.get("exit")),
        multiplier=d.get(
            "multiplier",
            cfg["multipliers"].get(d["symbol"].split("_")[0], 1),
        ),
    )

def load_book() -> List[Trade]:
    """Load trades from the JSON file"""
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
            }]
            t.pop("pnl", None)
            t["typ"] = t.get("typ", "FUTURE" if "_" not in symbol else "OPTION")
        
        # Convert leg entries to proper types
        for leg in t["legs"]:
            leg["entry"] = to_decimal(leg["entry"])
            leg["exit"] = to_decimal(leg.get("exit"))
        
        # Extract allowed fields
        allowed = {
            "id", "ts", "typ", "strat", "risk", "status", "pnl",
            "pnl_2h", "pnl_2h_recorded", "pnl_2h_timestamp", "original_qty"
        }
        core = {k: v for k, v in t.items() if k in allowed}
        
        # Convert risk dict to Risk object if needed
        if core.get("risk") and not isinstance(core["risk"], Risk):
            core["risk"] = Risk(**core["risk"])
        
        # Create Trade object
        trade = Trade(**core, legs=[Leg(**l) for l in t["legs"]])
        fixed.append(trade)
    
    return fixed

def save_book(book: List[Trade]):
    """Save trades to the JSON file"""
    BOOK.write_text(json.dumps([asdict(t) for t in book], default=str, indent=2))

def write_single_trade_file(tr: Trade):
    """Write a single trade to the inbox directory"""
    fn = f"{dt.datetime.now():%y%m%d}-{tr.id}.trade.json"
    INBOX.joinpath(fn).write_text(json.dumps(asdict(tr), default=str))

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
        
        # Move processed file to archive
        fp.rename(ARCHIVE / fp.name)
        if added > 0:
            print(f"📁 Imported {added} trade(s) from {fp.name}")
        total_added += added
    
    return total_added
