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
import time, uuid
import requests

class XRPLSendTokenTool(BaseCustomTool, BaseTool):
    """
    Tool for sending tokens on the XRPL chain.
    Input should be a comma-separated string:
        "destination_address, amount, token_code, issuer"
    If both issuer or token_code is not provided, this will fail.
    If only one is provided, the tool will attempt to find the issuer address in the users wallet.
    If only the token_code is provided, the tool will attempt to find the issuer address using the XRPLGetWalletTokensList tool
    """
    name: ClassVar[str] = "XRPLSendToken"
    description: ClassVar[str] = (
        "Send tokens on the XRPL chain. "
        "Input should be in the format 'destination_address, amount, token_code, issuer'. "
        "If both issuer or token_code is not provided, this will fail."
        "If only one is provided, the tool will attempt to find the issuer address in the users wallet."
        "Please use the tool XRPLGetWalletTokenBalances to make sure the user has the tokens, and to get the issuer address or token_code if needed."
    )

    def _validate_address(self, address: str) -> bool:
        """Validate if the input looks like a proper XRPL address."""
        if "user_account_address" in address.lower():
            address = Config.XRP_WALLET.address
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
        
    def _get_issuer_address(self, token_code: str) -> str:
        """Get the issuer address for the token code."""
        

    def _run(self, tool_input: str) -> str:
        try:
            parts = tool_input.split(",")
            if len(parts) != 4:
                return False, "Input must be in the format 'destination_address, amount, token_code, issuer'."
            
            destination = parts[0].strip()
            try:
                amount = float(parts[1].strip())
            except ValueError:
                return False, "Amount must be a numeric value."
            
            token_code = parts[2].strip().upper()
            issuer = parts[3].strip()

            # Validate addresses
            if not self._validate_address(destination):
                return False, f"Invalid destination address: {destination}"
            if not self._validate_address(issuer):
                return False, f"Invalid issuer address: {issuer}"

            # Connect to the XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)

            # Create Payment transaction
            payment = Payment(
                account=Config.XRP_WALLET.address,
                destination=destination,
                amount={
                    "currency": token_code,
                    "value": str(amount),
                    "issuer": issuer
                }
            )

            tx_id = str(uuid.uuid4())
            # Create XrpTransactionRequest object with attributes
            payload = json.dumps(
                {
                    "msg_type": "tx_send_xrp",
                    "tx_id": tx_id,
                    "transaction": payment.blob()
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
                response = f"Transaction Successful: sent {amount} {token_code} to {destination}"
                return True, response
            else:
                response = f"Transaction Failed: {response}"
                return False, response

        except Exception as e:
            return False, f"Error sending token: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLSendTokenTool.")

if __name__ == "__main__":
    # Example usage:
    # Input format: "destination_address, amount, token_code, issuer"
    tool = XRPLSendTokenTool()
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 100, USD"
    result = tool._run(example_input)
    print(result)