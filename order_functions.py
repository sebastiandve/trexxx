import time
import asyncio
import logging
from ccxt.base.errors import OrderNotFound, BadRequest
from config import STOP_LOSS_ROI, TAKE_PROFIT_PCTS, BALANCE_PCT, ORDER_EXPIRATION_TIME, MONITOR_ORDER_TIME

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


async def place_order(exchange, side, symbol, leverage, price, take_profit_prices):
    # Set leverage
    try:
      await exchange.set_leverage(leverage, symbol)
    except BadRequest as e:
      logging.error(f"Error: {str(e)}")

    # Calculate the amount
    quantity = await calculate_main_order_qty(exchange, leverage, price, symbol)

    # Calculate stop loss price
    stop_loss_price = calculate_stop_price(price, STOP_LOSS_ROI, leverage, side)
    params = {'stopLoss': {'type': 'market', 'triggerPrice': stop_loss_price}}
    
    # Place the main order
    try:
      order = await exchange.create_limit_order(symbol, side, quantity, price, params=params)
      logging.info(f"{symbol} {side} Order placed: {order['id']} Qty: {quantity} Price: {price} StopLoss: {stop_loss_price}")
    except Exception as e:
      logging.error(f"Error placing main order: {str(e)}")
      return
    
    # Wait for the main order to be filled
    res = await monitor_order(exchange, order['id'], symbol)
    if res:
      # Place take profit orders
      tp_orders = []
      profit_pcts = TAKE_PROFIT_PCTS
      remaining_quantity = quantity
      for i, (profit_price, profit_pct) in enumerate(zip(take_profit_prices, profit_pcts)):
        if i == len(profit_pcts) - 1:
          take_profit_quanitity = remaining_quantity
        else:
          take_profit_quanitity = float(exchange.amount_to_precision(symbol, quantity * profit_pct))
           
        remaining_quantity -= take_profit_quanitity
        take_profit_side = 'buy' if side == 'sell' else 'sell'
        try:
          tp_order = await exchange.create_limit_order(symbol, take_profit_side, take_profit_quanitity, profit_price)
          tp_orders.append(tp_order)
          logging.info(f"{symbol} {take_profit_side} TP Order placed: {tp_order['id']} Qty: {take_profit_quanitity} Price: {profit_price}")
        except Exception as e:
          logging.error(f"Error placing TP order: {str(e)}")
      if abs(remaining_quantity) > 0:
            logging.warning(f"Remaining quantity after placing TP orders: {remaining_quantity}")
      await monitor_position(exchange, symbol, tp_orders)

def calculate_stop_price(entry_price, roi, leverage, side):
    """
    Calculate the stop-loss price based on ROI, leverage, and position side.

    :param entry_price: The price at which the position was opened (float)
    :param roi: The desired ROI as a percentage (can be negative for stop-loss) (float)
    :param leverage: Leverage used for the position (float)
    :param side: 'buy' for long, 'sell' for short (str)
    :return: The stop-loss price (float)
    """
    
    if roi >= 0:
        raise ValueError("ROI should be negative for stop-loss calculations.")
    
    if side.lower() == 'buy':  # Long position
        stop_price = entry_price * (1 + (roi / (100 * leverage)))
    
    elif side.lower() == 'sell':  # Short position
        stop_price = entry_price * (1 - (roi / (100 * leverage)))
    
    else:
        raise ValueError(f'Invalid order side: {side}. Use "buy" for long or "sell" for short.')

    return stop_price


async def calculate_main_order_qty(exchange,leverage, price, symbol):
  balance = await exchange.fetch_balance()
  usdt_balance = balance['USDT'] if 'USDT' in balance else None
  usdt_balance = usdt_balance['free']
  qty = (usdt_balance * BALANCE_PCT * leverage) / price
  return float(exchange.amount_to_precision(symbol, qty))


async def monitor_order(exchange, order_id, symbol):
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
  

async def monitor_position(exchange, symbol, tp_orders):
   max_retries = 3
   retry_count = 0
   while True:
      await asyncio.sleep(MONITOR_ORDER_TIME)
      try:
        position = await exchange.fetch_position(symbol)
        if position['contracts'] == 0:
          logging.info(f"Position in {symbol} was closed.")
          for tp_order in tp_orders:
             try:
                await exchange.cancel_order(tp_order['id'], symbol)
                logging.info(f"TP Order {tp_order['id']} in {symbol} was canceled.")
             except OrderNotFound as e:
                logging.error(f"Error canceling TP order: {str(e)}")
          logging.info(f'All TP orders in {symbol} were canceled.')
          return
        else:
          logging.info(f"Position in {symbol} is still open.")
        retry_count = 0
      except Exception as e:
        logging.error(f"Error fetching position: {str(e)}")
        retry_count += 1
        if retry_count >= max_retries:
          logging.error(f"Max retries reached for {symbol}. Stopping position monitor.")
          return
        await asyncio.sleep(MONITOR_ORDER_TIME * retry_count)
      