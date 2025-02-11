import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenAcceptOffer
from xrpl import transaction as tx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from base import BaseCustomTool

class XRPLAcceptSellOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for accepting an NFT sell offer on the XRPL testnet.
    Input should be the offer index.
    The buyer's secret is taken from the environment variable:
        XRPL_WALLET_SECRET.
    """
    name: ClassVar[str] = "XRPLAcceptSellOffer"
    description: ClassVar[str] = (
        "Accept an NFT sell offer on the XRPL. "
        "Input should be the offer index. "
        "The buyer's secret is taken from XRPL_WALLET_SECRET environment variable."
    )

    def _run(self, tool_input: str) -> str:
        try:
            offer_index = tool_input.strip()
            
            buyer_secret = os.getenv("XRPL_WALLET_SECRET")
            if not buyer_secret:
                return "Buyer credentials not set. Please set XRPL_WALLET_SECRET in your environment."
            
            wallet = Wallet.from_seed(buyer_secret)
            client = JsonRpcClient("https://s.altnet.rippletest.net:51234")

            accept_offer_tx = NFTokenAcceptOffer(
                account=wallet.address,
                nftoken_sell_offer=offer_index
            )

            try:
                response = tx.submit_and_wait(accept_offer_tx, client, wallet)
                return str(response.result)
            except tx.XRPLReliableSubmissionException as e:
                return f"Submit failed: {e}"
        except Exception as e:
            return f"Error accepting sell offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAcceptSellOfferTool.")

if __name__ == "__main__":
    # Example usage:
    # Set XRPL_WALLET_SECRET env variable before running.
    tool = XRPLAcceptSellOfferTool()
    example_input = ""  # Replace with a real offer index
    result = tool._run(example_input)
    print(result)