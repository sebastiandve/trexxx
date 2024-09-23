import os
import asyncio
import logging
import ccxt.async_support as ccxt
from decimal import Decimal
from dotenv import load_dotenv
from telethon import TelegramClient, events
from order_functions import place_order

load_dotenv('.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
PHONE_NUMBER = os.getenv('TELEGRAM_PHONE_NUMBER')
CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID'))
SESSION_FILE = os.getenv('TELEGRAM_SESSION_FILE')

BYBIT_API_KEY = os.getenv('BYBIT_API_KEY')
BYBIT_SECRET_KEY = os.getenv('BYBIT_SECRET_KEY')


signal_pattern = r"""^🔥 #(\w+\/\w+) \((Long|Short)(?:📉|📈), x(\d+)\) 🔥

Entry - (\d+\.?\d*)
Take-Profit:

🥉 (\d+\.?\d*) \(40% of profit\)
🥈 (\d+\.?\d*) \(60% of profit\)
🥇 (\d+\.?\d*) \(80% of profit\)
🚀 (\d+\.?\d*) \(100% of profit\)"""

client = TelegramClient(SESSION_FILE, API_ID, API_HASH)


@client.on(events.NewMessage(pattern=signal_pattern, chats=[CHAT_ID]))
async def handle_signal(event):
  logging.info(f'Received new signal: {event.message.message}')
  asyncio.create_task(process_signal(event))


async def process_signal(event):
    try:
        # Parse the trade details from the message
        symbol = event.pattern_match.group(1)
        side = event.pattern_match.group(2)
        order_side = 'Buy' if side == 'Long' else 'Sell'
        leverage = int(event.pattern_match.group(3))
        entry = Decimal(str(event.pattern_match.group(4)))
        take_profit_prices = [Decimal(str(event.pattern_match.group(i))) for i in range(5, 9)]


        base = symbol.split('/')[1]
        if base != 'USDT':
          raise NameError(f'Wrong base currency: {base}')
        
        symbol = symbol.replace('/', '')

        logging.info(f"Processing signal: {symbol} {order_side} {leverage}x at {entry}")

        
        # Connect to the exchange
        exchange = ccxt.bybit({
          'apiKey': BYBIT_API_KEY,
          'secret': BYBIT_SECRET_KEY,
          'enableRateLimit': True,
          'options': {'defaultType': 'swap'}
        })
        exchange.enable_demo_trading(True) # remove this in prod
        await exchange.load_markets()

        await place_order(exchange, order_side, symbol, leverage, entry, take_profit_prices)

        await exchange.close()
    except Exception:
      logging.exception("Error processing signal")


async def main():
  try:     
    await client.start(phone=PHONE_NUMBER)
    logging.info("Bot is running. Version 1.2")
    await client.run_until_disconnected()
  except Exception as e:
     logging.exception("Error in main function")


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
    except Exception:
        logging.exception("Unexpected error")
    finally:
        loop.close()
        logging.info("Bot stopped.")
