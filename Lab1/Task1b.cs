using System.Diagnostics;

namespace Lab1;

// Task 1b: the numbers are already in an int array. Count them with as many threads as the processor
// has logical processors, in three ways:
//   1. shared counters without synchronisation (the result is wrong: this is the race condition)
//   2. shared counters protected by a lock
//   3. a separate counter for each thread, added together after all threads have finished
public class Task1b : ITask
{
    public void Run(string[] args)
    {
        string path = Args.Get(args, "input", "data/numbers.txt");
        int threadCount = Args.GetInt(args, "threads", Environment.ProcessorCount);

        // loading the numbers is not measured
        int[] numbers = new int[Counts.Expected];
        int loaded = 0;
        foreach (string line in File.ReadLines(path))
            numbers[loaded++] = int.Parse(line);
        Console.WriteLine($"Loaded {loaded} numbers");

        // version 1 is run three times
        for (int run = 1; run <= 3; run++)
            Measure("no_sync", run, numbers, threadCount);
        Measure("lock", 1, numbers, threadCount);
        Measure("per_thread", 1, numbers, threadCount);
    }

    private static void Measure(string version, int run, int[] numbers, int threadCount)
    {
        Stopwatch stopwatch = Stopwatch.StartNew();

        Counts total = version switch
        {
            "no_sync" => CountWithoutSync(numbers, threadCount),
            "lock" => CountWithLock(numbers, threadCount),
            _ => CountPerThread(numbers, threadCount)
        };

        stopwatch.Stop();
        double timeMs = stopwatch.Elapsed.TotalMilliseconds;
        double memoryMb = Results.PeakMemoryMb();
        bool correct = total.Total == Counts.Expected;

        Console.WriteLine($"task1b {version} (run {run}): threads={threadCount} time={timeMs:F1} ms peak memory={memoryMb:F1} MB " +
                          $"negative={total.Negative} zero={total.Zero} positive={total.Positive} total={total.Total} " +
                          (correct ? "OK" : "WRONG TOTAL"));

        Results.Save("task1b_results.csv",
            "version,run,threads,time_ms,peak_memory_mb,negative,zero,positive,total,correct",
            $"{version},{run},{threadCount},{timeMs:F3},{memoryMb:F2},{total.Negative},{total.Zero},{total.Positive},{total.Total},{(correct ? 1 : 0)}");
    }

    // The part of the array of thread 'index': from (included) to (not included).
    private static (int From, int To) GetRange(int length, int threadCount, int index)
    {
        int from = (int)((long)length * index / threadCount);
        int to = (int)((long)length * (index + 1) / threadCount);
        return (from, to);
    }

    private static Counts CountWithoutSync(int[] numbers, int threadCount)
    {
        long[] shared = new long[3];   // negative, zero, positive

        Thread[] threads = new Thread[threadCount];
        for (int i = 0; i < threadCount; i++)
        {
            int index = i;
            threads[i] = new Thread(() =>
            {
                (int from, int to) = GetRange(numbers.Length, threadCount, index);
                for (int k = from; k < to; k++)
                {
                    if (numbers[k] < 0) shared[0]++;
                    else if (numbers[k] == 0) shared[1]++;
                    else shared[2]++;
                }
            });
            threads[i].Start();
        }
        foreach (Thread thread in threads)
            thread.Join();

        return new Counts { Negative = shared[0], Zero = shared[1], Positive = shared[2] };
    }

    private static Counts CountWithLock(int[] numbers, int threadCount)
    {
        long[] shared = new long[3];
        object gate = new object();

        Thread[] threads = new Thread[threadCount];
        for (int i = 0; i < threadCount; i++)
        {
            int index = i;
            threads[i] = new Thread(() =>
            {
                (int from, int to) = GetRange(numbers.Length, threadCount, index);
                for (int k = from; k < to; k++)
                {
                    lock (gate)
                    {
                        if (numbers[k] < 0) shared[0]++;
                        else if (numbers[k] == 0) shared[1]++;
                        else shared[2]++;
                    }
                }
            });
            threads[i].Start();
        }
        foreach (Thread thread in threads)
            thread.Join();

        return new Counts { Negative = shared[0], Zero = shared[1], Positive = shared[2] };
    }

    private static Counts CountPerThread(int[] numbers, int threadCount)
    {
        // one slot per thread: nobody writes where somebody else writes
        Counts[] counts = new Counts[threadCount];

        Thread[] threads = new Thread[threadCount];
        for (int i = 0; i < threadCount; i++)
        {
            int index = i;
            threads[i] = new Thread(() =>
            {
                (int from, int to) = GetRange(numbers.Length, threadCount, index);
                Counts mine = new Counts();   // only this thread uses it
                for (int k = from; k < to; k++)
                    mine.Add(numbers[k]);
                counts[index] = mine;
            });
            threads[i].Start();
        }
        foreach (Thread thread in threads)
            thread.Join();

        // safe only after Join
        Counts total = new Counts();
        foreach (Counts part in counts)
            total.Add(part);
        return total;
    }
}
