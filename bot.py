#!/usr/bin/env python3
# ~~~~~==============   HOW TO RUN   ==============~~~~~
# 1) Configure things in CONFIGURATION section
# 2) Change permissions: chmod +x bot.py
# 3) Run in loop: while true; do ./bot.py --test prod-like; sleep 1; done

import argparse
from asyncore import read
from collections import deque
from collections import defaultdict
from enum import Enum
import time
import socket
import json

# ~~~~~============== CONFIGURATION  ==============~~~~~
# Replace "REPLACEME" with your team name!
team_name = "PACIFICSANDDAB"

# ~~~~~============== MAIN LOOP ==============~~~~~

# You should put your code here! We provide some starter code as an example,
# but feel free to change/remove/edit/update any of it as you'd like. If you
# have any questions about the starter code, or what to do next, please ask us!
#
# To help you get started, the sample code below tries to buy BOND for a low
# price, and it prints the current prices for VALE every second. The sample
# code is intended to be a working example, but it needs some improvement
# before it will start making good trades!

historical_trades = defaultdict(list)
positions = defaultdict(int)
book = defaultdict(int)
order_id = 1
HISTORICAL_TRADES_THRESHOLD_ETF = 3
HISTORICAL_TRADES_THRESHOLD_ADR = 10
ready_to_trade_etf = False
ready_to_trade_adr = False

def fair_value(symbol, lookback):
    sum_price = 0
    for i in range(1, lookback+1):
        sum_price += historical_trades[symbol][-i][0]
    return sum_price / lookback

def fair_adr_value(symbol):
    sum_adr_price = fair_value(symbol, HISTORICAL_TRADES_THRESHOLD_ADR)
    return int(sum_adr_price)

def fair_etf_value():
    weights = {"GS": 2, "MS": 3, "BOND": 3, "WFC": 2}
    sum_etf_price = 0
    for symbol in ["GS", "MS", "WFC", "BOND"]:
        sum_etf_price += weights[symbol]*fair_value(symbol, HISTORICAL_TRADES_THRESHOLD_ETF)
    return int(sum_etf_price)

def execute_bonds(exchange, best_bid, best_ask):
    global order_id
    print(f"executing bond for best bid {best_bid} and best ask {best_ask}")
    BOND_FAIR_VALUE = 1000
    BOND_BUY_SELL_SIZE = 5
    if best_bid and best_bid > BOND_FAIR_VALUE:
        print("submitted bond SELL")
        exchange.send_add_message(order_id, "BOND", Dir.SELL, 1001, BOND_BUY_SELL_SIZE)
        order_id += 1
    if best_ask and best_ask < BOND_FAIR_VALUE:
        print("submitted bond BUY")
        exchange.send_add_message(order_id, "BOND", Dir.BUY, 999, BOND_BUY_SELL_SIZE)
        order_id += 1

def execute_adr(exchange, best_bid, best_ask, symbol):
    # Executes for both VALE and VALBZ
    global order_id
    fair_value = fair_adr_value("VALBZ")
    VALBZ_BUY_SELL_SIZE = 1
    MARGIN = 7
    if best_ask and best_bid and best_bid > fair_value:
        # overvalued - we go long: buy underlying stock, convert, and sell the ADR
        print(f"submitted BUY for VABLZ at {fair_value}")
        exchange.send_add_message(order_id, "VALBZ", Dir.BUY, fair_value, VALBZ_BUY_SELL_SIZE)
        order_id += 1
        exchange.send_convert_message(order_id, "VALE", Dir.BUY, VALBZ_BUY_SELL_SIZE)
        order_id += 1
        exchange.send_add_message(order_id, "VALE", Dir.SELL, max(fair_value + MARGIN, best_bid), VALBZ_BUY_SELL_SIZE)
        order_id += 1
    if best_bid and best_ask and best_ask < fair_value:
        # undervalued - we go short: buy ADR, convert, and sell underlying stock
        print(f"submitted SELL for VALE at {best_ask}")
        exchange.send_add_message(order_id, "VALE", Dir.BUY, best_ask, VALBZ_BUY_SELL_SIZE)
        order_id += 1
        exchange.send_convert_message(order_id, "VALE", Dir.SELL, VALBZ_BUY_SELL_SIZE)
        order_id += 1
        exchange.send_add_message(order_id, "VALBZ", Dir.SELL, max(fair_value + MARGIN, best_bid), VALBZ_BUY_SELL_SIZE)
        order_id += 1

