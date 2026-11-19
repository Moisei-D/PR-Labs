using System.Collections.Concurrent;

namespace Lab2;

// Everything that the threads of the server share: the stock, the orders and who the provider is.
// The threads of the clients, the thread of the provider and the workers all come here,
// so every method takes the same lock (gate) before it reads or changes the shared data.
// Nothing is sent to a socket while the lock is held: a slow client must not stop the whole shop.
public class Shop
{
    public const int LowStock = 5;   // below this amount the provider is alerted

    private readonly object gate = new object();
    private readonly int[] stock = new int[Menu.Count];
    private int nextNumber = 1;
    private Connection? provider;

    // one alert at a time, so that two alerts cannot overtake each other on the way to the provider
    private readonly object alertGate = new object();

    // The orders that wait for a free worker, in the order in which they arrived.
    // The threads of the clients add (producers), the workers take (consumers); Take waits while the queue is empty.
    private readonly BlockingCollection<Order> queue = new BlockingCollection<Order>();

    private readonly string stockFile;

    public Shop(string stockFile, bool newStock)
    {
        this.stockFile = stockFile;

        if (!newStock && LoadStock())
        {
            Log.Write("server", $"stock read from {stockFile}: {Menu.Format(stock)}");
        }
        else
        {
            for (int i = 0; i < Menu.Count; i++)
                stock[i] = Random.Shared.Next(10, 51);   // from 10 to 50
            SaveStock();
            Log.Write("server", $"new random stock: {Menu.Format(stock)}");
        }
    }

    // a copy, so the caller can use it after the lock is released
    public int[] GetStock()
    {
        lock (gate)
        {
            return (int[])stock.Clone();
        }
    }

    // Checks the stock and takes the products in one step: no other thread can change the stock in between.
    // Returns null when the stock does not have enough; stockNow is the stock after the call in both cases.
    public Order? TakeOrder(Connection client, int[] items, out int[] stockNow)
    {
        lock (gate)
        {
            bool enough = true;
            for (int i = 0; i < Menu.Count; i++)
            {
                if (items[i] > stock[i])
                    enough = false;
            }

            if (!enough)
            {
                stockNow = (int[])stock.Clone();
                return null;
            }

            for (int i = 0; i < Menu.Count; i++)
                stock[i] -= items[i];
            SaveStock();

            Order order = new Order(nextNumber, client, items);
            nextNumber++;
            client.Orders.Add(order);

            stockNow = (int[])stock.Clone();
            return order;
        }
    }

    // The thread of a client puts its order in the queue.
    public void Enqueue(Order order)
    {
        queue.Add(order);
    }

    // A worker waits here for the oldest waiting order.
    public Order TakeNext()
    {
        return queue.Take();
    }

    // A worker starts an order. False: its client disappeared while the order waited in the queue.
    public bool StartPreparing(Order order)
    {
        lock (gate)
        {
            if (order.State == OrderState.Cancelled)
                return false;

            order.State = OrderState.Preparing;
            return true;
        }
    }

    // A worker has finished waiting. False: the client disappeared meanwhile and the products are already back.
    public bool Finish(Order order)
    {
        lock (gate)
        {
            if (order.State == OrderState.Cancelled)
                return false;

            order.State = OrderState.Ready;
            order.Client.Orders.Remove(order);
            return true;
        }
    }

    // A connection has ended: all its unfinished orders are cancelled and their products go back to the stock.
    // Returns one line for the log for every cancelled order.
    public List<string> Leave(Connection client)
    {
        List<string> cancelled = new List<string>();

        lock (gate)
        {
            foreach (Order order in client.Orders)
            {
                string where = order.State == OrderState.Preparing ? "was being prepared" : "waited in the queue";
                order.State = OrderState.Cancelled;

                for (int i = 0; i < Menu.Count; i++)
                    stock[i] += order.Items[i];

                cancelled.Add($"order {order.Number} cancelled ({where}): {Menu.FormatItems(order.Items)} back in the stock");
            }

            if (client.Orders.Count > 0)
            {
                client.Orders.Clear();
                SaveStock();
            }

            if (provider == client)
                provider = null;
        }
        return cancelled;
    }

    // Returns null when the connection is the provider now, or the text of the error.
    public string? SetProvider(Connection client)
    {
        lock (gate)
        {
            if (provider == client)
                return "you are already the provider";
            if (provider != null)
                return "a provider is already connected";
            if (client.Orders.Count > 0)
                return "a client with unfinished orders cannot become the provider";

            provider = client;
            return null;
        }
    }

    // The delivery is added to the stock at once. Returns the new stock.
    public int[] Deliver(int[] items)
    {
        lock (gate)
        {
            for (int i = 0; i < Menu.Count; i++)
                stock[i] += items[i];
            SaveStock();

            return (int[])stock.Clone();
        }
    }

    // Alerts the provider about each of the given products that is below LowStock at this moment.
    // Called by the thread of a client right after its order took products,
    // and by the thread of the provider when it connects (for all products).
    // When no provider is connected nothing is sent: the provider gets the alert when it connects.
    public void AlertProvider(int[] products)
    {
        lock (alertGate)
        {
            Connection? to;
            int[] now;
            lock (gate)
            {
                to = provider;
                now = (int[])stock.Clone();
            }

            if (to == null)
                return;

            for (int i = 0; i < Menu.Count; i++)
            {
                if (products[i] > 0 && now[i] < LowStock)
                {
                    Log.Write(to.Name, $"alert sent to the provider: {Menu.Names[i]}={now[i]}");
                    to.Send($"ALERT {Menu.Names[i]}={now[i]}");
                }
            }
        }
    }

    // ---- the stock is kept in a file, so that it survives a restart of the server (bonus) ----

    // called inside the lock, after every change of the stock
    private void SaveStock()
    {
        try
        {
            string[] lines = new string[Menu.Count];
            for (int i = 0; i < Menu.Count; i++)
                lines[i] = $"{Menu.Names[i]}={stock[i]}";

            string? folder = Path.GetDirectoryName(stockFile);
            if (!string.IsNullOrEmpty(folder))
                Directory.CreateDirectory(folder);

            // first a temporary file, then rename: the file is never half written
            File.WriteAllLines(stockFile + ".tmp", lines);
            File.Move(stockFile + ".tmp", stockFile, true);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            Log.Write("server", $"error: the stock was not saved: {e.Message}");
        }
    }

    // False when there is no file or it is not a stock file.
    private bool LoadStock()
    {
        try
        {
            if (!File.Exists(stockFile))
                return false;

            int[] loaded = new int[Menu.Count];
            bool[] found = new bool[Menu.Count];

            foreach (string line in File.ReadAllLines(stockFile))
            {
                string[] parts = line.Split('=');
                if (parts.Length != 2)
                    return false;

                int index = Menu.IndexOf(parts[0].Trim());
                if (index < 0 || !int.TryParse(parts[1], out int amount) || amount < 0)
                    return false;

                loaded[index] = amount;
                found[index] = true;
            }

            if (found.Contains(false))
                return false;

            loaded.CopyTo(stock, 0);
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            Log.Write("server", $"error: the stock file was not read: {e.Message}");
            return false;
        }
    }
}
