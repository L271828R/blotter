#!/usr/bin/env python
"""
Trade Blotter CLI (v4: bear-call + bull-put + inbox sync + prompts)
────────────────────────────────────────────────────────────────────
Folders
  blotter/
  ├─ inbox/    ← drop *.json trade files here (e-mail/cloud)
  ├─ archive/  ← processed files get moved here automatically
  └─ trades.json

Commands
  blotter.py ls
  blotter.py open               # fully interactive
  blotter.py open --strat BULL-PUT   --qty 1
  blotter.py open --strat BEAR-CALL  --qty 1
  blotter.py close <id>
"""

from __future__ import annotations
import uuid, json, datetime as dt, decimal as dec, pathlib
from dataclasses import dataclass, asdict, field

import typer, rich
from rich.table import Table
from ruamel.yaml import YAML

import os, tempfile, subprocess


# ───────── Helper ──────────
def to_decimal(v: str | dec.Decimal | None) -> dec.Decimal | None:
    if v is None or isinstance(v, dec.Decimal):
        return v
    return dec.Decimal(v)

def make_leg(d: dict) -> Leg:
    return Leg(
        symbol     = d["symbol"],
        side       = d["side"],
        qty        = d["qty"],
        entry      = to_decimal(d["entry"]),
        exit       = to_decimal(d.get("exit")),
        multiplier = d.get(
            "multiplier",
            cfg["multipliers"].get(d["symbol"].split("_")[0], 1),
        ),
    )

# ───────── Setup ──────────
app  = typer.Typer()
yaml = YAML(typ="safe")

CONFIG_FILE = pathlib.Path("config.yaml")
DEFAULT_CFG = {
    "option_block": {"start": "12:00", "end": "16:00"},
    "multipliers": {"/MES": 5, "MES_OPT": 50},
    "strategies": ["gap-fade", "vwap-reversal", "breakout", "BULL-PUT", "BEAR-CALL"],
}
if not CONFIG_FILE.exists():
    yaml.dump(DEFAULT_CFG, CONFIG_FILE)
cfg = yaml.load(CONFIG_FILE)

BOOK     = pathlib.Path("trades.json")
INBOX    = pathlib.Path("inbox");   INBOX.mkdir(exist_ok=True)
ARCHIVE  = pathlib.Path("archive"); ARCHIVE.mkdir(exist_ok=True)
NOW      = lambda: dt.datetime.now(dt.timezone.utc)

# ────────── Data model ──────────
@dataclass
class Risk:
    econ: bool; earnings: bool; bond: bool; note: str = ""
    def empty(self): return not (self.econ or self.earnings or self.bond or self.note.strip())

@dataclass
class Leg:
    symbol: str; side: str; qty: int; entry: dec.Decimal
    exit: dec.Decimal | None = None; multiplier: int = 50
    def pnl(self):
        if self.exit is None: return None
        signed = -1 if self.side == "SELL" else 1
        return (self.exit - self.entry) * self.multiplier * self.qty * signed

@dataclass
class Trade:
    id: str; ts: str; typ: str; strat: str
    legs: list[Leg] = field(default_factory=list)
    risk: Risk | None = None
    status: str = "OPEN"
    pnl: dec.Decimal | None = None
    # Add these new fields for 2-hour tracking
    pnl_2h: dec.Decimal | None = None  # PnL after 2 hours
    pnl_2h_recorded: bool = False      # Whether 2h PnL has been recorded
    pnl_2h_timestamp: str | None = None # When 2h PnL was recorded

# ────────── Persistence ──────────
def load_book() -> list[Trade]:
    if not BOOK.exists(): return []
    raw = json.load(BOOK.open())
    fixed: list[Trade] = []
    for t in raw:
        if "legs" not in t:
            symbol = t.pop("instr")
            mult   = cfg["multipliers"].get(symbol.split("_")[0], 1)
            t["legs"] = [{
                "symbol": symbol, "side": t.pop("side","BUY"),
                "qty": t.pop("qty",1),
                "entry": to_decimal(t.pop("price")),
                "exit":  to_decimal(t.pop("exit_price",None)),
                "multiplier": mult,
            }]
            t.pop("pnl",None)
            t["typ"] = t.get("typ","FUTURE" if "_" not in symbol else "OPTION")
        for leg in t["legs"]:
            leg["entry"] = to_decimal(leg["entry"])
            leg["exit"]  = to_decimal(leg.get("exit"))
        allowed = {"id","ts","typ","strat","risk","status","pnl"}
        core = {k:v for k,v in t.items() if k in allowed}
        if core.get("risk") and not isinstance(core["risk"],Risk):
            core["risk"] = Risk(**core["risk"])
        fixed.append(Trade(**core, legs=[Leg(**l) for l in t["legs"]]))
    return fixed

