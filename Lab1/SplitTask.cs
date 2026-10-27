namespace Lab1;

// Splits numbers.txt, in order, into 8 files of 6 250 000 numbers for Task 2.
public class SplitTask : ITask
{
    private const int Parts = 8;
    private const int LinesPerPart = 6_250_000;

    public void Run(string[] args)
    {
        string input = Args.Get(args, "input", "data/numbers.txt");
        string folder = Args.Get(args, "output", "data/parts");

        Directory.CreateDirectory(folder);

        using StreamReader reader = new StreamReader(input);
        for (int part = 1; part <= Parts; part++)
        {
            string path = Path.Combine(folder, $"numbers_part{part:D2}.txt");
            using StreamWriter writer = new StreamWriter(path);

            for (int i = 0; i < LinesPerPart; i++)
                writer.WriteLine(reader.ReadLine());

            Console.WriteLine($"Written {path}");
        }
    }
}
