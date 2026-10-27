#!/usr/bin/env python3
"""Makes the charts and the LaTeX tables of the report from the csv files in ../data.

    ../../.venv/bin/python make_figures.py        (needs matplotlib)

Input:  data/task1a_results.csv, task1b_results.csv, task1c_results.csv, task2_results.csv
Output: figures/*.pdf (+ .png), tables/*.tex and tables/numbers.tex (the numbers used in the text of the report)
"""
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DATA, FIG, TAB = ROOT / "data", ROOT / "figures", ROOT / "tables"
FIG.mkdir(exist_ok=True)
TAB.mkdir(exist_ok=True)

BLUE, ORANGE, GREEN, RED, GREY = "#2b6cb0", "#dd6b20", "#2f855a", "#c53030", "#718096"
plt.rcParams.update({"font.size": 7.5, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})

WORDS = {1: "One", 2: "Two", 4: "Four", 8: "Eight", 16: "Sixteen", 32: "ThirtyTwo", 64: "SixtyFour"}
macros = {}


def macro(name, value):
    """The text of the report uses \\name, so the numbers always come from the csv files."""
    macros[name] = value


def load(name):
    rows = list(csv.DictReader(open(DATA / name)))
    for r in rows:
        for key in ("threads", "workers", "run"):
            if key in r:
                r[key] = int(r[key])
        for key in ("time_ms", "peak_memory_mb", "read_ms", "parse_ms"):
            if key in r:
                r[key] = float(r[key])
        for key in ("negative", "zero", "positive", "total"):
            r[key] = int(r[key])
        r["correct"] = r["correct"] == "1"
    return rows


def group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return dict(sorted(g.items()))


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


def fmt_int(n):
    return f"{n:,}".replace(",", r"\,")


def scaling(rows, key, name, title, xlabel, series, agg=st.median, prefix=None, time_unit="ms"):
    """Time, speed-up and peak memory against the number of threads; one line per series (thread / pool).
    series = [(mode, label, color)].  Returns {mode: {count: (time_s, speedup, memory, runs)}}."""
    result = {}
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.9))
    for mode, label, color in series:
        g = group([r for r in rows if r["mode"] == mode], lambda r: r[key])
        xs = list(g)
        times = [agg(r["time_ms"] for r in g[x]) / 1000 for x in xs]
        memory = [agg(r["peak_memory_mb"] for r in g[x]) for x in xs]
        speed = [times[0] / t for t in times]
        result[mode] = {x: (t, s, m, len(g[x])) for x, t, s, m in zip(xs, times, speed, memory)}
        for a, ys, field, scale in ((ax[0], times, "time_ms", 1000), (ax[1], speed, None, 1), (ax[2], memory, "peak_memory_mb", 1)):
            if field:
                a.fill_between(xs, [min(r[field] for r in g[x]) / scale for x in xs],
                               [max(r[field] for r in g[x]) / scale for x in xs], color=color, alpha=0.15)
                for x in xs:
                    a.scatter([x] * len(g[x]), [r[field] / scale for r in g[x]], s=6, color=color, alpha=0.35)
            a.plot(xs, ys, "o-", color=color, label=label, ms=4)
    for a, ylabel in zip(ax, ("Execution time (s)", "Speed-up vs 1 thread", "Peak memory (MB)")):
        a.set_xscale("log", base=2)
        a.set_xticks(xs, [str(x) for x in xs])
        a.set_xlabel(xlabel)
        a.set_ylabel(ylabel)
        a.set_ylim(bottom=0)
        if "Task 2" not in title:
            for v in (8, 16):
                a.axvline(v, color=GREY, ls="--", lw=0.8)
    if "Task 2" not in title:
        ax[1].plot(xs, xs, ":", color=GREY, lw=0.8)
        ax[1].set_ylim(0, max(max(v[1] for v in result[m].values()) for m in result) * 1.2)
        ax[1].text(8, 0.1, "8 physical cores", rotation=90, va="bottom", ha="right", fontsize=6, color=GREY)
        ax[1].text(16, 0.1, "16 logical processors", rotation=90, va="bottom", ha="right", fontsize=6, color=GREY)
    ax[0].legend(fontsize=6.5)
    fig.suptitle(title, fontsize=9)
    save(fig, name)
    return result


