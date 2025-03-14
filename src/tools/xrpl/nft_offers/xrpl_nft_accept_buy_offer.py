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
import uuid, json

class XRPLNFTAcceptBuyOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for accepting an NFT buy offer on the XRPL testnet.
    Input should be the offer index.
    """
    name: ClassVar[str] = "XRPLNFTAcceptBuyOffer"
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
                tx_id = str(uuid.uuid4())
                # Create XrpTransactionRequest object with attributes
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "transaction": accept_offer_tx.blob()
                    }
                )
                send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, message=payload, key=Config.REQUEST_ID, msg_type='tx_send_xrp')
                match = False
                while not match:
                    response, key = get_kafka_latest_message(Config.consume_from_kafka(Config.kafka_in, Config.KAFKA_IN_TOPIC) ,message_id=Config.REQUEST_ID)
                    if tx_id == response.tx_id:
                        match = True
                    else:    
                        match = False
                if isinstance(response, Exception):
                    return False, f"Error processing message: {str(response)}"
                if "SUCCESS" in response.tx_status:
                    return True, f"Accept buy offer successful - nftoken buy offer: {offer_index}"
                else:
                    return False, f"Accept buy offer failed: {response}"
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Submit failed: {e}"
        except Exception as e:
            return False, f"Error accepting buy offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAcceptBuyOfferTool.")

if __name__ == "__main__":
    # Example usage:
    tool = XRPLNFTAcceptBuyOfferTool()
    example_input = ""  # Replace with a real offer index
    result = tool._run(example_input)
    print(result)