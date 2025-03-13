from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountOffers
from ....config import Config
from ...base import BaseCustomTool

class XRPLGetAccountOffersTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving the active offers created by an XRPL account.
    Input should be a valid XRPL account address.
    """
    name: ClassVar[str] = "XRPLGetAccountOffers"
    description: ClassVar[str] = (
        "Retrieve all active offers (buy and sell) created by an XRPL account. "
        "Input should be a valid XRPL wallet address. "
        "If the input is for user's address, input 'user_account_address'."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
        
    def _format_offer(self, offer: dict) -> str:
        """Format an offer for human-readable output."""
        offer_seq = offer.get("seq", "Unknown")
        flags = offer.get("flags", 0)
        
        # Determine offer direction
        is_sell = (flags & 0x80000000) != 0
        direction = "SELL" if is_sell else "BUY"
        
        # Format what the account wants to get
        taker_gets = offer.get("taker_gets", {})
        if isinstance(taker_gets, dict):
            gets_value = taker_gets.get("value", "Unknown")
            gets_currency = taker_gets.get("currency", "Unknown")
            gets_issuer = taker_gets.get("issuer", "")
            gets_str = f"{gets_value} {gets_currency}"
            if gets_issuer:
                gets_str += f" (Issuer: {gets_issuer})"
        else:
            # If taker_gets is not a dict, it's XRP in drops
            gets_value = float(taker_gets) / 1_000_000 if taker_gets else "Unknown"
            gets_str = f"{gets_value} XRP"
            
        # Format what the account wants to give
        taker_pays = offer.get("taker_pays", {})
        if isinstance(taker_pays, dict):
            pays_value = taker_pays.get("value", "Unknown")
            pays_currency = taker_pays.get("currency", "Unknown")
            pays_issuer = taker_pays.get("issuer", "")
            pays_str = f"{pays_value} {pays_currency}"
            if pays_issuer:
                pays_str += f" (Issuer: {pays_issuer})"
        else:
            # If taker_pays is not a dict, it's XRP in drops
            pays_value = float(taker_pays) / 1_000_000 if taker_pays else "Unknown"
            pays_str = f"{pays_value} XRP"
            
        # Calculate exchange rate
        try:
            if isinstance(taker_gets, dict) and isinstance(taker_pays, dict):
                rate = float(pays_value) / float(gets_value)
                rate_str = f"Rate: {rate:.6f} {pays_currency}/{gets_currency}"
            elif isinstance(taker_gets, dict):
                rate = float(taker_pays) / (float(gets_value) * 1_000_000)
                rate_str = f"Rate: {rate:.6f} XRP/{gets_currency}"
            elif isinstance(taker_pays, dict):
                rate = float(pays_value) / (float(taker_gets) / 1_000_000)
                rate_str = f"Rate: {rate:.6f} {pays_currency}/XRP"
            else:
                rate_str = "Rate: N/A"
        except (ValueError, ZeroDivisionError):
            rate_str = "Rate: N/A"
        
        return (
            f"Offer #{offer_seq} - {direction}\n"
            f"Giving: {pays_str}\n"
            f"Getting: {gets_str}\n"
            f"{rate_str}\n"
        )

    def _run(self, tool_input: str) -> str:
        try:
            # Clean the input
            address = tool_input.strip()
            if "user_account_address" in address.lower():
                address = Config.XRP_WALLET.address

            # Validate address format
            if not self._validate_address(address):
                return False, f"Invalid XRPL address format: {address}"

            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Create and send request
            request = AccountOffers(
                account=address,
                ledger_index="validated",
                strict=True
            )
            response = client.request(request)

            # Extract offers from response
            offers = response.result.get("offers", [])
            
            if not offers:
                return True, f"No active offers found for account {address}."

            # Format each offer for human-readable output
            formatted_offers = [self._format_offer(offer) for offer in offers]
            offers_text = "\n".join(formatted_offers)
            
            return True, f"Active offers for account {address}:\n\n{offers_text}"

        except Exception as e:
            return False, f"Error retrieving account offers: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLGetAccountOffersTool.")


if __name__ == "__main__":
    # Example usage
    tool = XRPLGetAccountOffersTool()
    example_input = "rExampleWalletAddress1234567890"  # Replace with real address
    result = tool._run(example_input)
    print(result)