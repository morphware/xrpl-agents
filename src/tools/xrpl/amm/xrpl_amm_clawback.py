import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import AMMWithdraw
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLAMMClawbackTool(BaseCustomTool, BaseTool):
    """
    Tool for reclaiming trading fees from an AMM instance on the XRPL.
    
    Input should be a comma-separated string:
        "asset1_currency, asset1_issuer, asset2_currency, asset2_issuer"
        
    - asset1_currency: The currency code of the first asset (e.g., "XRP" or token code)
    - asset1_issuer: The issuer address of the first asset (empty for XRP)
    - asset2_currency: The currency code of the second asset (e.g., "XRP" or token code)
    - asset2_issuer: The issuer address of the second asset (empty for XRP)
    
    The clawback can only be used by an account that won the auction for a trading fee slot.
    """
    name: ClassVar[str] = "XRPLAMMClawback"
    description: ClassVar[str] = (
        "Reclaim trading fees from an AMM instance on the XRPL that you have an auction slot for. "
        "Input format: 'asset1_currency, asset1_issuer, asset2_currency, asset2_issuer'. "
        "You must have previously won an auction for this AMM instance to perform a clawback."
    )
    
    def _validate_currency(self, currency: str) -> bool:
        """Validate if currency code is valid."""
        if currency == "XRP":
            return True
        return (
            isinstance(currency, str) and
            3 <= len(currency) <= 40
        )
    
    def _validate_issuer(self, issuer: str, currency: str) -> bool:
        """Validate issuer address is valid."""
        if currency == "XRP" and (issuer == "" or issuer is None):
            return True
        return (
            isinstance(issuer, str) and 
            issuer.startswith('r') and 
            len(issuer) >= 25 and 
            len(issuer) <= 35
        )
    
    def _run(self, tool_input: str) -> str:
        try:
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) != 4:
                return False, "Input must have 4 parts: asset1_currency, asset1_issuer, asset2_currency, asset2_issuer"
            
            asset1_currency = parts[0]
            asset1_issuer = parts[1]
            asset2_currency = parts[2]
            asset2_issuer = parts[3]
            
            # Validate currency codes
            if not self._validate_currency(asset1_currency):
                return False, f"Invalid first asset currency: {asset1_currency}"
            if not self._validate_currency(asset2_currency):
                return False, f"Invalid second asset currency: {asset2_currency}"
                
            # Validate issuers
            if not self._validate_issuer(asset1_issuer, asset1_currency):
                return False, f"Invalid first asset issuer: {asset1_issuer}"
            if not self._validate_issuer(asset2_issuer, asset2_currency):
                return False, f"Invalid second asset issuer: {asset2_issuer}"
                
            # Validate at least one asset is XRP
            if not (asset1_currency == "XRP" or asset2_currency == "XRP"):
                return False, "At least one asset must be XRP for AMM instances"
                
            # Create asset objects
            asset1 = {
                "currency": asset1_currency
            }
            if asset1_currency != "XRP" and asset1_issuer:
                asset1["issuer"] = asset1_issuer
                
            asset2 = {
                "currency": asset2_currency
            }
            if asset2_currency != "XRP" and asset2_issuer:
                asset2["issuer"] = asset2_issuer
            
            # Create AMM withdraw transaction with flags for clawback
            amm_clawback_tx = AMMWithdraw(
                account=Config.XRP_WALLET.address,
                asset=asset1,
                asset2=asset2,
                flags=131072  # tfLPToken=0x00010000, tfWithdrawAll=0x00020000
            )
            
            # Submit transaction through Kafka
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": amm_clawback_tx.blob()
                    }
                )
                
                send_to_kafka(producer=Config.kafka_out, topic=Config.KAFKA_OUT_TOPIC, 
                             message=payload, key=Config.REQUEST_ID, msg_type='tx_send_xrp')
                
                match = False
                while not match:
                    response, key = get_kafka_latest_message(
                        Config.consume_from_kafka(Config.kafka_in, Config.KAFKA_IN_TOPIC),
                        message_id=Config.REQUEST_ID
                    )
                    if tx_id == response.tx_id:
                        match = True
                    else:
                        match = False
                
                if isinstance(response, Exception):
                    return False, f"Error processing message: {str(response)}"
                
                if "SUCCESS" in response.tx_status:
                    response_msg = (
                        f"AMM clawback successful!\n"
                        f"Asset pair: {asset1_currency}/{asset2_currency}\n"
                    )
                    return True, response_msg
                else:
                    return False, f"AMM clawback failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error processing AMM clawback: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAMMClawbackTool.")


if __name__ == "__main__":
    # Example usage
    tool = XRPLAMMClawbackTool()
    example_input = "XRP, , USD, rKV6343QUo7gmpC1JFnSEX5JWfKm8"
    result = tool._run(example_input)
    print(result)