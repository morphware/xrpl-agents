from typing import Optional, Dict, Tuple, ClassVar, List
import pandas as pd
import numpy as np
import traceback
from ...exceptions import CryptoToolError
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from .utils import resolve_token_id, get_historical_data, get_high_level_market_data
from .price import CryptoPriceTool
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/crypto_analysis.log')

class CryptoAnalysisTool(BaseCustomTool, BaseTool):
    """Tool for analyzing cryptocurrency metrics and technical indicators."""
    name: ClassVar[str] = "CryptoAnalysis"
    description: ClassVar[str] = "Analyze one or more cryptocurrencies for technical indicators, trends, and comparisons (such as volume, marketcap, SMA, RSI, etc.). Separate multiple assets with commas."
    
    def _run(self, tool_input: str) -> str:
        """Execute the crypto analysis tool."""
        logger.info(f"Starting analysis for: {tool_input}")
        
        try:
            crypto_list = [c.strip() for c in tool_input.split(',')]
            
            if len(crypto_list) == 1:
                result = self._single_asset_analysis(crypto_list[0])
            else:
                result = self._compare_assets(crypto_list)
                
            logger.info(f"Successfully analyzed crypto(s): {tool_input}")
            return True, result
                
        except Exception as e:
            logger.error(f"Error analyzing crypto: {str(e)}", exc_info=True)
            return False, f"Error analyzing crypto: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        """Async version of run - not implemented."""
        raise NotImplementedError("Async execution is not supported for the CryptoAnalysis tool.")

    def _single_asset_analysis(self, crypto: str) -> str:
        """Analyze a single cryptocurrency."""
        try:
            token_id = resolve_token_id(crypto)
            df = get_historical_data(token_id)
            df_market_data = get_high_level_market_data(token_id)
            
            analysis = self._calculate_indicators(df['price'])
            trend_analysis = self.get_trend_analysis(df['price'])
            current_price = df['price'].iloc[-1]

            # Format the comprehensive analysis
            return (
                f"Analysis for {crypto.upper()}:\n\n"
                f"Price Analysis:\n"
                f"Current Price: ${current_price:.8f}\n"
                f"Market Cap: ${df_market_data['market_cap']:,.2f}\n"
                f"24h Volume: ${df_market_data['volume_24h']:,.2f}\n"
                f"24h Change: {df_market_data['price_change_24h']:,.2f}%\n"
                f"Volatility: {analysis.get('volatility', 0):.2f}%\n\n"
                
                f"Moving Averages:\n"
                f"SMA (7 days): ${analysis['sma7']:.8f}\n"
                f"SMA (20 days): ${analysis['sma20']:.8f}\n"
                f"SMA (50 days): ${analysis['sma50']:.8f}\n"
                f"EMA (21 days): ${analysis['ema21']:.8f}\n\n"
                
                f"Technical Indicators:\n"
                f"RSI (14): {analysis['rsi']:.2f}\n"
                f"RSI Condition: {trend_analysis['rsi_condition']}\n"
                f"MACD: {analysis['macd']:.8f}\n"
                f"MACD Signal: {analysis['signal']:.8f}\n"
                f"MACD Trend: {trend_analysis['macd_signal']}\n\n"
                
                f"Bollinger Bands:\n"
                f"Upper Band: ${analysis['upper_bb']:.8f}\n"
                f"Middle Band: ${analysis['middle_bb']:.8f}\n"
                f"Lower Band: ${analysis['lower_bb']:.8f}\n"
                f"Price Position: {trend_analysis['price_position']}\n\n"
                
                f"Trend Analysis:\n"
                f"Overall Trend: {trend_analysis['trend']}\n"
                f"Trend Strength: {trend_analysis['strength']}\n"
            )
        
        except Exception as e:
            logger.error(f"Error analyzing {crypto}: {str(e)}", exc_info=True)
            return f"Error analyzing {crypto}: {str(e)}"

    def _compare_assets(self, assets: List[str]) -> str:
        """Compare multiple cryptocurrencies."""
        try:
            results = []
            dataframes = {}
            market_data = {}
            
            # Fetch data for all assets
            for asset in assets:
                try:
                    token_id = resolve_token_id(asset)
                    dataframes[asset] = get_historical_data(token_id)
                    market_data[asset] = get_high_level_market_data(token_id)
                except Exception as e:
                    logger.error(f"Error fetching data for {asset}: {str(e)}")
                    results.append(f"Could not analyze {asset}: {str(e)}")
                    continue

            comparisons = self._prepare_comparisons(dataframes, market_data)
            return self._format_comparison_results(comparisons, dataframes)

        except Exception as e:
            logger.error(f"Error comparing assets: {str(e)}", exc_info=True)
            return f"Error comparing assets: {str(e)}"
        
    def _format_comparison_results(self, comparisons: List[Dict], dataframes: Dict[str, pd.DataFrame]) -> str:
        """Format comparison results for multiple assets."""
        try:
            # Format comparison results
            comparison_text = "Comparative Analysis:\n\n"
            
            # Sort by market cap
            for comp in sorted(comparisons, key=lambda x: x['market_cap'], reverse=True):
                comparison_text += (
                    f"{comp['asset'].upper()}:\n"
                    f"Market Data:\n"
                    f"• Price: ${comp['price']:.8f}\n"
                    f"• Market Cap: ${comp['market_cap']:,.2f}\n"
                    f"• 24h Volume: ${comp['volume_24h']:,.2f}\n"
                    f"• 24h Change: {comp['change_24h']:.2f}%\n\n"
                    
                    f"Technical Analysis:\n"
                    f"• RSI: {comp['indicators'].get('rsi', 0):.2f} "
                    f"({comp['trend'].get('rsi_condition', 'Unknown')})\n"
                    f"• MACD: {comp['indicators'].get('macd', 0):.8f}\n"
                    f"• Overall Trend: {comp['trend'].get('trend', 'Unknown')}\n"
                    f"• Trend Strength: {comp['trend'].get('strength', 'Unknown')}\n"
                    f"------------------------\n\n"
                )
            
            # Add correlation analysis if there are multiple assets
            if len(dataframes) > 1:
                correlations = {}
                assets = list(dataframes.keys())
                for i in range(len(assets)):
                    for j in range(i + 1, len(assets)):
                        asset1, asset2 = assets[i], assets[j]
                        df1, df2 = dataframes[asset1], dataframes[asset2]
                        common_index = df1.index.intersection(df2.index)
                        correlation = df1.loc[common_index, 'price'].corr(df2.loc[common_index, 'price'])
                        correlations[(asset1, asset2)] = correlation
                        
                comparison_text += "\nCorrelations:\n"
                for (asset1, asset2), corr in correlations.items():
                    strength = (
                        "Strong Positive" if corr > 0.7 else
                        "Strong Negative" if corr < -0.7 else
                        "Moderate Positive" if corr > 0.3 else
                        "Moderate Negative" if corr < -0.3 else
                        "Weak"
                    )
                    comparison_text += f"{asset1.upper()} vs {asset2.upper()}: {corr:.2f} ({strength})\n"
            
            return comparison_text
            
        except Exception as e:
            logger.error(f"Error formatting comparison results: {str(e)}", exc_info=True)
            return f"Error formatting comparison results: {str(e)}"

    def _prepare_comparisons(self, dataframes: Dict[str, pd.DataFrame], 
                           market_data: Dict[str, Dict]) -> List[Dict]:
        """Prepare comparison data for multiple assets."""
        comparisons = []
        for asset, df in dataframes.items():
            try:
                analysis = self._calculate_indicators(df['price'])
                trend_analysis = self.get_trend_analysis(df['price'])
                current_price = df['price'].iloc[-1]
                asset_market_data = market_data[asset]
                
                comparisons.append({
                    'asset': asset,
                    'price': current_price,
                    'market_cap': asset_market_data['market_cap'],
                    'volume_24h': asset_market_data['volume_24h'],
                    'change_24h': asset_market_data['price_change_24h'],
                    'indicators': analysis,
                    'trend': trend_analysis
                })
            except Exception as e:
                logger.error(f"Error preparing comparison for {asset}: {str(e)}")
                continue
        
        return comparisons

    def _calculate_indicators(self, prices: pd.Series) -> Dict[str, float]:
        """Calculate technical indicators."""
        try:
            macd_val, signal_val = self.calculate_macd(prices)
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(prices)
            
            return {
                'sma7': self.calculate_sma(prices, 7),
                'sma20': self.calculate_sma(prices, 20),
                'sma50': self.calculate_sma(prices, 50),
                'ema21': self.calculate_ema(prices, 21),
                'rsi': self.calculate_rsi(prices),
                'macd': macd_val,
                'signal': signal_val,
                'upper_bb': upper_bb,
                'middle_bb': middle_bb,
                'lower_bb': lower_bb,
                'volatility': prices.pct_change().std() * np.sqrt(365) * 100
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return {}

    def calculate_sma(self, prices: pd.Series, window: int = 20) -> float:
        """Calculate Simple Moving Average."""
        try:
            if len(prices) < window:
                return 0.0
            prices = pd.to_numeric(prices, errors='coerce').dropna()
            return float(prices.tail(window).mean())
        except Exception as e:
            logger.error(f"Error calculating SMA: {str(e)}")
            return 0.0

    def calculate_ema(self, prices: pd.Series, window: int = 21) -> float:
        """Calculate Exponential Moving Average."""
        try:
            if len(prices) < window:
                return 0.0
            return float(prices.ewm(span=window, adjust=False).mean().iloc[-1])
        except Exception as e:
            logger.error(f"Error calculating EMA: {str(e)}")
            return 0.0

    def calculate_rsi(self, prices: pd.Series, window: int = 14) -> float:
        """Calculate Relative Strength Index."""
        try:
            if len(prices) < window + 1:
                return 50.0
            
            delta = prices.diff()
            gains = delta.clip(lower=0)
            losses = -delta.clip(upper=0)
            
            avg_gains = gains.ewm(com=window-1, adjust=False).mean()
            avg_losses = losses.ewm(com=window-1, adjust=False).mean()
            
            rs = avg_gains / avg_losses
            rsi = 100 - (100 / (1 + rs))
            
            return float(rsi.iloc[-1])
        except Exception as e:
            logger.error(f"Error calculating RSI: {str(e)}")
            return 50.0

    def calculate_macd(self, prices: pd.Series) -> Tuple[float, float]:
        """Calculate MACD and Signal line."""
        try:
            fast_ema = prices.ewm(span=12, adjust=False).mean()
            slow_ema = prices.ewm(span=26, adjust=False).mean()
            macd = fast_ema - slow_ema
            signal = macd.ewm(span=9, adjust=False).mean()
            
            return float(macd.iloc[-1]), float(signal.iloc[-1])
        except Exception as e:
            logger.error(f"Error calculating MACD: {str(e)}")
            return 0.0, 0.0

    def calculate_bollinger_bands(self, prices: pd.Series) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands."""
        try:
            window = 20
            sma = prices.rolling(window=window).mean()
            std = prices.rolling(window=window).std()
            
            upper = sma + (std * 2)
            lower = sma - (std * 2)
            
            return float(upper.iloc[-1]), float(sma.iloc[-1]), float(lower.iloc[-1])
        except Exception as e:
            logger.error(f"Error calculating Bollinger Bands: {str(e)}")
            return 0.0, 0.0, 0.0

    def get_trend_analysis(self, prices: pd.Series) -> Dict[str, str]:
        """Analyze price trends."""
        try:
            sma_7 = self.calculate_sma(prices, 7)
            sma_20 = self.calculate_sma(prices, 20)
            rsi = self.calculate_rsi(prices)
            macd, signal = self.calculate_macd(prices)
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(prices)
            
            current_price = prices.iloc[-1]
            
            return {
                "trend": "Bullish" if sma_7 > sma_20 else "Bearish",
                "strength": "Strong" if abs(sma_7 - sma_20) / sma_20 > 0.02 else "Weak",
                "rsi_condition": "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral",
                "macd_signal": "Bullish" if macd > signal else "Bearish",
                "price_position": self._get_price_position(current_price, upper_bb, lower_bb)
            }
        except Exception as e:
            logger.error(f"Error in trend analysis: {str(e)}")
            return {}

    def _get_price_position(self, price: float, upper: float, lower: float) -> str:
        """Determine price position relative to Bollinger Bands."""
        if price > upper:
            return "Above upper band"
        elif price < lower:
            return "Below lower band"
        return "Within bands"