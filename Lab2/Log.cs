namespace Lab2;

// The log of the server: one line with the time, the endpoint of the client and what happened.
// Console.WriteLine writes a whole line at once, so lines of different threads do not mix.
public static class Log
{
    public static void Write(string who, string text)
    {
        Console.WriteLine($"{DateTime.Now:HH:mm:ss.fff}  {who,-21}  {text}");
    }
}
