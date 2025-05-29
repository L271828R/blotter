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

# ═══════════════════════════════════════════════════════════════════
# config.py - Configuration management
# ═══════════════════════════════════════════════════════════════════

import pathlib
from ruamel.yaml import YAML

yaml = YAML(typ="safe")
CONFIG_FILE = pathlib.Path("config.yaml")

DEFAULT_CFG = {
    "option_blocks": [
        {"start": "09:30", "end": "09:45", "name": "Market Open"},
        {"start": "12:00", "end": "16:00", "name": "Lunch Block"},
        {"start": "18:00", "end": "21:15", "name": "Asian Open"}
    ],
    "multipliers": {
        "/MES": 5,
        "MES": 5, 
        "MES_OPT": 5
    },
    "strategies": ["5AM", "NORMAL", "BULL-PUT", "BEAR-CALL", "BULL-PUT-OVERNIGHT"],
    "costs": {
        "FUTURE": {
            "commission_per_contract": "1.10",
            "exchange_fees_per_contract": "0.37",
            "regulatory_fees_per_contract": "0.00"
        },
        "OPTION": {
            "commission_per_contract": "1.25",
            "exchange_fees_per_contract": "0.50",
            "regulatory_fees_per_contract": "0.02"
        }
    }
}

def load_config():
    """Load configuration, creating defaults if needed"""
    if not CONFIG_FILE.exists():
        yaml.dump(DEFAULT_CFG, CONFIG_FILE)
    return yaml.load(CONFIG_FILE)

def save_config(config):
    """Save configuration to file"""
    yaml.dump(config, CONFIG_FILE)

# ═══════════════════════════════════════════════════════════════════
# utils.py - Utility functions
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

# ═══════════════════════════════════════════════════════════════════
# ls.py - List trades functionality
# ═══════════════════════════════════════════════════════════════════

import datetime as dt
from rich.table import Table
import rich

def list_trades(book):
    """List all trades with net PnL after commission and fees"""
    print("Need to implement the following:")
    print("Hot hand fallacy / Recency bias controls: after a good run, need cool off period")
    print("Need to monitor balance in blotter")
    print("Options controls: cannot go all in: 1/3 of pot? configuration")
    
    tbl = Table(title="Trades")
    for col, justify in [("id", "left"), ("date/time", "left"), ("type", None), ("strat", None),
                        ("legs", None), ("qty", "right"), ("status", None), ("PnL", "right")]:
        tbl.add_column(col, justify=justify)
    
    tz = dt.datetime.now().astimezone().tzinfo
    for t in book:
        ts = dt.datetime.fromisoformat(t.ts).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        legs = "; ".join(f"{l.side[0]} {l.symbol.split('_')[-1]}" for l in t.legs)
        
        current_qty = sum(l.qty for l in t.legs)
        if "-P" in t.id:
            qty_display = str(current_qty)
        else:
            if t.original_qty and t.original_qty != current_qty and t.status == "OPEN":
                qty_display = f"{current_qty}/{t.original_qty}"
            else:
                qty_display = str(current_qty)
        
        net_pnl = t.net_pnl()
        pnl_display = f"${net_pnl:.2f}" if net_pnl is not None else "-"
        
        tbl.add_row(t.id, ts, t.typ, t.strat, legs, qty_display, t.status, pnl_display)
    
    rich.print(tbl)

# ═══════════════════════════════════════════════════════════════════
# recalc.py - PnL recalculation functionality
# ═══════════════════════════════════════════════════════════════════

import rich
from rich.table import Table
import typer
import decimal as dec

from utils import calc_trade_pnl, to_decimal
from persistence import save_book, write_single_trade_file

def safe_to_decimal(value):
    """Safely convert any value to Decimal, handling strings and existing Decimals"""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return dec.Decimal(value)
        except (dec.InvalidOperation, ValueError):
            return None
    if isinstance(value, (int, float)):
        return dec.Decimal(str(value))
    if isinstance(value, dec.Decimal):
        return value
    return None

