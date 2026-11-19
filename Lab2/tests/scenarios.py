#!/usr/bin/env python3
"""Checks every task of the lab against the real server and saves what happened.

    dotnet build -c Release
    python3 tests/scenarios.py            # all scenarios (about 4 minutes)
    python3 tests/scenarios.py task2 race # only some of them

The clients here are Python sockets, so the script can do what a console client cannot:
send half a message, send random bytes, order from 20 connections at the same moment, never read.
A fresh server (bin/Release/net10.0/Lab2.dll) is started for every scenario, with a known stock.

Output, in data/:
    <scenario>_clients.txt   what every client sent (>) and received (<), with the time in seconds
    <scenario>_server.log    the log of the server
    checks.csv               every check and whether it passed
    idle_clients.csv, workers.csv   the two measurements
    environment.txt          the machine
The scenario 'network' needs root (it drops packets with iptables) and is skipped otherwise.
"""
import csv
import os
import platform
import queue
import random
import re
import resource
import select
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DLL = ROOT / "bin" / "Release" / "net10.0" / "Lab2.dll"
DATA = ROOT / "data"
HOST = "127.0.0.1"

checks = []          # (scenario, check, "PASS"/"FAIL"/"SKIP", detail)
facts = {}           # measured values that the report quotes (facts.csv)
next_port = [5100]


def fact(name, value):
    facts[name] = value


def check(scenario, text, ok, detail=""):
    result = "PASS" if ok else "FAIL"
    checks.append((scenario, text, result, detail))
    print(f"  [{result}] {text}" + (f"  ({detail})" if detail else ""))


class Scenario:
    """One server process and the transcript of the clients that talk to it."""

    def __init__(self, name, stock=None, workers=2):
        self.name = name
        self.workers = workers
        self.port = next_port[0]
        next_port[0] += 1
        self.stock_file = DATA / f"{name}_stock.txt"
        self.log_file = DATA / f"{name}_server.log"
        self.events = []
        self.lock = threading.Lock()
        self.server = None
        if stock is not None:
            self.stock_file.write_text("".join(f"{k}={v}\n" for k, v in stock.items()))
        elif self.stock_file.exists():
            self.stock_file.unlink()
        self.log_file.write_text("")
        print(f"\n== {name}")
        self.t0 = time.monotonic()

    def start(self, new_stock=False):
        command = ["dotnet", str(DLL), "server", "--port", str(self.port), "--workers", str(self.workers),
                   "--stock-file", str(self.stock_file)]
        if new_stock:
            command.append("--new-stock")
        seen = self.log().count("listening on port")
        self.server = subprocess.Popen(command, stdout=open(self.log_file, "a"), stderr=subprocess.STDOUT, cwd=ROOT)
        deadline = time.monotonic() + 15
        while self.log().count("listening on port") == seen:
            if time.monotonic() > deadline or self.server.poll() is not None:
                raise RuntimeError(f"the server did not start, see {self.log_file}")
            time.sleep(0.05)
        return self

    def stop(self, sig=None):
        if self.server and self.server.poll() is None:
            self.server.kill() if sig is None else self.server.send_signal(sig)
            self.server.wait()

    def alive(self):
        return self.server.poll() is None

    def now(self):
        return time.monotonic() - self.t0

    def record(self, label, direction, text):
        t = self.now()
        with self.lock:
            self.events.append((t, label, direction, text))
        return t

    def note(self, text):
        self.record("", "#", text)

    def log(self):
        return self.log_file.read_text(errors="replace")

    def wait_log(self, pattern, timeout=5.0):
        """Waits until a line of the server log matches; returns the seconds waited, or None."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if re.search(pattern, self.log()):
                return time.monotonic() - start
            time.sleep(0.005)
        return None

    def wait_count(self, text, count, timeout=5.0):
        """Waits until the server log contains the text at least count times."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.log().count(text) >= count:
                return True
            time.sleep(0.01)
        return False

    def save(self):
        self.stop()
        lines = []
        for t, label, direction, text in sorted(self.events, key=lambda e: e[0]):
            if direction == "#":
                lines.append(f"{t:7.3f}  -- {text}")
            else:
                lines.append(f"{t:7.3f}  {label:<3}{direction} {text}")
        (DATA / f"{self.name}_clients.txt").write_text("\n".join(lines) + "\n")
        for extra in (self.stock_file, Path(str(self.stock_file) + ".tmp")):
            if extra.exists():
                extra.unlink()


