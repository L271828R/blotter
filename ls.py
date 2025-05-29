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