def recalc_trade_pnl(trade_id: str, book: list, show_details: bool = False):
    """Recalculate PnL for a specific trade"""
    
    trade = None
    for t in book:
        if t.id == trade_id:
            trade = t
            break
    
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return False
    
    old_pnl = safe_to_decimal(trade.pnl)
    old_gross = trade.gross_pnl()
    old_costs = trade.total_costs()
    
    if trade.status == "CLOSED":
        trade.pnl = calc_trade_pnl(trade)
        new_pnl = trade.pnl
        new_gross = trade.gross_pnl()
        new_costs = trade.total_costs()
        
        rich.print(f"[cyan]Recalculated PnL for trade {trade_id}[/]")
        
        if show_details:
            tbl = Table(title=f"PnL Recalculation Details - {trade_id}")
            tbl.add_column("Metric", justify="left")
            tbl.add_column("Old Value", justify="right") 
            tbl.add_column("New Value", justify="right")
            tbl.add_column("Change", justify="right")
            
            gross_change = None
            if old_gross is not None and new_gross is not None:
                gross_change = new_gross - old_gross
            gross_change_str = f"${gross_change:.2f}" if gross_change is not None else "N/A"
            
            tbl.add_row(
                "Gross PnL",
                f"${old_gross:.2f}" if old_gross is not None else "N/A",
                f"${new_gross:.2f}" if new_gross is not None else "N/A",
                gross_change_str
            )
            
            costs_change = new_costs - old_costs
            tbl.add_row(
                "Total Costs",
                f"${old_costs:.2f}",
                f"${new_costs:.2f}",
                f"${costs_change:.2f}"
            )
            
            net_change = None
            if old_pnl is not None and new_pnl is not None:
                net_change = new_pnl - old_pnl
            net_change_str = f"${net_change:.2f}" if net_change is not None else "N/A"
            
            tbl.add_row(
                "Net PnL",
                f"${old_pnl:.2f}" if old_pnl is not None else "N/A", 
                f"${new_pnl:.2f}" if new_pnl is not None else "N/A",
                net_change_str
            )
            
            rich.print(tbl)
        else:
            rich.print(f"  Old PnL: ${old_pnl:.2f}" if old_pnl is not None else "  Old PnL: N/A")
            rich.print(f"  New PnL: ${new_pnl:.2f}" if new_pnl is not None else "  New PnL: N/A")
            
            if old_pnl is not None and new_pnl is not None:
                change = new_pnl - old_pnl
                change_color = "green" if change >= 0 else "red"
                rich.print(f"  Change: [{change_color}]${change:.2f}[/]")
        
        save_book(book)
        write_single_trade_file(trade)
        rich.print(f"[green]✓ Trade {trade_id} updated and saved[/]")
        
    else:
        rich.print(f"[yellow]Trade {trade_id} is still OPEN - no PnL to recalculate[/]")
        rich.print("[dim]Note: PnL is calculated when trades are closed[/]")
    
    return True

def recalc_all_trades(book: list):
    """Recalculate PnL for all closed trades"""
    closed_trades = [t for t in book if t.status == "CLOSED"]
    
    if not closed_trades:
        rich.print("[yellow]No closed trades found to recalculate[/]")
        return
    
    rich.print(f"[cyan]Recalculating PnL for {len(closed_trades)} closed trades...[/]")
    
    updated_count = 0
    for trade in closed_trades:
        old_pnl = safe_to_decimal(trade.pnl)
        new_pnl = calc_trade_pnl(trade)
        trade.pnl = new_pnl
        
        if old_pnl != new_pnl:
            updated_count += 1
            old_display = f"${old_pnl:.2f}" if old_pnl is not None else "N/A"
            new_display = f"${new_pnl:.2f}" if new_pnl is not None else "N/A"
            rich.print(f"  {trade.id}: {old_display} → {new_display}")
    
    if updated_count > 0:
        save_book(book)
        rich.print(f"[green]✓ Updated {updated_count} trades and saved[/]")
    else:
        rich.print("[dim]All PnL calculations were already correct[/]")

def fix_data_types(book: list):
    """Fix any string PnL values to Decimal objects"""
    fixed_count = 0
    
    for trade in book:
        if isinstance(trade.pnl, str):
            trade.pnl = safe_to_decimal(trade.pnl)
            fixed_count += 1
        
        if isinstance(trade.pnl_2h, str):
            trade.pnl_2h = safe_to_decimal(trade.pnl_2h)
    
    if fixed_count > 0:
        rich.print(f"[cyan]Fixed {fixed_count} data type issues[/]")
        save_book(book)
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
# audit.py - Detailed PnL audit functionality
# ═══════════════════════════════════════════════════════════════════

import rich
from rich.table import Table
import datetime as dt