def save_book(book: list[Trade]):
    BOOK.write_text(json.dumps([asdict(t) for t in book], default=str, indent=2))

# ───── inbox / archive sync ─────
def write_single_trade_file(tr: Trade):
    fn = f"{dt.datetime.now():%y%m%d}-{tr.id}.trade.json"
    INBOX.joinpath(fn).write_text(json.dumps(asdict(tr), default=str))

def import_inbox_files():
    seen = {t.id for t in book}
    total_added = 0
    for fp in INBOX.glob("*.json"):
        payload = json.loads(fp.read_text())
        raws    = payload if isinstance(payload,list) else [payload]
        added   = 0
        for raw in raws:
            if raw.get("risk") and not isinstance(raw["risk"],Risk):
                raw["risk"] = Risk(**raw["risk"])
            raw["legs"] = [make_leg(l) for l in raw["legs"]]
            tr = Trade(**raw)
            if tr.id not in seen:
                book.append(tr); seen.add(tr.id); added += 1
        fp.rename(ARCHIVE/ fp.name)
        rich.print(f":open_file_folder: Imported {added} trade(s) from {fp.name}")
        total_added += added
    if total_added:
        save_book(book)

# ────────── Runtime state ──────────
book = load_book()
import_inbox_files()

# ────────── Utils ──────────
def blocked_for_options():
    start = dt.time.fromisoformat(cfg["option_block"]["start"])
    end   = dt.time.fromisoformat(cfg["option_block"]["end"])
    now   = dt.datetime.now().time()
    return start <= now <= end

def calc_trade_pnl(tr: Trade):
    return None if any(l.exit is None for l in tr.legs) else sum(l.pnl() for l in tr.legs)

# ────────── Commands ──────────
@app.command("pnl2h")
def record_2h_pnl(id: str = None):
    """Record 2-hour PnL for a trade (required for BULL-PUT-OVERNIGHT before closing)"""
    
    if not id:
        # Show trades that need 2h PnL recording
        overnight_trades = [t for t in book if t.strat == "BULL-PUT-OVERNIGHT" and t.status == "OPEN"]
        if not overnight_trades:
            rich.print("[yellow]No open BULL-PUT-OVERNIGHT trades found[/]")
            return
            
        tbl = Table(title="BULL-PUT-OVERNIGHT Trades Needing 2H PnL")
        tbl.add_column("ID", justify="left")
        tbl.add_column("Time", justify="left") 
        tbl.add_column("2H PnL Status", justify="left")
        
        for t in overnight_trades:
            trade_time = dt.datetime.fromisoformat(t.ts)
            hours_elapsed = (dt.datetime.now(dt.timezone.utc) - trade_time).total_seconds() / 3600
            status = "✓ Recorded" if t.pnl_2h_recorded else f"⚠️ Missing ({hours_elapsed:.1f}h elapsed)"
            tbl.add_row(t.id, trade_time.strftime("%H:%M:%S"), status)
        
        rich.print(tbl)
        id = typer.prompt("Enter trade ID to record 2H PnL")
    
    # Find the trade
    for tr in book:
        if tr.id == id:
            if tr.strat != "BULL-PUT-OVERNIGHT":
                rich.print(f"[yellow]Trade {id} is not BULL-PUT-OVERNIGHT strategy[/]")
                return
                
            trade_time = dt.datetime.fromisoformat(tr.ts)
            hours_elapsed = (dt.datetime.now(dt.timezone.utc) - trade_time).total_seconds() / 3600
            
            rich.print(f"Trade {id} opened at: {trade_time.strftime('%H:%M:%S')}")
            rich.print(f"Hours elapsed: {hours_elapsed:.1f}")
            
            if tr.pnl_2h_recorded:
                rich.print(f"[yellow]2H PnL already recorded: ${tr.pnl_2h}[/]")
                if not typer.confirm("Update existing 2H PnL?"):
                    return
            
            # Record the 2-hour PnL
            pnl_2h = to_decimal(typer.prompt("PnL after 2 hours"))
            notes = typer.prompt("Notes (optional)", default="")
            
            tr.pnl_2h = pnl_2h
            tr.pnl_2h_recorded = True
            tr.pnl_2h_timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
            
            # Add notes to risk if provided
            if notes and tr.risk:
                tr.risk.note = f"{tr.risk.note} | 2H: {notes}".strip(" |")
            
            save_book(book)
            write_single_trade_file(tr)
            
            rich.print(f"[green]✓ Recorded 2H PnL: ${pnl_2h} for trade {id}[/]")
            return
    
    rich.print(f"[red]Trade ID {id} not found[/]")



