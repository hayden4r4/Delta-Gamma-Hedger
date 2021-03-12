from tda.client import Client
from tda.auth import easy_client
from tda import auth
from tda.orders import equities
from tda.orders.common import Duration, Session
import pandas as pd
import os
from datetime import datetime
from datetime import date
import threading
import atexit
import json
from pprint import pprint
import time
import asyncio
import traceback

# Set account variables and webdriver path
account_id = open(r'C:\Python\API Keys\TD\TD_ACCOUNT_ID.txt').read()
consumer_key = open(r'C:\Python\API Keys\TD\TD_CONSUMER_KEY.txt').read()
redirect_uri = 'http://localhost'
token_path = r'C:\Python\API Keys\TD\ameritrade-credentials.json'
geckodriver_path = r'C:\Webdrivers\geckodriver.exe'

# Set webdriver for getting refresh token
def make_webdriver():
    from selenium import webdriver

    driver = webdriver.Firefox(executable_path=geckodriver_path)
    atexit.register(lambda: driver.quit())
    return driver

# Define main function
def main():
    # Easy client with user account variables
    c = easy_client(consumer_key,
                            redirect_uri,
                            token_path,
                            make_webdriver)




    # Set options to be hedged
    symbols_to_hedge = ['SPY_041621C495']
    # The threshold that  an option's delta is allowed to move before
    # rehedging. For example, if threshold = 5, delta can increase/decrease
    # by 5 before rehedging, an effective range of 10 delta.  This delta
    # is per 100 shares (delta * 100).  The larger the threshold
    # the less hedged you may be at a given time, however this also reduces
    # transaction costs incurred by adjusting the hedge.
    threshold = 5

    # Get positions for account
    account_info = c.get_account(account_id, 
                    fields = [c.Account.Fields.POSITIONS, c.Account.Fields.ORDERS])
    account_info_json = account_info.json()


    # Seperate equity and option positions into seperate dataframes
    equity_positions_list = []
    option_positions_list = []
    for entry in account_info_json['securitiesAccount']['positions']:
        if entry['instrument']['assetType'] == 'EQUITY':
            equity_positions_list.append(entry)
        elif entry['instrument']['assetType'] == 'OPTION':
            option_positions_list.append(entry)


    if equity_positions_list:
        equity_positions = pd.DataFrame(equity_positions_list)
        equ_pos_ticker_list = []
        equ_pos_cusip_list = []
        equ_pos_assetType_list = []
        for row in equity_positions['instrument']:
            equ_pos_ticker_list.append(row['symbol'])
            equ_pos_cusip_list.append(row['cusip'])
            equ_pos_assetType_list.append(row['assetType'])
        equity_positions['symbol'] = equ_pos_ticker_list
        equity_positions['cusip'] = equ_pos_cusip_list
        equity_positions['assetType'] = equ_pos_assetType_list
        equity_positions.drop(columns = 'instrument', inplace = True)
        equity_positions.set_index('symbol', inplace = True)
        
    if option_positions_list:
        option_positions = pd.DataFrame(option_positions_list)
        opt_pos_symbol_list = []
        opt_pos_description_list = []
        opt_pos_putCall_list = []
        opt_pos_assetType_list = []
        opt_pos_underlyingSymbol_list = []
        for row in option_positions['instrument']:
            opt_pos_symbol_list.append(row['symbol'])
            opt_pos_description_list.append(row['description'])
            opt_pos_putCall_list.append(row['putCall'])
            opt_pos_assetType_list.append(row['assetType'])
            opt_pos_underlyingSymbol_list.append(row['underlyingSymbol'])
        option_positions['symbol'] = opt_pos_symbol_list
        option_positions['description'] = opt_pos_description_list
        option_positions['putCall'] = opt_pos_putCall_list
        option_positions['assetType'] = opt_pos_assetType_list
        option_positions['underlyingSymbol'] = opt_pos_underlyingSymbol_list
        option_positions.drop(columns = 'instrument', inplace = True)
        option_positions.set_index('symbol', inplace = True)

    # Calculate total quantity of holdings for both equities and options
    equity_positions['totalQuantity'] = equity_positions['longQuantity'] + equity_positions['shortQuantity']
    option_positions['totalQuantity'] = option_positions['longQuantity'] + option_positions['shortQuantity']
    
    # Check if the underlying of an option is in current positions,
    # if it is then add the underlying's quantity to the option
    # positions df.  If it is not, then set quantity to 0 and
    # add to options positions df.
    for symbol in option_positions['underlyingSymbol']:
        if equity_positions.index.isin([symbol]).any():
            underlyingQuantity = equity_positions.loc[equity_positions.index == symbol, 'totalQuantity'].iloc[0]
            option_positions.loc[option_positions['underlyingSymbol'] == symbol, 'underlyingQuantity'] = underlyingQuantity
        else:
            option_positions.loc[option_positions['underlyingSymbol'] == symbol, 'underlyingQuantity'] = 0

    # If option to hedge is in portfolio, then it is appended
    # to list, if it is not, it is appended to a different list
    # and a message is printed warning that you must purchase
    # the options before hedging them.
    symbols_to_hedge_in_holdings = []
    symbols_to_hedge_not_in_holdings = []
    for symbol in symbols_to_hedge:
        if option_positions.index.isin([symbol]).any():
            symbols_to_hedge_in_holdings.append(symbol)
        else:
            symbols_to_hedge_not_in_holdings.append(symbol)
            print('Could not hedge the following options because they are not currently held in portfolio:', '\n', symbols_to_hedge_not_in_holdings)
            continue
    
    # Gets quotes for options that are in portfolio and
    # set to be hedged, then merges the quotes and option
    # positions df into a new option_positions_to_hedge df.
    option_quotes_resp = c.get_quotes(symbols = symbols_to_hedge_in_holdings)
    option_quotes_df = pd.DataFrame.from_dict(option_quotes_resp.json(), orient = 'index')
    option_positions_to_hedge = pd.merge(option_positions.loc[option_positions.index.isin(symbols_to_hedge_in_holdings)], option_quotes_df, left_index = True, right_index = True)

    # Finds the total greek exposure for each option
    # by multiplying the quantity of an option by
    # the given greek then multiplying by 100
    # and adds to the option_positions_to_hedge df
    greeks = ['delta', 'gamma', 'theta', 'vega']
    for greek in greeks:
        option_positions_to_hedge['total' + greek.capitalize()] = abs(option_positions_to_hedge[greek]) * option_positions_to_hedge['totalQuantity'] * 100

    # A threaded function that places orders
    def place_orders(symbol):
        # Gets current date and time
        now = datetime.now().strftime('%d-%m-%y %I:%M:%S %p')
        # Finds the total deltas for options to be hedged on a particular underlying
        total_deltas_for_options_on_underlying = option_positions_to_hedge.loc[option_positions_to_hedge['underlyingSymbol'] == symbol]['totalDelta'].sum()
        # Finds the total quantity for a particular underlying
        underlying_quantity = option_positions_to_hedge.loc[option_positions_to_hedge['underlyingSymbol'] == symbol]['underlyingQuantity']
        # If the stock underlying an option to be hedged
        # is not owned, then the underlying quantity is set to 0.
        # If it is owned, then the quantity is set from the series as an integer
        if underlying_quantity.empty:
            underlying_quantity = 0
        else:
            underlying_quantity = int(underlying_quantity.iloc[0])
        # Determines the number of shares needed to be bought/sold to be delta neutral.
        # This is done by multiplying the total number of deltas for an option by -1,
        # then subtracting the quantity of the underlying for the options.
        shares_needed_to_hedge = int(total_deltas_for_options_on_underlying * -1 - underlying_quantity)
        # Place Orders, due to shorts and longs having seperate functions, it
        # complicates the order process, and it can be hard to follow.
        # The process itself is fairly straightforward, the number of shares
        # owned should be equal to the inverse of the total deltas on a particular
        # underlying.  So shares will either be purchased or sold to reach
        # this condition.  Adjustment is made when the total deltas
        # for the options on an underlying move past the previously set threshold, 
        # either above or below.
        if shares_needed_to_hedge > threshold:
            if underlying_quantity < 0 and underlying_quantity + shares_needed_to_hedge < 0:
                #Buy to cover shares_needed_to_hedge
                order_specs = equities.equity_buy_to_cover_market(symbol = symbol,
                                                                quantity = shares_needed_to_hedge).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order = c.place_order(account_id, order_specs)
                pprint(pd.DataFrame(order_specs['orderLegCollection'], index = [now]))
            elif underlying_quantity < 0 and underlying_quantity + shares_needed_to_hedge > 0:
                #Buy to cover abs(underlying_quantity)
                order1_specs = equities.equity_buy_to_cover_market(symbol = symbol,
                                                                quantity = abs(underlying_quantity)).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order1 = c.place_order(account_id, order1_specs)
                pprint(pd.DataFrame(order1_specs['orderLegCollection'], index = [now]))
                #Buy shares_needed_to_hedge - abs(underlying_quantity)
                order2_specs = equities.equity_buy_market(symbol = symbol,
                                                                quantity = shares_needed_to_hedge - abs(underlying_quantity)).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order2 = c.place_order(account_id, order2_specs)
                pprint(pd.DataFrame(order2_specs['orderLegCollection'], index = [now]))
            elif underlying_quantity > 0:
                #Buy shares_needed_to_hedge
                order_specs = equities.equity_buy_market(symbol = symbol,
                                                                quantity = shares_needed_to_hedge).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order = c.place_order(account_id, order_specs)
                pprint(pd.DataFrame(order_specs['orderLegCollection'], index = [now]))
        elif shares_needed_to_hedge < -threshold:
            if underlying_quantity > 0 and underlying_quantity + shares_needed_to_hedge > 0:
                #Sell abs(shares_needed_to_hedge)
                order_specs = equities.equity_sell_market(symbol = symbol,
                                                                quantity = abs(shares_needed_to_hedge)).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order = c.place_order(account_id, order_specs)
                pprint(pd.DataFrame(order_specs['orderLegCollection'], index = [now]))
            elif underlying_quantity > 0 and underlying_quantity + shares_needed_to_hedge < 0:
                #Sell underlying_quantity
                order1_specs = equities.equity_sell_market(symbol = symbol,
                                                                quantity = underlying_quantity).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order1 = c.place_order(account_id, order1_specs)
                pprint(pd.DataFrame(order1_specs['orderLegCollection'], index = [now]))
                #Sell short abs(underlying_quantity + shares_needed_to_hedge)
                order2_specs = equities.equity_sell_short_market(symbol = symbol,
                                                                quantity = abs(underlying_quantity + shares_needed_to_hedge)).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order2 = c.place_order(account_id, order2_specs)
                pprint(pd.DataFrame(order2_specs['orderLegCollection'], index = [now]))
            elif underlying_quantity < 0:
                #Sell to open abs(shares_needed_to_hedge)
                order_specs = equities.equity_sell_short_market(symbol = symbol,
                                                                quantity = abs(shares_needed_to_hedge)).set_duration(Duration.DAY).set_session(Session.SEAMLESS).build()
                order = c.place_order(account_id, order_specs)
                pprint(pd.DataFrame(order_specs['orderLegCollection'], index = [now]))

    # Since each option has an underlying value in the 
    # option_positions_to_hedge df, this can result in duplicated
    # symbols if there are multiple options on the same underlying
    # to be hedge.  This finds the unique underlyings in the
    # option_positions_to_hedge df, and appends to list.
    unique_symbols = option_positions_to_hedge['underlyingSymbol'].unique()
    # Iterate through the unique symbols in the unique symbols list
    # pass each one in a threaded process to the place_orders df.
    # This means that each stock is bought/sold as needed to neutralize
    # the delta of the options to be hedged. By running as a
    # threaded process this should provide significant speed
    # increases if there are many equities to iterate through.
    thread_list=[]
    def thread_place_orders():
        for symbol in unique_symbols:
            threadProcess = threading.Thread(name='simplethread', target=place_orders, args=[symbol])
            thread_list.append(threadProcess)
        for thread in thread_list:
            thread.start()
        for thread in thread_list:
            thread.join()
    thread_place_orders()

# This runs the main function indefinitely,
# sleeping for 5 seconds, this time can be
# adjusted as needed, however it is of note that
# TDAmeritrade has a limit of 120 api calls per sliding
# minute window, therefore it is recommended to be
# more conservative with the sleep time as the
# amount of options to be hedged increases.
# If an exception is raised, it is printed and
# the loop will continue.
while True:
    try:
        main()
        time.sleep(5)
    except Exception as e:
        pprint(e)
        time.sleep(5)
        continue


