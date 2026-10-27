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
