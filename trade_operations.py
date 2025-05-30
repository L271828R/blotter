# ═══════════════════════════════════════════════════════════════════
# trade_operations.py - Core trade operations with configurable prompts
# ═══════════════════════════════════════════════════════════════════

import uuid
import typer
import rich
from typing import Optional, Dict, Any

from models import Trade, Leg, Risk, CommissionFees
from utils import to_decimal, blocked_for_options, now_utc, calc_trade_pnl, get_open_qty, can_partial_close, calculate_costs
from persistence import save_book, write_single_trade_file

class TradeOperations:
    """Handles core trade operations like opening and closing with configurable prompts"""
    
    def __init__(self, book: list, cfg: dict):
        self.book = book
        self.cfg = cfg
    
    def _get_risk_assessment(self, strategy: str = None) -> Risk:
        """Get risk assessment using configurable prompts"""
        prompts = self.cfg.get("prompts", {})
        
        # Use configurable prompts or fallback to defaults
        econ_prompt = prompts.get("economic_events", "Economic event?")
        earn_prompt = prompts.get("earnings", "Big earnings / Earnings season?")
        auction_prompt = prompts.get("auction", "Bond auction 1PM (no bounce)?")
        
        # Get responses
        econ = typer.confirm(econ_prompt)
        earn = typer.confirm(earn_prompt)
        bond = typer.confirm(auction_prompt)
        
        # Additional configurable prompts if enabled
        additional_info = []
        
        if self.cfg.get("prompt_categories", {}).get("market_analysis", True):
            # Market conditions
            market_prompt = prompts.get("market_conditions", "Current market conditions/sentiment?")
            market_response = typer.prompt(market_prompt, default="", show_default=False)
            if market_response.strip():
                additional_info.append(f"Market: {market_response}")
            
            # Volatility
            vol_prompt = prompts.get("volatility", "VIX level and volatility environment?")
            vol_response = typer.prompt(vol_prompt, default="", show_default=False)
            if vol_response.strip():
                additional_info.append(f"Vol: {vol_response}")
        
        # Strategy-specific prompts
        if strategy and self.cfg.get("prompt_categories", {}).get("strategy_specific", True):
            strategy_prompts = self._get_strategy_prompts(strategy)
            for prompt_key, prompt_text in strategy_prompts.items():
                response = typer.prompt(prompt_text, default="", show_default=False)
                if response.strip():
                    additional_info.append(f"{prompt_key}: {response}")
        
        # Risk management prompts
        if self.cfg.get("prompt_categories", {}).get("risk_management", True):
            pos_size_prompt = prompts.get("position_size", "Position size as % of account?")
            pos_size = typer.prompt(pos_size_prompt, default="", show_default=False)
            if pos_size.strip():
                additional_info.append(f"Position size: {pos_size}")
            
            max_loss_prompt = prompts.get("max_loss", "Maximum acceptable loss for this trade?")
            max_loss = typer.prompt(max_loss_prompt, default="", show_default=False)
            if max_loss.strip():
                additional_info.append(f"Max loss: {max_loss}")
        
        # Main note prompt
        note_prompt = "Note"
        if additional_info:
            note_prompt += f" (Additional context: {'; '.join(additional_info)})"
        
        note = typer.prompt(note_prompt, default="")
        
        # Combine additional info with note
        if additional_info and note:
            note = f"{note} | {'; '.join(additional_info)}"
        elif additional_info and not note:
            note = '; '.join(additional_info)
        
        return Risk(econ, earn, bond, note)
    
    def _get_strategy_prompts(self, strategy: str) -> Dict[str, str]:
        """Get strategy-specific prompts"""
        prompts = self.cfg.get("prompts", {})
        strategy_key = strategy.lower().replace("-", "_")
        
        return prompts.get(strategy_key, {})
    
    def _show_fed_speakers_prompt(self):
        """Show Fed speakers prompt if configured"""
        prompts = self.cfg.get("prompts", {})
        if "fed_speakers" in prompts:
            fed_prompt = prompts["fed_speakers"]
            response = typer.prompt(fed_prompt, default="", show_default=False)
            if response.strip():
                rich.print(f"[yellow]Fed speakers: {response}[/]")
    
    def open_bull_put_spread(self, qty: Optional[int] = None, strat: str = "BULL-PUT", dry_run: bool = False):
        """Open a bull-put spread with configurable prompts"""
        # Check blocks only if not in dry run mode
        if not dry_run:
            is_blocked, block_name = blocked_for_options(self.cfg)
            if is_blocked:
                rich.print(f"[red]No options during {block_name}[/]")
                raise typer.Exit()
        elif blocked_for_options(self.cfg)[0]:
            # Show block warning in dry run mode but continue
            is_blocked, block_name = blocked_for_options(self.cfg)
            rich.print(f"[yellow]⚠️  Would normally be blocked: {block_name} (ignored in dry-run)[/]")
        
        # Show Fed speakers prompt if configured
        self._show_fed_speakers_prompt()
        
        # Get risk assessment with configurable prompts
        risk = self._get_risk_assessment(strat)
        
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]")
            raise typer.Exit()
        
        qty = qty or int(typer.prompt("Quantity", default="1"))
        
        # Strategy-specific prompts for bull put
        strategy_prompts = self._get_strategy_prompts("bull_put")
        if strategy_prompts:
            rich.print(f"\n[bold cyan]Bull Put Spread Setup[/]")
            for prompt_key, prompt_text in strategy_prompts.items():
                response = typer.prompt(prompt_text, default="", show_default=False)
                if response.strip():
                    rich.print(f"[dim]{prompt_key}: {response}[/]")
        
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
        
        # Only save if not in dry run mode
        if not dry_run:
            self.book.append(trade)
            save_book(self.book)
            write_single_trade_file(trade)
            save_status = "saved"
        else:
            save_status = "NOT SAVED (dry-run)"
        
        # Show cost breakdown
        total_costs = trade.total_costs()
        rich.print(f":rocket: {'[DRY RUN] ' if dry_run else ''}Opened [cyan]{trade.id}[/] Bull‑Put x{qty} - {save_status}")
        rich.print(f":money_with_wings: Entry costs: ${total_costs:.2f}")
        rich.print(f"  • Commission: ${short_costs.commission + long_costs.commission:.2f}")
        rich.print(f"  • Exchange fees: ${short_costs.exchange_fees + long_costs.exchange_fees:.2f}")
        if short_costs.regulatory_fees + long_costs.regulatory_fees > 0:
            rich.print(f"  • Regulatory fees: ${short_costs.regulatory_fees + long_costs.regulatory_fees:.2f}")
        
        return trade
    
    def open_bear_call_spread(self, qty: Optional[int] = None, dry_run: bool = False):
        """Open a bear-call spread with configurable prompts"""
        # Check blocks only if not in dry run mode
        if not dry_run:
            is_blocked, block_name = blocked_for_options(self.cfg)
            if is_blocked:
                rich.print(f"[red]No options during {block_name}[/]")
                raise typer.Exit()
        elif blocked_for_options(self.cfg)[0]:
            # Show block warning in dry run mode but continue
            is_blocked, block_name = blocked_for_options(self.cfg)
            rich.print(f"[yellow]⚠️  Would normally be blocked: {block_name} (ignored in dry-run)[/]")
        
        # Show Fed speakers prompt if configured
        self._show_fed_speakers_prompt()
        
        # Get risk assessment with configurable prompts
        risk = self._get_risk_assessment("BEAR-CALL")
        
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]")
            raise typer.Exit()
        
        qty = qty or int(typer.prompt("Quantity", default="1"))
        
        # Strategy-specific prompts for bear call
        strategy_prompts = self._get_strategy_prompts("bear_call")
        if strategy_prompts:
            rich.print(f"\n[bold cyan]Bear Call Spread Setup[/]")
            for prompt_key, prompt_text in strategy_prompts.items():
                response = typer.prompt(prompt_text, default="", show_default=False)
                if response.strip():
                    rich.print(f"[dim]{prompt_key}: {response}[/]")
        
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
        
        # Only save if not in dry run mode
        if not dry_run:
            self.book.append(trade)
            save_book(self.book)
            write_single_trade_file(trade)
            save_status = "saved"
        else:
            save_status = "NOT SAVED (dry-run)"
        
        # Show cost breakdown
        total_costs = trade.total_costs()
        rich.print(f":rocket: {'[DRY RUN] ' if dry_run else ''}Opened [cyan]{trade.id}[/] Bear‑Call x{qty} - {save_status}")
        rich.print(f":money_with_wings: Entry costs: ${total_costs:.2f}")
        rich.print(f"  • Commission: ${short_costs.commission + long_costs.commission:.2f}")
        rich.print(f"  • Exchange fees: ${short_costs.exchange_fees + long_costs.exchange_fees:.2f}")
        if short_costs.regulatory_fees + long_costs.regulatory_fees > 0:
            rich.print(f"  • Regulatory fees: ${short_costs.regulatory_fees + long_costs.regulatory_fees:.2f}")
        
        return trade
    
    def open_single_leg_trade(self, strat: str, typ: str, side: str, symbol: str, qty: int, price: str, dry_run: bool = False):
        """Open a single-leg trade (futures or options) with configurable prompts"""
        typ_u = typ.upper()
        
        if typ_u.startswith("OPTION"):
            # Check blocks only if not in dry run mode
            if not dry_run:
                is_blocked, block_name = blocked_for_options(self.cfg)
                if is_blocked:
                    rich.print(f"[red]No options during {block_name}[/]")
                    raise typer.Exit()
            elif blocked_for_options(self.cfg)[0]:
                # Show block warning in dry run mode but continue
                is_blocked, block_name = blocked_for_options(self.cfg)
                rich.print(f"[yellow]⚠️  Would normally be blocked: {block_name} (ignored in dry-run)[/]")
        
        risk = None
        if typ_u.startswith("OPTION"):
            # Show Fed speakers prompt if configured
            self._show_fed_speakers_prompt()
            
            # Get risk assessment with configurable prompts for options
            risk = self._get_risk_assessment(strat)
            
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
            multiplier=self.cfg.get("multipliers", {}).get(symbol.split("_")[0], 1),
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
        
        # Only save if not in dry run mode
        if not dry_run:
            self.book.append(trade)
            save_book(self.book)
            write_single_trade_file(trade)
            save_status = "saved"
        else:
            save_status = "NOT SAVED (dry-run)"
        
        # Show cost breakdown
        rich.print(f":rocket: {'[DRY RUN] ' if dry_run else ''}Opened [cyan]{trade.id}[/] - {save_status}")
        rich.print(f":money_with_wings: Entry costs: ${entry_costs.total():.2f}")
        rich.print(f"  • Commission: ${entry_costs.commission:.2f}")
        rich.print(f"  • Exchange fees: ${entry_costs.exchange_fees:.2f}")
        if entry_costs.regulatory_fees > 0:
            rich.print(f"  • Regulatory fees: ${entry_costs.regulatory_fees:.2f}")
        
        return trade
    
    def close_trade_partial(self, trade_id: str, qty: Optional[int] = None):
        """Close a trade completely or partially with configurable exit prompts"""
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
        
        # Show exit analysis prompts only if explicitly enabled
        if self.cfg.get("prompt_triggers", {}).get("on_exit", False):
            if self.cfg.get("prompt_categories", {}).get("exit_planning", False):
                self._show_exit_analysis()
        
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
    
    def _show_exit_analysis(self):
        """Show exit analysis prompts if configured"""
        prompts = self.cfg.get("prompts", {})
        
        rich.print(f"\n[bold cyan]Exit Analysis[/]")
        
        # Exit criteria
        exit_prompt = prompts.get("exit_criteria", "Exit criteria (% profit, days to expiry, delta)?")
        exit_response = typer.prompt(exit_prompt, default="", show_default=False)
        if exit_response.strip():
            rich.print(f"[dim]Exit criteria: {exit_response}[/]")
        
        # Early exit consideration
        early_prompt = prompts.get("early_exit", "Consider early exit if 50% profit achieved?")
        early_response = typer.confirm(early_prompt)
        if early_response:
            rich.print("[dim]Will consider early exit at 50% profit[/]")
        
        # Stop loss
        stop_prompt = prompts.get("stop_loss", "Stop loss level (% of premium or underlying move)?")
        stop_response = typer.prompt(stop_prompt, default="", show_default=False)
        if stop_response.strip():
            rich.print(f"[dim]Stop loss: {stop_response}[/]")
        
        print()  # Add spacing
    
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
