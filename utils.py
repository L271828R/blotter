# utils.py - Updated with cost calculation functions and strategy-aware blocking
"""Utility functions for the trade blotter"""
import datetime as dt
import decimal as dec
from typing import Tuple
# FIXED: Use absolute import instead of relative import
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

def blocked_for_options(cfg: dict, strategy: str = None) -> Tuple[bool, str | None]:
    """
    Check if current time falls within any configured option block periods
    Returns (is_blocked, block_name_or_reason)
    
    Args:
        cfg: Configuration dictionary
        strategy: Optional strategy name to check for exemptions
    """
    now = dt.datetime.now().time()
    
    # Check if strategy is exempt from blocks (using your "exemption" format)
    if strategy:
        exempt_strategies = cfg.get("exemption", [])
        
        if strategy.upper() in [s.upper() for s in exempt_strategies]:
            return False, f"Exempt: {strategy} is allowed during blocks"
    
    # Handle legacy single block configuration
    if "option_block" in cfg:
        start = dt.time.fromisoformat(cfg["option_block"]["start"])
        end = dt.time.fromisoformat(cfg["option_block"]["end"])
        if start <= now <= end:
            return True, cfg["option_block"].get("name", "Option Block")
    
    # Handle multiple blocks configuration
    if "option_blocks" in cfg:
        for block in cfg["option_blocks"]:
            start = dt.time.fromisoformat(block["start"])
            end = dt.time.fromisoformat(block["end"])
            
            # Handle overnight blocks (e.g., 18:00 to 21:15 next day)
            if start > end:  # Crosses midnight
                if now >= start or now <= end:
                    return True, block.get("name", "Option Block")
            else:  # Same day block
                if start <= now <= end:
                    return True, block.get("name", "Option Block")
    
    return False, None

def is_strategy_exempt(cfg: dict, strategy: str) -> Tuple[bool, str]:
    """
    Check if a strategy is exempt from option blocks (using your exemption format)
    Returns (is_exempt, reason)
    """
    exempt_strategies = cfg.get("exemption", [])
    
    if strategy.upper() in [s.upper() for s in exempt_strategies]:
        return True, f"{strategy} is allowed during blocks"
    
    return False, "Not exempt"

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
