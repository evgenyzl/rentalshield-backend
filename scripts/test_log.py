#!/usr/bin/env python3
"""
RentalShield — Test log viewer / manual entry.

Usage:
    python scripts/test_log.py                          # show summary table
    python scripts/test_log.py add --help               # add entry manually
    python scripts/test_log.py clear                    # wipe the log

Entries are auto-added every time you run compare.py.
Use 'add' only when you want to record a manual test (no session ID).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
from rentalshield.testing.test_log import log_comparison, all_entries, summary_text, _LOG_PATH
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def cmd_summary(_args):
    entries = all_entries()
    if not entries:
        console.print("[dim]No test entries yet. Run a comparison to add the first one.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAVY, show_footer=True)
    table.add_column("#",        style="dim",    width=3,  footer="TOT")
    table.add_column("Date",     style="cyan",   width=12)
    table.add_column("Plate",    style="bold",   width=12)
    table.add_column("Car",                      width=16)
    table.add_column("Company",                  width=10)
    table.add_column("Co.",      justify="right", width=4,
                     footer=str(sum(e["company_count"] for e in entries)))
    table.add_column("Ours",     justify="right", width=5,
                     footer=str(sum(e["our_count"] for e in entries)))
    table.add_column("Match",    justify="right", width=6,
                     footer=str(sum(e["matched"] for e in entries)))
    table.add_column("Miss",     justify="right", width=5,
                     footer=str(sum(e["missed"] for e in entries)))
    table.add_column("NEW ⚡",   justify="right", width=6, style="bold green",
                     footer=str(sum(e["new_undocumented"] for e in entries)))
    table.add_column("Recall",   justify="right", width=8)
    table.add_column("Notes",    style="dim")

    total_co  = sum(e["company_count"] for e in entries)
    total_mat = sum(e["matched"] for e in entries)
    avg_recall = f"{total_mat/total_co*100:.1f}%" if total_co else "—"
    table.columns[10].footer = avg_recall

    for i, e in enumerate(entries, 1):
        recall_str = f"{e['recall_pct']:.1f}%"
        recall_col = (
            "[green]" if e["recall_pct"] >= 80
            else "[yellow]" if e["recall_pct"] >= 50
            else "[red]"
        ) + recall_str

        new_str = str(e["new_undocumented"])

        table.add_row(
            str(i),
            e["date"],
            e["plate"],
            e["car"][:15],
            e["company"][:9],
            str(e["company_count"]),
            str(e["our_count"]),
            str(e["matched"]),
            str(e["missed"]),
            new_str,
            recall_col,
            e.get("notes", "")[:30],
        )

    console.print()
    console.rule("[bold]RentalShield — Test Log[/bold]")
    console.print(table)
    console.print(f"[dim]Log file: {_LOG_PATH}[/dim]")
    console.print()

    # Target check
    avg_r = total_mat / total_co * 100 if total_co else 0
    total_new = sum(e["new_undocumented"] for e in entries)
    console.print("[bold]Target:[/bold] recall ≥ 90% across all cars, ≥1 undocumented find per car")
    if avg_r >= 90:
        console.print(f"  [green]✓[/green] Recall: {avg_r:.1f}%  — on target")
    else:
        console.print(f"  [yellow]⚠[/yellow] Recall: {avg_r:.1f}%  — need {90 - avg_r:.1f}% more")
    console.print(f"  [green]✓[/green] Undocumented found: {total_new} across {len(entries)} car(s)")
    console.print()


def cmd_add(args):
    entry = log_comparison(
        audit_session_id = args.session or f"manual_{len(all_entries())+1:03d}",
        car_plate        = args.plate,
        car_model        = args.car,
        rental_company   = args.company,
        company_pdf      = args.pdf,
        company_count    = args.company_count,
        our_count        = args.our_count,
        matched          = args.matched,
        new_undocumented = args.new_found,
        notes            = args.notes or "",
    )
    console.print(f"[green]✓[/green] Entry added — recall {entry['recall_pct']}%, "
                  f"{entry['new_undocumented']} undocumented")
    cmd_summary(args)


def cmd_clear(_args):
    if _LOG_PATH.exists():
        _LOG_PATH.unlink()
        console.print("[green]✓[/green] Log cleared.")
    else:
        console.print("[dim]Log is already empty.[/dim]")


def main():
    parser = argparse.ArgumentParser(description="RentalShield test log")
    sub = parser.add_subparsers(dest="cmd")

    # summary (default)
    sub.add_parser("summary", help="Show summary table (default)")

    # add
    add = sub.add_parser("add", help="Manually add a test entry")
    add.add_argument("--session",       default=None,  help="Audit session ID")
    add.add_argument("--plate",         default=None)
    add.add_argument("--car",           default=None)
    add.add_argument("--company",       default=None)
    add.add_argument("--pdf",           default=None)
    add.add_argument("--company-count", type=int, required=True, dest="company_count",
                     help="Number of damages in company PDF")
    add.add_argument("--our-count",     type=int, required=True, dest="our_count",
                     help="Number of damages we detected")
    add.add_argument("--matched",       type=int, required=True,
                     help="How many of company's damages we also found")
    add.add_argument("--new-found",     type=int, required=True, dest="new_found",
                     help="Undocumented damages we found (not in company PDF)")
    add.add_argument("--notes",         default="")

    # clear
    sub.add_parser("clear", help="Wipe the log")

    args = parser.parse_args()

    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "clear":
        cmd_clear(args)
    else:
        cmd_summary(args)


if __name__ == "__main__":
    main()