class Peer:
    """One connection to the server. A thread receives and cuts the lines, with the time of arrival."""

    def __init__(self, scenario, label, quiet=False):
        self.sc = scenario
        self.label = label
        self.quiet = quiet          # not written to the transcript (for the scenarios with hundreds of messages)
        self.sock = socket.create_connection((HOST, scenario.port))
        self.port = self.sock.getsockname()[1]
        self.endpoint = f"{HOST}:{self.port}"
        self.lines = queue.Queue()
        self.all = []
        self.stopping = False
        self.receiver = threading.Thread(target=self._receive, daemon=True)
        self.receiver.start()

    def _record(self, direction, text):
        return self.sc.now() if self.quiet else self.sc.record(self.label, direction, text)

    def _receive(self):
        data = b""
        try:
            while not self.stopping:
                # recv is called only when something has arrived: a close() from the main thread
                # would not really close the socket while this thread is blocked inside recv
                if not select.select([self.sock], [], [], 0.02)[0]:
                    continue
                received = self.sock.recv(4096)
                if not received:
                    self._record("!", "the server closed the connection")
                    break
                data += received
                while b"\n" in data:
                    line, data = data.split(b"\n", 1)
                    text = line.decode("utf-8", "replace")
                    t = self._record("<", text)
                    self.all.append((t, text))
                    self.lines.put((t, text))
        except OSError:
            pass

    def _stop_receiving(self):
        self.stopping = True
        self.receiver.join()

    def send(self, text):
        t = self._record(">", text)
        self.sock.sendall((text + "\n").encode())
        return t

    def raw(self, data, shown):
        """Sends bytes exactly as given; 'shown' is what the transcript says about them."""
        t = self._record(">", shown)
        self.sock.sendall(data)
        return t

    def expect(self, prefix, timeout=5.0):
        """The next received line that starts with prefix: (time, text), or (None, None) after the timeout."""
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None, None
            try:
                t, text = self.lines.get(timeout=left)
            except queue.Empty:
                return None, None
            if text.startswith(prefix):
                return t, text

    def ask(self, text, prefix="", timeout=5.0):
        """Sends a message and returns (answer, milliseconds until it arrived)."""
        sent = self.send(text)
        t, answer = self.expect(prefix, timeout)
        return answer, (None if t is None else (t - sent) * 1000)

    def silent(self, seconds):
        """True when nothing arrives for this long."""
        try:
            self.lines.get(timeout=seconds)
            return False
        except queue.Empty:
            return True

    def close(self):
        self._stop_receiving()
        self._record("!", "closes the connection")
        self.sock.close()

    def reset(self):
        """Closes with RST instead of FIN, as when the process is killed with unread data."""
        self._stop_receiving()
        self._record("!", "resets the connection (RST)")
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        self.sock.close()


