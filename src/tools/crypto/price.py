from typing import ClassVar
from ...exceptions import CryptoToolError
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from .utils import make_coingecko_request, resolve_token_id
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/crypto_price.log')

class CryptoPriceTool(BaseCustomTool, BaseTool):
    """Tool for getting cryptocurrency prices."""
    name: ClassVar[str] = "CryptoPrice"
    description: ClassVar[str] = "Get the current price of one or more cryptocurrencies. Use full names like 'bitcoin' or 'ethereum'. For multiple assets, separate with commas."
    
    def _run(self, tool_input: str) -> str:
        """Execute the crypto price tool."""
        logger.info(f"Getting crypto price for input: {tool_input}")
        
        try:
            # Handle multiple assets
            crypto_list = [c.strip() for c in tool_input.split(',')]
            results = []
            
            for crypto in crypto_list:
                try:
                    price = self._get_single_price(crypto)
                    results.append(f"{crypto}: {price}")
                except Exception as e:
                    logger.error(f"Error processing {crypto}: {str(e)}", exc_info=True)
                    results.append(f"{crypto}: Error - {str(e)}")
            
            # Format response based on number of results
            if len(results) == 1:
                return results[0]
            return "\n".join(results)
            
        except Exception as e:
            logger.error(f"Error getting crypto price: {str(e)}", exc_info=True)
            return f"Error getting crypto price: {str(e)}"
    
    def _get_single_price(self, crypto: str) -> str:
        """Get price for a single cryptocurrency."""
        try:
            # Try direct lookup first
            data = make_coingecko_request(
                "simple/price",
                {
                    "ids": crypto.lower(),
                    "vs_currencies": "usd"
                }
            )
            
            if crypto.lower() in data:
                price = data[crypto.lower()]["usd"]
                logger.info(f"Direct lookup successful for {crypto}: ${price}")
                return f"${price:,.2f} USD"
            
            # If direct lookup fails, try to resolve the token ID
            logger.info(f"Direct lookup failed for {crypto}, attempting resolution")
            token_id = resolve_token_id(crypto)
            
            if isinstance(token_id, str) and (
                token_id.startswith("Could not find") or 
                token_id.startswith("Error")
            ):
                logger.warning(f"Could not resolve token ID for {crypto}")
                return f"Could not find price data for {crypto}"
            
            # Retry with resolved ID
            data = make_coingecko_request(
                "simple/price",
                {
                    "ids": token_id,
                    "vs_currencies": "usd"
                }
            )
            
            price = data[token_id]["usd"]
            logger.info(f"Resolved lookup successful for {crypto} ({token_id}): ${price}")
            return f"${price:,.2f} USD"
            
        except Exception as e:
            logger.error(f"Error getting price for {crypto}: {str(e)}")
            return f"Error getting price for {crypto}: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        """Async version of run - not implemented."""
        raise NotImplementedError("Async execution is not supported for the CryptoPrice tool.")