import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import AMMCreate
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLAMMCreateTool(BaseCustomTool, BaseTool):
    """
    Tool for creating a new Automated Market Maker (AMM) instance on the XRPL.
    
    Input should be a comma-separated string:
        "amount1, currency1, issuer1, amount2, currency2, issuer2, trading_fee"
        
    - amount1: The amount of the first asset to deposit
    - currency1: The currency code of the first asset (e.g., "XRP" or token code)
    - issuer1: The issuer address of the first asset (empty for XRP)
    - amount2: The amount of the second asset to deposit
    - currency2: The currency code of the second asset (e.g., "XRP" or token code)
    - issuer2: The issuer address of the second asset (empty for XRP)
    - trading_fee: The trading fee in basis points (0-1000, optional, default: 0)
    
    At least one asset must be XRP in an AMM instance.
    """
    name: ClassVar[str] = "XRPLAMMCreate"
    description: ClassVar[str] = (
        "Create a new Automated Market Maker (AMM) instance on the XRPL. "
        "Input format: 'amount1, currency1, issuer1, amount2, currency2, issuer2, trading_fee'. "
        "At least one of the asset pairs must be XRP. "
        "If currency is XRP, leave the issuer field empty. "
        "Trading fee is in basis points (0-1000, optional)."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if the input appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
    
    def _format_currency_amount(self, currency: str, issuer: str, amount: str):
        """Format currency amount for XRPL transaction."""
        if currency.upper() == "XRP":
            # Convert XRP to drops (1 XRP = 1,000,000 drops)
            try:
                drops = int(float(amount) * 1_000_000)
                return str(drops)
            except ValueError:
                raise ValueError(f"Invalid XRP amount: {amount}")
        else:
            # Return structured token amount
            return {
                "currency": currency,
                "issuer": issuer,
                "value": str(amount)
            }
        
    def _run(self, tool_input: str) -> str:
        try:
            # Parse input
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) < 6:
                return False, "Input must have at least 6 parts: amount1, currency1, issuer1, amount2, currency2, issuer2"
            
            amount1 = parts[0]
            currency1 = parts[1].upper()
            issuer1 = parts[2]
            amount2 = parts[3]
            currency2 = parts[4].upper()
            issuer2 = parts[5]
            
            # Optional trading fee
            trading_fee = 0
            if len(parts) > 6 and parts[6]:
                try:
                    trading_fee = int(parts[6])
                    if trading_fee < 0 or trading_fee > 1000:
                        return False, "Trading fee must be between 0 and 1000 basis points"
                except ValueError:
                    return False, f"Invalid trading fee: {parts[6]}"
            
            # Validate at least one asset is XRP
            if currency1 != "XRP" and currency2 != "XRP":
                return False, "At least one of the asset pairs must be XRP"
            
            # Validate addresses for non-XRP currencies
            if currency1 != "XRP" and not self._validate_address(issuer1):
                return False, f"Invalid issuer address for {currency1}: {issuer1}"
            if currency2 != "XRP" and not self._validate_address(issuer2):
                return False, f"Invalid issuer address for {currency2}: {issuer2}"
            
            # Format amounts
            try:
                if currency1 == "XRP":
                    amount1_formatted = amount1
                else:
                    amount1_formatted = {
                        "currency": currency1,
                        "issuer": issuer1,
                        "value": amount1
                    }
                
                if currency2 == "XRP":
                    amount2_formatted = amount2
                else:
                    amount2_formatted = {
                        "currency": currency2,
                        "issuer": issuer2,
                        "value": amount2
                    }
            except ValueError as e:
                return False, str(e)
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create AMMCreate transaction
            amm_create_tx = AMMCreate(
                account=Config.XRP_WALLET.address,
                amount=amount1_formatted,
                amount2=amount2_formatted,
                trading_fee=trading_fee
            )

            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": amm_create_tx.blob()
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
                    # Format asset descriptions
                    asset1_desc = f"{amount1} {currency1}"
                    if currency1 != "XRP":
                        asset1_desc += f" (Issuer: {issuer1})"
                    
                    asset2_desc = f"{amount2} {currency2}"
                    if currency2 != "XRP":
                        asset2_desc += f" (Issuer: {issuer2})"
                    
                    response_msg = (
                        f"AMM created successfully!\n"
                        f"Asset 1: {asset1_desc}\n"
                        f"Asset 2: {asset2_desc}\n"
                        f"Trading Fee: {trading_fee} basis points"
                    )
                    
                    return True, response_msg
                else:
                    return False, f"AMM creation failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error creating AMM: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAMMCreateTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLAMMCreateTool()
    
    # Example for XRP-USD pair
    example_input = "100, XRP, , 100, USD, rExampleIssuerAddress, 5"
    
    result = tool._run(example_input)
    print(result)