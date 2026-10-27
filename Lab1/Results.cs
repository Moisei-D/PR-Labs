using System.Diagnostics;

namespace Lab1;

// Memory and the csv files with the results (data/task1a_results.csv, ...).
public static class Results
{
    // the highest amount of memory the process had in RAM since it started
    public static double PeakMemoryMb()
    {
        using Process process = Process.GetCurrentProcess();
        return process.PeakWorkingSet64 / (1024.0 * 1024.0);
    }

    // adds one row to the file in the data folder; the header is written when the file is new
    public static void Save(string fileName, string header, string row)
    {
        Directory.CreateDirectory("data");
        string path = Path.Combine("data", fileName);

        if (!File.Exists(path))
            File.AppendAllText(path, header + "\n");
        File.AppendAllText(path, row + "\n");
    }
}
