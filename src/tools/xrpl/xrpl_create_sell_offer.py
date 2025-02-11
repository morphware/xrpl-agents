import os
import sys
from datetime import datetime
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenCreateOffer
from xrpl import transaction as tx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from base import BaseCustomTool

import xrpl.utils


class XRPLCreateSellOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for creating an NFT sell offer on the XRPL testnet.
    Input should be a comma-separated string:
        "amount, nftoken_id, expiration_seconds, destination"
    The seller's secret is taken from the environment variable:
        XRPL_WALLET_SECRET.
    If expiration or destination are empty strings, they will be ignored.
    """
    name: ClassVar[str] = "XRPLCreateSellOffer"
    description: ClassVar[str] = (
        "Create an NFT sell offer on the XRPL. "
        "Input should be in the format 'amount, nftoken_id, expiration_seconds, destination'. "
        "The seller's secret is taken from XRPL_WALLET_SECRET environment variable. "
        "If expiration_seconds or destination are empty, they will be treated as not set."
    )

    def _run(self, tool_input: str) -> str:
        try:
            parts = tool_input.split(",")
            if len(parts) != 4:
                return ("Input must be in the format 'amount, nftoken_id, expiration_seconds, destination'. "
                        "For no expiration or destination, pass an empty string for those fields.")
            
            amount = parts[0].strip()
            nftoken_id = parts[1].strip()
            expiration = parts[2].strip()
            destination = parts[3].strip()
            
            seller_secret = os.getenv("XRPL_WALLET_SECRET")
            if not seller_secret:
                return "Seller credentials not set. Please set XRPL_WALLET_SECRET in your environment."
            
            wallet = Wallet.from_seed(seller_secret)
            client = JsonRpcClient("https://s.altnet.rippletest.net:51234")

            # Prepare expiration if provided
            expiration_value = None
            if expiration != "":
                current_time = datetime.now()
                ripple_time = xrpl.utils.datetime_to_ripple_time(current_time)
                expiration_value = ripple_time + int(expiration)

            # Set destination to None if empty
            destination_value = destination if destination != "" else None

            sell_offer_tx = NFTokenCreateOffer(
                account=wallet.address,
                nftoken_id=nftoken_id,
                amount=amount,
                destination=destination_value,
                expiration=expiration_value,
                flags=1
            )

            try:
                response = tx.submit_and_wait(sell_offer_tx, client, wallet)
                return str(response.result)
            except tx.XRPLReliableSubmissionException as e:
                return f"Submit failed: {e}"
        except Exception as e:
            return f"Error creating sell offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCreateSellOfferTool.")

if __name__ == "__main__":
    # Example usage:
    # Set XRPL_WALLET_SECRET env variable before running.
    # Input format: "amount, nftoken_id, expiration_seconds, destination"
    tool = XRPLCreateSellOfferTool()
    example_input = "1000000, 1234567890ABCDEF, 3600, rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"
    result = tool._run(example_input)
    print(result)