# Delta-Gamma-Hedger
Hedges delta and readjusts based on a user-defined interval.  Uses TDameritrade for data and orders, making use of Alex Golec's tda-api.

Trading delta neutral can be useful for going long/short vol along with other strategies, by neutralizing directional movements effect on delta & gamma, with some slippage.

### TO USE: 
First set paths to your TDAmeritrade variables along with your choice of webdriver, if you need help I recommend reading the docs for tda-api https://tda-api.readthedocs.io/en/latest/auth.html, or TDAmeritrade's documentation. A forewarning, getting the credentials set up can be difficult.

Next set the interval of delta on which you wish to adjust your hedge at the beginning of the script, for example, an interval of 5 would mean that the position would be rehedged every time the total delta for the options you wish to hedge on an underlying either go above/below 5 delta away from the number of shares of the underlying, an effective range of 10 delta.  Note: The wider the range, the poorer the hedge, however the tighter the range, the higher the potential transaction cost.  There is (from what I have seen) no real concensus on a _best_ interval.

Finally, every option at TDAmeritrade has a unique symbol, the format is: ticker_datetypestrike, where ticker is the symbol of the underlying, date is the expiration in monthdayyear format, the type is a C or P for call or put, and the strike is the option's strike price. An example is: SPY_041621C495 a 495 Call on SPY expiring April 16, 2021. The options to be hedged should be entered at the beginning of the script in this format.  

Once the script is ran, it runs indefinitely, it will begin placing orders to neutralize the delta, and will readjust as necessary.

### TO DO:
I will eventually make the symbol entry more dynamic, where the list of symbols can be edited without having to stop the script, I am considering maybe a telegram bot? where a message can be sent containing the symbol and can be added/removed from the list remotely. I have no experience in this area so I will look into this, right now a semi-better solution is to read a list in from a csv file, which should be able to be edited without pausing the script, I may implement this later.

I would also like more options for hedging, like a hedge daily, weekly, etc. with the option of an interval as a safeguard.  I also think assigning different intervals to different options may be helpful. These may be implemented later.  

Please feel free to fork/contribute.


## Disclosure:
I have yet to test this script in a live market, only offline testing to ensure orders are placed properly.  I have attempted to make this code as solid as possible, as I do plan on using this myself occasionally, however it is up to you to evaluate the code and determine if it accomplishes what you seek and does so correctly, **I highly encourage you to do this**.  I will note that this is my first automated trading project, I do not consider myself a professional coder, therefore **please thoroughly evaluate before using this code**. While delta neutral strategies may have a high win rate, they also have extreme long tail risk, please consider and understand the risks of delta neutral trading before doing so.
