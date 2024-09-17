import os
import asyncio
from dotenv import load_dotenv
import ccxt.async_support as ccxt
from telethon import TelegramClient, events

load_dotenv()

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')

BYBIT_API_KEY = os.getenv('BYBIT_API_KEY')
BYBIT_SECRET_KEY = os.getenv('BYBIT_SECRET_KEY')

session_file = 'my_telegram.session'

signal_pattern = r"""^🔥 #(\w+\/\w+) \((Long|Short)(?:📉|📈), x(\d+)\) 🔥

Entry - (\d+\.?\d+)
Take-Profit:

🥉 (\d+\.?\d+) \(40% of profit\)
🥈 (\d+\.?\d+) \(60% of profit\)
🥇 (\d+\.?\d+) \(80% of profit\)
🚀 (\d+\.?\d+) \(100% of profit\)$/m"""

client = TelegramClient(session_file, API_ID, API_HASH)


@client.on(events.NewMessage(pattern=signal_pattern))
async def handle_signal(event):
  asyncio.create_task(process_signal(event))


async def process_signal(event):
    try:
        # Parse the trade details from the message
        symbol = event.pattern_match.group(1)
        side = event.pattern_match.group(2)
        leverage = float(event.pattern_match.group(3))
        entry = float(event.pattern_match.group(4))
        take_profit_levels = [float(event.pattern_match.group(i)) for i in range(5, 9)]

        order_side = 'buy' if side == 'Long' else 'sell'

        base = symbol.split('/')[1]
        if base != 'USDT':
          raise NameError(f'Wrong base currency: {base}')
        
        # Connect to the exchange
        exchange = ccxt.bybit({
          'apiKey': BYBIT_API_KEY,
          'secret': BYBIT_SECRET_KEY,
          'enableRateLimit': True,
          'options': {'defaultType': 'swap'}
        })
        exchange.set_sandbox_mode(True) # remove this in production
        await exchange.load_markets()

        await place_order(exchange, order_side, symbol, leverage, entry, take_profit_levels)

        await exchange.close()
    except Exception as e:
        print(f"Error: {str(e)}")


async def place_order(exchange,side, symbol, leverage, price, take_profit_prices):
    # Set leverage
    try:
      await exchange.set_leverage(leverage, symbol)
    except Exception as e:
      print(f"Error: {str(e)}")

    # Calculate the amount
    quantity = await calculate_main_order_qty(exchange, leverage, price, symbol)
    print(f"Quantity of quote currency {symbol}: {quantity}")
    
    # Place the main order
    order = await exchange.create_limit_order(symbol, side, quantity, price)
    print(f"Main order placed: {order['id']}")

    # Wait for the main order to be filled
    res = await wait_for_order_filled(exchange, order['id'])
    if res:
      # Place take profit orders
      profit_pcts = [0.4, 0.2, 0.2, 0.2]
      for profit_price, profit_pct in zip(take_profit_prices, profit_pcts):
        take_profit_quanitity = exchange.amount_to_precision(symbol, quantity * profit_pct)
        take_profit_side = 'buy' if side == 'sell' else 'sell'
        order = await exchange.create_limit_order(symbol, take_profit_side, float(take_profit_quanitity), profit_price)
        print(f"Take profit order placed at {profit_price} for {take_profit_quanitity}: {order['id']}")


async def calculate_main_order_qty(exchange,leverage, price, symbol):
  balance = await exchange.fetch_balance()
  usdt_balance = balance['USDT'] if 'USDT' in balance else None
  usdt_balance = usdt_balance['free']
  qty = (usdt_balance * 0.02 * leverage) / price
  return float(exchange.amount_to_precision(symbol, qty))


async def wait_for_order_filled(exchange, order_id):
  status = 'open'
  while status not in ['closed', 'canceled', 'expired', 'rejected']:
    await asyncio.sleep(5)
    order = await exchange.fetch_order(order_id)
    status = order['status']
    print(f"Checking order {order_id} status: {status}")

  if order['status'] == 'closed':
    print(f"Order {order_id} filled")
    return order
  else:
    print(f"Order {order_id} not filled")
    return None


async def main():
  if not os.path.exists(session_file):
    print("Session file not found. Creating a new session...")
    await client.start(phone=PHONE_NUMBER)
  else:
    await client.start()

  print("Bot is running.")
  await client.run_until_disconnected()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
