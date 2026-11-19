# Lab 2 – A coffee shop server

C# (.NET 10), TCP sockets with the `Socket` class only (no `TcpListener`, `TcpClient` or `NetworkStream`).
One program: the first argument chooses the role, the other arguments are its options.
Run everything from this folder (`Lab2/`).

```bash
dotnet build -c Release
```

| File | What it does |
|------|--------------|
| `Program.cs` | starts the role chosen by the first argument: `server`, `client` or `provider` |
| `Server.cs` | the listening socket, the accept loop, the worker threads |
| `Connection.cs` | one accepted socket and its thread: receives, handles the messages, sends the answers |
| `Shop.cs` | everything the threads share (stock, orders, queue, provider) and the lock that protects it |
| `MessageReader.cs` | cuts the received bytes into messages (one line = one message); used by the server and the client |
| `Menu.cs`, `Order.cs` | the products with their times; one order and its state |
| `Client.cs` | the console program of a client and of the provider |
| `Log.cs`, `Args.cs` | the log lines of the server; reading `--options` |
| `python/client.py` | the same client and provider in Python (bonus: two languages) |
| `tests/scenarios.py` | checks every task against the real server and saves the transcripts for the report |

## Running

```bash
dotnet run -c Release -- server                              # port 5000, one worker per logical processor
dotnet run -c Release -- client                              # in another terminal
dotnet run -c Release -- provider                            # in a third terminal
```

| Option | Role | Meaning |
|--------|------|---------|
| `--port 5000` | all | the port of the server |
| `--host 127.0.0.1` | client, provider | the address (or name) of the server |
| `--workers N` | server | number of workers; default: the number of logical processors. Use `--workers 2` to show more clients than workers |
| `--new-stock` | server | forget the saved stock and put a new random amount (10–50) of each product |
| `--stock-file data/stock.txt` | server | where the stock is saved |

Between two computers in the same network: start the server on one, find its address with `ip addr`
(open the port in the firewall if there is one), and on the other run `dotnet run -c Release -- client --host 192.168.x.y`.

The Python client speaks the same protocol: `python3 python/client.py client --port 5000` (or `provider`).

## What to type in the client

```
menu                               the products and how many are in stock
order croissant 2 tea 1 coffee 1   order (the client)
deliver coffee 20 croissant 10     bring products (the provider)
help, quit
```

Everything else that is typed is sent to the server as it is, so wrong commands can be tried too.
The messages of the server are shown when they arrive, also in the middle of a line that is being typed
(the typed text is not lost: finish it and press Enter).
`quit` (or Ctrl+D) leaves the shop: the orders that are not ready are cancelled, like for a client that disappears.

## Protocol

Text over TCP. A message is one line that ends with `\n` (`\r\n` is accepted), at most 1024 bytes, UTF-8.
Commands are not case sensitive. Quantities are whole numbers from 1 to 1000.

| Client sends | Server answers |
|--------------|----------------|
| `MENU` | `MENU coffee=12 tea=30 croissant=7` |
| `ORDER croissant 2 tea 1` | `ACCEPTED order=7 seconds=7`, and later, by itself, `READY order=7` |
| | or `REFUSED not enough in stock: coffee=12 tea=30 croissant=1` |
| `PROVIDER` | `PROVIDER ok`, then an `ALERT` for every product that is below 5 |
| `DELIVER coffee 20 croissant 10` (provider only) | `DELIVERED coffee=32 tea=30 croissant=17` |
| anything wrong | `ERROR <what is wrong>` |

The server sends by itself: `READY order=N` to the client of the order, and `ALERT croissant=3` to the provider
when an order leaves a product below 5.

## Showing the tasks by hand

```bash
dotnet run -c Release -- server --workers 2
```

- **Task 1**: one client: `menu`, `order croissant 2 tea 1 coffee 1` (11 s), `menu` again at once, `order coffee 999`, `order beer 1`, `order tea 0`.
- **Task 2**: three or more clients, each `order coffee 2`: two are prepared, the others wait; `menu` is answered meanwhile.
- **Task 3**: a provider: `deliver coffee 20`; in a client `deliver coffee 1` (error); order until a product is below 5 and watch the provider.
- **Task 4**: order in a client and close its terminal (or `kill -9` it): the log shows the cancelled orders and `menu` shows the products back.
  Type nonsense; stop the server with Ctrl+C and watch the clients end.

The messages can also be sent by hand: `nc 127.0.0.1 5000` and type `MENU`.

## Automatic scenarios

```bash
python3 tests/scenarios.py            # all, about 4 minutes; prints PASS / FAIL for every check
python3 tests/scenarios.py task2 race # only some; the names are at the end of the script
sudo python3 tests/scenarios.py network   # the client whose network is gone: needs root (iptables)
```

A fresh server is started for every scenario with a known stock. The results are written to `data/`
(`<scenario>_clients.txt`, `<scenario>_server.log`, `checks.csv`, `idle_clients.csv`, `workers.csv`, `environment.txt`).
`data/` is not committed; the report keeps its own copy.

## Tables and charts for the report

```bash
cp data/*.txt data/*.log data/*.csv "../Reports/Lab2 Report/data/"
../Reports/.venv/bin/python "../Reports/Lab2 Report/plots/make_figures.py"
cd "../Reports/Lab2 Report" && tectonic Lab2_Moisei_Daniel_Report.tex
```
