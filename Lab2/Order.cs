namespace Lab2;

public enum OrderState
{
    Waiting,     // in the queue
    Preparing,   // a worker has it
    Ready,
    Cancelled    // its client disappeared; the products are back in the stock
}

public class Order
{
    public int Number;
    public Connection Client;
    public int[] Items;        // quantity of every product
    public int Seconds;        // preparation time
    public OrderState State;   // changed by the thread of the client and by a worker: only inside the lock of the shop

    public Order(int number, Connection client, int[] items)
    {
        Number = number;
        Client = client;
        Items = items;
        Seconds = Menu.PreparationSeconds(items);
        State = OrderState.Waiting;
    }
}