def menu_of(text):
    """'MENU coffee=1 tea=2 croissant=3' -> {'coffee': 1, ...}; also for DELIVERED and REFUSED lines."""
    return {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", text or "")}


def stock_via(peer):
    answer, _ = peer.ask("MENU", "MENU")
    return menu_of(answer)


STOCK = {"coffee": 12, "tea": 30, "croissant": 7}


# ---------------------------------------------------------------------------------------------------------------
def task1():
    sc = Scenario("task1", STOCK).start()
    a = Peer(sc, "A")

    answer, _ = a.ask("MENU", "MENU")
    check("task1", "the menu shows the products and the stock", menu_of(answer) == STOCK, answer)

    answer, ms = a.ask("ORDER croissant 2 tea 1 coffee 1")
    accepted_at = a.all[-1][0]
    check("task1", "the order is accepted with its number and 2*2+3+4 = 11 seconds",
          answer == "ACCEPTED order=1 seconds=11", f"{answer}, answered in {ms:.1f} ms")
    fact("one_answer_ms", f"{ms:.1f}")

    answer, _ = a.ask("MENU", "MENU")
    check("task1", "the products are taken from the stock at once, before the order is ready",
          menu_of(answer) == {"coffee": 11, "tea": 29, "croissant": 5}, answer)

    answer, _ = a.ask("ORDER croissant 6")
    check("task1", "more than the stock has: refused, with how many are left",
          answer is not None and answer.startswith("REFUSED") and menu_of(answer)["croissant"] == 5, answer)
    check("task1", "a refused order takes nothing", stock_via(a)["croissant"] == 5)

    for message, why in (("ORDER beer 1", "unknown product"), ("ORDER tea 0", "quantity 0"),
                         ("ORDER tea -1", "negative quantity"), ("ORDER tea two", "quantity that is not a number"),
                         ("ORDER tea 1.5", "quantity that is not whole")):
        answer, _ = a.ask(message)
        check("task1", f"{why} gets an error message", answer is not None and answer.startswith("ERROR"), answer)

    t, answer = a.expect("READY", 15)
    waited = None if t is None else t - accepted_at
    check("task1", "READY arrives by itself after the preparation time",
          answer == "READY order=1" and 10.9 < waited < 11.6, f"{waited:.2f} s after ACCEPTED" if waited else "no READY")
    fact("one_ready_seconds", f"{waited:.2f}" if waited else "-")
    a.close()
    sc.save()


def framing():
    sc = Scenario("framing", STOCK).start()
    a = Peer(sc, "A")

    sc.note("one message in two pieces, half a second apart")
    a.raw(b"ME", "'ME'")
    quiet = a.silent(0.5)
    a.raw(b"NU\n", "'NU\\n'")
    t, answer = a.expect("", 2)
    check("framing", "half a message gets no answer; the answer comes when the rest arrives",
          quiet and answer is not None and answer.startswith("MENU"), answer)

    sc.note("three messages in one send")
    a.raw(b"MENU\nORDER tea 1\nMENU\n", "'MENU\\nORDER tea 1\\nMENU\\n'")
    answers = [a.expect("", 2)[1] for _ in range(3)]
    check("framing", "three messages in one send get three answers, in order",
          answers[0].startswith("MENU") and answers[1].startswith("ACCEPTED") and answers[2].startswith("MENU")
          and menu_of(answers[2])["tea"] == menu_of(answers[0])["tea"] - 1, " | ".join(answers))

    sc.note("one message sent byte by byte")
    a._record(">", "'M' 'E' 'N' 'U' '\\n' (five sends, 0.05 s apart)")
    for b in b"MENU\n":
        a.sock.sendall(bytes([b]))
        time.sleep(0.05)
    t, answer = a.expect("", 2)
    check("framing", "a message sent byte by byte gets one answer",
          answer is not None and answer.startswith("MENU") and a.silent(0.3), answer)

    sc.note("a line that ends with \\r\\n, as telnet sends it")
    a.raw(b"menu\r\n", "'menu\\r\\n'")
    t, answer = a.expect("", 2)
    check("framing", "\\r\\n and lower case are accepted", answer is not None and answer.startswith("MENU"), answer)
    a.close()
    sc.save()


# ---------------------------------------------------------------------------------------------------------------
def task2():
    sc = Scenario("task2", STOCK, workers=2).start()
    peers = {label: Peer(sc, label) for label in "ABCDE"}
    orders = {"A": "coffee 1", "B": "tea 1", "C": "croissant 2", "D": "croissant 1", "E": "tea 1 croissant 1"}

    sc.note("five clients, two workers: the orders arrive 0.1 s apart")
    accepted = 0
    for label, items in orders.items():
        answer, _ = peers[label].ask("ORDER " + items)
        accepted += answer is not None and answer.startswith("ACCEPTED")
        time.sleep(0.1)
    check("task2", "all five orders are accepted at once, though only two workers exist", accepted == 5)

    time.sleep(0.5)
    sc.note("both workers are busy: C asks for the menu, D orders again")
    answer, ms = peers["C"].ask("MENU", "MENU")
    check("task2", "a client that waits for its order can ask for the menu and is answered at once",
          answer is not None and ms < 100, f"{ms:.1f} ms")
    fact("two_menu_ms", f"{ms:.1f}")
    answer, ms = peers["D"].ask("ORDER tea 1", "ACCEPTED")
    check("task2", "a client that waits for its order can order again", answer == "ACCEPTED order=6 seconds=3", answer)

    ready = {}
    for label, count in (("A", 1), ("B", 1), ("C", 1), ("D", 2), ("E", 1)):
        for _ in range(count):
            t, answer = peers[label].expect("READY", 20)
            if answer:
                ready[int(answer.split("=")[1])] = t
    check("task2", "every client is told when its order is ready", sorted(ready) == [1, 2, 3, 4, 5, 6], str(sorted(ready)))

    for peer in peers.values():
        peer.close()
    sc.wait_count("  disconnected", 5)
    sc.save()

    # from the log of the server: who prepared what, and when
    starts, ends = {}, {}
    for line in sc.log().splitlines():
        m = re.match(r"(\d+):(\d+):([\d.]+)\s+\S+\s+order (\d+)(: worker \d+ prepares it| ready)", line)
        if m:
            t = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
            (starts if "prepares" in m[5] else ends)[int(m[4])] = t
    moments = sorted([(t, 1) for t in starts.values()] + [(t, -1) for t in ends.values()])
    busy = most = 0
    for _, change in moments:
        busy += change
        most = max(most, busy)
    check("task2", "never more than two orders are prepared at the same time", most == 2, f"at most {most}")
    fact("two_seconds", f"{max(ends.values()) - min(starts.values()):.1f}")
    check("task2", "the workers take the waiting orders in the order in which they arrived",
          [n for n, _ in sorted(starts.items(), key=lambda kv: kv[1])] == [1, 2, 3, 4, 5, 6],
          " ".join(str(n) for n, _ in sorted(starts.items(), key=lambda kv: kv[1])))


def race():
    rounds, clients, croissants = 10, 20, 7
    sc = Scenario("race", STOCK, workers=2).start()
    watcher = Peer(sc, "W")
    sc.note(f"{rounds} rounds: {clients} clients order 1 croissant at the same moment, the stock has {croissants}")

    all_ok, restored_ok, counts = True, True, []
    for r in range(rounds):
        peers = [Peer(sc, f"c{i}", quiet=True) for i in range(clients)]
        barrier = threading.Barrier(clients)
        answers = [None] * clients

        def order(i):
            barrier.wait()                       # all threads leave together
            peers[i].sock.sendall(b"ORDER croissant 1\n")
            answers[i] = peers[i].expect("", 5)[1]

        threads = [threading.Thread(target=order, args=(i,)) for i in range(clients)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        accepted = sum(1 for a in answers if a and a.startswith("ACCEPTED"))
        refused = sum(1 for a in answers if a and a.startswith("REFUSED"))
        left = stock_via(watcher)["croissant"]
        numbers = [a.split()[1] for a in answers if a and a.startswith("ACCEPTED")]
        counts.append((accepted, refused, left))
        sc.note(f"round {r + 1}: accepted {accepted}, refused {refused}, croissants left {left}")
        if accepted != croissants or refused != clients - croissants or left != 0 or len(set(numbers)) != accepted:
            all_ok = False

        for p in peers:
            p.close()
        # every client left before its order was ready, so all the croissants must come back
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and stock_via(watcher)["croissant"] != croissants:
            time.sleep(0.02)
        if stock_via(watcher)["croissant"] != croissants:
            restored_ok = False

    check("race", f"in each of {rounds} rounds exactly {croissants} of {clients} simultaneous orders get a croissant",
          all_ok, "accepted/refused/left: " + " ".join(f"{a}/{b}/{c}" for a, b, c in counts))
    check("race", "after the clients leave, all the croissants are back in the stock", restored_ok)
    watcher.close()
    sc.save()
    fact("race_rounds", rounds)
    fact("race_clients", clients)
    fact("race_croissants", croissants)
    fact("race_orders", rounds * clients)
    fact("race_accepted", sum(a for a, _, _ in counts))
    fact("race_refused", sum(b for _, b, _ in counts))


# ---------------------------------------------------------------------------------------------------------------
def task3():
    sc = Scenario("task3", {"coffee": 6, "tea": 30, "croissant": 7}, workers=2).start()
    a = Peer(sc, "A")

    answer, _ = a.ask("DELIVER coffee 5")
    check("task3", "a client that tries to deliver gets an error", answer == "ERROR only the provider can deliver", answer)

    sc.note("no provider is connected; an order leaves 4 coffees")
    answer, _ = a.ask("ORDER coffee 2")
    check("task3", "the shop works without a provider", answer is not None and answer.startswith("ACCEPTED"), answer)

    sc.note("the provider connects")
    p = Peer(sc, "P")
    answer, _ = p.ask("PROVIDER")
    t, alert = p.expect("ALERT", 2)
    check("task3", "the provider gets the waiting alert when it connects, without asking",
          answer == "PROVIDER ok" and alert == "ALERT coffee=4", f"{answer} | {alert}")

    sc.note("an order of a client makes the coffee fall again")
    sent = a.send("ORDER coffee 1")
    t, alert = p.expect("ALERT", 2)
    check("task3", "the provider is alerted at once when a product falls below 5",
          alert == "ALERT coffee=3", f"{alert}, {(t - sent) * 1000:.1f} ms after the order was sent" if t else "no alert")
    fact("three_alert_ms", f"{(t - sent) * 1000:.1f}" if t else "-")
    a.expect("ACCEPTED", 2)

    a.ask("ORDER tea 1")
    check("task3", "no alert for a product that has 5 or more", p.silent(0.5))

    answer, _ = p.ask("DELIVER coffee 20 croissant 10")
    check("task3", "a delivery is added to the stock at once",
          answer == "DELIVERED coffee=23 tea=29 croissant=17", answer)
    check("task3", "the clients see the delivered products", stock_via(a) == {"coffee": 23, "tea": 29, "croissant": 17})

    for message, expected, why in (("ORDER tea 1", "ERROR the provider cannot order", "the provider cannot order"),
                                   ("DELIVER coffee", "ERROR usage", "a delivery without a quantity gets an error"),
                                   ("DELIVER coffee -5", "ERROR the quantity", "a negative delivery gets an error")):
        answer, _ = p.ask(message)
        check("task3", why, answer is not None and answer.startswith(expected), answer)

    p2 = Peer(sc, "P2")
    answer, _ = p2.ask("PROVIDER")
    check("task3", "a second provider is refused while the first is connected",
          answer == "ERROR a provider is already connected", answer)
    p2.close()

    sc.note("the provider disappears; the shop goes on")
    p.close()
    sc.wait_log(re.escape(p.endpoint) + r"\s+disconnected")
    answer, _ = a.ask("ORDER croissant 14")
    check("task3", "orders are accepted after the provider has disappeared", answer is not None and answer.startswith("ACCEPTED"), answer)

    sc.note("a new provider connects")
    p3 = Peer(sc, "P3")
    answer, _ = p3.ask("PROVIDER")
    t, alert = p3.expect("ALERT", 2)
    check("task3", "a new provider can connect and gets the alert that nobody received",
          answer == "PROVIDER ok" and alert == "ALERT croissant=3", f"{answer} | {alert}")
    a.close()
    p3.close()
    sc.save()


def conservation():
    """A delivery and orders change the stock at the same moment: no change may be lost."""
    deliveries, clients, each = 300, 4, 100
    sc = Scenario("conservation", {"coffee": 20, "tea": 100, "croissant": 100}, workers=2).start()
    watcher = Peer(sc, "W")
    p = Peer(sc, "P", quiet=True)
    p.ask("PROVIDER")
    peers = [Peer(sc, f"c{i}", quiet=True) for i in range(clients)]
    sc.note(f"the provider sends {deliveries} deliveries of 1 coffee while {clients} clients send {each} orders of 1 coffee each")

    barrier = threading.Barrier(clients + 1)

    def deliver():
        barrier.wait()
        for _ in range(deliveries):
            p.sock.sendall(b"DELIVER coffee 1\n")

    def order(peer):
        barrier.wait()
        for _ in range(each):
            peer.sock.sendall(b"ORDER coffee 1\n")

    threads = [threading.Thread(target=deliver)] + [threading.Thread(target=order, args=(peer,)) for peer in peers]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # wait until every message has been answered
    delivered = sum(1 for _ in range(deliveries) if p.expect("DELIVERED", 5)[1])
    accepted = refused = 0
    for peer in peers:
        got = 0
        while got < each:
            t, answer = peer.expect("", 5)
            if answer is None:
                break
            if answer.startswith("ACCEPTED"):
                accepted, got = accepted + 1, got + 1
            elif answer.startswith("REFUSED"):
                refused, got = refused + 1, got + 1

    coffee = stock_via(watcher)["coffee"]
    expected = 20 + delivered - accepted
    sc.note(f"delivered {delivered}, accepted {accepted}, refused {refused}: coffee must be 20 + {delivered} - {accepted} = {expected}; the menu says {coffee}")
    check("conservation", "deliveries and orders at the same moment: the stock is exactly start + delivered - ordered",
          delivered == deliveries and accepted + refused == clients * each and coffee == expected,
          f"20 + {delivered} - {accepted} = {expected}, menu: {coffee}")

    for peer in peers:
        peer.close()
    sc.wait_count("  disconnected", clients, 10)
    time.sleep(0.3)
    ready = len(re.findall(r"order \d+ ready", sc.log()))
    coffee = stock_via(watcher)["coffee"]
    sc.note(f"the clients leave; {ready} orders were ready before, the others are cancelled: coffee must be 20 + {delivered} - {ready} = {20 + delivered - ready}; the menu says {coffee}")
    check("conservation", "after the clients leave, every order that was not ready is back in the stock",
          coffee == 20 + delivered - ready, f"20 + {delivered} - {ready} = {20 + delivered - ready}, menu: {coffee}")
    watcher.close()
    p.close()
    sc.save()
    fact("cons_deliveries", deliveries)
    fact("cons_clients", clients)
    fact("cons_orders", clients * each)
    fact("cons_accepted", accepted)
    fact("cons_refused", refused)
    fact("cons_ready", ready)
    fact("cons_stock", 20 + delivered - accepted)
    fact("cons_stock_after", coffee)


# ---------------------------------------------------------------------------------------------------------------
def task4():
    sc = Scenario("task4", STOCK, workers=2).start()
    x, y = Peer(sc, "X"), Peer(sc, "Y")

    sc.note("X has one order at a worker and one in the queue; Y the same")
    x.ask("ORDER coffee 2")       # order 1, worker
    time.sleep(0.05)
    y.ask("ORDER tea 2")          # order 2, the other worker
    time.sleep(0.05)
    x.ask("ORDER croissant 3")    # order 3, queue
    time.sleep(0.05)
    y.ask("ORDER croissant 1")    # order 4, queue
    check("task4", "before: the products of all four orders are out of the stock",
          stock_via(y) == {"coffee": 10, "tea": 28, "croissant": 3})

    time.sleep(1.0)
    sc.note("X closes its connection")
    closed_at = time.monotonic()
    x.close()
    waited = sc.wait_log(re.escape(x.endpoint) + r"\s+disconnected")
    check("task4", "a closed connection is noticed at once", waited is not None and waited < 0.5,
          f"{waited * 1000:.0f} ms" if waited is not None else "not noticed")
    fact("four_close_ms", f"{waited * 1000:.0f}" if waited is not None else "-")
    log = sc.log()
    check("task4", "the order at the worker and the order in the queue are both cancelled",
          "order 1 cancelled (was being prepared)" in log and "order 3 cancelled (waited in the queue)" in log)
    check("task4", "the worker stops preparing the cancelled order", sc.wait_log(r"order 1: worker \d stopped", 1) is not None)
    check("task4", "the products go back to the stock", stock_via(y) == {"coffee": 12, "tea": 28, "croissant": 6})

    t, answer = y.expect("READY", 5)
    freed = time.monotonic() - closed_at
    check("task4", "the freed worker takes the next waiting order at once (order 4, 2 s)",
          answer == "READY order=4" and 1.9 < freed < 2.6, f"{answer} {freed:.2f} s after X left")
    fact("four_freed_seconds", f"{freed:.2f}")
    t, answer = y.expect("READY", 8)
    check("task4", "the orders of the other client are not touched", answer == "READY order=2", answer)

    sc.note("Z resets its connection (RST) while its order is prepared")
    z = Peer(sc, "Z")
    z.ask("ORDER coffee 3")
    time.sleep(0.5)
    z.reset()
    waited = sc.wait_log(re.escape(z.endpoint) + r"\s+disconnected: connection lost \(ConnectionReset\)")
    check("task4", "a reset connection is noticed at once (Receive fails)", waited is not None and waited < 0.5,
          f"{waited * 1000:.0f} ms" if waited is not None else "not noticed")
    fact("four_reset_ms", f"{waited * 1000:.0f}" if waited is not None else "-")
    check("task4", "its products are back", stock_via(y) == {"coffee": 12, "tea": 28, "croissant": 6})

    sc.note("the process of a console client (Client.cs) is killed while its order is prepared")
    victim = subprocess.Popen(["dotnet", str(DLL), "client", "--port", str(sc.port)], stdin=subprocess.PIPE,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    victim.stdin.write(b"order tea 5\n")
    victim.stdin.flush()
    sc.wait_log(r"order 6 accepted", 10)
    time.sleep(0.5)
    before = len(re.findall(r"disconnected", sc.log()))
    victim.kill()
    killed_at = time.monotonic()
    while len(re.findall(r"disconnected", sc.log())) == before and time.monotonic() - killed_at < 5:
        time.sleep(0.005)
    waited = time.monotonic() - killed_at
    victim.wait()
    sc.note(f"kill -9 of the client process; the server logged the end of the connection {waited * 1000:.0f} ms later")
    check("task4", "a killed client process is noticed at once (the system closes its socket)",
          waited < 0.5 and "order 6 cancelled (was being prepared)" in sc.log(), f"{waited * 1000:.0f} ms")
    fact("four_kill_ms", f"{waited * 1000:.0f}")
    check("task4", "its products are back too", stock_via(y) == {"coffee": 12, "tea": 28, "croissant": 6})
    y.close()
    sc.save()


def network():
    """The network of a client is gone: its packets are dropped in both directions (needs root)."""
    if os.geteuid() != 0 or subprocess.run(["iptables", "-L", "-n"], capture_output=True).returncode != 0:
        print("\n== network: skipped (needs root and iptables)")
        checks.append(("network", "a client whose network is gone is noticed by keep-alive", "SKIP", "needs root and iptables"))
        return None

    sc = Scenario("network", STOCK, workers=2).start()
    x, y = Peer(sc, "X"), Peer(sc, "Y")
    x.ask("ORDER coffee 10")     # 40 s: longer than the keep-alive needs
    time.sleep(1.0)

    rules = [["INPUT", "-p", "tcp", "--sport", str(x.port), "--dport", str(sc.port), "-j", "DROP"],
             ["INPUT", "-p", "tcp", "--sport", str(sc.port), "--dport", str(x.port), "-j", "DROP"]]
    sc.note("the network of X is cut: all its packets are dropped, in both directions; nothing is closed")
    for rule in rules:
        subprocess.run(["iptables", "-I"] + rule, check=True)
    cut_at = time.monotonic()
    try:
        time.sleep(3)
        check("network", "3 s after the cut the server has noticed nothing: the products of X are still out",
              stock_via(y)["coffee"] == 2 and re.search(re.escape(x.endpoint) + r"\s+disconnected", sc.log()) is None)
        waited = sc.wait_log(re.escape(x.endpoint) + r"\s+disconnected: connection lost \(TimedOut\)", 60)
        if waited is not None:
            waited = time.monotonic() - cut_at
        sc.note(f"the server noticed {waited:.1f} s after the cut" if waited else "the server did not notice in 60 s")
        check("network", "keep-alive notices the silent client in about 25 s (10 s + 3 probes of 5 s)",
              waited is not None and 20 < waited < 32, f"{waited:.1f} s" if waited else "not noticed")
        check("network", "then its order is cancelled and the products are back",
              "order 1 cancelled (was being prepared)" in sc.log() and stock_via(y)["coffee"] == 12)
    finally:
        for rule in rules:
            subprocess.run(["iptables", "-D"] + rule)
    y.close()
    sc.save()
    fact("net_seconds", f"{waited:.1f}" if waited else "-")


def invalid():
    sc = Scenario("invalid", STOCK, workers=2).start()
    z, w = Peer(sc, "Z"), Peer(sc, "W", quiet=True)

    sc.note("unknown commands, missing and wrong parameters")
    for message in ("HELLO", "", "ORDER", "ORDER coffee", "ORDER coffee x", "ORDER coffee 1 tea", "ORDER coffee 99999999999",
                    "ORDER coffee 600 coffee 600", "MENU please", "PROVIDER now", "DELIVER coffee 1"):
        answer, _ = z.ask(message)
        check("invalid", f"'{message}' gets an error message", answer is not None and answer.startswith("ERROR"), answer)

    sc.note("a message that is too long: 3000 bytes without a line end, then the line end and MENU")
    z.raw(b"A" * 3000, "3000 x 'A'")
    t, answer = z.expect("", 2)
    check("invalid", "a message that is too long gets one error message, already before its end arrives",
          answer is not None and answer.startswith("ERROR message too long"), answer)
    z.raw(b"\nMENU\n", "'\\nMENU\\n'")
    t, answer = z.expect("", 2)
    check("invalid", "after the long message the connection works again", answer is not None and answer.startswith("MENU"), answer)

    sc.note("random bytes")
    rng = random.Random(2026)
    z.raw(bytes(rng.randrange(256) for _ in range(2000)) + b"\n", "2000 random bytes and '\\n'")
    time.sleep(0.5)
    errors = 0
    while not z.lines.empty():
        errors += z.lines.get()[1].startswith("ERROR")
    answer, _ = z.ask("MENU", "MENU")
    check("invalid", "random bytes get error messages and the connection still works",
          errors > 0 and answer is not None, f"{errors} error messages, then {answer}")

    sc.note("Z floods the server with 256 KB of random bytes while W asks for the menu 50 times")
    z.quiet = True   # the hundreds of error messages that Z gets now are not written to the transcript
    flood_done = threading.Event()

    def flood():
        data = bytes(rng.randrange(256) for _ in range(64 * 1024))
        try:
            for _ in range(4):
                z.sock.sendall(data)
        except OSError:
            pass
        flood_done.set()

    threading.Thread(target=flood, daemon=True).start()
    times = []
    for _ in range(50):
        answer, ms = w.ask("MENU", "MENU")
        times.append(ms if answer else 9999)
        time.sleep(0.01)
    flood_done.wait(10)
    time.sleep(0.5)
    flood_errors = sum(1 for _, text in z.all if text.startswith("ERROR")) - 13 - errors
    worst = max(times)
    fact("bad_random_errors", errors)
    fact("bad_flood_errors", flood_errors)
    fact("bad_flood_worst_ms", f"{worst:.1f}")
    check("invalid", "the flood of one client does not block another client", worst < 200,
          f"50 menus, the slowest answer {worst:.1f} ms")
    sc.note(f"Z got {flood_errors} more error messages; W: 50 x MENU answered, the slowest in {worst:.1f} ms")
    z.sock.sendall(b"\n")   # ends the last, unfinished line of the flood
    time.sleep(0.3)
    while not z.lines.empty():
        z.lines.get()
    z.quiet = False
    answer, _ = z.ask("MENU", "MENU")
    check("invalid", "after the flood the connection of Z itself still works", answer is not None, answer)
    z.close()
    w.close()
    check("invalid", "the server is still running after all of this", sc.alive())
    sc.save()


def never_reads():
    """A client that sends requests and never reads the answers must not hold a thread of the server for ever."""
    sc = Scenario("never_reads", STOCK, workers=2).start()
    w = Peer(sc, "W")

    sc.note("N sends MENU again and again and never calls recv")
    n = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    n.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)     # a small buffer fills quickly
    n.connect((HOST, sc.port))
    endpoint = f"{HOST}:{n.getsockname()[1]}"
    n.settimeout(0.5)
    started = time.monotonic()
    sent = 0
    waited = None
    while time.monotonic() - started < 20:
        try:
            n.sendall(b"MENU\n" * 1000)
            sent += 1000
        except OSError:
            pass                                                # our own send is stuck too: the server stopped reading
        if re.search(re.escape(endpoint) + r"\s+error: send failed", sc.log()):
            waited = time.monotonic() - started
            break
    sc.note(f"N sent about {sent} x MENU; the server gave up and closed the connection after {waited:.1f} s" if waited
            else "the server did not close the connection in 20 s")
    check("never_reads", "a client that never reads is disconnected (Send gives up after 5 s)",
          waited is not None and "TimedOut" in sc.log(), f"{waited:.1f} s" if waited else "")
    fact("mute_seconds", f"{waited:.1f}" if waited else "-")
    fact("mute_sent", sent)
    answer, ms = w.ask("MENU", "MENU")
    check("never_reads", "another client is served normally", answer is not None and ms < 200, f"{ms:.1f} ms" if ms else "")
    n.close()
    w.close()
    sc.save()


def programs():
    """The two console clients: Client.cs and python/client.py."""
    for name, command in (("client_cs", ["dotnet", str(DLL), "client"]),
                          ("client_py", [sys.executable, str(ROOT / "python" / "client.py"), "client"])):
        sc = Scenario(name, STOCK, workers=2).start()
        out_file = DATA / f"{name}_output.txt"
        with open(out_file, "w") as out:
            client = subprocess.Popen(command + ["--port", str(sc.port)], stdin=subprocess.PIPE, stdout=out, stderr=subprocess.STDOUT)
            time.sleep(1.0)
            client.stdin.write(b"menu\norder tea 1\n")
            client.stdin.flush()
            # the keyboard stays open and nothing is typed: READY must appear anyway after 3 s
            time.sleep(4.0)
            text = out_file.read_text()
            check(name, "READY is shown while the program waits for the keyboard", "READY order=1" in text)
            sc.stop()   # the server disappears (kill -9)
            try:
                code = client.wait(timeout=3)
            except subprocess.TimeoutExpired:
                code = None
                client.kill()
        text = out_file.read_text()
        check(name, "the program ends by itself, with exit code 0, when the server disappears",
              code == 0, f"exit code {code}; last line: {text.strip().splitlines()[-1]}")
        sc.save()


def restart():
    sc = Scenario("restart", None, workers=2).start(new_stock=True)
    first = re.search(r"new random stock: (.*)", sc.log())
    stock = menu_of(first[1]) if first else {}
    check("restart", "a new stock has a random amount from 10 to 50 of each product",
          len(stock) == 3 and all(10 <= v <= 50 for v in stock.values()), first[1] if first else "")

    a = Peer(sc, "A")
    a.ask("ORDER croissant 1")
    p = Peer(sc, "P")
    p.ask("PROVIDER")
    p.ask("DELIVER tea 5")
    a.expect("READY", 5)
    before = stock_via(a)
    sc.note("the server is killed (kill -9) and started again")
    sc.stop()
    time.sleep(0.3)
    sc.start()
    b = Peer(sc, "B")
    after = stock_via(b)
    check("restart", "the stock is the same after the server was killed and started again",
          before == after and before == {**stock, "croissant": stock["croissant"] - 1, "tea": stock["tea"] + 5},
          f"before: {before}  after: {after}")
    fact("restart_first", first[1] if first else "-")
    fact("restart_after", " ".join(f"{k}={v}" for k, v in after.items()))
    b.close()
    sc.save()

    amounts = []
    for i in range(5):
        s = Scenario("random", None).start(new_stock=True)
        amounts += list(menu_of(re.search(r"new random stock: (.*)", s.log())[1]).values())
        s.stop()
        s.save()
        for f in (DATA / "random_clients.txt", DATA / "random_server.log"):
            f.unlink()
    check("restart", "five more starts with --new-stock: all 15 amounts are from 10 to 50",
          len(amounts) == 15 and all(10 <= v <= 50 for v in amounts), " ".join(map(str, amounts)))


# ---------------------------------------------------------------------------------------------------------------
def proc_status(pid):
    values = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        key, _, rest = line.partition(":")
        values[key] = rest.strip()
    return int(values["Threads"]), int(values["VmRSS"].split()[0]) / 1024


def cpu_ms(pid):
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) * 1000 / os.sysconf("SC_CLK_TCK")


def idle_clients():
    """What does a waiting client cost? Threads and memory of the server with 0 ... 1000 idle connections."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < 4096:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, 4096), hard))

    sc = Scenario("idle_clients", STOCK, workers=2).start()
    probe = socket.create_connection((HOST, sc.port))   # a plain socket: send, wait for the answer, measure
    rows, sockets = [], []
    for target in (0, 100, 250, 500, 1000):
        while len(sockets) < target:
            sockets.append(socket.create_connection((HOST, sc.port)))
        sc.wait_count("  connected", target + 1, 20)
        time.sleep(1.0)
        times = []
        for _ in range(101):
            started = time.perf_counter()
            probe.sendall(b"MENU\n")
            probe.recv(4096)
            times.append((time.perf_counter() - started) * 1000)
        median = sorted(times)[50]
        threads, rss = proc_status(sc.server.pid)
        rows.append((target, threads, f"{rss:.1f}", f"{median:.3f}"))
        print(f"  {target:5d} idle clients: {threads} threads, {rss:.1f} MB, menu answered in {median:.3f} ms (median of 101)")
    with open(DATA / "idle_clients.csv", "w", newline="") as f:
        csv.writer(f).writerows([("clients", "threads", "memory_mb", "menu_ms")] + rows)
    check("idle_clients", "with 1000 idle clients the server has about 1000 more threads and still answers",
          rows[-1][1] - rows[0][1] in range(990, 1011) and float(rows[-1][3]) < 100,
          f"{rows[0][1]} -> {rows[-1][1]} threads, {rows[0][2]} -> {rows[-1][2]} MB")
    for s in sockets:
        s.close()
    sc.save()
    for f in (DATA / "idle_clients_clients.txt", DATA / "idle_clients_server.log"):
        f.unlink()


def workers():
    """8 orders of 2 s arrive together. How long until all are ready, with 1 ... 16 workers?"""
    rows = []
    orders = 8
    for count in (1, 2, 4, 8, 16):
        sc = Scenario("workers", {"coffee": 50, "tea": 50, "croissant": 50}, workers=count).start()
        peers = [Peer(sc, f"c{i}", quiet=True) for i in range(orders)]
        time.sleep(0.5)
        cpu_before = cpu_ms(sc.server.pid)
        started = time.monotonic()
        for peer in peers:
            peer.sock.sendall(b"ORDER croissant 1\n")
        for peer in peers:
            peer.expect("READY", 30)
        seconds = time.monotonic() - started
        cpu = cpu_ms(sc.server.pid) - cpu_before
        rows.append((count, orders, f"{seconds:.2f}", f"{cpu:.0f}"))
        print(f"  {count:2d} workers: {orders} orders of 2 s ready after {seconds:.2f} s; the server used {cpu:.0f} ms of processor time")
        for peer in peers:
            peer.close()
        sc.save()
    for f in (DATA / "workers_clients.txt", DATA / "workers_server.log"):
        f.unlink()
    with open(DATA / "workers.csv", "w", newline="") as f:
        csv.writer(f).writerows([("workers", "orders", "seconds", "cpu_ms")] + rows)
    expected = {1: 16, 2: 8, 4: 4, 8: 2, 16: 2}
    check("workers", "8 orders of 2 s take 16, 8, 4, 2 and 2 s with 1, 2, 4, 8 and 16 workers",
          all(abs(float(s) - expected[c]) < 0.5 for c, _, s, _ in rows), " ".join(f"{c}:{s}s" for c, _, s, _ in rows))


def environment():
    def run(command):
        try:
            return subprocess.run(command, capture_output=True, text=True).stdout.strip()
        except OSError:
            return ""

    lscpu = dict(line.split(":", 1) for line in run(["lscpu"]).splitlines() if ":" in line)
    os_name = ""
    for line in Path("/etc/os-release").read_text().splitlines():
        if line.startswith("PRETTY_NAME="):
            os_name = line.split("=", 1)[1].strip('"')
    memory = int(re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text())[1]) / 1024 / 1024
    lines = {
        "processor": lscpu.get("Model name", "").strip(),
        "logical_processors": str(os.cpu_count()),
        "cores_per_socket": lscpu.get("Core(s) per socket", "").strip(),
        "threads_per_core": lscpu.get("Thread(s) per core", "").strip(),
        "memory_gib": f"{memory:.1f}",
        "os": os_name,
        "kernel": platform.release(),
        "dotnet": run(["dotnet", "--version"]),
        "python": platform.python_version(),
        "date": time.strftime("%Y-%m-%d"),
    }
    (DATA / "environment.txt").write_text("".join(f"{k}={v}\n" for k, v in lines.items()))


ALL = {"task1": task1, "framing": framing, "task2": task2, "race": race, "task3": task3, "conservation": conservation,
       "task4": task4, "network": network, "invalid": invalid, "never_reads": never_reads, "programs": programs,
       "restart": restart, "idle_clients": idle_clients, "workers": workers}


def main():
    if not DLL.exists():
        sys.exit("build first: dotnet build -c Release")
    DATA.mkdir(exist_ok=True)
    names = sys.argv[1:] or list(ALL)
    for name in names:
        if name not in ALL:
            sys.exit(f"unknown scenario '{name}'; scenarios: {' '.join(ALL)}")

    environment()
    for name in names:
        ALL[name]()

    # keep the checks and facts of the scenarios that were not run this time
    def merge(path, new_rows):
        old = []
        if path.exists():
            old = [row for row in csv.reader(open(path)) if row and row[0] not in {r[0] for r in new_rows}][1:]
        return old + new_rows

    rows = merge(DATA / "checks.csv", [list(c) for c in checks])
    with open(DATA / "checks.csv", "w", newline="") as f:
        csv.writer(f).writerows([["scenario", "check", "result", "detail"]] + rows)
    fact_rows = merge(DATA / "facts.csv", [[k, str(v)] for k, v in facts.items()])
    with open(DATA / "facts.csv", "w", newline="") as f:
        csv.writer(f).writerows([["name", "value"]] + fact_rows)

    failed = [c for c in checks if c[2] == "FAIL"]
    print(f"\n{len(checks)} checks, {len(failed)} failed" + "".join(f"\n  FAILED: {c[0]}: {c[1]}" for c in failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
