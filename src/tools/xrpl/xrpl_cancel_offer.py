import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenCancelOffer
from xrpl import transaction as tx
from ...config import Config
from ..base import BaseCustomTool

class XRPLCancelOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for canceling an NFT offer on the XRPL testnet.
    Input should be the offer ID.
    """
    name: ClassVar[str] = "XRPLCancelOffer"
    description: ClassVar[str] = (
        "Cancel an NFT offer on the XRPL. "
        "Input should be the offer ID. "
    )

    def _run(self, tool_input: str) -> str:
        try:
            offer_id = tool_input.strip()
            
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            cancel_offer_tx = NFTokenCancelOffer(
                account=Config.XRP_WALLET.address,
                nftoken_offers=[offer_id]
            )

            try:
                response = tx.submit_and_wait(cancel_offer_tx, client, Config.XRP_WALLET.address)
                return str(response.result)
            except tx.XRPLReliableSubmissionException as e:
                return f"Submit failed: {e}"
        except Exception as e:
            return f"Error canceling offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCancelOfferTool.")

if __name__ == "__main__":
    # Example usage:
    tool = XRPLCancelOfferTool()
    example_input = ""  # Replace with a real offer index
    result = tool._run(example_input)
    print(result)