from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import BookOffers
from ....config import Config
from ...base import BaseCustomTool

class XRPLGetBookOffersTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving the order book offers between two currencies on the XRPL.
    Input should be in the format: 
    'gets_currency,gets_issuer,pays_currency,pays_issuer,limit'
    
    - For XRP, use 'XRP' as currency and leave issuer empty
    - For other currencies, provide both currency code and issuer address
    - Limit is optional (default is 10)
    
    Example: 'XRP,USD,rXXXXXXXXXXXXXXXXXXXXX,20'
    """
    name: ClassVar[str] = "XRPLGetBookOffers"
    description: ClassVar[str] = (
        "Retrieve order book offers between two currencies on the XRPL. "
        "Input format: 'gets_currency,gets_issuer,pays_currency,pays_issuer,limit'. "
        "For XRP, use 'XRP' as currency and leave issuer empty. "
        "Limit is optional (defaults to 10)."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        if not address:  # Empty string is valid for XRP
            return True
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
    
    def _format_amount(self, amount) -> str:
        """Format an amount object or XRP drops to a readable string."""
        if isinstance(amount, dict):
            value = amount.get("value", "Unknown")
            currency = amount.get("currency", "Unknown")
            issuer = amount.get("issuer", "")
            
            result = f"{value} {currency}"
            if issuer:
                result += f" (Issuer: {issuer})"
            return result
        else:
            # Handle XRP amount in drops
            try:
                xrp_amount = float(amount) / 1_000_000
                return f"{xrp_amount} XRP"
            except (ValueError, TypeError):
                return f"{amount} drops"
    
    def _format_offer(self, offer: dict, index: int) -> str:
        """Format an offer for human-readable output."""
        account = offer.get("Account", "Unknown")
        sequence = offer.get("Sequence", "Unknown")
        quality = offer.get("quality", "Unknown")
        flags = offer.get("Flags", 0)
        
        # Get amounts
        taker_gets = offer.get("TakerGets", {})
        taker_pays = offer.get("TakerPays", {})
        
        gets_str = self._format_amount(taker_gets)
        pays_str = self._format_amount(taker_pays)
        
        # Calculate price
        try:
            if isinstance(taker_gets, dict) and isinstance(taker_pays, dict):
                price = float(taker_pays["value"]) / float(taker_gets["value"])
            elif isinstance(taker_gets, dict):
                # TakerGets is a token, TakerPays is XRP
                price = float(taker_pays) / (float(taker_gets["value"]) * 1_000_000)
            elif isinstance(taker_pays, dict):
                # TakerGets is XRP, TakerPays is a token
                price = float(taker_pays["value"]) / (float(taker_gets) / 1_000_000)
            else:
                # Both are XRP (uncommon)
                price = float(taker_pays) / float(taker_gets)
            price_str = f"Price: {price:.6f}"
        except (ValueError, ZeroDivisionError, TypeError, KeyError):
            price_str = "Price: Unknown"
        
        return (
            f"Offer #{index+1} (Seq: {sequence})\n"
            f"Account: {account}\n"
            f"Giving: {pays_str}\n"
            f"Getting: {gets_str}\n"
            f"{price_str}\n"
            f"Quality: {quality}\n"
        )

    def _run(self, tool_input: str) -> str:
        try:
            # Parse input
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) < 4:
                return False, "Input must have at least 4 parts: gets_currency, gets_issuer, pays_currency, pays_issuer"
            
            gets_currency = parts[0]
            gets_issuer = parts[1]
            pays_currency = parts[2]
            pays_issuer = parts[3]
            
            # Set default limit
            limit = 10
            if len(parts) > 4 and parts[4]:
                try:
                    limit = int(parts[4])
                    if limit < 1:
                        limit = 10
                    elif limit > 400:
                        limit = 400  # XRPL has a maximum limit
                except ValueError:
                    pass  # Use default limit
            
            # Validate currency pairs
            if not gets_currency or not pays_currency:
                return False, "Both currencies must be specified"
            
            # Validate addresses if not XRP
            if gets_currency != "XRP" and not self._validate_address(gets_issuer):
                return False, f"Invalid issuer address for {gets_currency}: {gets_issuer}"
            if pays_currency != "XRP" and not self._validate_address(pays_issuer):
                return False, f"Invalid issuer address for {pays_currency}: {pays_issuer}"
            
            # Set up taker_gets and taker_pays based on currency type
            taker_gets = {"currency": gets_currency}
            if gets_currency != "XRP":
                taker_gets["issuer"] = gets_issuer
            else:
                taker_gets = "XRP"
                
            taker_pays = {"currency": pays_currency}
            if pays_currency != "XRP":
                taker_pays["issuer"] = pays_issuer
            else:
                taker_pays = "XRP"
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create and send request
            request = BookOffers(
                taker_gets=taker_gets,
                taker_pays=taker_pays,
                limit=limit,
                ledger_index="validated"
            )
            
            response = client.request(request)
            offers = response.result.get("offers", [])
            
            if not offers:
                return True, f"No offers found for {gets_currency}/{pays_currency} pair."
            
            # Format each offer for human-readable output
            formatted_offers = [self._format_offer(offer, i) for i, offer in enumerate(offers)]
            offers_text = "\n".join(formatted_offers)
            
            pair_description = f"{gets_currency}"
            if gets_currency != "XRP" and gets_issuer:
                pair_description += f"/{gets_issuer}"
            
            pair_description += f" → {pays_currency}"
            if pays_currency != "XRP" and pays_issuer:
                pair_description += f"/{pays_issuer}"
            
            return True, f"Order book offers for {pair_description}:\n\n{offers_text}"
            
        except Exception as e:
            return False, f"Error retrieving book offers: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLGetBookOffersTool.")


if __name__ == "__main__":
    # Example usage
    tool = XRPLGetBookOffersTool()
    # Example input: 'XRP,USD,rXXXXXXXXXXXXXXXXXXXXX,10'
    example_input = "XRP,USD,rQUkzQ9EM3FpvMLheX674qLr1XFstZdEAh,10"
    result = tool._run(example_input)
    print(result)