def main():
    # only the thread counts of the assignment are used (other counts are test runs)
    a_rows = [r for r in load("task1a_results.csv") if r["threads"] in WORDS]
    b_rows = load("task1b_results.csv")
    c_rows = [r for r in load("task1c_results.csv") if r["workers"] in WORDS]
    t_rows = [r for r in load("task2_results.csv") if r["threads"] in (1, 2, 4)]

    for name, rows in (("task1a", a_rows), ("task1b", b_rows), ("task1c", c_rows), ("task2", t_rows)):
        wrong = [r for r in rows if not r["correct"]]
        if name == "task1b":
            wrong = [r for r in wrong if r["version"] != "no_sync"]
        assert not wrong, f"{name}: a run has a wrong total"
        print(name, len(rows), "rows")

    series = [("thread", "own threads", BLUE), ("pool", "thread pool", ORANGE)]

    # ---------------------------------------------------------------- Task 1a
    a = scaling(a_rows, "threads", "task1a", "Task 1a: one file, N threads (each thread reads its own part)", "Threads", series)
    counts = sorted(a["thread"])
    write_table("task1a", ["Threads", "Time (ms)", "Speed-up", "Peak mem. (MB)", "Pool: time (ms)", "Pool: speed-up", "Pool: peak mem. (MB)"],
                [(n, f"{a['thread'][n][0] * 1000:.0f}", f"{a['thread'][n][1]:.2f}", f"{a['thread'][n][2]:.1f}",
                  f"{a['pool'][n][0] * 1000:.0f}", f"{a['pool'][n][1]:.2f}", f"{a['pool'][n][2]:.1f}") for n in counts], "rrrrrrr")
    for n in counts:
        w = WORDS[n]
        macro(f"aMs{w}", f"{a['thread'][n][0] * 1000:.0f}")
        macro(f"aSpeed{w}", f"{a['thread'][n][1]:.2f}")
        macro(f"aMem{w}", f"{a['thread'][n][2]:.1f}")
        macro(f"aPoolMs{w}", f"{a['pool'][n][0] * 1000:.0f}")
        macro(f"aPoolSpeed{w}", f"{a['pool'][n][1]:.2f}")
    macro("aSecOne", f"{a['thread'][1][0]:.3f}")
    macro("aSecBest", f"{min(v[0] for v in a['thread'].values()):.3f}")
    macro("aSpeedBest", f"{max(v[1] for v in a['thread'].values()):.2f}")
    macro("aGainSMT", f"{(a['thread'][16][1] / a['thread'][8][1] - 1) * 100:.0f}")
    diffs = [abs(a["pool"][n][0] / a["thread"][n][0] - 1) * 100 for n in counts]
    macro("aPoolMaxDiff", f"{max(diffs):.0f}")
    macro("aRunsEach", str(a["thread"][1][3]))
    macro("aMemExtraPerThread", f"{(a['thread'][64][2] - a['thread'][1][2]) / 63:.1f}")

    # ---------------------------------------------------------------- Task 1b
    versions = [("no_sync", "no sync", RED), ("lock", "lock", BLUE), ("per_thread", "per thread", GREEN)]
    g = group(b_rows, lambda r: r["version"])
    med = {v: st.median(r["time_ms"] for r in g[v]) for v, _, _ in versions}
    fig, ax = plt.subplots(1, 3, figsize=(7.6, 2.9))
    for i, (v, label, color) in enumerate(versions):
        ax[0].bar(label, med[v], color=color, alpha=0.8)
        ax[0].scatter([i] * len(g[v]), [r["time_ms"] for r in g[v]], s=10, color="black", zorder=3)
        ax[0].text(i, max(r["time_ms"] for r in g[v]) * 1.15, f"median {med[v]:.0f}", ha="center", fontsize=6.5)
        ax[1].bar(label, st.median(r["peak_memory_mb"] for r in g[v]), color=color, alpha=0.8)
        ax[2].scatter([i] * len(g[v]), [r["total"] / 1e6 for r in g[v]], s=14, color=color, zorder=3)
    ax[0].set_yscale("log")
    ax[0].set_ylim(8, 2e4)
    ax[0].set_ylabel("Execution time (ms, log scale)")
    ax[1].set_ylabel("Peak memory (MB)")
    ax[2].axhline(50, color="k", ls="--", lw=0.8)
    ax[2].set_xticks(range(3), [l for _, l, _ in versions])
    ax[2].set_ylabel("Counted numbers (millions), every run")
    ax[2].set_ylim(0, 56)
    fig.suptitle("Task 1b: three ways of counting (16 threads, dots = single runs)", fontsize=9)
    save(fig, "task1b")

    lines = []
    names = {"no_sync": "1. no synchronisation", "lock": "2. lock", "per_thread": "3. counter per thread"}
    for v, _, _ in versions:
        rs = g[v]
        totals = [r["total"] for r in rs]
        lines.append((names[v], len(rs), f"{med[v]:.0f}", f"{min(r['time_ms'] for r in rs):.0f}--{max(r['time_ms'] for r in rs):.0f}",
                      f"{max(r['peak_memory_mb'] for r in rs):.0f}",
                      fmt_int(totals[0]) if min(totals) == max(totals) else f"{fmt_int(min(totals))}--{fmt_int(max(totals))}"))
    write_table("task1b", ["Version", "Runs", "Median (ms)", "Min--max (ms)", "Peak mem. (MB)", "Counted total"], lines, "lrrrrr")
    macro("bThreads", str(g["lock"][0]["threads"]))
    macro("bRuns", str(len(g["no_sync"])))
    macro("bNoSyncMsMin", f"{min(r['time_ms'] for r in g['no_sync']):.0f}")
    macro("bNoSyncMsMax", f"{max(r['time_ms'] for r in g['no_sync']):.0f}")
    macro("bNoSyncMs", f"{med['no_sync']:.0f}")
    macro("bLockMs", f"{med['lock']:.0f}")
    macro("bLockMsMin", f"{min(r['time_ms'] for r in g['lock']):.0f}")
    macro("bLockMsMax", f"{max(r['time_ms'] for r in g['lock']):.0f}")
    macro("bPerThreadMs", f"{med['per_thread']:.0f}")
    macro("bPerThreadMsMin", f"{min(r['time_ms'] for r in g['per_thread']):.0f}")
    macro("bPerThreadMsMax", f"{max(r['time_ms'] for r in g['per_thread']):.0f}")
    macro("bNoSyncRatio", f"{med['no_sync'] / med['per_thread']:.0f}")
    macro("bLockRatio", f"{med['lock'] / med['per_thread']:.0f}")
    macro("bLockOverNoSync", f"{med['lock'] / med['no_sync']:.0f}")
    macro("bNoSyncCountMin", f"{min(r['total'] for r in g['no_sync']) / 1e6:.1f}")
    macro("bNoSyncCountMax", f"{max(r['total'] for r in g['no_sync']) / 1e6:.1f}")
    macro("bNoSyncShareMax", f"{max(r['total'] for r in g['no_sync']) / 5e5:.0f}")
    macro("bMemMin", f"{min(r['peak_memory_mb'] for r in b_rows):.0f}")
    macro("bMemMax", f"{max(r['peak_memory_mb'] for r in b_rows):.0f}")

    # ---------------------------------------------------------------- Task 1c
    c = scaling(c_rows, "workers", "task1c", "Task 1c: one reader, N workers, queue of 100 batches of 10 000 lines", "Workers", series)
    write_table("task1c", ["Workers", "Time (s)", "Speed-up", "Peak mem. (MB)", "Pool: time (s)", "Pool: speed-up", "Pool: peak mem. (MB)"],
                [(n, f"{c['thread'][n][0]:.3f}", f"{c['thread'][n][1]:.2f}", f"{c['thread'][n][2]:.1f}",
                  f"{c['pool'][n][0]:.3f}", f"{c['pool'][n][1]:.2f}", f"{c['pool'][n][2]:.1f}") for n in counts], "rrrrrrr")
    for n in counts:
        w = WORDS[n]
        macro(f"cSec{w}", f"{c['thread'][n][0]:.2f}")
        macro(f"cSpeed{w}", f"{c['thread'][n][1]:.2f}")
        macro(f"cMem{w}", f"{c['thread'][n][2]:.0f}")
        macro(f"cPoolSec{w}", f"{c['pool'][n][0]:.2f}")
        macro(f"cPoolMem{w}", f"{c['pool'][n][2]:.0f}")
    best_c = min(counts, key=lambda n: c["thread"][n][0])
    macro("cBestWorkers", str(best_c))
    macro("cSecBest", f"{c['thread'][best_c][0]:.2f}")
    macro("cSpeedBest", f"{c['thread'][best_c][1]:.2f}")
    macro("cOverAOne", f"{c['thread'][1][0] / a['thread'][1][0]:.1f}")
    macro("cOverABest", f"{c['thread'][best_c][0] / min(v[0] for v in a['thread'].values()):.0f}")
    macro("cSlowdownSixtyFour", f"{(c['thread'][64][0] / c['thread'][1][0] - 1) * 100:.0f}")
    macro("cPoolGainSixtyFour", f"{(1 - c['pool'][64][0] / c['thread'][64][0]) * 100:.0f}")
    macro("cPoolMemSavedSixtyFour", f"{c['thread'][64][2] - c['pool'][64][2]:.0f}")
    one = [r["time_ms"] / 1000 for r in c_rows if r["mode"] == "thread" and r["workers"] == 1]
    macro("cOneMin", f"{min(one):.2f}")
    macro("cOneMax", f"{max(one):.2f}")

    # ---------------------------------------------------------------- Task 2
    usb = [r for r in t_rows if r["storage"] == "usb"]
    ssd = [r for r in t_rows if r["storage"] == "internal"]
    tu = group(usb, lambda r: r["threads"])
    ts = group(ssd, lambda r: r["threads"])
    for r in usb:
        r["mode"] = "usb"
    t = scaling(usb, "threads", "task2", "Task 2: eight files on the USB drive (mean of three runs)", "Threads",
                [("usb", "USB drive", BLUE)], agg=st.mean)
    lines = []
    for label, groups in (("USB drive", tu), ("Internal SSD", ts)):
        base = st.mean(r["time_ms"] for r in groups[1])
        for n, rs in groups.items():
            mean = lambda f: st.mean(r[f] for r in rs)
            lines.append((label, n, f"{mean('time_ms') / 1000:.2f}", f"{base / mean('time_ms'):.2f}", f"{mean('read_ms') / 1000:.2f}",
                          f"{mean('parse_ms') / 1000:.2f}", f"{mean('peak_memory_mb'):.0f}", len(rs)))
    write_table("task2", ["Storage", "Threads", "Time (s)", "Speed-up", "Reading (s)", "Parsing (s)", "Peak mem. (MB)", "Runs"],
                lines, "lrrrrrrr")

    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    labels, reads, parses = [], [], []
    for label, groups in (("USB", tu), ("SSD", ts)):
        for n, rs in groups.items():
            labels.append(f"{label}\n{n} thr")
            reads.append(st.mean(r["read_ms"] for r in rs) / 1000)
            parses.append(st.mean(r["parse_ms"] for r in rs) / 1000)
    ax.bar(labels, reads, color=BLUE, label="reading")
    ax.bar(labels, parses, bottom=reads, color=GREEN, label="parsing")
    ax.set_yscale("log")
    ax.set_ylim(0.01, 200)
    ax.set_ylabel("Time of all threads together (s, log scale)")
    ax.legend(fontsize=7)
    ax.set_title("Task 2: reading and parsing time", fontsize=9)
    save(fig, "task2-breakdown")

    for n in (1, 2, 4):
        w = WORDS[n]
        rs = tu[n]
        macro(f"tUsbSec{w}", f"{st.mean(r['time_ms'] for r in rs) / 1000:.2f}")
        macro(f"tUsbSpeed{w}", f"{st.mean(r['time_ms'] for r in tu[1]) / st.mean(r['time_ms'] for r in rs):.2f}")
        macro(f"tUsbRead{w}", f"{st.mean(r['read_ms'] for r in rs) / 1000:.1f}")
        macro(f"tUsbParse{w}", f"{st.mean(r['parse_ms'] for r in rs) / 1000:.2f}")
        macro(f"tUsbMem{w}", f"{st.mean(r['peak_memory_mb'] for r in rs):.0f}")
        macro(f"tUsbSpread{w}", f"{(max(r['time_ms'] for r in rs) - min(r['time_ms'] for r in rs)) / 1000:.1f}")
        macro(f"tSsdMs{w}", f"{st.mean(r['time_ms'] for r in ts[n]):.0f}")
        macro(f"tSsdSpeed{w}", f"{st.mean(r['time_ms'] for r in ts[1]) / st.mean(r['time_ms'] for r in ts[n]):.2f}")
    one = tu[1]
    read_share = st.mean(r["read_ms"] for r in one) / st.mean(r["read_ms"] + r["parse_ms"] for r in one) * 100
    macro("tUsbReadShare", f"{read_share:.0f}")
    macro("tUsbOverA", f"{st.mean(r['time_ms'] for r in one) / 1000 / a['thread'][1][0]:.0f}")
    macro("tUsbOverSsd", f"{st.mean(r['time_ms'] for r in one) / st.mean(r['time_ms'] for r in ts[1]):.0f}")
    macro("tUsbMiBs", f"{352.3 / (st.mean(r['read_ms'] for r in one) / 1000):.0f}")
    macro("tSsdReadShare", f"{st.mean(r['read_ms'] for r in ts[1]) / st.mean(r['read_ms'] + r['parse_ms'] for r in ts[1]) * 100:.0f}")
    macro("tSsdParseOne", f"{st.mean(r['parse_ms'] for r in ts[1]) / 1000:.2f}")
    macro("tSsdReadOne", f"{st.mean(r['read_ms'] for r in ts[1]) / 1000:.2f}")

    # -------------------------------------------------------------- numbers.tex
    lines = ["% generated by plots/make_figures.py - do not edit"]
    for name, value in macros.items():
        lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")
    (TAB / "numbers.tex").write_text("\n".join(lines) + "\n")
    print(len(macros), "numbers written to tables/numbers.tex")


if __name__ == "__main__":
    main()
