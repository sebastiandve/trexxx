import time
import asyncio
import logging
from decimal import Decimal
from ccxt.async_support import Exchange
from ccxt.base.errors import OrderNotFound, BadRequest
from config import LEVELS, BALANCE_PCT, ORDER_EXPIRATION_TIME, MONITOR_ORDER_TIME, TRAILING_SL_ROI

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def place_order(exchange: Exchange, side: str, symbol: str, leverage: Decimal, entry_price: Decimal):
    # Set leverage
    try:
      await exchange.set_leverage(leverage, symbol)
    except BadRequest as e:
      logging.error(f"Error: {str(e)}")

    # Calculate the total quantity
    total_quantity = await calculate_main_order_qty(exchange, leverage, entry_price, symbol)


    orders = []
    remaining_quantity = total_quantity

    for i, level in enumerate(LEVELS):
        qty_pct = Decimal(str(level['qty_pct']))
        roiTP = Decimal(str(level['roiTP']))
        roiSL = Decimal(str(level['roiSL']))

        if i == len(LEVELS) - 1:
            order_quantity = remaining_quantity
        else:
            order_quantity = float(exchange.amount_to_precision(symbol, total_quantity * qty_pct))
            order_quantity = Decimal(str(order_quantity))

        remaining_quantity -= order_quantity

        # Calculate stop loss price
        stop_loss_price = calculate_price(entry_price, roiSL, leverage, side)



        params = {
          'category': 'linear',
          'symbol': symbol,
          'isLeverage': 1,
          'side': side,
          'orderType': 'Limit',
          'qty': str(order_quantity),
          'price': str(entry_price),

          'tpslMode': 'Partial',

          'stopLoss': str(stop_loss_price),
          'slOrderType': 'Market'
        }
        if i > 0: # Risky order does not have TP but uses trailing stop loss
          take_profit_price = calculate_price(entry_price, roiTP, leverage, side)
          params['takeProfit'] = str(take_profit_price)
          params['tpOrderType'] = 'Market'
        if i == 1: # Activation price for trailing stop loss is the TP of the 2nd riskiest order
           tsl_activation_price = take_profit_price

        # Create main orders with TP and SL
        try:
            order = await exchange.private_post_v5_order_create(params)
            orders.append(order)
            logging.info(f"{symbol} {side} Order placed: {order['result']['orderId']} Qty: {order_quantity} Price: {entry_price} StopLoss: {stop_loss_price} TakeProfit: {take_profit_price}")
        except Exception as e:
            logging.error(f"Error placing order: {str(e)}", exc_info=True)

    if abs(remaining_quantity) > 0:
        logging.warning(f"Remaining quantity after placing orders: {remaining_quantity}")

    asyncio.create_task(monitor_position(exchange, symbol, tsl_activation_price, leverage, side))
    asyncio.create_task(close_open_orders(exchange, symbol))


async def calculate_main_order_qty(exchange: Exchange, leverage: Decimal, price: Decimal, symbol: str) -> Decimal:
  balance = await exchange.fetch_balance()
  usdt_balance = balance['USDT'] if 'USDT' in balance else None
  usdt_balance = usdt_balance['free']
  qty = (Decimal(str(usdt_balance)) * Decimal(str(BALANCE_PCT)) * leverage) / price
  return Decimal(str(exchange.amount_to_precision(symbol, qty)))


async def monitor_order(exchange: Exchange, order_id: str, symbol: str) -> dict | None:
  status = 'open'
  start_time = time.time()
  while status not in ['closed', 'canceled', 'expired', 'rejected']:
    await asyncio.sleep(MONITOR_ORDER_TIME)
    elapsed_time = time.time() - start_time
    try:
      order = await exchange.fetch_open_order(order_id)
      status = order['status']
      if (status == 'open' and elapsed_time > ORDER_EXPIRATION_TIME):
         await exchange.cancel_order(order_id, symbol)
         logging.info(f'Order {order_id} in {symbol} was canceled after {elapsed_time}s.')
         return None
    except OrderNotFound as e:
       try: 
          order = await exchange.fetch_closed_order(order_id)
          status = order['status']
       except OrderNotFound as e:
          logging.error(f"Error fetching closed order: {str(e)}")
          return None
    logging.info(f"Checking order {order_id} status: {status}")

  if order['status'] == 'closed':
    logging.info(f"Order {order_id} was filled")
    return order
  else:
    logging.info(f"Order {order_id} was not filled")
    return None
  

