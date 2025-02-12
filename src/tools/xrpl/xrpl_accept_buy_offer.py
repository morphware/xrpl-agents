import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from ...config import Config
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenAcceptOffer
from xrpl import transaction as tx
from ..base import BaseCustomTool

class XRPLAcceptBuyOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for accepting an NFT buy offer on the XRPL testnet.
    Input should be the offer index.
    """
    name: ClassVar[str] = "XRPLAcceptBuyOffer"
    description: ClassVar[str] = (
        "Accept an NFT buy offer on the XRPL. "
        "Input should be the offer index. "
    )

    def _run(self, tool_input: str) -> str:
        try:
            offer_index = tool_input.strip()
            
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            accept_offer_tx = NFTokenAcceptOffer(
                account=Config.XRP_WALLET.address,
                nftoken_buy_offer=offer_index
            )

            try:
                response = tx.submit_and_wait(accept_offer_tx, client, Config.XRP_WALLET)
                return str(response.result)
            except tx.XRPLReliableSubmissionException as e:
                return f"Submit failed: {e}"
        except Exception as e:
            return f"Error accepting buy offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAcceptBuyOfferTool.")

if __name__ == "__main__":
    # Example usage:
    tool = XRPLAcceptBuyOfferTool()
    example_input = ""  # Replace with a real offer index
    result = tool._run(example_input)
    print(result)