# ═══════════════════════════════════════════════════════════════════
# 1. utils.py - Complete file with block override helper
# ═══════════════════════════════════════════════════════════════════

import datetime as dt
import decimal as dec
from typing import Tuple

from models import CommissionFees

def to_decimal(v: str | dec.Decimal | None) -> dec.Decimal | None:
    """Convert value to Decimal, handling None and existing Decimals"""
    if v is None or isinstance(v, dec.Decimal):
        return v
    return dec.Decimal(v)

def calculate_costs(trade_type: str, qty: int, cfg: dict) -> CommissionFees:
    """Calculate commission and fees for a trade"""
    costs_config = cfg.get("costs", {}).get(trade_type.upper(), {})
    
    commission_rate = to_decimal(costs_config.get("commission_per_contract", "0"))
    exchange_rate = to_decimal(costs_config.get("exchange_fees_per_contract", "0"))
    regulatory_rate = to_decimal(costs_config.get("regulatory_fees_per_contract", "0"))
    
    return CommissionFees(
        commission=commission_rate * qty,
        exchange_fees=exchange_rate * qty,
        regulatory_fees=regulatory_rate * qty
    )

def blocked_for_options(cfg: dict) -> Tuple[bool, str | None]:
    """Check if current time falls within any configured option block periods"""
    now = dt.datetime.now().time()
    
    if "option_block" in cfg:
        start = dt.time.fromisoformat(cfg["option_block"]["start"])
        end = dt.time.fromisoformat(cfg["option_block"]["end"])
        if start <= now <= end:
            return True, cfg["option_block"].get("name", "Option Block")
    
    if "option_blocks" in cfg:
        for block in cfg["option_blocks"]:
            start = dt.time.fromisoformat(block["start"])
            end = dt.time.fromisoformat(block["end"])
            
            if start > end:  # Crosses midnight
                if now >= start or now <= end:
                    return True, block.get("name", "Option Block")
            else:  # Same day block
                if start <= now <= end:
                    return True, block.get("name", "Option Block")
    
    return False, None

def check_time_against_blocks(check_time: dt.time, cfg: dict) -> bool:
    """Check if a specific time falls within any configured option block periods"""
    
    # Check legacy single block
    if "option_block" in cfg:
        start = dt.time.fromisoformat(cfg["option_block"]["start"])
        end = dt.time.fromisoformat(cfg["option_block"]["end"])
        if start <= check_time <= end:
            return True
    
    # Check multiple blocks
    if "option_blocks" in cfg:
        for block in cfg["option_blocks"]:
            start = dt.time.fromisoformat(block["start"])
            end = dt.time.fromisoformat(block["end"])
            
            if start > end:  # Crosses midnight
                if check_time >= start or check_time <= end:
                    return True
            else:  # Same day block
                if start <= check_time <= end:
                    return True
    
    return False

def calc_trade_pnl(tr, use_net=True):
    """Calculate total PnL for a trade (net by default, gross if use_net=False)"""
    if use_net:
        return tr.net_pnl()
    else:
        return tr.gross_pnl()

def get_open_qty(tr) -> int:
    """Get the total open quantity for a trade"""
    return sum(l.qty for l in tr.legs if l.exit is None)

def can_partial_close(tr, qty: int) -> bool:
    """Check if we can close the specified quantity"""
    open_qty = get_open_qty(tr)
    return 0 < qty <= open_qty

def now_utc() -> dt.datetime:
    """Get current UTC datetime"""
    return dt.datetime.now(dt.timezone.utc)


