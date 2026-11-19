# Reports

One subfolder per laboratory work. `.venv/` (not committed) is a Python environment with matplotlib for the charts.

## `Lab1 Report/` – Concurrency in Practice

| Path | Content |
|------|---------|
| `Lab1_Moisei_Daniel_Report.tex` / `.pdf` | the report (`tectonic Lab1_Moisei_Daniel_Report.tex`) |
| `data/` | `task1a_results.csv`, `task1b_results.csv`, `task1c_results.csv`, `task2_results.csv` (copied from `Lab1/data`), `hardware.txt`, `usb-throughput.txt` (cold-read test of the USB drive with `dd`) |
| `plots/make_figures.py` | makes `figures/` and `tables/` (also `tables/numbers.tex`, the numbers used in the text) from `data/` |
| `figures/` | charts (pdf for LaTeX, png for preview) and the university logo |
| `tables/` | generated LaTeX tables and numbers |

```bash
.venv/bin/python "Lab1 Report/plots/make_figures.py"
cd "Lab1 Report" && tectonic Lab1_Moisei_Daniel_Report.tex
```

## `Lab2 Report/` – A Coffee Shop Server

| Path | Content |
|------|---------|
| `Lab2_Moisei_Daniel_Report.tex` / `.pdf` | the report (`tectonic Lab2_Moisei_Daniel_Report.tex`) |
| `data/` | the output of `Lab2/tests/scenarios.py`, copied from `Lab2/data`: transcripts of the clients (`*_clients.txt`), logs of the server (`*_server.log`), `checks.csv`, `facts.csv`, `idle_clients.csv`, `workers.csv`, `environment.txt` |
| `plots/make_figures.py` | makes `figures/` and `tables/` (also `tables/numbers.tex`, the numbers used in the text, and `tables/excerpt_*.txt`, the parts of the transcripts and logs that the report shows) from `data/` |
| `figures/` | charts (pdf for LaTeX, png for preview) and the university logo |
| `tables/` | generated LaTeX tables, numbers and excerpts |

```bash
cp ../Lab2/data/*.txt ../Lab2/data/*.log ../Lab2/data/*.csv "Lab2 Report/data/"
.venv/bin/python "Lab2 Report/plots/make_figures.py"
cd "Lab2 Report" && tectonic Lab2_Moisei_Daniel_Report.tex
```

The environment table, the transcripts and every number of the report come from the last run of the scenarios,
so the report describes the machine on which they were run: run them again on your own machine before compiling.
