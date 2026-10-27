namespace Lab1;

// How many negative, zero and positive numbers were found.
public struct Counts
{
    public long Negative;
    public long Zero;
    public long Positive;

    public const long Expected = 50_000_000;

    public readonly long Total => Negative + Zero + Positive;

    public void Add(int number)
    {
        if (number < 0) Negative++;
        else if (number == 0) Zero++;
        else Positive++;
    }

    public void Add(Counts other)
    {
        Negative += other.Negative;
        Zero += other.Zero;
        Positive += other.Positive;
    }

    // Parses the text in the buffer (one number per line) and counts the numbers.
    // Works on the raw bytes, so no string is created for a line.
    // Returns how many bytes were used: everything up to the last '\n'. The rest is the beginning of a line
    // that continues in the next buffer. With isLast = true the rest is a complete line and is counted too.
    public int AddText(ReadOnlySpan<byte> text, bool isLast)
    {
        int number = 0;
        bool minus = false;
        bool hasDigits = false;
        int used = 0;

        for (int i = 0; i < text.Length; i++)
        {
            byte b = text[i];

            if (b >= '0' && b <= '9')
            {
                number = number * 10 + (b - '0');
                hasDigits = true;
            }
            else if (b == '-')
            {
                minus = true;
            }
            else if (b == '\n')
            {
                if (hasDigits) Add(minus ? -number : number);
                number = 0;
                minus = false;
                hasDigits = false;
                used = i + 1;
            }
        }

        if (isLast)
        {
            if (hasDigits) Add(minus ? -number : number);
            used = text.Length;
        }
        return used;
    }
}
