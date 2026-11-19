#!/usr/bin/env python3
"""Makes the charts, the tables and the log excerpts of the report from the files in ../data.

    ../../.venv/bin/python make_figures.py        (needs matplotlib)

Input:  data/  - the output of Lab2/tests/scenarios.py (transcripts, server logs, checks.csv, facts.csv,
                 idle_clients.csv, workers.csv, environment.txt)
Output: figures/*.pdf (+ .png), tables/*.tex, tables/numbers.tex (the numbers used in the text of the report)
        and tables/excerpt_*.txt (the parts of the transcripts and logs that the report shows)
"""
import csv
import re
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent.parent
DATA, FIG, TAB = ROOT / "data", ROOT / "figures", ROOT / "tables"
FIG.mkdir(exist_ok=True)
TAB.mkdir(exist_ok=True)

BLUE, ORANGE, GREEN, RED, GREY = "#2b6cb0", "#dd6b20", "#2f855a", "#c53030", "#718096"
WAITING = "#cbd5e0"
WORKER_COLORS = [BLUE, ORANGE, GREEN, "#6b46c1"]
plt.rcParams.update({"font.size": 7.5, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})

WIDTH = 108     # characters that fit in a line of the report
macros = {}


def macro(name, value):
    """The text of the report uses \\name, so the numbers always come from the data files."""
    assert re.fullmatch(r"[A-Za-z]+", name), name
    macros[name] = str(value)


def tex(text):
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#"), ("$", r"\$"),
                 ("{", r"\{"), ("}", r"\}")):
        text = text.replace(a, b)
    return text


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.pdf")
    fig.savefig(FIG / f"{name}.png")
    plt.close(fig)
    print("figure", name)


def write_table(name, header, lines, align):
    body = "\n".join(" & ".join(map(str, line)) + r" \\" for line in lines)
    (TAB / f"{name}.tex").write_text(
        "\\begin{tabular}{" + align + "}\n\\toprule\n" + " & ".join(header) + " \\\\\n\\midrule\n" + body +
        "\n\\bottomrule\n\\end{tabular}\n")
    print("table", name)


def read_lines(name):
    return (DATA / name).read_text(errors="replace").splitlines()


def excerpt(name, lines):
    """A part of a transcript or log, ready for \\VerbatimInput: long lines are wrapped."""
    out = []
    for line in lines:
        line = re.sub(r"[^\x20-\x7e]", "?", line.rstrip())
        # the endpoint column of the server log is padded for the widest address: make it narrower
        line = re.sub(r"^(\d\d:\d\d:\d\d\.\d\d\d)  (\S+)\s+", lambda m: f"{m[1]}  {m[2]:<15}  ", line)
        line = re.sub(r"stock read from \S*/(\w+\.txt)", r"stock read from data/\1", line)
        out += textwrap.wrap(line, WIDTH, subsequent_indent=" " * 32, break_long_words=True) or [""]
    (TAB / f"excerpt_{name}.txt").write_text("\n".join(out) + "\n")
    print("excerpt", name, len(out), "lines")


def seconds(clock):
    h, m, s = clock.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def orders_of(log_lines):
    """From a server log: {number: {accepted, start, end, worker, how, items, client}} with times in seconds."""
    orders = {}
    for line in log_lines:
        m = re.match(r"(\d\d:\d\d:[\d.]+)\s+(\S+)\s+order (\d+)(.*)", line)
        if not m:
            continue
        t, n, rest = seconds(m[1]), int(m[3]), m[4]
        o = orders.setdefault(n, {"client": m[2]})
        if rest.startswith(" accepted: "):
            o["accepted"] = t
            o["items"] = rest.split("accepted: ")[1].split(",")[0]
        elif "prepares it" in rest:
            o["start"] = t
            o["worker"] = int(re.search(r"worker (\d+)", rest)[1])
        elif rest.startswith(" ready"):
            o["end"], o["how"] = t, "ready"
        elif rest.startswith(" cancelled"):
            o["end"], o["how"] = t, "cancelled"
    return orders


