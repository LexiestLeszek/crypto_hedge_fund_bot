import ccxt
import time
import json
import os
import math
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Configuration (replace with your own values)
API_KEY = 'YOUR_API_KEY'
API_SECRET = 'YOUR_API_SECRET'
EXCHANGE_ID = 'binance'  # You can change to any supported exchange
AMOUNT_TO_BUY = 5  # $5 worth of crypto
PRICE_DROP_THRESHOLD = 0.05  # 5% drop
PRICE_RISE_THRESHOLD = 0.10  # 10% rise
COINS = ['BTC', 'TON', 'ETH', 'XRP', 'ADA', 'DOGE']
CHECK_INTERVAL = 60  # Check prices every 60 seconds

# File to store trading state
STATE_FILE = 'trading_state.json'

def initialize_exchange():
    """Initialize the exchange connection."""
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
    })
    return exchange

def load_state():
    """Load the trading state from file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    else:
        # Initialize with empty holdings and reference prices
        state = {
            'holdings': {},  # What we're currently holding (amount in coin)
            'buy_prices': {},  # Prices at which we bought
            'reference_prices': {},  # Reference prices for calculating drops
        }
        return state

def save_state(state):
    """Save the trading state to file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def get_current_prices(exchange, coins):
    """Get current prices for all coins."""
    current_prices = {}
    for coin in coins:
        try:
            symbol = f"{coin}/USDT"
            ticker = exchange.fetch_ticker(symbol)
            current_prices[coin] = ticker['last']
            logger.info(f"Current price of {coin}: ${current_prices[coin]}")
        except Exception as e:
            logger.error(f"Error fetching price for {coin}: {e}")
    return current_prices

def round_amount(amount, precision):
    """Round amount mathematically to the specified precision."""
    factor = 10 ** precision
    return math.floor(amount * factor + 0.5) / factor

def check_trading_conditions(exchange, state, current_prices):
    """Check if we should buy or sell based on price movements."""
    for coin, price in current_prices.items():
        symbol = f"{coin}/USDT"
        
        # Initialize reference price if we don't have one
        if coin not in state['reference_prices']:
            state['reference_prices'][coin] = price
            continue
        
        # If we're not holding this coin and price dropped by threshold or more from reference
        if coin not in state['holdings']:
            reference_price = state['reference_prices'][coin]
            price_change = (price - reference_price) / reference_price
            
            if price_change <= -PRICE_DROP_THRESHOLD:
                logger.info(f"Price of {coin} dropped by {-price_change*100:.2f}% from ${reference_price} to ${price}. Buying ${AMOUNT_TO_BUY} worth.")
                
                try:
                    # Calculate amount to buy (in coin units)
                    amount_in_coin = AMOUNT_TO_BUY / price
                    
                    # Some exchanges require specific precision for amounts
                    markets = exchange.load_markets()
                    market = markets[symbol]
                    
                    # Get the precision required by the exchange
                    amount_precision = market['precision']['amount'] if isinstance(market['precision']['amount'], int) else 8
                    
                    # Round the amount mathematically to the required precision
                    amount_in_coin = round_amount(amount_in_coin, amount_precision)
                    
                    logger.info(f"Placing buy order for {amount_in_coin} {coin} (${AMOUNT_TO_BUY})")
                    order = exchange.create_market_buy_order(symbol, amount_in_coin)
                    logger.info(f"Buy order executed: {order}")
                    
                    # Record the purchase
                    state['holdings'][coin] = amount_in_coin
                    state['buy_prices'][coin] = price
                    
                    # Reset reference price after buying
                    state['reference_prices'][coin] = price
                    
                except Exception as e:
                    logger.error(f"Error executing buy order for {coin}: {e}")
            else:
                # Update reference price if price is lower
                if price < reference_price:
                    state['reference_prices'][coin] = price
                    logger.info(f"Updated reference price for {coin} to ${price}")
        
        # If we're holding this coin, check if price rose by threshold
        else:
            buy_price = state['buy_prices'][coin]
            price_change = (price - buy_price) / buy_price
            
            if price_change >= PRICE_RISE_THRESHOLD:
                logger.info(f"Price of {coin} rose by {price_change*100:.2f}% from ${buy_price} to ${price}. Selling all.")
                
                amount_to_sell = state['holdings'][coin]
                
                try:
                    logger.info(f"Placing sell order for {amount_to_sell} {coin}")
                    order = exchange.create_market_sell_order(symbol, amount_to_sell)
                    logger.info(f"Sell order executed: {order}")
                    
                    # Remove from holdings after successful sell
                    del state['holdings'][coin]
                    del state['buy_prices'][coin]
                    
                    # Reset reference price for future buying opportunities
                    state['reference_prices'][coin] = price
                    
                except Exception as e:
                    logger.error(f"Error executing sell order for {coin}: {e}")
    
    return state

def main():
    """Main function to run the trading bot."""
    logger.info("Initializing trading bot...")
    exchange = initialize_exchange()
    state = load_state()
    
    logger.info(f"Monitoring coins: {', '.join(COINS)}")
    logger.info(f"Buy condition: {PRICE_DROP_THRESHOLD*100}% price drop, Buy amount: ${AMOUNT_TO_BUY}")
    logger.info(f"Sell condition: {PRICE_RISE_THRESHOLD*100}% price rise from buy price")
    
    # Get initial prices if we don't have reference prices
    if not state['reference_prices']:
        logger.info("Getting initial prices...")
        current_prices = get_current_prices(exchange, COINS)
        for coin, price in current_prices.items():
            state['reference_prices'][coin] = price
        save_state(state)
    
    try:
        while True:
            logger.info(f"--- {datetime.now()} ---")
            
            # Get current prices
            current_prices = get_current_prices(exchange, COINS)
            
            # Check if we should buy or sell
            state = check_trading_conditions(exchange, state, current_prices)
            
            # Save the updated state
            save_state(state)
            
            # Wait before next check
            logger.info(f"Waiting {CHECK_INTERVAL} seconds before next check...")
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Trading bot stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        logger.info("Saving final state...")
        save_state(state)
        logger.info("Trading bot shut down.")

if __name__ == "__main__":
    main()
