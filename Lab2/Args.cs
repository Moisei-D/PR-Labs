namespace Lab2;

// Reads the options of the command line, for example: --port 5000 --workers 2
public static class Args
{
    public static string Get(string[] args, string name, string defaultValue)
    {
        int index = Array.IndexOf(args, "--" + name);
        if (index >= 0 && index + 1 < args.Length)
            return args[index + 1];
        return defaultValue;
    }

    // a whole number between min and max; a wrong value ends the program with a message
    public static int GetInt(string[] args, string name, int defaultValue, int min, int max)
    {
        string text = Get(args, name, defaultValue.ToString());
        if (int.TryParse(text, out int value) && value >= min && value <= max)
            return value;

        Console.WriteLine($"--{name} must be a number from {min} to {max}, not '{text}'");
        Environment.Exit(1);
        return 0;
    }

    // an option without a value, for example --new-stock
    public static bool Has(string[] args, string name)
    {
        return args.Contains("--" + name);
    }
}