def timeline(log_name, fig_name, title, labels):
    """One bar for every order: grey while it waits in the queue, coloured while a worker prepares it."""
    orders = orders_of(read_lines(log_name))
    t0 = min(o["accepted"] for o in orders.values())
    numbers = sorted(orders)
    workers = sorted({o["worker"] for o in orders.values() if "worker" in o})

    fig, ax = plt.subplots(figsize=(7.6, 0.36 * len(numbers) + 1.3))
    for row, n in enumerate(numbers):
        o = orders[n]
        accepted, end = o["accepted"] - t0, o["end"] - t0
        start = o.get("start", o["end"]) - t0
        if start - accepted > 0.02:
            ax.barh(row, start - accepted, left=accepted, height=0.55, color=WAITING, edgecolor="white", lw=1)
        if "worker" in o:
            color = WORKER_COLORS[workers.index(o["worker"]) % len(WORKER_COLORS)]
            ax.barh(row, end - start, left=start, height=0.55, color=color, edgecolor="white", lw=1)
            if end - start > 1.2:
                ax.text((start + end) / 2, row, f"worker {o['worker']}", ha="center", va="center", color="white", fontsize=6.5)
        if o["how"] == "cancelled":
            ax.plot([end], [row], marker="x", color=RED, ms=7, mew=2, zorder=5)
            ax.text(end + 0.12, row, "cancelled: the client left", va="center", fontsize=6.5, color="#1a202c")
        else:
            ax.text(end + 0.12, row, f"READY at {end:.1f} s", va="center", fontsize=6.5, color="#1a202c")
    ax.set_yticks(range(len(numbers)), [f"order {n}  ({labels.get(orders[n]['client'], '?')}: {orders[n]['items'].replace('=', ' ')})"
                                        for n in numbers])
    ax.invert_yaxis()
    ax.set_xlabel("Seconds after the first order was accepted")
    ax.set_xlim(0, max(o["end"] for o in orders.values()) - t0 + 2.6)
    ax.grid(axis="y", visible=False)
    handles = [Patch(color=WAITING, label="waits in the queue")] + \
              [Patch(color=WORKER_COLORS[i % len(WORKER_COLORS)], label=f"prepared by worker {w}") for i, w in enumerate(workers)]
    ax.legend(handles=handles, fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=len(handles), frameon=False)
    ax.set_title(title, fontsize=9)
    save(fig, fig_name)
    return orders


def labels_of(clients_name):
    """The transcripts name the clients A, B, ...; the server log has their endpoints. They connect in this order."""
    seen = []
    for line in read_lines(clients_name):
        m = re.match(r"\s*[\d.]+\s+(\w+)\s*[<>!]", line)
        if m and m[1] not in seen:
            seen.append(m[1])
    return seen


