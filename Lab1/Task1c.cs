using System.Collections.Concurrent;
using System.Diagnostics;

namespace Lab1;

// Task 1c: producer and consumers.
// One reader thread reads numbers.txt line by line and puts the lines, in batches of 10 000, in a queue.
// The queue is blocking and holds at most 100 batches: when it is full the reader waits, when it is empty the workers wait.
// The workers take a batch and count its numbers. At the end of the file the reader closes the queue.
// With --pool the reader and the workers run on the thread pool (Task.Run) instead of our own threads.
public class Task1c : ITask
{
    private const int BatchSize = 10_000;
    private const int QueueSize = 100;

    public void Run(string[] args)
    {
        string path = Args.Get(args, "input", "data/numbers.txt");
        int workerCount = Args.GetInt(args, "threads", 1);
        bool usePool = Args.Has(args, "pool");

        Stopwatch stopwatch = Stopwatch.StartNew();

        BlockingCollection<List<string>> queue = new BlockingCollection<List<string>>(QueueSize);

        // one slot per worker: nobody writes where somebody else writes
        Counts[] counts = new Counts[workerCount];

        if (usePool)
        {
            Task reader = Task.Run(() => ReadFile(path, queue));
            Task[] workers = new Task[workerCount];
            for (int i = 0; i < workerCount; i++)
            {
                int index = i;
                workers[i] = Task.Run(() => { counts[index] = CountBatches(queue); });
            }
            reader.Wait();
            Task.WaitAll(workers);
        }
        else
        {
            Thread reader = new Thread(() => ReadFile(path, queue));
            reader.Start();

            Thread[] workers = new Thread[workerCount];
            for (int i = 0; i < workerCount; i++)
            {
                int index = i;
                workers[i] = new Thread(() => { counts[index] = CountBatches(queue); });
                workers[i].Start();
            }
            reader.Join();
            foreach (Thread worker in workers)
                worker.Join();
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

        Console.WriteLine($"task1c {mode}: workers={workerCount} time={timeMs:F1} ms peak memory={memoryMb:F1} MB " +
                          $"negative={total.Negative} zero={total.Zero} positive={total.Positive} total={total.Total} " +
                          (correct ? "OK" : "WRONG TOTAL"));

        Results.Save("task1c_results.csv",
            "mode,workers,time_ms,peak_memory_mb,negative,zero,positive,total,correct",
            $"{mode},{workerCount},{timeMs:F3},{memoryMb:F2},{total.Negative},{total.Zero},{total.Positive},{total.Total},{(correct ? 1 : 0)}");
    }

    // The producer: reads the file and fills the queue.
    private static void ReadFile(string path, BlockingCollection<List<string>> queue)
    {
        using StreamReader reader = new StreamReader(path);
        List<string> batch = new List<string>(BatchSize);

        string? line;
        while ((line = reader.ReadLine()) != null)
        {
            batch.Add(line);
            if (batch.Count == BatchSize)
            {
                queue.Add(batch);   // waits here while the queue is full
                batch = new List<string>(BatchSize);
            }
        }

        if (batch.Count > 0)
            queue.Add(batch);

        queue.CompleteAdding();   // no more batches: the workers can stop
    }

    // A consumer: takes batches until the queue is closed and empty.
    private static Counts CountBatches(BlockingCollection<List<string>> queue)
    {
        Counts counts = new Counts();

        // waits while the queue is empty, ends after CompleteAdding when nothing is left
        foreach (List<string> batch in queue.GetConsumingEnumerable())
        {
            foreach (string line in batch)
                counts.Add(int.Parse(line));
        }
        return counts;
    }
}