def audit_trade(trade_id: str, book: list):
    """Audit a specific trade showing detailed PnL calculation"""
    
    trade = None
    for t in book:
        if t.id == trade_id:
            trade = t
            break
    
    if not trade:
        rich.print(f"[red]Trade ID {trade_id} not found[/]")
        return False
    
    rich.print(f"\n[bold cyan]═══ TRADE AUDIT: {trade_id} ═══[/]")
    
    trade_time = dt.datetime.fromisoformat(trade.ts)
    formatted_time = trade_time.strftime("%Y-%m-%d %H:%M:%S")
    
    overview_table = Table(title="Trade Overview", show_header=False)
    overview_table.add_column("Field", style="bold", width=15)
    overview_table.add_column("Value", width=30)
    
    overview_table.add_row("Trade ID", trade.id)
    overview_table.add_row("Timestamp", formatted_time)
    overview_table.add_row("Type", trade.typ)
    overview_table.add_row("Strategy", trade.strat)
    overview_table.add_row("Status", f"[green]{trade.status}[/]" if trade.status == "CLOSED" else f"[yellow]{trade.status}[/]")
    
    if trade.original_qty:
        current_qty = sum(l.qty for l in trade.legs)
        overview_table.add_row("Quantity", f"{current_qty}/{trade.original_qty} (current/original)")
    else:
        overview_table.add_row("Quantity", str(sum(l.qty for l in trade.legs)))
    
    rich.print(overview_table)
    
    if trade.risk and not trade.risk.empty():
        rich.print(f"\n[bold yellow]Risk Assessment:[/]")
        risk_items = []
        if trade.risk.econ: risk_items.append("Economic Event")
        if trade.risk.earnings: risk_items.append("Earnings")
        if trade.risk.bond: risk_items.append("Bond Auction")
        if risk_items:
            rich.print(f"  Flags: {', '.join(risk_items)}")
        if trade.risk.note:
            rich.print(f"  Note: {trade.risk.note}")
    
    rich.print(f"\n[bold magenta]═══ LEG-BY-LEG BREAKDOWN ═══[/]")
    
    total_gross_pnl = 0
    total_costs = 0
    
    for i, leg in enumerate(trade.legs, 1):
        rich.print(f"\n[bold]Leg {i}: {leg.side} {leg.qty} {leg.symbol}[/]")
        
        leg_table = Table(show_header=False, box=None, padding=(0, 2))
        leg_table.add_column("Item", style="dim", width=20)
        leg_table.add_column("Value", width=15)
        leg_table.add_column("Calculation", style="dim", width=40)
        
        leg_table.add_row("Entry Price", f"${leg.entry:.2f}", "")
        leg_table.add_row("Multiplier", str(leg.multiplier), "")
        leg_table.add_row("Quantity", str(leg.qty), "")
        
        entry_commission = leg.entry_costs.commission
        entry_exchange = leg.entry_costs.exchange_fees
        entry_regulatory = leg.entry_costs.regulatory_fees
        entry_total = leg.entry_costs.total()
        
        leg_table.add_row("", "", "")
        leg_table.add_row("[bold]Entry Costs:", "", "")
        leg_table.add_row("  Commission", f"${entry_commission:.2f}", f"")
        leg_table.add_row("  Exchange Fees", f"${entry_exchange:.2f}", f"")
        if entry_regulatory > 0:
            leg_table.add_row("  Regulatory", f"${entry_regulatory:.2f}", f"")
        leg_table.add_row("  [bold]Entry Total", f"[bold]${entry_total:.2f}[/]", "")
        
        if leg.exit is not None:
            leg_table.add_row("", "", "")
            leg_table.add_row("Exit Price", f"${leg.exit:.2f}", "")
            
            price_diff = leg.exit - leg.entry
            signed_diff = price_diff * (-1 if leg.side == "SELL" else 1)
            gross_pnl = signed_diff * leg.multiplier * leg.qty
            
            leg_table.add_row("Price Movement", f"${price_diff:.2f}", f"${leg.exit:.2f} - ${leg.entry:.2f}")
            leg_table.add_row("Signed Movement", f"${signed_diff:.2f}", f"${price_diff:.2f} × {-1 if leg.side == 'SELL' else 1} ({leg.side})")
            leg_table.add_row("[bold]Gross PnL", f"[bold]${gross_pnl:.2f}[/]", f"${signed_diff:.2f} × {leg.multiplier} × {leg.qty}")
            
            if leg.exit_costs:
                exit_commission = leg.exit_costs.commission
                exit_exchange = leg.exit_costs.exchange_fees
                exit_regulatory = leg.exit_costs.regulatory_fees
                exit_total = leg.exit_costs.total()
                
                leg_table.add_row("", "", "")
                leg_table.add_row("[bold]Exit Costs:", "", "")
                leg_table.add_row("  Commission", f"${exit_commission:.2f}", "")
                leg_table.add_row("  Exchange Fees", f"${exit_exchange:.2f}", "")
                if exit_regulatory > 0:
                    leg_table.add_row("  Regulatory", f"${exit_regulatory:.2f}", "")
                leg_table.add_row("  [bold]Exit Total", f"[bold]${exit_total:.2f}[/]", "")
            else:
                exit_total = 0
                leg_table.add_row("[dim]Exit Costs", "[dim]$0.00", "[dim]No exit costs recorded")
            
            total_leg_costs = entry_total + exit_total
            net_pnl = gross_pnl - total_leg_costs
            
            leg_table.add_row("", "", "")
            leg_table.add_row("Total Leg Costs", f"${total_leg_costs:.2f}", f"${entry_total:.2f} + ${exit_total:.2f}")
            leg_table.add_row("[bold green]Net Leg PnL", f"[bold green]${net_pnl:.2f}[/]", f"${gross_pnl:.2f} - ${total_leg_costs:.2f}")
            
            total_gross_pnl += gross_pnl
            total_costs += total_leg_costs
            
        else:
            leg_table.add_row("[dim]Exit Price", "[dim]Not closed", "")
            leg_table.add_row("[dim]Gross PnL", "[dim]N/A", "[dim]Position still open")
            leg_table.add_row("[dim]Exit Costs", "[dim]N/A", "[dim]Will be calculated on close")
            total_costs += entry_total
        
        rich.print(leg_table)
    
    rich.print(f"\n[bold cyan]═══ TRADE SUMMARY ═══[/]")
    
    summary_table = Table(show_header=False)
    summary_table.add_column("Metric", style="bold", width=20)
    summary_table.add_column("Amount", width=15)
    summary_table.add_column("Calculation", style="dim", width=40)
    
    if trade.status == "CLOSED":
        summary_table.add_row("Total Gross PnL", f"${total_gross_pnl:.2f}", "Sum of all leg gross PnL")
        summary_table.add_row("Total Costs", f"${total_costs:.2f}", "Sum of all entry + exit costs")
        
        net_pnl = total_gross_pnl - total_costs
        color = "green" if net_pnl >= 0 else "red"
        summary_table.add_row(f"[bold {color}]Final Net PnL", f"[bold {color}]${net_pnl:.2f}[/]", f"${total_gross_pnl:.2f} - ${total_costs:.2f}")
        
        stored_pnl = trade.net_pnl()
        if stored_pnl is not None:
            diff = abs(net_pnl - stored_pnl)
            if diff > 0.01:
                summary_table.add_row("[red]Stored PnL", f"[red]${stored_pnl:.2f}[/]", f"[red]⚠️ Differs by ${diff:.2f}[/]")
            else:
                summary_table.add_row("[green]Stored PnL", f"[green]${stored_pnl:.2f}[/]", "[green]✓ Matches calculation[/]")
    else:
        summary_table.add_row("Status", "OPEN", "PnL will be calculated when closed")
        summary_table.add_row("Entry Costs Paid", f"${total_costs:.2f}", "Costs already incurred")
        summary_table.add_row("Unrealized PnL", "N/A", "Position still open")
    
    if trade.strat == "BULL-PUT-OVERNIGHT":
        summary_table.add_row("", "", "")
        if trade.pnl_2h_recorded:
            summary_table.add_row("2H PnL Recorded", f"${trade.pnl_2h:.2f}", f"At {trade.pnl_2h_timestamp}")
            if trade.status == "CLOSED" and trade.pnl_2h is not None:
                change = net_pnl - trade.pnl_2h
                change_color = "green" if change >= 0 else "red"
                summary_table.add_row("2H → Final Change", f"[{change_color}]${change:.2f}[/]", f"${net_pnl:.2f} - ${trade.pnl_2h:.2f}")
        else:
            summary_table.add_row("[yellow]2H PnL Status", "[yellow]⚠️ Missing[/]", "[yellow]Required for overnight trades[/]")
    
    rich.print(summary_table)
    
    if total_costs > 0 and trade.status == "CLOSED":
        rich.print(f"\n[bold yellow]Cost Analysis:[/]")
        cost_percentage = (total_costs / abs(total_gross_pnl)) * 100 if total_gross_pnl != 0 else 0
        rich.print(f"  Total costs represent {cost_percentage:.1f}% of gross PnL")
        
        if cost_percentage > 20:
            rich.print(f"  [red]⚠️ High cost ratio - consider position sizing[/]")
        elif cost_percentage > 10:
            rich.print(f"  [yellow]⚠️ Moderate cost ratio[/]")
        else:
            rich.print(f"  [green]✓ Reasonable cost ratio[/]")
    
    return True

