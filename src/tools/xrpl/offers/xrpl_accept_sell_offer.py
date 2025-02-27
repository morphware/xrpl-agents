import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from ....config import Config
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenAcceptOffer
from xrpl import transaction as tx
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message
import uuid

class XRPLAcceptSellOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for accepting an NFT sell offer on the XRPL testnet.
    Input should be the offer index.
    """
    name: ClassVar[str] = "XRPLAcceptSellOffer"
    description: ClassVar[str] = (
        "Accept an NFT sell offer on the XRPL. "
        "Input should be the offer index. "
    )

    def _run(self, tool_input: str) -> str:
        try:
            offer_index = tool_input.strip()
            
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            accept_offer_tx = NFTokenAcceptOffer(
                account=Config.XRP_WALLET.address,
                nftoken_sell_offer=offer_index
            )

            try:
                accept_offer_req = accept_offer_tx.to_xrpl()
                message_id = str(uuid.uuid4())
                send_to_kafka(
                    producer=Config.kafka_out,
                    topic=Config.KAFKA_TX_TOPIC + "_IN",
                    message=accept_offer_req,
                    key=Config.REQUEST_ID
                )
                response, key = get_kafka_latest_message(
                    Config.consume_from_kafka(Config.kafka_tx, Config.KAFKA_TX_TOPIC + "_OUT"),
                    message_id=message_id
                )
                if isinstance(response, Exception):
                    return False, f"Error processing message: {str(response)}"
                if "Successful" in response:
                    return True, f"Accept sell offer successful - nftoken sell offer: {offer_index}"
                else:
                    return False, f"Accept sell offer failed: {response}"
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Submit failed: {e}"
        except Exception as e:
            return False, f"Error accepting sell offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAcceptSellOfferTool.")

if __name__ == "__main__":
    # Example usage:
    tool = XRPLAcceptSellOfferTool()
    example_input = ""  # Replace with a real offer index
    result = tool._run(example_input)
    print(result)