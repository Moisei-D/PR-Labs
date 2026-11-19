using System.Net;
using System.Net.Sockets;
using System.Text;

namespace Lab2;

// The console program of a client and of the provider (the provider says PROVIDER when it connects).
// Two threads: the main thread receives and shows the messages of the server,
// a second thread reads the keyboard and sends what the user types.
public class Client
{
    private Socket socket = null!;
    private volatile bool quitting;

    public void Run(string[] args, bool isProvider)
    {
        string host = Args.Get(args, "host", "127.0.0.1");
        int port = Args.GetInt(args, "port", 5000, 1, 65535);

        socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
        try
        {
            // the host can be an address (192.168.1.20) or a name (localhost)
            IPAddress address = Dns.GetHostAddresses(host).First(a => a.AddressFamily == AddressFamily.InterNetwork);
            socket.Connect(new IPEndPoint(address, port));
        }
        catch (Exception e) when (e is SocketException or InvalidOperationException or ArgumentException)
        {
            Console.WriteLine($"Cannot connect to {host}:{port}: {e.Message}");
            return;
        }

        Console.WriteLine($"Connected to {host}:{port} as {(isProvider ? "the provider" : "a client")}.");
        PrintHelp(isProvider);

        if (isProvider)
            Send("PROVIDER");

        // a background thread does not keep the program alive: when the main thread ends,
        // the program ends, also while this thread still waits in Console.ReadLine
        Thread keyboard = new Thread(() => ReadKeyboard(isProvider));
        keyboard.IsBackground = true;
        keyboard.Start();

        try
        {
            byte[] buffer = new byte[4096];
            MessageReader reader = new MessageReader();

            while (true)
            {
                int count = socket.Receive(buffer);   // waits here for the server
                if (count == 0)
                {
                    Console.WriteLine(quitting ? "Bye." : "The server closed the connection.");
                    break;
                }
                reader.Add(buffer, count, Show, () => Show("(a message that was too long)"));
            }
        }
        catch (SocketException e)
        {
            Console.WriteLine($"The connection to the server was lost ({e.SocketErrorCode}).");
        }

        socket.Close();
    }

    // every message is shown the moment it arrives, with the time
    private static void Show(string message)
    {
        Console.WriteLine($"[{DateTime.Now:HH:mm:ss}] {message}");
    }

    private void ReadKeyboard(bool isProvider)
    {
        string? line;
        while ((line = Console.ReadLine()) != null)
        {
            line = line.Trim();

            if (line == "quit" || line == "exit")
                break;

            if (line == "help")
                PrintHelp(isProvider);
            else if (line != "")
                Send(line);
        }

        // The user has finished. Only our direction is closed: the server sees the end of the stream,
        // closes its side, and the main thread ends when Receive returns 0.
        quitting = true;
        try
        {
            socket.Shutdown(SocketShutdown.Send);
        }
        catch (Exception e) when (e is SocketException or ObjectDisposedException)
        {
        }
    }

    private void Send(string message)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(message + "\n");
        try
        {
            int sent = 0;
            while (sent < bytes.Length)
                sent += socket.Send(bytes, sent, bytes.Length - sent, SocketFlags.None);
        }
        catch (Exception e) when (e is SocketException or ObjectDisposedException)
        {
            // the server is gone; the main thread notices the same in Receive and ends the program
        }
    }

    private static void PrintHelp(bool isProvider)
    {
        Console.WriteLine("Commands:");
        Console.WriteLine("  menu                                 the products and how many are in stock");
        if (isProvider)
            Console.WriteLine("  deliver coffee 20 croissant 10       bring products");
        else
            Console.WriteLine("  order croissant 2 tea 1 coffee 1     order products");
        Console.WriteLine("  help, quit");
    }
}
