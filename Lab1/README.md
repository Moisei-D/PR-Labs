# Lab 1 – Concurrency in practice

C# (.NET 10). One program: the first argument chooses the task, the other arguments are its options.
Run everything from this folder (`Lab1/`) in **Release** mode.

```bash
dotnet build -c Release
```

| File | What it does |
|------|--------------|
| `Program.cs` | creates the task chosen by the first argument and runs it |
| `ITask.cs` | the interface of a task: `Run(string[] args)` |
| `GenerateTask.cs`, `SplitTask.cs` | create `numbers.txt` and the 8 files for Task 2 |
| `Task1a.cs`, `Task1b.cs`, `Task1c.cs`, `Task2.cs` | the tasks of the lab; each one creates its own threads |
| `Counts.cs` | negative / zero / positive counters and the byte parser |
| `Args.cs`, `Results.cs` | reading `--options`, peak memory, writing the csv files |

Every task prints its counters (`OK` means they add up to 50 000 000) and appends a row to `data/<task>_results.csv`
(`task1a_results.csv`, `task1b_results.csv`, `task1c_results.csv`, `task2_results.csv`).
`numbers.txt` and `data/parts/` are not committed; the csv files are.

## Data

```bash
dotnet run -c Release -- generate     # data/numbers.txt; prints the correct counters
dotnet run -c Release -- split        # data/parts/numbers_part01.txt ... 08.txt
```

## Task 1a – one file, N threads

```bash
dotnet run -c Release -- task1a --threads 1
dotnet run -c Release -- task1a --threads 2        # 4, 8, 16, 32, 64 in the same way
dotnet run -c Release -- task1a --threads 8 --pool # the same work on the thread pool (experiment)
```

## Task 1b – shared counters

```bash
dotnet run -c Release -- task1b       # threads = logical processors; version 1 runs three times
```

## Task 1c – reader and workers

```bash
dotnet run -c Release -- task1c --threads 1        # workers: 2, 4, 8, 16, 32, 64
dotnet run -c Release -- task1c --threads 8 --pool # workers on the thread pool (experiment)
```

## Task 2 – files on the USB drive

1. Plug in the drive and mount it; find its folder: `lsblk -o NAME,SIZE,TRAN,MOUNTPOINT`
   (not mounted: `udisksctl mount -b /dev/sdX1`).
2. Copy the files to it (the folder must be writable for you):
   ```bash
   dotnet run -c Release -- split --output /run/media/$USER/DRIVE
   ```
3. **Before every run** eject the drive, unplug it, plug it back in, wait until it is mounted, then run one configuration:
   ```bash
   dotnet run -c Release -- task2 --dir /run/media/$USER/DRIVE --threads 1 --storage usb
   ```
   and the same with `--threads 2` and `--threads 4`, each time after unplugging the drive again.
4. For the comparison with Task 1a, on the internal disk: `dotnet run -c Release -- task2 --threads 1 --storage internal`

## Hardware for the report

```bash
lscpu
free -h
lsblk -d -o NAME,MODEL,SIZE,TRAN
lsusb -t        # speed of the drive: 480M = USB 2.0, 5000M = USB 3.x
dotnet --version
```

## Charts and tables for the report

Copy the results to the report folder and run the python script (matplotlib is in `Reports/.venv`):

```bash
cp data/*_results.csv "../Reports/Lab1 Report/data/"
../Reports/.venv/bin/python "../Reports/Lab1 Report/plots/make_figures.py"
cd "../Reports/Lab1 Report" && tectonic Lab1_Moisei_Daniel_Report.tex
```

Start a new process for every measurement (that is what the commands above do), so the peak memory belongs to that run.
The first run after a long time also fills the file cache: run Task 1a once before measuring.

## Extra check used in the report (not part of the program)

How fast the USB drive is with 1, 2 and 4 readers, without the file cache (direct I/O); the result is in `Reports/Lab1 Report/data/usb-throughput.txt`:

```bash
dd if=/run/media/$USER/DRIVE/numbers_part01.txt of=/dev/null bs=1M iflag=direct
# for 2 and 4 readers start dd for part01, part02, (part03, part04) at the same time and divide the total size by the time
```
