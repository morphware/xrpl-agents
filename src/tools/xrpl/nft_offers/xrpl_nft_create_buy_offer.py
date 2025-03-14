import os
import sys
from datetime import datetime
from typing import ClassVar
from langchain.tools import BaseTool
from ....config import Config
from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet
from xrpl.models.transactions import NFTokenCreateOffer
from xrpl import transaction as tx
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message
import uuid, json

import xrpl.utils


class XRPLNFTCreateBuyOfferTool(BaseCustomTool, BaseTool):
    """
    Tool for creating an NFT buy offer on the XRPL testnet.
    Input should be a comma-separated string:
        "amount, nftoken_id, owner, expiration_seconds, destination"
    If expiration or destination are empty strings, they will be ignored.
    """
    name: ClassVar[str] = "XRPLNFTCreateBuyOffer"
    description: ClassVar[str] = (
        "Create an NFT buy offer on the XRPL. "
        "Input should be in the format 'amount, nftoken_id, owner, expiration_seconds, destination'. "
        "If expiration_seconds or destination are empty, they will be treated as not set."
    )

    def _run(self, tool_input: str) -> str:
        try:
            parts = tool_input.split(",")
            if len(parts) != 5:
                return ("Input must be in the format 'amount, nftoken_id, owner, expiration_seconds, destination'. "
                        "For no expiration or destination, pass an empty string for those fields.")
            
            amount = parts[0].strip()
            nftoken_id = parts[1].strip()
            owner = parts[2].strip()
            expiration = parts[3].strip()
            destination = parts[4].strip()
            
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Prepare expiration if provided
            expiration_value = None
            if expiration != "":
                current_time = datetime.now()
                ripple_time = xrpl.utils.datetime_to_ripple_time(current_time)
                expiration_value = ripple_time + int(expiration)

            # Set destination to None if empty
            destination_value = destination if destination != "" else None

            buy_offer_tx = NFTokenCreateOffer(
                account=Config.XRP_WALLET.address,
                nftoken_id=nftoken_id,
                amount=amount,
                owner=owner,
                expiration=expiration_value,
                destination=destination_value,
                flags=0
            )

            try:
                tx_id = str(uuid.uuid4())
                # Create XrpTransactionRequest object with attributes
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "transaction": buy_offer_tx.blob()
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
                    response = (
                        f"Buy Offer created successfully - nftoken id: {nftoken_id}, amount: {amount}, "
                        f"owner: {owner}, destination: {destination}, expiration: {expiration}"
                    )
                    return True, response
                else:
                    response = f"Create Buy Offer failed: {response}"
                    return False, response
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Submit failed: {e}"
        except Exception as e:
            return False, f"Error creating buy offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCreateBuyOfferTool.")

if __name__ == "__main__":
    # Example usage:
    # Input format: "amount, nftoken_id, owner, expiration_seconds, destination"
    tool = XRPLNFTCreateBuyOfferTool()
    example_input = "1000000, 1234567890ABCDEF, rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 3600, rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"
    result = tool._run(example_input)
    print(result)