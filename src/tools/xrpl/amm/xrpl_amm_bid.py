import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import AMMBid
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLAMMBidTool(BaseCustomTool, BaseTool):
    """
    Tool for bidding on an AMM's auction slot on the XRPL.
    
    Input should be a comma-separated string:
        "asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, auth_accounts, bid_min, bid_max"
        
    - asset1_currency: The currency code of the first asset (e.g., "XRP" or token code)
    - asset1_issuer: The issuer address of the first asset (empty for XRP)
    - asset2_currency: The currency code of the second asset (e.g., "XRP" or token code)
    - asset2_issuer: The issuer address of the second asset (empty for XRP)
    - auth_accounts: Number of authorized accounts (1-10)
    - bid_min: Minimum bid amount in LP tokens
    - bid_max: Maximum bid amount in LP tokens
    """
    name: ClassVar[str] = "XRPLAMMBid"
    description: ClassVar[str] = (
        "Bid on an AMM's auction slot on the XRPL, allowing you to become an authorized trader. "
        "Input format: 'asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, auth_accounts, bid_min, bid_max'. "
        "At least one asset must be XRP."
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
            
            if len(parts) != 7:
                return False, "Input must have 7 parts: asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, auth_accounts, bid_min, bid_max"
            
            asset1_currency = parts[0]
            asset1_issuer = parts[1]
            asset2_currency = parts[2]
            asset2_issuer = parts[3]
            auth_accounts = parts[4]
            bid_min = parts[5]
            bid_max = parts[6]
            
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
                
            # Validate auth_accounts
            try:
                auth_accounts_int = int(auth_accounts)
                if not (1 <= auth_accounts_int <= 10):
                    return False, "Auth accounts must be between 1 and 10"
            except ValueError:
                return False, f"Invalid auth_accounts value: {auth_accounts}"
                
            # Validate bid amounts
            try:
                bid_min_float = float(bid_min)
                if bid_min_float <= 0:
                    return False, "Bid minimum must be positive"
            except ValueError:
                return False, f"Invalid bid_min value: {bid_min}"
                
            try:
                bid_max_float = float(bid_max)
                if bid_max_float <= 0:
                    return False, "Bid maximum must be positive"
                if bid_max_float < bid_min_float:
                    return False, "Bid maximum must be greater than or equal to bid minimum"
            except ValueError:
                return False, f"Invalid bid_max value: {bid_max}"
                
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
            
            # Create AMM bid transaction
            amm_bid_tx = AMMBid(
                account=Config.XRP_WALLET.address,
                asset=asset1,
                asset2=asset2,
                auth_accounts=auth_accounts_int,
                bid_min=str(int(bid_min_float * 1_000_000)),  # Convert to drops for XRP
                bid_max=str(int(bid_max_float * 1_000_000))   # Convert to drops for XRP
            )
            
            # Submit transaction through Kafka
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "transaction": amm_bid_tx.blob()
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
                        f"AMM bid submitted successfully!\n"
                        f"Asset pair: {asset1_currency}/{asset2_currency}\n"
                        f"Auth accounts: {auth_accounts}\n"
                        f"Bid min: {bid_min}\n"
                        f"Bid max: {bid_max}\n"
                    )
                    return True, response_msg
                else:
                    return False, f"AMM bid failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error submitting AMM bid: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAMMBidTool.")


if __name__ == "__main__":
    # Example usage
    tool = XRPLAMMBidTool()
    example_input = "XRP, , USD, rKV6343QUo7gmpC1JFnSEX5JWfKm8, 2, 100, 500"
    result = tool._run(example_input)
    print(result)