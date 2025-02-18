from typing import ClassVar
from langchain.tools import BaseTool
from ...config import Config
from ..base import BaseCustomTool
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import BookOffers
import os
import sys

class XRPLTokenPriceTool(BaseCustomTool, BaseTool):
    """
    Tool for getting the current price of a token on the XRPL chain.
    Provide the token code and issuer as a comma-separated string, e.g.:
        "TOKEN, rXXXX...XYZ"
    The tool queries the XRP order book for offers selling the token for XRP and returns
    an approximate price in XRP per token.
    """
    name: ClassVar[str] = "XRPLTokenPrice"
    description: ClassVar[str] = (
        "Get the current price of a token on the XRPL chain. "
        "Input should be in the format 'TOKEN, rIssuerAddress'."
    )

    def _run(self, tool_input: str) -> str:
        try:
            parts = tool_input.split(",")
            if len(parts) != 2:
                return "Input must be in the format 'TOKEN, rIssuerAddress'."
            token_code = parts[0].strip().upper()
            issuer = parts[1].strip()
            # Connect to the XRPL mainnet
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Build order book request:
            # Get offers where taker_gets is XRP and taker_pays is the token.
            request = BookOffers(
                taker_gets={"currency": "XRP"},
                taker_pays={"currency": token_code, "issuer": issuer},
                limit=10
            )
            response = client.request(request)
            offers = response.result.get("offers", [])
            if not offers:
                return f"No order book offers found for {token_code} issued by {issuer}."

            # Use the best (first) offer from the order book.
            best_offer = offers[0]

            # In XRPL, XRP is represented in drops.
            # "taker_gets" is usually a string representing drops of XRP.
            taker_gets = best_offer.get("taker_gets")
            # "taker_pays" is usually a dict with a "value" field.
            taker_pays = best_offer.get("taker_pays")

            # Convert XRP drops to XRP
            try:
                # If taker_gets is a numeric string (drops)
                xrp_amount = float(taker_gets) / 1_000_000
            except Exception:
                # If it is a dict, try to get the value directly.
                xrp_amount = float(taker_gets.get("value", 0))

            token_amount = float(taker_pays.get("value", 0)) if isinstance(taker_pays, dict) else float(taker_pays)
            if token_amount == 0:
                return True, f"Token amount is zero in the best offer for {token_code}."

            # Calculate price as XRP per token
            price = xrp_amount / token_amount

            return True, f"The current price for {token_code} is approximately {price:.6f} XRP per token."
        except Exception as e:
            return False, f"Error retrieving token price: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLTokenPriceTool.")
    
if __name__ == "__main__":
    # Example usage:
    tool = XRPLTokenPriceTool()
    # Replace with a valid token code and issuer address.
    user_input = "PHNIX, rDFXbW2ZZCG5WgPtqwNiA2xZokLMm9ivmN"
    result = tool._run(user_input)
    print(result)
