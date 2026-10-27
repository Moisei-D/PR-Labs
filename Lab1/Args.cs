namespace Lab1;

// Reads the options of the command line, for example: --threads 8 --pool
public static class Args
{
    public static string Get(string[] args, string name, string defaultValue)
    {
        int index = Array.IndexOf(args, "--" + name);
        if (index >= 0 && index + 1 < args.Length)
            return args[index + 1];
        return defaultValue;
    }

    public static int GetInt(string[] args, string name, int defaultValue)
    {
        return int.Parse(Get(args, name, defaultValue.ToString()));
    }

    // an option without a value, for example --pool
    public static bool Has(string[] args, string name)
    {
        return args.Contains("--" + name);
    }
}
