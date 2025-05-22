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
    risk: Risk | None = None; status: str = "OPEN"; pnl: dec.Decimal | None = None

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
@app.command("ls")
def list_trades():
    tbl = Table(title="Trades")
    for col,justify in [("id","left"),("date/time","left"),("type",None),("strat",None),
                        ("legs",None),("qty","right"),("status",None),("PnL","right")]:
        tbl.add_column(col, justify=justify)
    tz = dt.datetime.now().astimezone().tzinfo
    for t in book:
        ts = dt.datetime.fromisoformat(t.ts).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
        legs = "; ".join(f"{l.side[0]} {l.symbol.split('_')[-1]}" for l in t.legs)
        qty = sum(l.qty for l in t.legs)
        tbl.add_row(t.id, ts, t.typ, t.strat, legs, str(qty), t.status, str(t.pnl or "-"))
    rich.print(tbl)

@app.command("close")
def close_trade(id: str):
    for tr in book:
        if tr.id==id:
            if tr.status=="CLOSED":
                rich.print("[yellow]Already closed[/]"); return
            for l in tr.legs:
                l.exit = to_decimal(typer.prompt(f"Exit price for {l.symbol} [{l.side}]"))
            tr.pnl, tr.status = calc_trade_pnl(tr), "CLOSED"
            save_book(book); write_single_trade_file(tr)
            rich.print(f":check_mark: Closed {id}  PnL = [bold]{tr.pnl}[/]"); return
    rich.print("[red]ID not found[/]")

@app.command("open")
def open_trade(
    strat: str | None = typer.Option(None, help="Strategy"),
    typ:   str | None = typer.Option(None, help="FUTURE or OPTION"),
    side:  str | None = typer.Option(None, help="BUY or SELL"),
    symbol:str | None = typer.Option(None, help="Ticker"),
    qty:   int | None = typer.Option(None, help="Contracts"),
    price: str | None = typer.Option(None, help="Fill price"),
):
    if not strat:
        strat = typer.prompt("Strategy (NORMAL, BULL-PUT, BEAR-CALL …)")
    u = strat.upper()

    # fully prompt for single-leg unless a spread shortcut
    if u not in ("BULL-PUT","BEAR-CALL"):
        typ    = typ    or typer.prompt("Type", default="FUTURE")
        side   = side   or typer.prompt("Side", default="BUY")
        symbol = symbol or typer.prompt("Symbol")
        qty    = qty    or int(typer.prompt("Quantity",default="1"))
        price  = price  or typer.prompt("Entry price")

    # ===================== BULL-PUT =====================
    if u=="BULL-PUT":
        if blocked_for_options(): rich.print("[red]No options 12-16[/]"); raise typer.Exit()
        econ=typer.confirm("Economic event?"); earn=typer.confirm("Big earnings?")
        bond=typer.confirm("Bond auction?"); note=typer.prompt("Note",default="")
        risk=Risk(econ,earn,bond,note)
        if risk.empty(): rich.print("[red]Need risk checklist/note[/]"); raise typer.Exit()
        qty = qty or int(typer.prompt("Quantity",default="1"))
        typer.echo("---- Bull-Put spread ----")
        s_sym = typer.prompt("Short-put (SELL) symbol"); s_pr=to_decimal(typer.prompt("Credit price"))
        l_sym = typer.prompt("Long-put  (BUY)  symbol"); l_pr=to_decimal(typer.prompt("Debit price"))
        legs=[Leg(s_sym,"SELL",qty,s_pr), Leg(l_sym,"BUY",qty,l_pr)]
        trade=Trade(str(uuid.uuid4())[:8],NOW().isoformat(),"OPTION_SPREAD",strat,legs,risk)
        book.append(trade); save_book(book); write_single_trade_file(trade)
        rich.print(f":rocket: Opened [cyan]{trade.id}[/] Bull‑Put x{qty}"); return

    # ===================== BEAR-CALL =====================
    if u=="BEAR-CALL":
        if blocked_for_options(): rich.print("[red]No options 12-16[/]"); raise typer.Exit()
        econ=typer.confirm("Economic event?"); earn=typer.confirm("Big earnings?")
        bond=typer.confirm("Bond auction?"); note=typer.prompt("Note",default="")
        risk=Risk(econ,earn,bond,note)
        if risk.empty(): rich.print("[red]Need risk checklist/note[/]"); raise typer.Exit()
        qty = qty or int(typer.prompt("Quantity",default="1"))
        typer.echo("---- Bear-Call spread ----")
        s_sym = typer.prompt("Short-call (SELL) symbol"); s_pr=to_decimal(typer.prompt("Credit price"))
        l_sym = typer.prompt("Long-call  (BUY)  symbol"); l_pr=to_decimal(typer.prompt("Debit price"))
        legs=[Leg(s_sym,"SELL",qty,s_pr), Leg(l_sym,"BUY",qty,l_pr)]
        trade=Trade(str(uuid.uuid4())[:8],NOW().isoformat(),"OPTION_SPREAD",strat,legs,risk)
        book.append(trade); save_book(book); write_single_trade_file(trade)
        rich.print(f":rocket: Opened [cyan]{trade.id}[/] Bear‑Call x{qty}"); return

    # ================= Single-leg futures/options ================
    typ_u = typ.upper()
    if typ_u.startswith("OPTION") and blocked_for_options():
        rich.print("[red]No options 12-16[/]"); raise typer.Exit()
    risk=None
    if typ_u.startswith("OPTION"):
        econ=typer.confirm("Economic event?"); earn=typer.confirm("Big earnings?")
        bond=typer.confirm("Bond auction?"); note=typer.prompt("Note",default="")
        risk=Risk(econ,earn,bond,note)
        if risk.empty(): rich.print("[red]Need risk checklist/note[/]"); raise typer.Exit()

    leg=Leg(symbol,side.upper(),qty,to_decimal(price),
            cfg["multipliers"].get(symbol.split("_")[0],1))
    trade=Trade(str(uuid.uuid4())[:8],NOW().isoformat(),typ_u,strat,[leg],risk)
    book.append(trade); save_book(book); write_single_trade_file(trade)
    rich.print(f":rocket: Opened [cyan]{trade.id}[/]")

if __name__=="__main__":
    app()

