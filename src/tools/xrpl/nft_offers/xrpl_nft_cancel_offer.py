import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenCancelOffer
from xrpl import transaction as tx
from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message
import uuid, json

class XRPLNFTCancelOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for canceling an NFT offer on the XRPL testnet.
    Input should be the offer ID.
    """
    name: ClassVar[str] = "XRPLNFTCancelOffer"
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
                tx_id = str(uuid.uuid4())
                # Create XrpTransactionRequest object with attributes
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": cancel_offer_tx.blob()
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
                    return True, f"Cancel offer successful - offer id: {offer_id}"
                else:
                    return False, f"Cancel offer failed: {response}"
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Submit failed: {e}"
        except Exception as e:
            return False, f"Error canceling offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCancelOfferTool.")

if __name__ == "__main__":
    # Example usage:
    tool = XRPLNFTCancelOfferTool()
    example_input = ""  # Replace with a real offer index
    result = tool._run(example_input)
    print(result)