using System.Diagnostics;
using Microsoft.Win32.SafeHandles;

namespace Lab1;

// Task 1a: count the numbers of one file with N threads.
// The file is divided into N parts and every thread reads and parses only its own part.
// With --pool the parts are given to the thread pool (Task.Run) instead of our own threads.
public class Task1a : ITask
{
    private const int BufferSize = 1024 * 1024;

    public void Run(string[] args)
    {
        string path = Args.Get(args, "input", "data/numbers.txt");
        int threadCount = Args.GetInt(args, "threads", 1);
        bool usePool = Args.Has(args, "pool");

        Stopwatch stopwatch = Stopwatch.StartNew();

        using SafeFileHandle file = File.OpenHandle(path);
        long size = RandomAccess.GetLength(file);

        // one slot per thread: nobody writes where somebody else writes
        Counts[] counts = new Counts[threadCount];

        if (usePool)
        {
            Task[] tasks = new Task[threadCount];
            for (int i = 0; i < threadCount; i++)
            {
                int index = i;
                tasks[i] = Task.Run(() => { counts[index] = CountPart(file, size, index, threadCount); });
            }
            Task.WaitAll(tasks);
        }
        else
        {
            Thread[] threads = new Thread[threadCount];
            for (int i = 0; i < threadCount; i++)
            {
                int index = i;
                threads[i] = new Thread(() => { counts[index] = CountPart(file, size, index, threadCount); });
                threads[i].Start();
            }
            foreach (Thread thread in threads)
                thread.Join();
        }

        // safe only after Join
        Counts total = new Counts();
        foreach (Counts part in counts)
            total.Add(part);

        stopwatch.Stop();
        double timeMs = stopwatch.Elapsed.TotalMilliseconds;
        double memoryMb = Results.PeakMemoryMb();
        string mode = usePool ? "pool" : "thread";
        bool correct = total.Total == Counts.Expected;

        Console.WriteLine($"task1a {mode}: threads={threadCount} time={timeMs:F1} ms peak memory={memoryMb:F1} MB " +
                          $"negative={total.Negative} zero={total.Zero} positive={total.Positive} total={total.Total} " +
                          (correct ? "OK" : "WRONG TOTAL"));

        Results.Save("task1a_results.csv",
            "mode,threads,time_ms,peak_memory_mb,negative,zero,positive,total,correct",
            $"{mode},{threadCount},{timeMs:F3},{memoryMb:F2},{total.Negative},{total.Zero},{total.Positive},{total.Total},{(correct ? 1 : 0)}");
    }

    // Counts part number 'index' of the file.
    // The end of this part is the start of the next part, so every line belongs to exactly one thread.
    private static Counts CountPart(SafeFileHandle file, long size, int index, int partCount)
    {
        long start = FindPartStart(file, size, index, partCount);
        long end = FindPartStart(file, size, index + 1, partCount);

        Counts counts = new Counts();
        byte[] buffer = new byte[BufferSize];
        long position = start;
        int leftover = 0;   // the beginning of a line from the previous block

        while (position < end)
        {
            int toRead = (int)Math.Min(buffer.Length - leftover, end - position);
            int read = RandomAccess.Read(file, buffer.AsSpan(leftover, toRead), position);
            if (read == 0) break;
            position += read;

            int filled = leftover + read;
            bool isLast = position >= end;
            int used = counts.AddText(buffer.AsSpan(0, filled), isLast);

            // move the unfinished line to the start of the buffer
            leftover = filled - used;
            Array.Copy(buffer, used, buffer, 0, leftover);
        }
        return counts;
    }

    // Where part number 'index' begins. Cutting the file at size * index / partCount would usually
    // stop in the middle of a line, so we go to the first byte after the next '\n'.
    // We look from the byte before the cut: if that byte is a '\n', the line starts exactly at the cut.
    // The same position always gives the same answer, so no line is skipped and none is counted twice.
    private static long FindPartStart(SafeFileHandle file, long size, int index, int partCount)
    {
        if (index == 0) return 0;
        if (index == partCount) return size;

        long position = size * index / partCount - 1;
        byte[] buffer = new byte[4096];

        while (position < size)
        {
            int read = RandomAccess.Read(file, buffer, position);
            if (read == 0) break;

            int newLine = Array.IndexOf(buffer, (byte)'\n', 0, read);
            if (newLine >= 0)
                return position + newLine + 1;

            position += read;
        }
        return size;
    }
}
