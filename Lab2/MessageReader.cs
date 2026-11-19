using System.Text;

namespace Lab2;

// Cuts the bytes received from a socket into messages. A message is one line of text that ends with '\n'.
// TCP is a stream of bytes: one Receive can bring half a message, or several messages at once.
// The bytes of an unfinished message are kept here until the rest arrives.
public class MessageReader
{
    public const int MaxLength = 1024;

    private readonly byte[] line = new byte[MaxLength];
    private int length;
    private bool skipping;   // the message was too long: the rest of it is thrown away, up to its '\n'

    // Called after every Receive with the bytes that arrived.
    // onMessage is called once for every complete message; onTooLong once for a message longer than MaxLength.
    public void Add(byte[] buffer, int count, Action<string> onMessage, Action onTooLong)
    {
        for (int i = 0; i < count; i++)
        {
            byte b = buffer[i];

            if (b == '\n')
            {
                if (!skipping)
                    onMessage(Encoding.UTF8.GetString(line, 0, length).TrimEnd('\r'));
                length = 0;
                skipping = false;
            }
            else if (skipping)
            {
                // still inside the message that was too long
            }
            else if (length == MaxLength)
            {
                skipping = true;
                onTooLong();
            }
            else
            {
                line[length] = b;
                length++;
            }
        }
    }
}