def main():
    # ------------------------------------------------------------------ environment
    env = dict(line.split("=", 1) for line in read_lines("environment.txt") if "=" in line)
    macro("envProcessor", tex(env["processor"]))
    macro("envLogical", env["logical_processors"])
    macro("envCores", str(int(env["logical_processors"]) // max(1, int(env["threads_per_core"] or 1))))
    macro("envThreadsPerCore", env["threads_per_core"])
    macro("envMemory", env["memory_gib"])
    macro("envOs", tex(env["os"]))
    macro("envKernel", tex(env["kernel"]))
    macro("envDotnet", env["dotnet"])
    macro("envPython", env["python"])
    macro("envDate", env["date"])

    # ------------------------------------------------------------------ facts measured by the scenarios
    names = {"one_answer_ms": "oneAnswerMs", "one_ready_seconds": "oneReadySeconds", "two_menu_ms": "twoMenuMs",
             "two_seconds": "twoSeconds", "race_rounds": "raceRounds", "race_clients": "raceClients",
             "race_croissants": "raceCroissants", "race_orders": "raceOrders", "race_accepted": "raceAccepted",
             "race_refused": "raceRefused", "three_alert_ms": "threeAlertMs", "cons_deliveries": "consDeliveries",
             "cons_clients": "consClients", "cons_orders": "consOrders", "cons_accepted": "consAccepted",
             "cons_refused": "consRefused", "cons_ready": "consReady", "cons_stock": "consStock",
             "cons_stock_after": "consStockAfter", "four_close_ms": "fourCloseMs", "four_freed_seconds": "fourFreedSeconds",
             "four_reset_ms": "fourResetMs", "four_kill_ms": "fourKillMs", "net_seconds": "netSeconds",
             "bad_random_errors": "badRandomErrors", "bad_flood_errors": "badFloodErrors",
             "bad_flood_worst_ms": "badFloodWorstMs", "mute_seconds": "muteSeconds", "mute_sent": "muteSent",
             "restart_first": "restartFirst", "restart_after": "restartAfter"}
    facts = {row["name"]: row["value"] for row in csv.DictReader(open(DATA / "facts.csv"))}
    for key, name in names.items():
        macro(name, tex(facts.get(key, "--")))
    # the network scenario needs root; without it the report says that it was not run
    macro("netRun", "1" if "net_seconds" in facts else "0")

    # ------------------------------------------------------------------ checks
    checks = list(csv.DictReader(open(DATA / "checks.csv")))
    about = [("task1", "Task 1", "menu, order, refusal, errors, READY after 11 s"),
             ("framing", "Task 1", "messages in pieces, several in one send"),
             ("task2", "Task 2", "five clients, two workers, queue order"),
             ("race", "Task 2", "20 simultaneous orders for 7 croissants, 10 rounds"),
             ("task3", "Task 3", "provider, delivery, alerts"),
             ("conservation", "Task 3", "deliveries and orders at the same moment"),
             ("task4", "Task 4", "closed, reset and killed clients"),
             ("network", "Task 4", "a client whose network is gone"),
             ("invalid", "Task 4", "wrong commands, long message, random bytes"),
             ("never_reads", "Task 4", "a client that never reads"),
             ("client_cs", "Task 4", "the console client in C\\#"),
             ("client_py", "Bonus", "the console client in Python"),
             ("restart", "Bonus", "random stock; stock kept after a restart"),
             ("idle_clients", "Questions", "1000 idle clients"),
             ("workers", "Questions", "1 to 16 workers")]
    lines = []
    for key, task, what in about:
        rows = [c for c in checks if c["scenario"] == key]
        if not rows:
            continue
        passed = sum(c["result"] == "PASS" for c in rows)
        skipped = sum(c["result"] == "SKIP" for c in rows)
        result = "not run" if skipped == len(rows) else f"{passed} of {len(rows)}"
        lines.append((f"\\texttt{{{tex(key)}}}", task, what, result))
    write_table("checks", ["Scenario", "For", "What it tries", "Checks passed"], lines, "lllr")
    macro("checksTotal", sum(c["result"] != "SKIP" for c in checks))
    macro("checksPassed", sum(c["result"] == "PASS" for c in checks))
    macro("checksFailed", sum(c["result"] == "FAIL" for c in checks))
    macro("checksScenarios", len({c["scenario"] for c in checks if c["result"] != "SKIP"}))
    assert not [c for c in checks if c["result"] == "FAIL"], "a check failed: the text of the report says that all passed"

    # ------------------------------------------------------------------ timelines of Task 2 and Task 4
    letters = labels_of("task2_clients.txt")
    endpoints = []
    for line in read_lines("task2_server.log"):
        m = re.match(r"\S+\s+(\S+)\s+order \d+ accepted", line)
        if m and m[1] not in endpoints:
            endpoints.append(m[1])
    two = timeline("task2_server.log", "task2", "Task 2: six orders of five clients, two workers",
                   dict(zip(endpoints, [l for l in letters if l])))
    macro("twoOrders", len(two))
    macro("twoEndpoints", ", ".join(f"\\texttt{{{e}}}" for e in endpoints))

    four_lines = read_lines("task4_server.log")
    endpoints = []
    for line in four_lines:
        m = re.match(r"\S+\s+(\S+)\s+order \d+ accepted", line)
        if m and m[1] not in endpoints:
            endpoints.append(m[1])
    timeline("task4_server.log", "task4", "Task 4: clients disappear while their orders wait or are prepared",
             dict(zip(endpoints, ["X", "Y", "Z", "K"])))

    # ------------------------------------------------------------------ measurements
    work = list(csv.DictReader(open(DATA / "workers.csv")))
    idle = list(csv.DictReader(open(DATA / "idle_clients.csv")))

    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.7))
    xs = [int(r["workers"]) for r in work]
    ys = [float(r["seconds"]) for r in work]
    ax[0].plot(xs, ys, "o-", color=BLUE, ms=4)
    for x, y in zip(xs, ys):
        ax[0].annotate(f"{y:.0f} s", (x, y), textcoords="offset points", xytext=(4, 5), fontsize=6.5)
    ax[0].set_xscale("log", base=2)
    ax[0].set_xticks(xs, [str(x) for x in xs])
    ax[0].set_xlabel("Workers")
    ax[0].set_ylabel(f"Seconds until {work[0]['orders']} orders of 2 s are ready")
    ax[0].set_ylim(0, max(ys) * 1.2)
    ax[0].set_title("More workers", fontsize=8)

    xi = [int(r["clients"]) for r in idle]
    for a, field, label, color in ((ax[1], "threads", "Threads of the server", BLUE),
                                   (ax[2], "memory_mb", "Memory of the server (MB)", BLUE)):
        vals = [float(r[field]) for r in idle]
        a.plot(xi, vals, "o-", color=color, ms=4)
        a.annotate(f"{vals[0]:.0f}", (xi[0], vals[0]), textcoords="offset points", xytext=(8, -9), fontsize=6.5)
        a.annotate(f"{vals[-1]:.0f}", (xi[-1], vals[-1]), textcoords="offset points", xytext=(-8, 4), fontsize=6.5, ha="right")
        a.set_xlabel("Idle clients connected")
        a.set_ylabel(label)
        a.set_ylim(0, max(vals) * 1.2)
        a.set_title("More waiting clients", fontsize=8)
    save(fig, "measurements")

    write_table("workers", ["Workers", "Orders", "All ready after (s)", "Processor time of the server (ms)"],
                [(r["workers"], r["orders"], r["seconds"], r["cpu_ms"]) for r in work], "rrrr")
    write_table("idle_clients", ["Idle clients", "Threads", "Memory (MB)", "Menu answered in (ms, median of 101)"],
                [(r["clients"], r["threads"], r["memory_mb"], r["menu_ms"]) for r in idle], "rrrr")
    by_workers = {int(r["workers"]): r for r in work}
    for n, word in ((1, "One"), (2, "Two"), (4, "Four"), (8, "Eight"), (16, "Sixteen")):
        macro(f"workSeconds{word}", f"{float(by_workers[n]['seconds']):.1f}")
    macro("workOrders", work[0]["orders"])
    macro("workCpuMax", max(int(r["cpu_ms"]) for r in work))
    first, last = idle[0], idle[-1]
    macro("idleClientsMax", last["clients"])
    macro("idleThreadsZero", first["threads"])
    macro("idleThreadsMax", last["threads"])
    macro("idleMemZero", first["memory_mb"])
    macro("idleMemMax", last["memory_mb"])
    per_client = (float(last["memory_mb"]) - float(first["memory_mb"])) * 1024 / int(last["clients"])
    macro("idleKbPerClient", f"{per_client:.0f}")
    macro("idleMenuMs", last["menu_ms"])

    # ------------------------------------------------------------------ excerpts shown in the report
    excerpt("task1_clients", read_lines("task1_clients.txt"))
    excerpt("task1_server", read_lines("task1_server.log"))
    excerpt("framing", read_lines("framing_clients.txt"))
    excerpt("task2_clients", [l for l in read_lines("task2_clients.txt") if "closes the connection" not in l])
    excerpt("race", [l for l in read_lines("race_clients.txt") if "  -- " in l])
    excerpt("task3", read_lines("task3_clients.txt"))
    excerpt("conservation", [l for l in read_lines("conservation_clients.txt") if "  -- " in l])
    start = next(i for i, l in enumerate(four_lines) if "order 3 accepted" in l)
    excerpt("task4_server", four_lines[start:])
    if (DATA / "network_server.log").exists():
        excerpt("network", read_lines("network_clients.txt") + ["", "the log of the server:"] +
                [l for l in read_lines("network_server.log") if "order 1" in l or "disconnected" in l])
    else:
        excerpt("network", ["(the scenario 'network' was not run: it needs root)"])
    bad = read_lines("invalid_clients.txt")
    cut = next(i for i, l in enumerate(bad) if "random bytes" in l)
    after = next(i for i, l in enumerate(bad) if i > cut and l.rstrip().endswith("> MENU"))
    excerpt("invalid", bad[:cut + 3] + [f"         ... ({after - cut - 3} more error messages)"] + bad[after:])
    excerpt("never_reads", read_lines("never_reads_clients.txt")[:1] + [l for l in read_lines("never_reads_clients.txt") if "N sent" in l] +
            ["", "the log of the server:"] + [l for l in read_lines("never_reads_server.log") if "send failed" in l or "the server closed" in l])
    excerpt("client_cs", read_lines("client_cs_output.txt"))
    excerpt("restart", [l for l in read_lines("restart_server.log") if "stock" in l or "listening" in l or "delivery" in l or "accepted" in l])

    (TAB / "numbers.tex").write_text(
        "% made by plots/make_figures.py - do not edit\n" +
        "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(macros.items())))
    print("numbers", len(macros))


if __name__ == "__main__":
    main()
