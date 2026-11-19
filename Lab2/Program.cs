using Lab2;

// the first argument chooses the role, the other arguments are its options (for example --port 5000)
if (args.Length == 0)
{
    Console.WriteLine("usage: dotnet run -c Release -- server   [--port 5000] [--workers N] [--new-stock]");
    Console.WriteLine("       dotnet run -c Release -- client   [--host 127.0.0.1] [--port 5000]");
    Console.WriteLine("       dotnet run -c Release -- provider [--host 127.0.0.1] [--port 5000]");
    return;
}

switch (args[0])
{
    case "server":
        new Server().Run(args[1..]);
        break;
    case "client":
        new Client().Run(args[1..], isProvider: false);
        break;
    case "provider":
        new Client().Run(args[1..], isProvider: true);
        break;
    default:
        Console.WriteLine($"Unknown role '{args[0]}'");
        break;
}
