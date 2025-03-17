import os
import sys
import json
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import Payment
from xrpl import transaction as tx
from xrpl.wallet import Wallet
from ...base import BaseCustomTool
from ....config import Config
from ....utils.kafka import send_to_kafka, get_kafka_messages, get_kafka_latest_message
from ....utils.types import XrpTransactionRequest
import time, uuid

class XRPLSendXrpTool(BaseCustomTool, BaseTool):
    """
    Tool for sending XRP tokens on the XRPL chain.
    Input should be a comma-separated string:
        "destination_address, amount_in_XRP"
    """
    name: ClassVar[str] = "XRPLSendXRP"
    description: ClassVar[str] = (
        "Send XRP tokens on the XRPL chain. "
        "Input should be in the format 'destination_address, amount_in_XRP'. "
    )

    def _run(self, tool_input: str) -> str:
        try:
            parts = tool_input.split(",")
            if len(parts) != 2:
                return "Input must be in the format 'destination_address, amount_in_XRP'."
            
            destination = parts[0].strip()
            try:
                amount_xrp = float(parts[1].strip())
            except ValueError:
                return "Amount must be a numeric value."

            # Convert amount from XRP to drops (1 XRP = 1,000,000 drops)
            amount_drops = str(int(amount_xrp * 1_000_000))

            # Connect to the XRPL mainnet
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Create Payment transaction
            payment = Payment(
                account=Config.XRP_WALLET.address,
                destination=destination,
                amount=amount_drops
            )
            tx_id = str(uuid.uuid4())
            # Create XrpTransactionRequest object with attributes
            payload = json.dumps(
                {
                    "msg_type": "tx_send_xrp",
                    "tx_id": tx_id,
                    "raw_tx": payment.blob()
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
                response = f"Transaction Successfull: sent {amount_xrp} XRP to {destination} " # at time {output.result['close_time_iso']} , transaction hash: {output.result['hash']}"
                return True, response
            else:
                response = f"Transaction Failed: {response}"
                return False, response
        except Exception as e:
            return False, f"Error sending XRP: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLSendXRPTool.")

if __name__ == "__main__":
    # Example usage:
    # Input format: "destination_address, amount_in_XRP"
    tool = XRPLSendXrpTool()
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 10"
    result = tool._run(example_input)
    print(result)