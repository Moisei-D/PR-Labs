using Lab1;

// the first argument chooses the task, the other arguments are its options (for example --threads 8)
if (args.Length == 0)
{
    Console.WriteLine("usage: dotnet run -c Release -- <generate|split|task1a|task1b|task1c|task2> [--option value]");
    return;
}

ITask? task = args[0] switch
{
    "generate" => new GenerateTask(),
    "split" => new SplitTask(),
    "task1a" => new Task1a(),
    "task1b" => new Task1b(),
    "task1c" => new Task1c(),
    "task2" => new Task2(),
    _ => null
};

if (task == null)
{
    Console.WriteLine($"Unknown task '{args[0]}'");
    return;
}

task.Run(args[1..]);