def execute_etf(exchange, best_bid, best_ask):
    # ONLY FOR XLF BOOK
    global order_id
    etf_fair_value = fair_etf_value()
    XLF_BUY_SELL_SIZE = 100
    MARGIN = 45

    gs_fair_value = fair_value("GS", HISTORICAL_TRADES_THRESHOLD_ETF)
    ms_fair_value = fair_value("MS", HISTORICAL_TRADES_THRESHOLD_ETF)
    wfc_fair_value = fair_value("WFC", HISTORICAL_TRADES_THRESHOLD_ETF)

    if fair_value("XLF", HISTORICAL_TRADES_THRESHOLD_ETF) - MARGIN > etf_fair_value // 10:
        # overvalued - we go long: buy underlying stock, convert, and sell the ETF
        print(f"submitted BUY for underlying XLF stocks at {fair_value}")
        exchange.send_add_message(order_id, "GS", Dir.BUY, int(gs_fair_value), 20)
        order_id += 1

        exchange.send_add_message(order_id, "MS", Dir.BUY, int(ms_fair_value), 30)
        order_id += 1

        exchange.send_add_message(order_id, "BOND", Dir.BUY, 1000, 30)
        order_id += 1

        exchange.send_add_message(order_id, "WFC", Dir.BUY, int(wfc_fair_value), 20)
        order_id += 1

        exchange.send_convert_message(order_id, "XLF", Dir.BUY, XLF_BUY_SELL_SIZE)
        order_id += 1

        exchange.send_add_message(order_id, "XLF", Dir.SELL, etf_fair_value // 10 + 35, XLF_BUY_SELL_SIZE)
        order_id += 1

    if fair_value("XLF", HISTORICAL_TRADES_THRESHOLD_ETF) + MARGIN < etf_fair_value // 10:
        # undervalued - we go short: buy ETF, convert, and sell underlying stocks
        print(f"submitted SELL for underlying XLF stocks at {best_ask}")
        exchange.send_add_message(order_id, "XLF", Dir.BUY, etf_fair_value // 10, XLF_BUY_SELL_SIZE)
        order_id += 1

        exchange.send_convert_message(order_id, "XLF", Dir.SELL, XLF_BUY_SELL_SIZE)
        order_id += 1

        # selling_price = max(fair_value // 10 + MARGIN, best_bid)
        # selling_price = fair_value // 10
        exchange.send_add_message(order_id, "GS", Dir.SELL, int(gs_fair_value+10), 20)
        order_id += 1

        exchange.send_add_message(order_id, "MS", Dir.SELL, int(ms_fair_value+10), 30)
        order_id += 1

        exchange.send_add_message(order_id, "BOND", Dir.SELL, 1000, 30)
        order_id += 1

        exchange.send_add_message(order_id, "WFC", Dir.SELL, int(wfc_fair_value+10), 20)
        order_id += 1

    time.sleep(0.001)

def main():
    global ready_to_trade_adr, ready_to_trade_etf, historical_trades, historical_trades_ct, order_id, HISTORICAL_TRADES_THRESHOLD_ADR, HISTORICAL_TRADES_THRESHOLD_ETF
    args = parse_arguments()

    exchange = ExchangeConnection(args=args)

    # Store and print the "hello" message received from the exchange. This
    # contains useful information about your positions. Normally you start with
    # all positions at zero, but if you reconnect during a round, you might
    # have already bought/sold symbols and have non-zero positions.
    hello_message = exchange.read_message()
    print("First message from exchange:", hello_message)

    # Set up some variables to track the bid and ask price of a symbol. Right
    # now this doesn't track much information, but it's enough to get a sense
    # of the VALE market.
    vale_bid_price, vale_ask_price = None, None
    vale_last_print_time = time.time()

    # Here is the main loop of the program. It will continue to read and
    # process messages in a loop until a "close" message is received. You
    # should write to code handle more types of messages (and not just print
    # the message). Feel free to modify any of the starter code below.
    #
    # Note: a common mistake people make is to call write_message() at least
    # once for every read_message() response.
    #
    # Every message sent to the exchange generates at least one response
    # message. Sending a message in response to every exchange message will
    # cause a feedback loop where your bot's messages will quickly be
    # rate-limited and ignored. Please, don't do that!
    while True:
        message = exchange.read_message()

        # Some of the message types below happen infrequently and contain
        # important information to help you understand what your bot is doing,
        # so they are printed in full. We recommend not always printing every
        # message because it can be a lot of information to read. Instead, let
        # your code handle the messages and just print the information
        # important for you!
        if message["type"] == "close":
            print("The round has ended")
            break
        elif message["type"] == "hello":
            print(message)
            # logic to update data structures with current positions in case connection closes
        elif message["type"] == "error":
            print(message)
        elif message["type"] == "reject":
            print(message)
        elif message["type"] == "fill":
            print(message)
            if message["dir"] == "BUY":
                positions[message["symbol"]] += 1
            else:
                positions[message["symbol"]] -= 1
        elif message["type"] == "book":
            def best_price(side):
                if message[side]:
                    return message[side][0][0]
            book[message["symbol"]] = (best_price("buy"), best_price("sell"))
            if message["symbol"] == "BOND":
                execute_bonds(exchange, best_price("buy"), best_price("sell"))
            if ready_to_trade_adr:
                if message["symbol"] == "VALE" or message["symbol"] == "VALBZ":
                    execute_adr(exchange, best_price("buy"), best_price("sell"), message["symbol"])
            if ready_to_trade_etf:
                if message["symbol"] == "XLF":
                    execute_etf(exchange, best_price("buy"), best_price("sell"))
        elif message["type"] == "trade":
            historical_trades[message["symbol"]].append((message["price"], message["size"]))
            if (len(historical_trades["VALBZ"]) >= HISTORICAL_TRADES_THRESHOLD_ADR):
                ready_to_trade_adr = True
            if (len(historical_trades["XLF"]) >= HISTORICAL_TRADES_THRESHOLD_ETF and len(historical_trades["GS"]) >= HISTORICAL_TRADES_THRESHOLD_ETF and len(historical_trades["BOND"]) >= HISTORICAL_TRADES_THRESHOLD_ETF and (len(historical_trades["MS"]) >= HISTORICAL_TRADES_THRESHOLD_ETF) and (len(historical_trades["WFC"]) >= HISTORICAL_TRADES_THRESHOLD_ETF)):
                ready_to_trade_etf = True
                print("ETF READY")

# ~~~~~============== PROVIDED CODE ==============~~~~~

# You probably don't need to edit anything below this line, but feel free to
# ask if you have any questions about what it is doing or how it works. If you
# do need to change anything below this line, please feel free to


class Dir(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExchangeConnection:
    def __init__(self, args):
        self.message_timestamps = deque(maxlen=500)
        self.exchange_hostname = args.exchange_hostname
        self.port = args.port
        self.exchange_socket = self._connect(add_socket_timeout=args.add_socket_timeout)

        self._write_message({"type": "hello", "team": team_name.upper()})

    def read_message(self):
        """Read a single message from the exchange"""
        message = json.loads(self.exchange_socket.readline())
        if "dir" in message:
            message["dir"] = Dir(message["dir"])
        return message

    def send_add_message(
        self, order_id: int, symbol: str, dir: Dir, price: int, size: int
    ):
        print(order_id, symbol, dir, price, size)
        """Add a new order"""
        self._write_message(
            {
                "type": "add",
                "order_id": order_id,
                "symbol": symbol,
                "dir": dir,
                "price": price,
                "size": size,
            }
        )

    def send_convert_message(self, order_id: int, symbol: str, dir: Dir, size: int):
        """Convert between related symbols"""
        self._write_message(
            {
                "type": "convert",
                "order_id": order_id,
                "symbol": symbol,
                "dir": dir,
                "size": size,
            }
        )

    def send_cancel_message(self, order_id: int):
        """Cancel an existing order"""
        self._write_message({"type": "cancel", "order_id": order_id})

    def _connect(self, add_socket_timeout):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if add_socket_timeout:
            # Automatically raise an exception if no data has been recieved for
            # multiple seconds. This should not be enabled on an "empty" test
            # exchange.
            s.settimeout(5)
        s.connect((self.exchange_hostname, self.port))
        return s.makefile("rw", 1)

    def _write_message(self, message):
        json.dump(message, self.exchange_socket)
        self.exchange_socket.write("\n")

        now = time.time()
        self.message_timestamps.append(now)
        if len(
            self.message_timestamps
        ) == self.message_timestamps.maxlen and self.message_timestamps[0] > (now - 1):
            print(
                "WARNING: You are sending messages too frequently. The exchange will start ignoring your messages. Make sure you are not sending a message in response to every exchange message."
            )


def parse_arguments():
    test_exchange_port_offsets = {"prod-like": 0, "slower": 1, "empty": 2}

    parser = argparse.ArgumentParser(description="Trade on an ETC exchange!")
    exchange_address_group = parser.add_mutually_exclusive_group(required=True)
    exchange_address_group.add_argument(
        "--production", action="store_true", help="Connect to the production exchange."
    )
    exchange_address_group.add_argument(
        "--test",
        type=str,
        choices=test_exchange_port_offsets.keys(),
        help="Connect to a test exchange.",
    )

    # Connect to a specific host. This is only intended to be used for debugging.
    exchange_address_group.add_argument(
        "--specific-address", type=str, metavar="HOST:PORT", help=argparse.SUPPRESS
    )

    args = parser.parse_args()
    args.add_socket_timeout = True

    if args.production:
        args.exchange_hostname = "production"
        args.port = 25000
    elif args.test:
        args.exchange_hostname = "test-exch-" + team_name
        args.port = 25000 + test_exchange_port_offsets[args.test]
        if args.test == "empty":
            args.add_socket_timeout = False
    elif args.specific_address:
        args.exchange_hostname, port = args.specific_address.split(":")
        args.port = int(port)

    return args


if __name__ == "__main__":
    # Check that [team_name] has been updated.
    assert (
        team_name != "[team_name]"
    ), "Please put your team name in the variable [team_name]."

    main()
