using System.Diagnostics;

namespace Lab1;

// Task 2: the 8 files are on a USB drive. A file is the unit of work: a thread reads it in one operation
// into one byte buffer, parses the buffer and counts the numbers. The files are divided among the threads.
// The time of the reading and the time of the parsing are measured separately: if reading takes most of
// the time the work is I/O-bound, if parsing does it is CPU-bound.
public class Task2 : ITask
{
    public void Run(string[] args)
    {
        string folder = Args.Get(args, "dir", "data/parts");
        int threadCount = Args.GetInt(args, "threads", 1);
        string storage = Args.Get(args, "storage", "internal");   // only a label for the csv file: usb or internal

        string[] files = Directory.GetFiles(folder, "numbers_part*.txt");
        Array.Sort(files);
        if (files.Length == 0)
        {
            Console.WriteLine($"No numbers_part*.txt files in {folder}");
            return;
        }

        // one slot per thread: nobody writes where somebody else writes
        Counts[] counts = new Counts[threadCount];
        double[] readMs = new double[threadCount];
        double[] parseMs = new double[threadCount];

        Stopwatch stopwatch = Stopwatch.StartNew();

        Thread[] threads = new Thread[threadCount];
        for (int i = 0; i < threadCount; i++)
        {
            int index = i;
            threads[i] = new Thread(() =>
            {
                // this thread takes the files from 'first' (included) to 'last' (not included)
                int first = files.Length * index / threadCount;
                int last = files.Length * (index + 1) / threadCount;

                // one buffer for the largest of its files, used again for the next file
                long largest = 0;
                for (int k = first; k < last; k++)
                    largest = Math.Max(largest, new FileInfo(files[k]).Length);
                byte[] buffer = new byte[largest];

                for (int k = first; k < last; k++)
                {
                    long start = Stopwatch.GetTimestamp();
                    int length;
                    using (FileStream stream = File.OpenRead(files[k]))
                    {
                        length = (int)stream.Length;
                        stream.ReadExactly(buffer, 0, length);   // the whole file at once
                    }
                    long afterRead = Stopwatch.GetTimestamp();

                    counts[index].AddText(buffer.AsSpan(0, length), true);
                    long afterParse = Stopwatch.GetTimestamp();

                    readMs[index] += Stopwatch.GetElapsedTime(start, afterRead).TotalMilliseconds;
                    parseMs[index] += Stopwatch.GetElapsedTime(afterRead, afterParse).TotalMilliseconds;
                }
            });
            threads[i].Start();
        }
        foreach (Thread thread in threads)
            thread.Join();

        // safe only after Join
        Counts total = new Counts();
        foreach (Counts part in counts)
            total.Add(part);

        stopwatch.Stop();
        double timeMs = stopwatch.Elapsed.TotalMilliseconds;
        double memoryMb = Results.PeakMemoryMb();
        double readTotal = readMs.Sum();
        double parseTotal = parseMs.Sum();
        bool correct = total.Total == Counts.Expected;

        Console.WriteLine($"task2 {storage}: threads={threadCount} time={timeMs:F1} ms peak memory={memoryMb:F1} MB " +
                          $"negative={total.Negative} zero={total.Zero} positive={total.Positive} total={total.Total} " +
                          (correct ? "OK" : "WRONG TOTAL"));
        Console.WriteLine($"reading of all threads together: {readTotal:F1} ms, parsing of all threads together: {parseTotal:F1} ms");

        Results.Save("task2_results.csv",
            "storage,threads,time_ms,peak_memory_mb,read_ms,parse_ms,negative,zero,positive,total,correct",
            $"{storage},{threadCount},{timeMs:F3},{memoryMb:F2},{readTotal:F3},{parseTotal:F3},{total.Negative},{total.Zero},{total.Positive},{total.Total},{(correct ? 1 : 0)}");
    }
}
