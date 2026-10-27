namespace Lab1;

// Creates numbers.txt: 50 000 000 random integers from -1 000 000 to 1 000 000, one per line.
public class GenerateTask : ITask
{
    public void Run(string[] args)
    {
        string path = Args.Get(args, "output", "data/numbers.txt");
        int seed = Args.GetInt(args, "seed", 12345);

        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);

        Random random = new Random(seed);
        Counts counts = new Counts();

        using (StreamWriter writer = new StreamWriter(path))
        {
            for (long i = 0; i < Counts.Expected; i++)
            {
                int number = random.Next(-1_000_000, 1_000_001);
                writer.WriteLine(number);
                counts.Add(number);
            }
        }

        // the correct answer that every task has to find
        Console.WriteLine($"Written {path}: negative={counts.Negative} zero={counts.Zero} positive={counts.Positive}");
    }
}