def audit_all_positions(book: list, status_filter: str = "ALL"):
    """Show summary of positions with entry costs and PnL"""
    if status_filter == "OPEN":
        trades = [t for t in book if t.status == "OPEN"]
        title = "Open Positions"
    elif status_filter == "CLOSED":
        trades = [t for t in book if t.status == "CLOSED"]
        title = "Closed Positions"
    else:
        trades = book
        title = "All Positions"
    
    if not trades:
        rich.print(f"[yellow]No {status_filter.lower()} positions found[/]")
        return
    
    rich.print(f"\n[bold cyan]═══ {title.upper()} AUDIT ═══[/]")
    
    tbl = Table(title=f"{title} ({len(trades)} trades)")
    tbl.add_column("ID", justify="left")
    tbl.add_column("Strategy", justify="left")
    tbl.add_column("Type", justify="left")
    tbl.add_column("Legs", justify="left")
    tbl.add_column("Qty", justify="right")
    tbl.add_column("Entry Costs", justify="right")
    tbl.add_column("Exit Costs", justify="right")
    tbl.add_column("Total Costs", justify="right")
    if status_filter != "OPEN":
        tbl.add_column("Net PnL", justify="right")
    tbl.add_column("Age", justify="right")
    
    total_entry_costs = 0
    total_exit_costs = 0
    total_net_pnl = 0
    
    for trade in trades:
        legs_summary = "; ".join(f"{l.side[0]} {l.symbol.split('_')[-1]}" for l in trade.legs)
        current_qty = sum(l.qty for l in trade.legs)
        
        if trade.original_qty and trade.original_qty != current_qty:
            qty_display = f"{current_qty}/{trade.original_qty}"
        else:
            qty_display = str(current_qty)
        
        entry_costs = sum(l.entry_costs.total() for l in trade.legs)
        exit_costs = sum(l.exit_costs.total() if l.exit_costs else 0 for l in trade.legs)
        total_costs = entry_costs + exit_costs
        
        total_entry_costs += entry_costs
        total_exit_costs += exit_costs
        
        trade_time = dt.datetime.fromisoformat(trade.ts)
        age = dt.datetime.now(dt.timezone.utc) - trade_time
        age_str = f"{age.days}d" if age.days > 0 else f"{age.seconds//3600}h"
        
        row_data = [
            trade.id,
            trade.strat,
            trade.typ,
            legs_summary,
            qty_display,
            f"${entry_costs:.2f}",
            f"${exit_costs:.2f}" if exit_costs > 0 else "-",
            f"${total_costs:.2f}",
        ]
        
        if status_filter != "OPEN":
            net_pnl = trade.net_pnl()
            if net_pnl is not None:
                color = "green" if net_pnl >= 0 else "red"
                row_data.append(f"[{color}]${net_pnl:.2f}[/]")
                total_net_pnl += net_pnl
            else:
                row_data.append("-")
        
        row_data.append(age_str)
        tbl.add_row(*row_data)
    
    rich.print(tbl)
    
    rich.print(f"\n[bold]{title} Summary:[/]")
    rich.print(f"  Total entry costs: ${total_entry_costs:.2f}")
    if total_exit_costs > 0:
        rich.print(f"  Total exit costs: ${total_exit_costs:.2f}")
        rich.print(f"  Total all costs: ${total_entry_costs + total_exit_costs:.2f}")
    
    if status_filter != "OPEN" and total_net_pnl != 0:
        color = "green" if total_net_pnl >= 0 else "red"
        rich.print(f"  [{color}]Total net PnL: ${total_net_pnl:.2f}[/]")

