# trade_operations.py - Core trade operations with commission and fees
"""Core trade operations like opening and closing trades with commission and fees"""

import uuid
import typer
import rich
from typing import Optional

from models import Trade, Leg, Risk, CommissionFees
from utils import to_decimal, blocked_for_options, now_utc, calc_trade_pnl, get_open_qty, can_partial_close, calculate_costs
from persistence import save_book, write_single_trade_file

class TradeOperations:
    """Handles core trade operations like opening and closing with commission and fees"""
    
    def __init__(self, book: list, cfg: dict):
        self.book = book
        self.cfg = cfg
    
    def open_bull_put_spread(self, qty: Optional[int] = None, strat: str = "BULL-PUT"):
        """Open a bull-put spread with commission and fees"""
        is_blocked, block_name = blocked_for_options(self.cfg)
        if is_blocked:
            rich.print(f"[red]No options during {block_name}[/]")
            raise typer.Exit()
        
        # Get risk assessment
        econ = typer.confirm("Economic event?")
        earn = typer.confirm("Big earnings / Earnings season?")
        bond = typer.confirm("Bond auction 1PM (no bounce)?")
        note = typer.prompt("Note", default="")
        risk = Risk(econ, earn, bond, note)
        
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]")
            raise typer.Exit()
        
        qty = qty or int(typer.prompt("Quantity", default="1"))
        
        typer.echo("---- Bull‑Put spread ----")
        s_sym = typer.prompt("Short‑put (SELL) symbol")
        s_pr = to_decimal(typer.prompt("Credit price"))
        l_sym = typer.prompt("Long‑put  (BUY)  symbol")
        l_pr = to_decimal(typer.prompt("Debit price"))
        
        # Calculate entry costs for both legs
        short_costs = calculate_costs("OPTION", qty, self.cfg)
        long_costs = calculate_costs("OPTION", qty, self.cfg)
        
        legs = [
            Leg(s_sym, "SELL", qty, s_pr, entry_costs=short_costs),
            Leg(l_sym, "BUY", qty, l_pr, entry_costs=long_costs)
        ]
        
        trade = Trade(
            id=str(uuid.uuid4())[:8],
            ts=now_utc().isoformat(),
            typ="OPTION_SPREAD",
            strat=strat,
            legs=legs,
            risk=risk
        )
        
        self.book.append(trade)
        save_book(self.book)
        write_single_trade_file(trade)
        
        # Show cost breakdown
        total_costs = trade.total_costs()
        rich.print(f":rocket: Opened [cyan]{trade.id}[/] Bull‑Put x{qty}")
        rich.print(f":money_with_wings: Entry costs: ${total_costs:.2f}")
        rich.print(f"  • Commission: ${short_costs.commission + long_costs.commission:.2f}")
        rich.print(f"  • Exchange fees: ${short_costs.exchange_fees + long_costs.exchange_fees:.2f}")
        if short_costs.regulatory_fees + long_costs.regulatory_fees > 0:
            rich.print(f"  • Regulatory fees: ${short_costs.regulatory_fees + long_costs.regulatory_fees:.2f}")
        
        return trade
    
    def open_bear_call_spread(self, qty: Optional[int] = None):
        """Open a bear-call spread with commission and fees"""
        is_blocked, block_name = blocked_for_options(self.cfg)
        if is_blocked:
            rich.print(f"[red]No options during {block_name}[/]")
            raise typer.Exit()
        
        # Get risk assessment
        econ = typer.confirm("Economic event?")
        earn = typer.confirm("Big earnings?")
        bond = typer.confirm("Bond auction?")
        note = typer.prompt("Note", default="")
        risk = Risk(econ, earn, bond, note)
        
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]")
            raise typer.Exit()
        
        qty = qty or int(typer.prompt("Quantity", default="1"))
        
        typer.echo("---- Bear‑Call spread ----")
        s_sym = typer.prompt("Short‑call (SELL) symbol")
        s_pr = to_decimal(typer.prompt("Credit price"))
        l_sym = typer.prompt("Long‑call  (BUY)  symbol")
        l_pr = to_decimal(typer.prompt("Debit price"))
        
        # Calculate entry costs for both legs
        short_costs = calculate_costs("OPTION", qty, self.cfg)
        long_costs = calculate_costs("OPTION", qty, self.cfg)
        
        legs = [
            Leg(s_sym, "SELL", qty, s_pr, entry_costs=short_costs),
            Leg(l_sym, "BUY", qty, l_pr, entry_costs=long_costs)
        ]
        
        trade = Trade(
            id=str(uuid.uuid4())[:8],
            ts=now_utc().isoformat(),
            typ="OPTION_SPREAD",
            strat="BEAR-CALL",
            legs=legs,
            risk=risk
        )
        
        self.book.append(trade)
        save_book(self.book)
        write_single_trade_file(trade)
        
        # Show cost breakdown
        total_costs = trade.total_costs()
        rich.print(f":rocket: Opened [cyan]{trade.id}[/] Bear‑Call x{qty}")
        rich.print(f":money_with_wings: Entry costs: ${total_costs:.2f}")
        rich.print(f"  • Commission: ${short_costs.commission + long_costs.commission:.2f}")
        rich.print(f"  • Exchange fees: ${short_costs.exchange_fees + long_costs.exchange_fees:.2f}")
        if short_costs.regulatory_fees + long_costs.regulatory_fees > 0:
            rich.print(f"  • Regulatory fees: ${short_costs.regulatory_fees + long_costs.regulatory_fees:.2f}")
        
        return trade
    
    def open_single_leg_trade(self, strat: str, typ: str, side: str, symbol: str, qty: int, price: str):
        """Open a single-leg trade (futures or options) with commission and fees"""
        typ_u = typ.upper()
        
        if typ_u.startswith("OPTION"):
            is_blocked, block_name = blocked_for_options(self.cfg)
            if is_blocked:
                rich.print(f"[red]No options during {block_name}[/]")
                raise typer.Exit()
        
        risk = None
        if typ_u.startswith("OPTION"):
            # Get risk assessment for options
            econ = typer.confirm("Economic event?")
            earn = typer.confirm("Big earnings?")
            bond = typer.confirm("Bond auction?")
            note = typer.prompt("Note", default="")
            risk = Risk(econ, earn, bond, note)
            
            if risk.empty():
                rich.print("[red]Need risk checklist/note[/]")
                raise typer.Exit()
        
        # Calculate entry costs
        trade_type = "FUTURE" if typ_u == "FUTURE" else "OPTION"
        entry_costs = calculate_costs(trade_type, qty, self.cfg)
        
        leg = Leg(
            symbol=symbol,
            side=side.upper(),
            qty=qty,
            entry=to_decimal(price),
            multiplier=self.cfg["multipliers"].get(symbol.split("_")[0], 1),
            entry_costs=entry_costs
        )
        
        trade = Trade(
            id=str(uuid.uuid4())[:8],
            ts=now_utc().isoformat(),
            typ=typ_u,
            strat=strat,
            legs=[leg],
            risk=risk
        )
        
        self.book.append(trade)
        save_book(self.book)
        write_single_trade_file(trade)
        
        # Show cost breakdown
        rich.print(f":rocket: Opened [cyan]{trade.id}[/]")
        rich.print(f":money_with_wings: Entry costs: ${entry_costs.total():.2f}")
        rich.print(f"  • Commission: ${entry_costs.commission:.2f}")
        rich.print(f"  • Exchange fees: ${entry_costs.exchange_fees:.2f}")
        if entry_costs.regulatory_fees > 0:
            rich.print(f"  • Regulatory fees: ${entry_costs.regulatory_fees:.2f}")
        
        return trade
    
    def close_trade_partial(self, trade_id: str, qty: Optional[int] = None):
        """Close a trade completely or partially with commission and fees"""
        tr = self._find_trade(trade_id)
        if not tr:
            rich.print("[red]ID not found[/]")
            return False
        
        if tr.status == "CLOSED":
            rich.print("[yellow]Already closed[/]")
            return False
        
        # Check BULL-PUT-OVERNIGHT 2H PnL requirement
        if tr.strat == "BULL-PUT-OVERNIGHT" and not tr.pnl_2h_recorded:
            rich.print("[red]❌ Cannot close BULL-PUT-OVERNIGHT trade without 2H PnL data![/]")
            rich.print(f"Please run: blotter.py pnl2h {trade_id}")
            return False
        
        # Get current open quantity
        open_qty = get_open_qty(tr)
        
        # Store original quantity on first partial close (FIXED)
        if tr.original_qty is None:
            tr.original_qty = open_qty  # Use open_qty, not total qty
        
        # Determine quantity to close
        if qty is None:
            rich.print(f"Current open quantity: {open_qty}")
            if open_qty > 1:
                qty = int(typer.prompt(f"Quantity to close (1-{open_qty})", default=str(open_qty)))
            else:
                qty = open_qty
        
        # Validate quantity
        if not can_partial_close(tr, qty):
            rich.print(f"[red]Invalid quantity. Can close 1-{open_qty} contracts[/]")
            return False
        
        # Handle partial vs full close
        if qty == open_qty:
            self._full_close(tr)
        else:
            self._partial_close(tr, qty)
        
        save_book(self.book)
        write_single_trade_file(tr)
        return True
    
    def _find_trade(self, trade_id: str):
        """Find a trade by ID"""
        for trade in self.book:
            if trade.id == trade_id:
                return trade
        return None
    
    def _full_close(self, tr):
        """Handle full close of a trade with exit costs"""
        # Close all legs and calculate exit costs
        for l in tr.legs:
            if l.exit is None:  # Only close open legs
                l.exit = to_decimal(typer.prompt(f"Exit price for {l.symbol} [{l.side}]"))
                
                # Calculate exit costs
                trade_type = "FUTURE" if tr.typ == "FUTURE" else "OPTION"
                l.exit_costs = calculate_costs(trade_type, l.qty, self.cfg)
        
        tr.pnl = calc_trade_pnl(tr)  # This will use net PnL
        tr.status = "CLOSED"
        
        # Show detailed PnL breakdown
        gross_pnl = tr.gross_pnl()
        net_pnl = tr.net_pnl()
        total_costs = tr.total_costs()
        
        rich.print(f":chart_with_upwards_trend: Gross PnL: ${gross_pnl:.2f}")
        rich.print(f":money_with_wings: Total costs: ${total_costs:.2f}")
        rich.print(f":check_mark: Net PnL: [bold]${net_pnl:.2f}[/]")
        
        # Show 2H vs final PnL comparison for BULL-PUT-OVERNIGHT
        if tr.strat == "BULL-PUT-OVERNIGHT" and tr.pnl_2h is not None:
            pnl_change = net_pnl - tr.pnl_2h
            rich.print(f":arrow_right: Change from 2H: ${pnl_change:.2f}")
    
    def _partial_close(self, tr, qty):
        """Handle partial close of a trade with exit costs"""
        exit_price = to_decimal(typer.prompt("Exit price for partial close"))
        
        # Calculate exit costs for the partial close
        trade_type = "FUTURE" if tr.typ == "FUTURE" else "OPTION"
        exit_costs = calculate_costs(trade_type, qty, self.cfg)
        
        # Create new closed trade for the closed portion
        closed_legs = []
        for l in tr.legs:
            if l.exit is None:  # Only process open legs
                # Create a proportional entry cost for this partial close
                entry_cost_ratio = qty / l.qty
                partial_entry_costs = CommissionFees(
                    commission=l.entry_costs.commission * entry_cost_ratio,
                    exchange_fees=l.entry_costs.exchange_fees * entry_cost_ratio,
                    regulatory_fees=l.entry_costs.regulatory_fees * entry_cost_ratio
                )
                
                closed_leg = Leg(
                    symbol=l.symbol,
                    side=l.side,
                    qty=qty,
                    entry=l.entry,
                    exit=exit_price,
                    multiplier=l.multiplier,
                    entry_costs=partial_entry_costs,
                    exit_costs=exit_costs
                )
                closed_legs.append(closed_leg)
                
                # Reduce quantity and adjust entry costs in original leg
                remaining_ratio = (l.qty - qty) / l.qty
                l.entry_costs = CommissionFees(
                    commission=l.entry_costs.commission * remaining_ratio,
                    exchange_fees=l.entry_costs.exchange_fees * remaining_ratio,
                    regulatory_fees=l.entry_costs.regulatory_fees * remaining_ratio
                )
                l.qty -= qty
        
        # Create the closed trade record
        partial_count = len([t for t in self.book if t.id.startswith(tr.id + '-P')]) + 1
        closed_trade = Trade(
            id=f"{tr.id}-P{partial_count}",
            ts=now_utc().isoformat(),
            typ=tr.typ,
            strat=tr.strat,
            legs=closed_legs,
            risk=tr.risk,
            status="CLOSED",
            pnl=calc_trade_pnl(closed_trade),
            original_qty=qty  # FIXED: Set to closed quantity
        )
        
        self.book.append(closed_trade)
        write_single_trade_file(closed_trade)
        
        # Show detailed partial close breakdown
        partial_gross = closed_trade.gross_pnl()
        partial_net = closed_trade.net_pnl()
        partial_costs = closed_trade.total_costs()
        remaining_qty = get_open_qty(tr)
        
        rich.print(f":scissors: Partially closed {qty} of {tr.original_qty} contracts from {tr.id}")
        rich.print(f":chart_with_upwards_trend: Partial gross PnL: ${partial_gross:.2f}")
        rich.print(f":money_with_wings: Partial costs: ${partial_costs:.2f}")
        rich.print(f":moneybag: Partial net PnL: [bold]${partial_net:.2f}[/]")
        rich.print(f":hourglass: Remaining open: {remaining_qty} contracts")
