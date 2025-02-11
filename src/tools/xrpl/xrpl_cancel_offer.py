import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenCancelOffer
from xrpl import transaction as tx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from base import BaseCustomTool

class XRPLCancelOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for canceling an NFT offer on the XRPL testnet.
    Input should be the offer ID.
    The wallet secret is taken from the environment variable:
        XRPL_WALLET_SECRET.
    """
    name: ClassVar[str] = "XRPLCancelOffer"
    description: ClassVar[str] = (
        "Cancel an NFT offer on the XRPL. "
        "Input should be the offer ID. "
        "The wallet secret is taken from XRPL_WALLET_SECRET environment variable."
    )

    def _run(self, tool_input: str) -> str:
        try:
            offer_id = tool_input.strip()
            
            wallet_secret = os.getenv("XRPL_WALLET_SECRET")
            if not wallet_secret:
                return "Wallet credentials not set. Please set XRPL_WALLET_SECRET in your environment."
            
            wallet = Wallet.from_seed(wallet_secret)
            client = JsonRpcClient("https://s.altnet.rippletest.net:51234")

            cancel_offer_tx = NFTokenCancelOffer(
                account=wallet.address,
                nftoken_offers=[offer_id]
            )

            try:
                response = tx.submit_and_wait(cancel_offer_tx, client, wallet)
                return str(response.result)
            except tx.XRPLReliableSubmissionException as e:
                return f"Submit failed: {e}"
        except Exception as e:
            return f"Error canceling offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCancelOfferTool.")

if __name__ == "__main__":
    # Example usage:
    # Set XRPL_WALLET_SECRET env variable before running.
    tool = XRPLCancelOfferTool()
    example_input = ""  # Replace with a real offer index
    result = tool._run(example_input)
    print(result)