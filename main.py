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

exchange = ccxt.bybit({
  'apiKey': BYBIT_API_KEY,
  'secret': BYBIT_SECRET_KEY,
  'enableRateLimit': True,
  'options': {'defaultType': 'future'}
})

async def place_order(side, symbol, leverage, amount, price, take_profit_levels):
    await exchange.load_markets()
    
    # Set leverage
    await exchange.set_leverage(leverage, symbol)
    
    # Place the main order
    order = await exchange.create_market_order(symbol, side, amount)
    print(f"Main order placed: {order}")
    
    # Place take profit orders
    for level in take_profit_levels:
        tp_price = price * (1 + level / 100) if side == 'buy' else price * (1 - level / 100)
        tp_order = await exchange.create_limit_order(symbol, 'sell' if side == 'buy' else 'buy', amount / len(take_profit_levels), tp_price)
        print(f"Take profit order placed at {level}%: {tp_order}")

@client.on(events.NewMessage(pattern=signal_pattern))
async def handle_trade_command(event):
    try:
        # Parse the trade details from the message
        symbol = event.pattern_match.group(1)
        side = event.pattern_match.group(2)
        leverage = event.pattern_match.group(3)
        entry = event.pattern_match.group(4)
        take_profit_levels = [event.pattern_match.group(i) for i in range(5, 9)]

        order_side = 'buy' if side == 'Long' else 'sell'
        
        await place_order(order_side, symbol, leverage, amount, price, take_profit_levels)
    except Exception as e:
        print(f"Error: {str(e)}")

async def main():
  if not os.path.exists(session_file):
    print("Session file not found. Creating a new session...")
    await client.start(phone=PHONE_NUMBER)
  else:
    await client.start()


  
  await exchange.load_markets()
  print("Bot is running.")
  await client.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
