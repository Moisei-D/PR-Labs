using System.Net;
using System.Net.Sockets;

namespace Lab2;

// The server of the coffee shop.
// The main thread accepts connections, every connection has its own thread (Connection.Run),
// and a fixed number of worker threads prepare the orders.
public class Server
{
    private Shop shop = null!;

    public void Run(string[] args)
    {
        int port = Args.GetInt(args, "port", 5000, 1, 65535);
        // one worker for each logical processor; --workers is only for showing more clients than workers
        int workerCount = Args.GetInt(args, "workers", Environment.ProcessorCount, 1, 1024);
        string stockFile = Args.Get(args, "stock-file", "data/stock.txt");

        shop = new Shop(stockFile, Args.Has(args, "new-stock"));

        for (int i = 1; i <= workerCount; i++)
        {
            int number = i;
            Thread worker = new Thread(() => Work(number));
            worker.IsBackground = true;
            worker.Start();
        }

        // the listening socket: it only waits for new connections, no data of the clients passes through it
        Socket listener = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
        try
        {
            // lets the server start again on the same port right after it was stopped
            listener.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
            // Any: all addresses of this machine, so the server is also reachable from other computers
            listener.Bind(new IPEndPoint(IPAddress.Any, port));
            listener.Listen(100);
        }
        catch (SocketException e)
        {
            Console.WriteLine($"Cannot listen on port {port}: {e.Message}");
            return;
        }

        Log.Write("server", $"listening on port {port}, {workerCount} workers");

        while (true)
        {
            Socket client;
            try
            {
                client = listener.Accept();   // waits here; returns a new socket for every client
            }
            catch (SocketException e)
            {
                Log.Write("server", $"error: accept failed ({e.SocketErrorCode})");
                Thread.Sleep(100);
                continue;
            }

            try
            {
                Prepare(client);

                Connection connection = new Connection(client, shop);
                Thread thread = new Thread(connection.Run);
                thread.IsBackground = true;
                thread.Start();
            }
            catch (SocketException e)
            {
                // the client was gone again before its thread started
                Log.Write("server", $"error: a new connection was lost ({e.SocketErrorCode})");
                client.Close();
            }
        }
    }

    private static void Prepare(Socket client)
    {
        // A client that does not read must not block a worker for ever: Send gives up after 5 seconds.
        client.SendTimeout = 5000;

        // A client whose network is gone sends nothing, not even a close. With keep-alive the system
        // asks a silent client "are you there?" after 10 s, then every 5 s; after 3 questions without
        // an answer Receive fails, so the server notices in about 25 s.
        client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.KeepAlive, true);
        client.SetSocketOption(SocketOptionLevel.Tcp, SocketOptionName.TcpKeepAliveTime, 10);
        client.SetSocketOption(SocketOptionLevel.Tcp, SocketOptionName.TcpKeepAliveInterval, 5);
        client.SetSocketOption(SocketOptionLevel.Tcp, SocketOptionName.TcpKeepAliveRetryCount, 3);
    }

    // A worker: takes the oldest waiting order, prepares it, tells the client, takes the next one.
    private void Work(int number)
    {
        while (true)
        {
            Order order = shop.TakeNext();   // waits here while the queue is empty

            try
            {
                if (!shop.StartPreparing(order))
                    continue;   // cancelled while it waited in the queue

                Log.Write(order.Client.Name, $"order {order.Number}: worker {number} prepares it ({order.Seconds} s)");

                // The preparation is simulated by waiting.
                // The wait ends earlier when the client disappears.
                order.Client.Gone.Wait(TimeSpan.FromSeconds(order.Seconds));

                if (shop.Finish(order))
                {
                    Log.Write(order.Client.Name, $"order {order.Number} ready (worker {number})");
                    order.Client.Send($"READY order={order.Number}");
                }
                else
                {
                    Log.Write(order.Client.Name, $"order {order.Number}: worker {number} stopped, the client is gone");
                }
            }
            catch (Exception e)
            {
                // a mistake in our code must not end the worker
                Log.Write("server", $"error: worker {number}: {e.GetType().Name}: {e.Message}");
            }
        }
    }
}
