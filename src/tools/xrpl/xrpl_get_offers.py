import os
import sys
import json
from typing import ClassVar
from langchain.tools import BaseTool
from ...config import Config
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import NFTBuyOffers, NFTSellOffers
from ..base import BaseCustomTool

class XRPLGetOffersTool(BaseCustomTool, BaseTool):
    """
    Tool for getting buy and sell offers for an NFT on the XRPL testnet.
    Input should be the NFT ID.
    """
    name: ClassVar[str] = "XRPLGetOffers"
    description: ClassVar[str] = (
        "Get buy and sell offers for an NFT on the XRPL. "
        "Input should be the NFT ID."
    )

    def _run(self, tool_input: str) -> str:
        try:
            nft_id = tool_input.strip()
            client = JsonRpcClient("https://s.altnet.rippletest.net:51234")

            # Get buy offers
            buy_offers_request = NFTBuyOffers(nft_id=nft_id)
            buy_offers_response = client.request(buy_offers_request)
            buy_offers_json = json.dumps(buy_offers_response.result, indent=4)
            buy_offers_str = "Buy Offers:\n" + buy_offers_json

            # Get sell offers
            sell_offers_request = NFTSellOffers(nft_id=nft_id)
            sell_offers_response = client.request(sell_offers_request)
            sell_offers_json = json.dumps(sell_offers_response.result, indent=4)
            sell_offers_str = "\n\nSell Offers:\n" + sell_offers_json

            all_offers = buy_offers_str + sell_offers_str
            return all_offers
        except Exception as e:
            return f"Error getting offers: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLGetOffersTool.")

if __name__ == "__main__":
    # Example usage:
    tool = XRPLGetOffersTool()
    example_input = ""  # Replace with a real NFT ID
    result = tool._run(example_input)
    print(result)