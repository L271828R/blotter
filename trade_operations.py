# ═══════════════════════════════════════════════════════════════════
# Enhanced trade_operations.py - Bull Put Spread with Net Credit Entry
# ═══════════════════════════════════════════════════════════════════

import datetime as dt
import rich
import uuid
import hashlib
from decimal import Decimal
import typer

from models import Trade, Leg, Risk, CommissionFees
from utils import to_decimal, calculate_costs, now_utc, blocked_for_options
from persistence import save_book, write_single_trade_file

class TradeOperations:
    def __init__(self, book, cfg):
        self.book = book
        self.cfg = cfg
    
    def _generate_trade_id(self):
        """Generate a unique trade ID"""
        # Use timestamp + random component for uniqueness
        timestamp = dt.datetime.now().strftime("%y%m%d%H%M%S")
        random_part = str(uuid.uuid4())[:8]
        return f"{timestamp[-8:]}"  # Use last 8 chars of timestamp
    
    def _create_timestamp(self, custom_entry_time=None, custom_entry_date=None):
        """Create timestamp for trade entry"""
        if custom_entry_time and custom_entry_date:
            custom_datetime = dt.datetime.combine(custom_entry_date, custom_entry_time)
            trade_timestamp = custom_datetime.replace(tzinfo=dt.timezone.utc)
            rich.print(f"[cyan]Using historical timestamp: {trade_timestamp.strftime('%Y-%m-%d %I:%M %p UTC')}[/]")
        elif custom_entry_time:  # Only time provided, use today's date
            today = dt.date.today()
            custom_datetime = dt.datetime.combine(today, custom_entry_time)
            trade_timestamp = custom_datetime.replace(tzinfo=dt.timezone.utc)
            rich.print(f"[cyan]Using custom time today: {trade_timestamp.strftime('%Y-%m-%d %I:%M %p UTC')}[/]")
        else:
            trade_timestamp = dt.datetime.now(dt.timezone.utc)
        
        return trade_timestamp
    
    def auto_estimate_leg_prices(self, short_strike, long_strike, net_credit):
        """Auto-estimate individual leg prices from net credit"""
        short_strike = float(short_strike)
        long_strike = float(long_strike)
        net_credit = Decimal(str(net_credit))
        
        # Simple estimation logic
        strike_diff = short_strike - long_strike  # e.g., 5990 - 5970 = 20
        
        if strike_diff <= 25:
            # Narrow spread - long probably worth very little
            estimated_long = Decimal("0.10")
            estimated_short = net_credit + estimated_long
        else:
            # Wider spread - distribute more proportionally
            estimated_long = net_credit * Decimal("0.15")  # 15% of net credit
            estimated_short = net_credit + estimated_long
        
        return estimated_short, estimated_long
    
    def open_bull_put_spread_enhanced(self, qty, strat, dry_run=False, 
                                    custom_entry_time=None, custom_entry_date=None):
        """Enhanced Bull Put Spread with flexible entry modes"""
        
        # Create timestamp
        trade_timestamp = self._create_timestamp(custom_entry_time, custom_entry_date)
        
        # Generate trade ID
        trade_id = self._generate_trade_id()
        
        rich.print(f"[cyan]Opening Bull Put Spread ({strat})[/]")
        
        # Choose entry mode
        rich.print("\n[bold]Entry Mode:[/]")
        rich.print("1. Net Credit (what you see on broker)")
        rich.print("2. Individual Leg Prices")
        
        while True:
            mode = input("Choose mode (1 or 2): ").strip()
            if mode in ["1", "2"]:
                break
            rich.print("[red]Please enter 1 or 2[/]")
        
        # Get strikes first (common to both modes)
        rich.print("\n[bold]Strike Information:[/]")
        short_strike = input("Short put strike (sell/higher): ").strip()
        long_strike = input("Long put strike (buy/lower): ").strip()
        
        # Validate strikes
        try:
            short_strike_float = float(short_strike)
            long_strike_float = float(long_strike)
            if short_strike_float <= long_strike_float:
                rich.print("[red]Error: Short strike must be higher than long strike[/]")
                return None
        except ValueError:
            rich.print("[red]Error: Invalid strike format[/]")
            return None
        
        if mode == "1":
            # NET CREDIT MODE
            rich.print(f"\n[bold]Net Credit Mode:[/]")
            net_credit_input = input("Net credit received: ").strip()
            net_credit = to_decimal(net_credit_input)
            
            if net_credit is None or net_credit <= 0:
                rich.print("[red]Error: Invalid net credit[/]")
                return None
            
            rich.print(f"\n[yellow]Auto-estimating individual leg prices for tracking...[/]")
            estimated_short, estimated_long = self.auto_estimate_leg_prices(
                short_strike, long_strike, net_credit
            )
            
            rich.print(f"[green]Estimated short put ({short_strike}): ${estimated_short}[/]")
            rich.print(f"[green]Estimated long put ({long_strike}): ${estimated_long}[/]")
            rich.print(f"[green]Net credit: ${net_credit} ✓[/]")
            
            # Confirm estimates
            if not typer.confirm("\nDo these estimates look reasonable?", default=True):
                rich.print("\n[yellow]Please provide better estimates:[/]")
                long_price_input = input(f"Long put {long_strike} price: ").strip()
                estimated_long = to_decimal(long_price_input)
                estimated_short = net_credit + estimated_long
                rich.print(f"[green]Recalculated short put price: ${estimated_short}[/]")
            
            short_price = estimated_short
            long_price = estimated_long
        
        else:
            # INDIVIDUAL LEG PRICES MODE
            rich.print(f"\n[bold]Individual Leg Prices:[/]")
            short_price_input = input(f"Short put {short_strike} price (premium received): ").strip()
            long_price_input = input(f"Long put {long_strike} price (premium paid): ").strip()
            
            short_price = to_decimal(short_price_input)
            long_price = to_decimal(long_price_input)
            
            if short_price is None or long_price is None:
                rich.print("[red]Error: Invalid price format[/]")
                return None
            
            # Calculate net credit for verification
            net_credit = short_price - long_price
            rich.print(f"[green]Calculated net credit: ${net_credit}[/]")
            
            if net_credit <= 0:
                rich.print("[red]Warning: Net credit is not positive. Check your prices.[/]")
                if not typer.confirm("Continue anyway?"):
                    return None
        
        # Get multiplier from config
        symbol_base = "MES"  # Default for MES options
        multiplier = self.cfg.get("multipliers", {}).get("MES", 5)
        
        # Calculate costs for the SPREAD (not individual legs)
        # TOS charges commission per spread order, not per leg
        spread_costs = calculate_costs("OPTION", qty, self.cfg)
        
        # For spread trades, assign all costs to the first leg and zero to the second
        # This reflects the reality that it's one order with one commission
        short_costs = spread_costs
        long_costs = CommissionFees(
            commission=Decimal('0'),
            exchange_fees=Decimal('0'), 
            regulatory_fees=Decimal('0')
        )
        
        # Build symbols
        short_symbol = f"MES_P_{short_strike}"
        long_symbol = f"MES_P_{long_strike}"
        
        # Create legs
        short_leg = Leg(
            symbol=short_symbol,
            side="SELL",
            qty=qty,
            entry=short_price,
            exit=None,
            multiplier=multiplier,
            entry_costs=short_costs,
            exit_costs=None
        )
        
        long_leg = Leg(
            symbol=long_symbol,
            side="BUY", 
            qty=qty,
            entry=long_price,
            exit=None,
            multiplier=multiplier,
            entry_costs=long_costs,
            exit_costs=None
        )
        
        # Create trade
        trade = Trade(
            id=trade_id,
            ts=trade_timestamp,
            typ="OPTION-SPREAD",
            strat=strat.upper(),
            status="OPEN",
            legs=[short_leg, long_leg],
            pnl=None,
            risk=None
        )
        
        # Calculate trade metrics - convert all to Decimal for consistency
        strike_diff = Decimal(str(short_strike_float - long_strike_float))  # For bull put: should be positive
        total_premium = (short_price - long_price) * qty * multiplier
        total_costs = short_costs.total() + long_costs.total()  # Only short_costs has actual costs
        net_credit_amount = total_premium - total_costs
        max_risk = (strike_diff * qty * multiplier) - net_credit_amount
        
        # Save trade unless dry run
        if not dry_run:
            self.book.append(trade)
            save_book(self.book)
            write_single_trade_file(trade)
            
            rich.print(f"\n[green]✓ Bull Put Spread opened: {trade_id}[/]")
            rich.print(f"[green]  Short: SELL {qty} {short_symbol} @ ${short_price}[/]")
            rich.print(f"[green]  Long:  BUY {qty} {long_symbol} @ ${long_price}[/]")
            rich.print(f"[green]  Net Credit: ${net_credit_amount:.2f} (after costs)[/]")
            rich.print(f"[green]  Max Risk: ${max_risk:.2f}[/]")
            rich.print(f"[green]  Total Costs: ${total_costs:.2f}[/]")
        else:
            rich.print(f"\n[yellow]DRY RUN: Would create Bull Put Spread {trade_id}[/]")
            rich.print(f"[yellow]  Net Credit: ${net_credit_amount:.2f}[/]")
        
        return trade
    
    def open_bear_call_spread_enhanced(self, qty, strat, dry_run=False, 
                                     custom_entry_time=None, custom_entry_date=None):
        """Enhanced Bear Call Spread with flexible entry modes"""
        
        # Create timestamp
        trade_timestamp = self._create_timestamp(custom_entry_time, custom_entry_date)
        
        # Generate trade ID
        trade_id = self._generate_trade_id()
        
        rich.print(f"[cyan]Opening Bear Call Spread ({strat})[/]")
        
        # Choose entry mode
        rich.print("\n[bold]Entry Mode:[/]")
        rich.print("1. Net Credit (what you see on broker)")
        rich.print("2. Individual Leg Prices")
        
        while True:
            mode = input("Choose mode (1 or 2): ").strip()
            if mode in ["1", "2"]:
                break
            rich.print("[red]Please enter 1 or 2[/]")
        
        # Get strikes first (common to both modes)
        rich.print("\n[bold]Strike Information:[/]")
        short_strike = input("Short call strike (sell/lower): ").strip()
        long_strike = input("Long call strike (buy/higher): ").strip()
        
        # Validate strikes
        try:
            short_strike_float = float(short_strike)
            long_strike_float = float(long_strike)
            if short_strike_float >= long_strike_float:
                rich.print("[red]Error: Short strike must be lower than long strike for bear call[/]")
                return None
        except ValueError:
            rich.print("[red]Error: Invalid strike format[/]")
            return None
        
        if mode == "1":
            # NET CREDIT MODE
            rich.print(f"\n[bold]Net Credit Mode:[/]")
            net_credit_input = input("Net credit received: ").strip()
            net_credit = to_decimal(net_credit_input)
            
            if net_credit is None or net_credit <= 0:
                rich.print("[red]Error: Invalid net credit[/]")
                return None
            
            rich.print(f"\n[yellow]Auto-estimating individual leg prices for tracking...[/]")
            estimated_short, estimated_long = self.auto_estimate_leg_prices(
                long_strike, short_strike, net_credit  # Reverse for calls
            )
            
            rich.print(f"[green]Estimated short call ({short_strike}): ${estimated_short}[/]")
            rich.print(f"[green]Estimated long call ({long_strike}): ${estimated_long}[/]")
            rich.print(f"[green]Net credit: ${net_credit} ✓[/]")
            
            # Confirm estimates
            if not typer.confirm("\nDo these estimates look reasonable?", default=True):
                rich.print("\n[yellow]Please provide better estimates:[/]")
                long_price_input = input(f"Long call {long_strike} price: ").strip()
                estimated_long = to_decimal(long_price_input)
                estimated_short = net_credit + estimated_long
                rich.print(f"[green]Recalculated short call price: ${estimated_short}[/]")
            
            short_price = estimated_short
            long_price = estimated_long
        
        else:
            # INDIVIDUAL LEG PRICES MODE
            rich.print(f"\n[bold]Individual Leg Prices:[/]")
            short_price_input = input(f"Short call {short_strike} price (premium received): ").strip()
            long_price_input = input(f"Long call {long_strike} price (premium paid): ").strip()
            
            short_price = to_decimal(short_price_input)
            long_price = to_decimal(long_price_input)
            
            if short_price is None or long_price is None:
                rich.print("[red]Error: Invalid price format[/]")
                return None
            
            # Calculate net credit for verification
            net_credit = short_price - long_price
            rich.print(f"[green]Calculated net credit: ${net_credit}[/]")
            
            if net_credit <= 0:
                rich.print("[red]Warning: Net credit is not positive. Check your prices.[/]")
                if not typer.confirm("Continue anyway?"):
                    return None
        
        # Get multiplier from config
        symbol_base = "MES"  # Default for MES options
        multiplier = self.cfg.get("multipliers", {}).get("MES", 5)
        
        # Calculate costs for the SPREAD (not individual legs)
        # TOS charges commission per spread order, not per leg
        spread_costs = calculate_costs("OPTION", qty, self.cfg)
        
        # For spread trades, assign all costs to the first leg and zero to the second
        # This reflects the reality that it's one order with one commission
        short_costs = spread_costs
        long_costs = CommissionFees(
            commission=Decimal('0'),
            exchange_fees=Decimal('0'), 
            regulatory_fees=Decimal('0')
        )
        
        # Build symbols
        short_symbol = f"MES_C_{short_strike}"
        long_symbol = f"MES_C_{long_strike}"
        
        # Create legs
        short_leg = Leg(
            symbol=short_symbol,
            side="SELL",
            qty=qty,
            entry=short_price,
            exit=None,
            multiplier=multiplier,
            entry_costs=short_costs,
            exit_costs=None
        )
        
        long_leg = Leg(
            symbol=long_symbol,
            side="BUY", 
            qty=qty,
            entry=long_price,
            exit=None,
            multiplier=multiplier,
            entry_costs=long_costs,
            exit_costs=None
        )
        
        # Create trade
        trade = Trade(
            id=trade_id,
            ts=trade_timestamp,
            typ="OPTION-SPREAD",
            strat=strat.upper(),
            status="OPEN",
            legs=[short_leg, long_leg],
            pnl=None,
            risk=None
        )
        
        # Calculate trade metrics - convert all to Decimal for consistency  
        strike_diff = Decimal(str(long_strike_float - short_strike_float))  # For bear call: should be positive
        total_premium = (short_price - long_price) * qty * multiplier
        total_costs = short_costs.total() + long_costs.total()  # Only short_costs has actual costs
        net_credit_amount = total_premium - total_costs
        max_risk = (strike_diff * qty * multiplier) - net_credit_amount
        
        # Save trade unless dry run
        if not dry_run:
            self.book.append(trade)
            save_book(self.book)
            write_single_trade_file(trade)
            
            rich.print(f"\n[green]✓ Bear Call Spread opened: {trade_id}[/]")
            rich.print(f"[green]  Short: SELL {qty} {short_symbol} @ ${short_price}[/]")
            rich.print(f"[green]  Long:  BUY {qty} {long_symbol} @ ${long_price}[/]")
            rich.print(f"[green]  Net Credit: ${net_credit_amount:.2f} (after costs)[/]")
            rich.print(f"[green]  Max Risk: ${max_risk:.2f}[/]")
            rich.print(f"[green]  Total Costs: ${total_costs:.2f}[/]")
        else:
            rich.print(f"\n[yellow]DRY RUN: Would create Bear Call Spread {trade_id}[/]")
            rich.print(f"[yellow]  Net Credit: ${net_credit_amount:.2f}[/]")
        
        return trade
    
    def open_single_leg_trade(self, strat, typ, side, symbol, qty, price, dry_run=False, 
                             custom_entry_time=None, custom_entry_date=None):
        """Open a single-leg trade with optional custom date and time"""
        
        # Create timestamp
        trade_timestamp = self._create_timestamp(custom_entry_time, custom_entry_date)
        
        # Generate trade ID
        trade_id = self._generate_trade_id()
        
        # Validate inputs
        if not all([strat, typ, side, symbol, qty, price]):
            rich.print("[red]Error: Missing required trade parameters[/]")
            return None
        
        # Convert price to decimal
        entry_price = to_decimal(price)
        if entry_price is None:
            rich.print(f"[red]Error: Invalid price format: {price}[/]")
            return None
        
        # Get multiplier from config
        symbol_base = symbol.split("_")[0]  # e.g., "MES" from "MES_C_6000"
        multiplier = self.cfg.get("multipliers", {}).get(symbol_base, 1)
        
        # Calculate costs
        entry_costs = calculate_costs(typ, qty, self.cfg)
        
        # Create leg
        leg = Leg(
            symbol=symbol,
            side=side.upper(),
            qty=qty,
            entry=entry_price,
            exit=None,
            multiplier=multiplier,
            entry_costs=entry_costs,
            exit_costs=None
        )
        
        # Create trade
        trade = Trade(
            id=trade_id,
            ts=trade_timestamp,
            typ=typ.upper(),
            strat=strat.upper(),
            status="OPEN",
            legs=[leg],
            pnl=None,
            risk=None
        )
        
        # Save trade unless dry run
        if not dry_run:
            self.book.append(trade)
            save_book(self.book)
            write_single_trade_file(trade)
            
            rich.print(f"[green]✓ {typ} {side} trade opened: {trade_id}[/]")
            rich.print(f"[green]  Symbol: {symbol} | Qty: {qty} | Price: ${entry_price}[/]")
            rich.print(f"[green]  Costs: ${entry_costs.total():.2f}[/]")
        else:
            rich.print(f"[yellow]DRY RUN: Would create {typ} {side} trade {trade_id}[/]")
            rich.print(f"[yellow]  Symbol: {symbol} | Qty: {qty} | Price: ${entry_price}[/]")
        
        return trade
    
    def close_trade_partial(self, trade_id, partial_qty=None):
        """Close a trade completely or partially"""
        
        # Find the trade
        trade = None
        for t in self.book:
            if t.id == trade_id:
                trade = t
                break
        
        if not trade:
            rich.print(f"[red]Trade ID {trade_id} not found[/]")
            return False
        
        if trade.status == "CLOSED":
            rich.print(f"[red]Trade {trade_id} is already closed[/]")
            return False
        
        # Check if it's a partial close
        if partial_qty:
            # Handle partial close logic
            open_qty = sum(leg.qty for leg in trade.legs if leg.exit is None)
            if partial_qty > open_qty:
                rich.print(f"[red]Cannot close {partial_qty} contracts - only {open_qty} open[/]")
                return False
            
            rich.print(f"[yellow]Partial close not fully implemented yet[/]")
            rich.print(f"[yellow]Would close {partial_qty} of {open_qty} contracts[/]")
            return False
        
        # Full close - check if it's a spread
        if len(trade.legs) > 1:
            return self._close_spread(trade)
        else:
            return self._close_single_leg(trade)
    
    def _close_spread(self, trade):
        """Close a multi-leg spread trade"""
        rich.print(f"[cyan]Closing {trade.strat} spread {trade.id}[/]")
        rich.print(f"Strategy: {trade.strat} | Type: {trade.typ}")
        
        # Offer different closing methods
        rich.print("\n[bold]Closing Options:[/]")
        rich.print("1. Net debit (what broker shows)")
        rich.print("2. Individual leg prices")
        
        while True:
            choice = input("Choose method (1 or 2): ").strip()
            if choice in ["1", "2"]:
                break
            rich.print("[red]Please enter 1 or 2[/]")
        
        exit_timestamp = dt.datetime.now(dt.timezone.utc)
        
        if choice == "1":
            # Net debit method
            net_debit_input = input("Net debit to close spread: ").strip()
            net_debit = to_decimal(net_debit_input)
            
            if net_debit is None:
                rich.print("[red]Invalid net debit format[/]")
                return False
            
            # Estimate individual leg prices from net debit
            self._estimate_exit_prices_from_net_debit(trade, net_debit)
            
        else:
            # Individual leg prices method
            for i, leg in enumerate(trade.legs):
                if leg.exit is not None:
                    rich.print(f"[dim]Leg {i+1} already closed: {leg.symbol}[/]")
                    continue
                
                rich.print(f"\n[bold]Leg {i+1}: {leg.side} {leg.qty} {leg.symbol}[/]")
                rich.print(f"Entry: ${leg.entry}")
                
                # Get exit price
                exit_price_input = input(f"Exit price for {leg.symbol}: ").strip()
                exit_price = to_decimal(exit_price_input)
                
                if exit_price is None:
                    rich.print(f"[red]Invalid price format for {leg.symbol}[/]")
                    return False
                
                leg.exit = exit_price
                
                # Calculate exit costs - for spreads, only apply costs to first leg
                if i == 0:
                    # First leg gets the spread exit costs
                    trade_type = "OPTION" if "OPTION" in trade.typ else "FUTURE"
                    leg.exit_costs = calculate_costs(trade_type, leg.qty, self.cfg)
                else:
                    # Additional legs get zero exit costs (it's one spread order)
                    leg.exit_costs = CommissionFees(
                        commission=Decimal('0'),
                        exchange_fees=Decimal('0'), 
                        regulatory_fees=Decimal('0')
                    )
                
                rich.print(f"[green]✓ Leg {leg.symbol} closed at ${leg.exit}[/]")
        
        # Mark trade as closed
        trade.status = "CLOSED"
        
        # Calculate P&L
        gross_pnl = trade.gross_pnl()
        net_pnl = trade.net_pnl()
        total_costs = trade.total_costs()
        trade.pnl = net_pnl
        
        # Save the updated trade
        save_book(self.book)
        write_single_trade_file(trade)
        
        rich.print(f"\n[green]✓ Spread {trade.id} closed successfully[/]")
        rich.print(f"[green]  Gross P&L: ${gross_pnl:.2f}[/]")
        rich.print(f"[green]  Total Costs: ${total_costs:.2f}[/]")
        rich.print(f"[green]  Net P&L: ${net_pnl:.2f}[/]")
        
        return True
    
    def _close_single_leg(self, trade):
        """Close a single-leg trade"""
        leg = trade.legs[0]
        
        rich.print(f"[cyan]Closing {trade.strat} trade {trade.id}[/]")
        rich.print(f"Position: {leg.side} {leg.qty} {leg.symbol}")
        rich.print(f"Entry: ${leg.entry}")
        
        # Get exit price
        exit_price_input = input(f"Exit price for {leg.symbol}: ").strip()
        exit_price = to_decimal(exit_price_input)
        
        if exit_price is None:
            rich.print("[red]Invalid exit price format[/]")
            return False
        
        leg.exit = exit_price
        
        # Calculate exit costs
        trade_type = "OPTION" if "OPTION" in trade.typ else "FUTURE"
        leg.exit_costs = calculate_costs(trade_type, leg.qty, self.cfg)
        
        # Mark trade as closed
        trade.status = "CLOSED"
        
        # Calculate P&L
        gross_pnl = trade.gross_pnl()
        net_pnl = trade.net_pnl()
        total_costs = trade.total_costs()
        trade.pnl = net_pnl
        
        # Save the updated trade
        save_book(self.book)
        write_single_trade_file(trade)
        
        rich.print(f"\n[green]✓ Trade {trade.id} closed successfully[/]")
        rich.print(f"[green]  Gross P&L: ${gross_pnl:.2f}[/]")
        rich.print(f"[green]  Total Costs: ${total_costs:.2f}[/]")
        rich.print(f"[green]  Net P&L: ${net_pnl:.2f}[/]")
        
        return True
    
    def _estimate_exit_prices_from_net_debit(self, trade, net_debit):
        """Estimate individual leg exit prices from net debit"""
        rich.print(f"[yellow]Estimating individual leg prices from net debit of ${net_debit}[/]")
        
        if len(trade.legs) == 2:
            # For two-leg spreads, estimate based on leg types
            for i, leg in enumerate(trade.legs):
                if leg.side == "SELL":
                    # Short leg gets most of the debit (you're buying it back)
                    estimated_exit = leg.entry + (net_debit * Decimal("0.7"))
                else:
                    # Long leg gets smaller portion (you're selling it)
                    estimated_exit = leg.entry - (net_debit * Decimal("0.3"))
                
                leg.exit = estimated_exit
                
                # Calculate exit costs - for spreads, only apply costs to first leg
                if i == 0:
                    # First leg gets the spread exit costs
                    trade_type = "OPTION" if "OPTION" in trade.typ else "FUTURE"
                    leg.exit_costs = calculate_costs(trade_type, leg.qty, self.cfg)
                else:
                    # Additional legs get zero exit costs (it's one spread order)
                    leg.exit_costs = CommissionFees(
                        commission=Decimal('0'),
                        exchange_fees=Decimal('0'), 
                        regulatory_fees=Decimal('0')
                    )
                
                rich.print(f"[yellow]  Estimated {leg.symbol} exit: ${estimated_exit:.2f}[/]")
        else:
            # For complex spreads, distribute evenly
            for i, leg in enumerate(trade.legs):
                estimated_exit = leg.entry + (net_debit / len(trade.legs))
                leg.exit = estimated_exit
                
                # Calculate exit costs - for spreads, only apply costs to first leg
                if i == 0:
                    trade_type = "OPTION" if "OPTION" in trade.typ else "FUTURE"
                    leg.exit_costs = calculate_costs(trade_type, leg.qty, self.cfg)
                else:
                    leg.exit_costs = CommissionFees(
                        commission=Decimal('0'),
                        exchange_fees=Decimal('0'), 
                        regulatory_fees=Decimal('0')
                    )
                
                rich.print(f"[yellow]  Estimated {leg.symbol} exit: ${estimated_exit:.2f}[/]")
    
    def delete_trade(self, trade_id):
        """Delete a trade from the book"""
        
        # Find the trade
        trade = None
        trade_index = None
        for i, t in enumerate(self.book):
            if t.id == trade_id:
                trade = t
                trade_index = i
                break
        
        if not trade:
            return False, "Trade not found"
        
        # Remove from book
        del self.book[trade_index]
        
        # Save updated book
        save_book(self.book)
        
        return True, f"Trade {trade_id} deleted successfully"
    
    def get_open_trades(self):
        """Get all open trades"""
        return [trade for trade in self.book if trade.status == "OPEN"]
    
    def get_closed_trades(self):
        """Get all closed trades"""
        return [trade for trade in self.book if trade.status == "CLOSED"]
    
    def find_trade(self, trade_id):
        """Find a trade by ID"""
        for trade in self.book:
            if trade.id == trade_id:
                return trade
        return None
    
    def get_trade_summary(self):
        """Get summary of all trades"""
        open_trades = self.get_open_trades()
        closed_trades = self.get_closed_trades()
        
        total_pnl = sum(trade.pnl for trade in closed_trades if trade.pnl)
        winning_trades = len([t for t in closed_trades if t.pnl and t.pnl > 0])
        
        return {
            "total_trades": len(self.book),
            "open_trades": len(open_trades),
            "closed_trades": len(closed_trades),
            "total_pnl": total_pnl,
            "winning_trades": winning_trades,
            "win_rate": (winning_trades / len(closed_trades) * 100) if closed_trades else 0
        }
