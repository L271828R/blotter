# ═══════════════════════════════════════════════════════════════════
# models.py - Core data models
# ═══════════════════════════════════════════════════════════════════

from __future__ import annotations
import decimal as dec
from dataclasses import dataclass, field

@dataclass
class Risk:
    econ: bool
    earnings: bool
    bond: bool
    note: str = ""
    
    def empty(self) -> bool:
        return not (self.econ or self.earnings or self.bond or self.note.strip())

@dataclass
class CommissionFees:
    """Commission and fees structure"""
    commission: dec.Decimal = dec.Decimal('0')
    exchange_fees: dec.Decimal = dec.Decimal('0')
    regulatory_fees: dec.Decimal = dec.Decimal('0')
    
    def total(self) -> dec.Decimal:
        """Total cost of commission + all fees"""
        return self.commission + self.exchange_fees + self.regulatory_fees

@dataclass
class Leg:
    symbol: str
    side: str
    qty: int
    entry: dec.Decimal
    exit: dec.Decimal | None = None
    multiplier: int = 50
    entry_costs: CommissionFees = field(default_factory=CommissionFees)
    exit_costs: CommissionFees | None = None
    
    def gross_pnl(self) -> dec.Decimal | None:
        """PnL before commission and fees"""
        if self.exit is None:
            return None
        signed = -1 if self.side == "SELL" else 1
        return (self.exit - self.entry) * self.multiplier * self.qty * signed
    
    def net_pnl(self) -> dec.Decimal | None:
        """PnL after commission and fees"""
        gross = self.gross_pnl()
        if gross is None:
            return None
        
        total_costs = self.entry_costs.total()
        if self.exit_costs:
            total_costs += self.exit_costs.total()
        
        return gross - total_costs
    
    def total_costs(self) -> dec.Decimal:
        """Total commission and fees for this leg"""
        costs = self.entry_costs.total()
        if self.exit_costs:
            costs += self.exit_costs.total()
        return costs

@dataclass 
class Trade:
    id: str
    ts: str
    typ: str
    strat: str
    legs: list[Leg] = field(default_factory=list)
    risk: Risk | None = None
    status: str = "OPEN"
    pnl: dec.Decimal | None = None
    pnl_2h: dec.Decimal | None = None
    pnl_2h_recorded: bool = False
    pnl_2h_timestamp: str | None = None
    original_qty: int | None = None
    
    def gross_pnl(self) -> dec.Decimal | None:
        """Total gross PnL (before costs) for the trade"""
        if any(l.gross_pnl() is None for l in self.legs):
            return None
        return sum(l.gross_pnl() for l in self.legs)
    
    def net_pnl(self) -> dec.Decimal | None:
        """Total net PnL (after costs) for the trade"""
        if any(l.net_pnl() is None for l in self.legs):
            return None
        return sum(l.net_pnl() for l in self.legs)
    
    def total_costs(self) -> dec.Decimal:
        """Total commission and fees for the trade"""
        return sum(l.total_costs() for l in self.legs)

