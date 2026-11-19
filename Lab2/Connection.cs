using System.Globalization;
using System.Net.Sockets;
using System.Text;

namespace Lab2;

// One connected client (or the provider): the socket returned by Accept and the thread that reads from it.
public class Connection
{
    private const int MaxQuantity = 1000;

    private readonly Socket socket;
    private readonly Shop shop;
    private bool isProvider;   // used only by the thread of this connection

    // set by the thread that closes the socket, read by the others; volatile: every thread sees the new value at once
    private volatile bool closed;

    // The thread of this connection sends the answers; a worker sends READY; the thread of another client
    // sends an ALERT to the provider. Only one of them can be inside Send at a time.
    private readonly object sendGate = new object();

    // the endpoint of the client, for the log: 192.168.1.20:53422
    public readonly string Name;

    // the orders of this client that are not ready yet; protected by the lock of the shop
    public readonly List<Order> Orders = new List<Order>();

    // set when the client has disappeared; a worker that prepares one of its orders waits on it
    public readonly ManualResetEventSlim Gone = new ManualResetEventSlim(false);

    public Connection(Socket socket, Shop shop)
    {
        this.socket = socket;
        this.shop = shop;
        Name = socket.RemoteEndPoint?.ToString() ?? "unknown";
    }

    // The thread of the connection: receives until the client disappears, then cleans up.
    public void Run()
    {
        Log.Write(Name, "connected");
        string end = "disconnected";

        try
        {
            byte[] buffer = new byte[4096];
            MessageReader reader = new MessageReader();

            while (true)
            {
                int count = socket.Receive(buffer);   // waits here for the client
                if (count == 0)
                {
                    end = "disconnected: the client closed the connection";
                    break;
                }
                reader.Add(buffer, count, Handle, TooLong);
            }
        }
        catch (SocketException e)
        {
            // reset: the process of the client was killed; timed out: the client did not answer the keep-alive probes
            if (closed)
                end = "disconnected: the server closed the connection";   // another thread closed the socket after a failed Send
            else
                end = $"disconnected: connection lost ({e.SocketErrorCode})";
        }
        catch (ObjectDisposedException)
        {
            end = "disconnected: the server closed the connection";
        }
        catch (Exception e)
        {
            // a mistake in our code must end one connection, not the server
            end = $"disconnected: error {e.GetType().Name}: {e.Message}";
        }

        Log.Write(Name, end);

        // First the orders are cancelled inside the lock of the shop, then the worker is woken:
        // when it looks at its order, the order is already cancelled.
        List<string> cancelled = shop.Leave(this);
        foreach (string line in cancelled)
            Log.Write(Name, line);

        Gone.Set();
        Close();
    }

    // Sends one message. Can be called from any thread.
    public void Send(string message)
    {
        if (closed)
            return;

        byte[] bytes = Encoding.UTF8.GetBytes(message + "\n");

        try
        {
            lock (sendGate)
            {
                // Send can take only a part of the bytes: it is repeated until all are sent
                int sent = 0;
                while (sent < bytes.Length)
                    sent += socket.Send(bytes, sent, bytes.Length - sent, SocketFlags.None);
            }
        }
        catch (Exception e) when (e is SocketException or ObjectDisposedException)
        {
            // The client is gone, or it has not read for 5 seconds (SendTimeout).
            // The socket is closed here; the thread of the connection then leaves Receive
            // and cancels the orders.
            if (!closed)
                Log.Write(Name, $"error: send failed ({(e as SocketException)?.SocketErrorCode.ToString() ?? "closed"}), the server closes the connection");
            Close();
        }
    }

    private void Close()
    {
        closed = true;
        try
        {
            socket.Close();
        }
        catch (SocketException)
        {
        }
    }

    // ---- messages ----

    private void TooLong()
    {
        if (closed)
            return;

        Error($"message too long (the limit is {MessageReader.MaxLength} bytes)", "...");
    }

    private void Handle(string message)
    {
        if (closed)
            return;   // the messages that were received together with the last one are not handled any more

        string[] words = message.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (words.Length == 0)
        {
            Error("empty message", message);
            return;
        }

        switch (words[0].ToUpperInvariant())
        {
            case "MENU":
                HandleMenu(words, message);
                break;
            case "ORDER":
                HandleOrder(words, message);
                break;
            case "PROVIDER":
                HandleProvider(words, message);
                break;
            case "DELIVER":
                HandleDeliver(words, message);
                break;
            default:
                Error("unknown command (commands: MENU, ORDER, PROVIDER, DELIVER)", message);
                break;
        }
    }