@app.command("close")
def close_trade(id: str):
    for tr in book:
        if tr.id == id:
            if tr.status == "CLOSED":
                rich.print("[yellow]Already closed[/]"); return
            
            # Check if this is BULL-PUT-OVERNIGHT and needs 2H PnL
            if tr.strat == "BULL-PUT-OVERNIGHT" and not tr.pnl_2h_recorded:
                rich.print("[red]❌ Cannot close BULL-PUT-OVERNIGHT trade without 2H PnL data![/]")
                rich.print("Please run: blotter.py pnl2h " + id)
                
                if typer.confirm("Record 2H PnL now?"):
                    # Inline 2H PnL recording
                    trade_time = dt.datetime.fromisoformat(tr.ts)
                    hours_elapsed = (dt.datetime.now(dt.timezone.utc) - trade_time).total_seconds() / 3600
                    
                    rich.print(f"Trade opened at: {trade_time.strftime('%H:%M:%S')}")
                    rich.print(f"Hours elapsed: {hours_elapsed:.1f}")
                    
                    pnl_2h = to_decimal(typer.prompt("PnL after 2 hours"))
                    notes = typer.prompt("2H Notes (optional)", default="")
                    
                    tr.pnl_2h = pnl_2h
                    tr.pnl_2h_recorded = True
                    tr.pnl_2h_timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
                    
                    if notes and tr.risk:
                        tr.risk.note = f"{tr.risk.note} | 2H: {notes}".strip(" |")
                    
                    rich.print(f"[green]✓ Recorded 2H PnL: ${pnl_2h}[/]")
                else:
                    return
            
            # Proceed with normal closing
            for l in tr.legs:
                l.exit = to_decimal(typer.prompt(f"Exit price for {l.symbol} [{l.side}]"))
            
            tr.pnl, tr.status = calc_trade_pnl(tr), "CLOSED"
            save_book(book); write_single_trade_file(tr)
            
            # Show 2H vs final PnL comparison for BULL-PUT-OVERNIGHT
            if tr.strat == "BULL-PUT-OVERNIGHT" and tr.pnl_2h is not None:
                pnl_change = tr.pnl - tr.pnl_2h
                rich.print(f":chart_with_upwards_trend: 2H PnL: ${tr.pnl_2h}")
                rich.print(f":check_mark: Final PnL: ${tr.pnl}")
                rich.print(f":arrow_right: Change: ${pnl_change} ({'+' if pnl_change >= 0 else ''}{pnl_change})")
            else:
                rich.print(f":check_mark: Closed {id}  PnL = [bold]{tr.pnl}[/]")
            return
    
    rich.print("[red]ID not found[/]")

@app.command("ls")
def list_trades():
    print("Need to implement the following:")
    print("Hot hand fallacy / Recency bias controls: after a good run, need cool off period")
    print("Need to monitor balance in blotter")
    print("Options controls: cannot go all in: 1/3 of pot? configuration")

    tbl = Table(title="Trades")
    for col,justify in [("id","left"),("date/time","left"),("type",None),("strat",None),
                        ("legs",None),("qty","right"),("2H PnL","right"),("status",None),("PnL","right")]:
        tbl.add_column(col, justify=justify)
    
    tz = dt.datetime.now().astimezone().tzinfo
    for t in book:
        ts = dt.datetime.fromisoformat(t.ts).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        legs = "; ".join(f"{l.side[0]} {l.symbol.split('_')[-1]}" for l in t.legs)
        qty = sum(l.qty for l in t.legs)
        
        # Show 2H PnL for BULL-PUT-OVERNIGHT trades
        pnl_2h_display = ""
        if t.strat == "BULL-PUT-OVERNIGHT":
            if t.pnl_2h_recorded:
                pnl_2h_display = str(t.pnl_2h)
            else:
                pnl_2h_display = "⚠️ Missing"
        else:
            pnl_2h_display = "-"
        
        tbl.add_row(t.id, ts, t.typ, t.strat, legs, str(qty), pnl_2h_display, t.status, str(t.pnl or "-"))
    
    rich.print(tbl)