def calculate_price(entry_price: Decimal, roi: Decimal, leverage: Decimal, side: str) -> Decimal:
    """
    Calculate the price based on ROI, leverage, and position side.

    :param entry_price: The price at which the position was opened (Decimal)
    :param roi: The desired ROI as a percentage (can be negative for stop-loss) (Decimal)
    :param leverage: Leverage used for the position (Decimal)
    :param side: 'Buy' for long, 'Sell' for short (str)
    :return: The price (Decimal)
    """

    if side.lower() == 'buy':  # Long position
        stop_price = entry_price * (1 + (roi / (100 * leverage)))
    
    elif side.lower() == 'sell':  # Short position
        stop_price = entry_price * (1 - (roi / (100 * leverage)))
    
    else:
        raise ValueError(f'Invalid order side: {side}. Use "Buy" for long or "Sell" for short.')

    return stop_price


async def close_open_orders(exchange: Exchange, symbol: str):
    max_retries = 5
    retry_count = 0

    while retry_count < max_retries:
        await asyncio.sleep(MONITOR_ORDER_TIME)
        try:
            orders = await exchange.fetch_open_orders(symbol)
            if not orders:
                logging.info(f"No open orders in {symbol}")
                return

            now = time.time() * 1000
            for order in orders:
                if now - order['timestamp'] > ORDER_EXPIRATION_TIME and order['filled'] == 0:
                    try:
                        await exchange.cancel_order(order['id'], symbol)
                        logging.info(f"Order {order['id']} in {symbol} was canceled")
                    except Exception as e:
                        logging.error(f"Error canceling order {order['id']}: {str(e)}")

            retry_count = 0

        except Exception as e:
            logging.error(f"Error fetching open orders: {str(e)}")
            retry_count += 1
            await asyncio.sleep(60)

    logging.warning(f"Max retries reached for closing open orders in {symbol}. Exiting function.")


async def add_trailing_stop_loss(exchange: Exchange, symbol: str, activation_price: Decimal, leverage: Decimal, side: str):
    trailing_stop_price = calculate_price(activation_price, Decimal(str(TRAILING_SL_ROI)), leverage, side)
    ts_params = {
      'category': 'linear',
      'symbol': symbol,
      'activePrice': str(activation_price),
      'trailingStop': str(activation_price - trailing_stop_price),
    }
    await exchange.private_post_v5_position_trading_stop(ts_params)
    logging.info(f"Trailing stop loss order placed for {symbol} at {trailing_stop_price} activation price: {activation_price}")


async def monitor_position(exchange: Exchange, symbol: str, tsl_activation_price: Decimal, leverage: Decimal, side: str):
    max_retries = 5
    retry_count = 0
    await asyncio.sleep(30)
    while retry_count < max_retries:
      try:
        position = await exchange.fetch_position(symbol)
        if position['contracts'] != 0:
          await add_trailing_stop_loss(exchange, symbol, tsl_activation_price, leverage, side)
          return
        else:
          logging.info(f"No trailing stop loss added for {symbol} because position not open yet")
        
        orders = await exchange.fetch_open_orders(symbol)
        if not orders and position['contracts'] == 0:
           logging.info(f"No open orders in {symbol} and position is closed")
           return
        
        await asyncio.sleep(MONITOR_ORDER_TIME)
        retry_count = 0
      except Exception as e:
        logging.error(f"Error monitoring position: {str(e)}", exc_info=True)
        retry_count += 1
        await asyncio.sleep(MONITOR_ORDER_TIME * retry_count * 2)

    logging.warning(f"Max retries reached for monitoring position in {symbol}. Exiting function.")
       
