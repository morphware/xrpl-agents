import os
import sys
from datetime import datetime
from typing import ClassVar
from langchain.tools import BaseTool
from ...config import Config
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenCreateOffer
from xrpl import transaction as tx
from ..base import BaseCustomTool

import xrpl.utils


class XRPLCreateSellOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for creating an NFT sell offer on the XRPL testnet.
    Input should be a comma-separated string:
        "amount, nftoken_id, expiration_seconds, destination"
    If expiration or destination are empty strings, they will be ignored.
    """
    name: ClassVar[str] = "XRPLCreateSellOffer"
    description: ClassVar[str] = (
        "Create an NFT sell offer on the XRPL. "
        "Input should be in the format 'amount, nftoken_id, expiration_seconds, destination'. "
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
            
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Prepare expiration if provided
            expiration_value = None
            if expiration != "":
                current_time = datetime.now()
                ripple_time = xrpl.utils.datetime_to_ripple_time(current_time)
                expiration_value = ripple_time + int(expiration)

            # Set destination to None if empty
            destination_value = destination if destination != "" else None

            sell_offer_tx = NFTokenCreateOffer(
                account=Config.XRP_WALLET.address,
                nftoken_id=nftoken_id,
                amount=amount,
                destination=destination_value,
                expiration=expiration_value,
                flags=1
            )

            try:
                response = tx.submit_and_wait(sell_offer_tx, client, Config.XRP_WALLET)
                return str(response.result)
            except tx.XRPLReliableSubmissionException as e:
                return f"Submit failed: {e}"
        except Exception as e:
            return f"Error creating sell offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCreateSellOfferTool.")

if __name__ == "__main__":
    # Example usage:
    # Input format: "amount, nftoken_id, expiration_seconds, destination"
    tool = XRPLCreateSellOfferTool()
    example_input = "1000000, 1234567890ABCDEF, 3600, rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"
    result = tool._run(example_input)
    print(result)