    private void HandleMenu(string[] words, string message)
    {
        if (words.Length != 1)
        {
            Error("MENU has no parameters", message);
            return;
        }
        Send("MENU " + Menu.Format(shop.GetStock()));
    }

    private void HandleOrder(string[] words, string message)
    {
        if (isProvider)
        {
            Error("the provider cannot order", message);
            return;
        }

        int[]? items = ParseItems(words, message);
        if (items == null)
            return;

        Order? order = shop.TakeOrder(this, items, out int[] stockNow);
        if (order == null)
        {
            Log.Write(Name, $"order refused: {Menu.FormatItems(items)}; in stock: {Menu.Format(stockNow)}");
            Send("REFUSED not enough in stock: " + Menu.Format(stockNow));
            return;
        }

        // The products are already taken. The client gets its answer now, the order goes to the workers,
        // and READY is sent later by the worker that prepares it.
        Log.Write(Name, $"order {order.Number} accepted: {Menu.FormatItems(items)}, {order.Seconds} s; in stock: {Menu.Format(stockNow)}");
        Send($"ACCEPTED order={order.Number} seconds={order.Seconds}");
        shop.Enqueue(order);

        shop.AlertProvider(items);
    }

    private void HandleProvider(string[] words, string message)
    {
        if (words.Length != 1)
        {
            Error("PROVIDER has no parameters", message);
            return;
        }

        string? error = shop.SetProvider(this);
        if (error != null)
        {
            Error(error, message);
            return;
        }

        isProvider = true;
        Log.Write(Name, "is the provider");
        Send("PROVIDER ok");

        // the alerts that nobody received while no provider was connected
        int[] all = new int[Menu.Count];
        Array.Fill(all, 1);
        shop.AlertProvider(all);
    }

    private void HandleDeliver(string[] words, string message)
    {
        if (!isProvider)
        {
            Error("only the provider can deliver", message);
            return;
        }

        int[]? items = ParseItems(words, message);
        if (items == null)
            return;

        int[] stockNow = shop.Deliver(items);
        Log.Write(Name, $"delivery: {Menu.FormatItems(items)}; in stock: {Menu.Format(stockNow)}");
        Send("DELIVERED " + Menu.Format(stockNow));
    }

    // Reads "<product> <quantity> <product> <quantity> ..." after the command.
    // Returns the quantity of every product, or null after it has sent an error message.
    private int[]? ParseItems(string[] words, string message)
    {
        string command = words[0].ToUpperInvariant();

        if (words.Length < 3 || words.Length % 2 == 0)
        {
            Error($"usage: {command} <product> <quantity> [<product> <quantity> ...]", message);
            return null;
        }

        int[] items = new int[Menu.Count];

        for (int i = 1; i < words.Length; i += 2)
        {
            int product = Menu.IndexOf(words[i]);
            if (product < 0)
            {
                Error($"unknown product '{Printable(words[i])}' (products: {string.Join(", ", Menu.Names)})", message);
                return null;
            }

            // NumberStyles.None: only digits, so "-1", "+2", "1.5" and "two" are all refused
            bool isNumber = int.TryParse(words[i + 1], NumberStyles.None, CultureInfo.InvariantCulture, out int quantity);
            if (!isNumber || quantity < 1 || quantity > MaxQuantity)
            {
                Error($"the quantity of {Menu.Names[product]} must be a number from 1 to {MaxQuantity}, not '{Printable(words[i + 1])}'", message);
                return null;
            }

            items[product] += quantity;   // the same product twice in one message is added up
            if (items[product] > MaxQuantity)
            {
                Error($"the quantity of {Menu.Names[product]} must be a number from 1 to {MaxQuantity}", message);
                return null;
            }
        }
        return items;
    }

    private void Error(string text, string received)
    {
        Log.Write(Name, $"error: {text} <- \"{Printable(received)}\"");
        Send("ERROR " + text);
    }

    // What a client sent can be anything, also bytes that are not text: before it goes to the log
    // or back to the client, the characters that cannot be printed are replaced and long text is cut.
    private static string Printable(string text)
    {
        StringBuilder result = new StringBuilder();
        foreach (char c in text)
        {
            if (result.Length == 40)
            {
                result.Append("...");
                break;
            }
            result.Append(c < ' ' || c > '~' ? '?' : c);
        }
        return result.ToString();
    }
}