@app.command("edit")
def edit_trade(id: str):
    """
    Edit a single trade by ID in your $EDITOR (defaults to vim).
    Saves changes back into trades.json when you exit.
    """
    # 1) load raw JSON list
    data = json.loads(BOOK.read_text())

    # 2) find the index of the trade
    for idx, raw in enumerate(data):
        if raw.get("id") == id:
            break
    else:
        rich.print(f"[red]Trade ID {id} not found in ledger.[/]")
        raise typer.Exit(1)

    # 3) dump that one trade to a temp file
    editor = os.environ.get("EDITOR", "vim")
    with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as tf:
        tfname = tf.name
        json.dump(raw, tf, indent=2, default=str)

    # 4) open your editor
    subprocess.call([editor, tfname])

    # 5) read the file back
    try:
        edited = json.loads(open(tfname).read())
    except Exception as e:
        rich.print(f"[red]Failed to parse JSON after edit: {e}[/]")
        os.unlink(tfname)
        raise typer.Exit(1)

    os.unlink(tfname)

    # 6) validate ID
    if edited.get("id") != id:
        rich.print("[red]The trade ID cannot be changed.[/]")
        raise typer.Exit(1)

    # 7) replace in the list and save
    data[idx] = edited
    BOOK.write_text(json.dumps(data, default=str, indent=2))

    rich.print(f"[green]Trade {id} updated successfully.[/]")


