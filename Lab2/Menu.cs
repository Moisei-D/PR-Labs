namespace Lab2;

// The products of the shop and the time each one takes to prepare.
// Everywhere in the program a list of products is an int[]: one quantity per product, in the order of Names.
public static class Menu
{
    public static readonly string[] Names = { "coffee", "tea", "croissant" };
    public static readonly int[] Seconds = { 4, 3, 2 };

    public static int Count => Names.Length;

    // the position of a product in Names, or -1 when the shop does not sell it
    public static int IndexOf(string name)
    {
        return Array.IndexOf(Names, name.ToLowerInvariant());
    }

    // all products: "coffee=12 tea=30 croissant=7"
    public static string Format(int[] amounts)
    {
        string[] parts = new string[Count];
        for (int i = 0; i < Count; i++)
            parts[i] = $"{Names[i]}={amounts[i]}";
        return string.Join(" ", parts);
    }

    // only the products of an order or a delivery: "croissant=2 tea=1"
    public static string FormatItems(int[] items)
    {
        List<string> parts = new List<string>();
        for (int i = 0; i < Count; i++)
        {
            if (items[i] > 0)
                parts.Add($"{Names[i]}={items[i]}");
        }
        return string.Join(" ", parts);
    }

    // the preparation time of an order: the sum of the times of all its items
    public static int PreparationSeconds(int[] items)
    {
        int seconds = 0;
        for (int i = 0; i < Count; i++)
            seconds += items[i] * Seconds[i];
        return seconds;
    }
}
