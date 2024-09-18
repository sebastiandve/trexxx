import os
import re
import asyncio
import ccxt.async_support as ccxt
from dotenv import load_dotenv
from telethon import TelegramClient, events
from order_functions import place_order

load_dotenv('.env')

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
  asyncio.create_task(process_signal(event))


async def process_signal(event):
    try:
        # Parse the trade details from the message
        symbol = event.pattern_match.group(1)
        side = event.pattern_match.group(2)
        leverage = float(event.pattern_match.group(3))
        entry = float(event.pattern_match.group(4))
        take_profit_prices = [float(event.pattern_match.group(i)) for i in range(5, 9)]

        order_side = 'buy' if side == 'Long' else 'sell'

        base = symbol.split('/')[1]
        if base != 'USDT':
          raise NameError(f'Wrong base currency: {base}')
        
        symbol = symbol.replace('/', '')
        
        # Connect to the exchange
        exchange = ccxt.bybit({
          'apiKey': BYBIT_API_KEY,
          'secret': BYBIT_SECRET_KEY,
          'enableRateLimit': True,
          'options': {'defaultType': 'swap'}
        })
        exchange.set_sandbox_mode(True) # remove this in production
        await exchange.load_markets()

        await place_order(exchange, order_side, symbol, leverage, entry, take_profit_prices)

        await exchange.close()
    except Exception as e:
        print(f"Error: {str(e)}")


async def main():
  await client.start(phone=PHONE_NUMBER)
  print("Bot is running.")
  await client.run_until_disconnected()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