@app.command("open")
def open_trade(
    strat: str | None = typer.Option(None, help="Strategy"),
    typ:   str | None = typer.Option(None, help="FUTURE or OPTION"),
    side:  str | None = typer.Option(None, help="BUY or SELL"),
    symbol:str | None = typer.Option(None, help="Ticker"),
    qty:   int | None = typer.Option(None, help="Contracts"),
    price: str | None = typer.Option(None, help="Fill price"),
):
    # ── 0) Enforce configured strategies ───────────────────────────────
    allowed = {s.upper() for s in cfg.get("strategies", [])}
    # Prompt until we get a valid one
    while True:
        if not strat:
            strat = typer.prompt(f"Strategy ({', '.join(sorted(allowed))})")
        u = strat.upper()
        if u in allowed:
            break
        rich.print(f"[red]Unknown strategy: {strat!r}[/]")
        rich.print(f"[green]Valid strategies are:[/] {', '.join(sorted(allowed))}")
        strat = None  # force re-prompt

    # ── 1) Gather single‑leg basics (unless spread) ────────────────────
    if u not in ("BULL-PUT", "BEAR-CALL", "BULL-PUT-OVERNIGHT"):
        typ    = typ    or typer.prompt("Type", default="FUTURE")
        side   = side   or typer.prompt("Side", default="BUY")
        symbol = symbol or typer.prompt("Symbol")
        qty    = qty    or int(typer.prompt("Quantity", default="1"))
        price  = price  or typer.prompt("Entry price")

    # ── 2) Bull‑Put shortcut ──────────────────────────────────────────
    if u == "BULL-PUT":
        if blocked_for_options():
            rich.print("[red]No options 12–16[/]"); raise typer.Exit()
        econ = typer.confirm("Economic event?")
        earn = typer.confirm("Big earnings / Earnings season? ")
        bond = typer.confirm("Bond auction 1PM (no bounce)?")
        note = typer.prompt("Note", default="")
        risk = Risk(econ, earn, bond, note)
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]"); raise typer.Exit()

        qty = qty or int(typer.prompt("Quantity", default="1"))
        typer.echo("---- Bull‑Put spread ----")
        s_sym = typer.prompt("Short‑put (SELL) symbol")
        s_pr  = to_decimal(typer.prompt("Credit price"))
        l_sym = typer.prompt("Long‑put  (BUY)  symbol")
        l_pr  = to_decimal(typer.prompt("Debit price"))

        legs = [
            Leg(s_sym, "SELL", qty, s_pr),
            Leg(l_sym, "BUY",  qty, l_pr)
        ]
        trade = Trade(str(uuid.uuid4())[:8], NOW().isoformat(), "OPTION_SPREAD", strat, legs, risk)
        book.append(trade); save_book(book); write_single_trade_file(trade)
        rich.print(f":rocket: Opened [cyan]{trade.id}[/] Bull‑Put x{qty}")
        return

    # ── 2b) Bull‑Put-Overnight shortcut (same as Bull-Put but different strategy name) ──────────
    if u == "BULL-PUT-OVERNIGHT":
        if blocked_for_options():
            rich.print("[red]No options 12–16[/]"); raise typer.Exit()
        econ = typer.confirm("Economic event?")
        earn = typer.confirm("Big earnings?")
        bond = typer.confirm("Bond auction?")
        note = typer.prompt("Note", default="")
        risk = Risk(econ, earn, bond, note)
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]"); raise typer.Exit()

        qty = qty or int(typer.prompt("Quantity", default="1"))
        typer.echo("---- Bull‑Put-Overnight spread ----")
        s_sym = typer.prompt("Short‑put (SELL) symbol")
        s_pr  = to_decimal(typer.prompt("Credit price"))
        l_sym = typer.prompt("Long‑put  (BUY)  symbol")
        l_pr  = to_decimal(typer.prompt("Debit price"))

        legs = [
            Leg(s_sym, "SELL", qty, s_pr),
            Leg(l_sym, "BUY",  qty, l_pr)
        ]
        trade = Trade(str(uuid.uuid4())[:8], NOW().isoformat(), "OPTION_SPREAD", u, legs, risk)
        book.append(trade); save_book(book); write_single_trade_file(trade)
        rich.print(f":rocket: Opened [cyan]{trade.id}[/] Bull‑Put-Overnight x{qty}")
        return

    # ── 3) Bear‑Call shortcut ─────────────────────────────────────────
    if u == "BEAR-CALL":
        if blocked_for_options():
            rich.print("[red]No options 12–16[/]"); raise typer.Exit()
        econ = typer.confirm("Economic event?")
        earn = typer.confirm("Big earnings?")
        bond = typer.confirm("Bond auction?")
        note = typer.prompt("Note", default="")
        risk = Risk(econ, earn, bond, note)
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]"); raise typer.Exit()

        qty = qty or int(typer.prompt("Quantity", default="1"))
        typer.echo("---- Bear‑Call spread ----")
        s_sym = typer.prompt("Short‑call (SELL) symbol")
        s_pr  = to_decimal(typer.prompt("Credit price"))
        l_sym = typer.prompt("Long‑call  (BUY)  symbol")
        l_pr  = to_decimal(typer.prompt("Debit price"))

        legs = [
            Leg(s_sym, "SELL", qty, s_pr),
            Leg(l_sym, "BUY",  qty, l_pr)
        ]
        trade = Trade(str(uuid.uuid4())[:8], NOW().isoformat(), "OPTION_SPREAD", strat, legs, risk)
        book.append(trade); save_book(book); write_single_trade_file(trade)
        rich.print(f":rocket: Opened [cyan]{trade.id}[/] Bear‑Call x{qty}")
        return

    # ── 4) Single‑leg futures/options ─────────────────────────────────
    typ_u = typ.upper()
    if typ_u.startswith("OPTION") and blocked_for_options():
        rich.print("[red]No options 12–16[/]"); raise typer.Exit()

    risk = None
    if typ_u.startswith("OPTION"):
        econ = typer.confirm("Economic event?")
        earn = typer.confirm("Big earnings?")
        bond = typer.confirm("Bond auction?")
        note = typer.prompt("Note", default="")
        risk = Risk(econ, earn, bond, note)
        if risk.empty():
            rich.print("[red]Need risk checklist/note[/]"); raise typer.Exit()

    leg = Leg(
        symbol,
        side.upper(),
        qty,
        to_decimal(price),
        cfg["multipliers"].get(symbol.split("_")[0], 1),
    )
    trade = Trade(str(uuid.uuid4())[:8], NOW().isoformat(), typ_u, strat, [leg], risk)
    book.append(trade); save_book(book); write_single_trade_file(trade)
    rich.print(f":rocket: Opened [cyan]{trade.id}[/]")


if __name__=="__main__":
    app()

