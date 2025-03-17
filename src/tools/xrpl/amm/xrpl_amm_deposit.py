import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import AMMDeposit
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLAMMDepositTool(BaseCustomTool, BaseTool):
    """
    Tool for depositing assets into an existing AMM instance on the XRPL.
    
    Input should be a comma-separated string:
        "asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, amount1, amount2, lptoken_out, deposit_type"
        
    - asset1_currency: The currency code of the first asset (e.g., "XRP" or token code)
    - asset1_issuer: The issuer address of the first asset (empty for XRP)
    - asset2_currency: The currency code of the second asset (e.g., "XRP" or token code)
    - asset2_issuer: The issuer address of the second asset (empty for XRP)
    - amount1: The amount of the first asset to deposit (optional depending on deposit_type)
    - amount2: The amount of the second asset to deposit (optional depending on deposit_type)
    - lptoken_out: The LP token amount expected (optional depending on deposit_type)
    - deposit_type: The type of deposit ("LPToken", "TwoAsset", "SingleAsset", optional, default: TwoAsset)
    """
    name: ClassVar[str] = "XRPLAMMDeposit"
    description: ClassVar[str] = (
        "Deposit assets into an existing AMM instance on the XRPL. "
        "Input format: 'asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, amount1, amount2, lptoken_out, deposit_type'. "
        "If currency is XRP, leave the issuer field empty. "
        "Deposit type can be 'LPToken', 'TwoAsset', or 'SingleAsset'. "
        "Required fields depend on the deposit type."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if the input appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
    
    def _format_amount(self, currency: str, issuer: str, amount: str):
        """Format currency amount for XRPL transaction."""
        if not amount:
            return None
            
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
                return False, "Input must have at least 6 parts: asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, amount1, amount2"
            
            asset1_currency = parts[0].upper()
            asset1_issuer = parts[1]
            asset2_currency = parts[2].upper()
            asset2_issuer = parts[3]
            amount1 = parts[4] if parts[4] else None
            amount2 = parts[5] if parts[5] else None
            
            # Optional parameters
            lptoken_out = None
            if len(parts) > 6 and parts[6]:
                lptoken_out = parts[6]
                
            deposit_type = "TwoAsset"  # Default
            if len(parts) > 7 and parts[7]:
                deposit_type = parts[7]
                if deposit_type not in ["LPToken", "TwoAsset", "SingleAsset"]:
                    return False, "Deposit type must be 'LPToken', 'TwoAsset', or 'SingleAsset'"
            
            # Validate addresses for non-XRP currencies
            if asset1_currency != "XRP" and not self._validate_address(asset1_issuer):
                return False, f"Invalid issuer address for {asset1_currency}: {asset1_issuer}"
            if asset2_currency != "XRP" and not self._validate_address(asset2_issuer):
                return False, f"Invalid issuer address for {asset2_currency}: {asset2_issuer}"
            
            # Validate input based on deposit type
            if deposit_type == "LPToken" and not lptoken_out:
                return False, "LP token amount is required for LPToken deposit type"
            elif deposit_type == "SingleAsset" and not (amount1 or amount2):
                return False, "At least one asset amount is required for SingleAsset deposit type"
            elif deposit_type == "TwoAsset" and (not amount1 or not amount2):
                return False, "Both asset amounts are required for TwoAsset deposit type"
            
            # Format amounts
            try:
                amount1_formatted = self._format_amount(asset1_currency, asset1_issuer, amount1) if amount1 else None
                amount2_formatted = self._format_amount(asset2_currency, asset2_issuer, amount2) if amount2 else None
            except ValueError as e:
                return False, str(e)
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create asset dictionary for AMM identifier
            asset1 = {
                "currency": asset1_currency
            }
            if asset1_currency != "XRP":
                asset1["issuer"] = asset1_issuer
                
            asset2 = {
                "currency": asset2_currency
            }
            if asset2_currency != "XRP":
                asset2["issuer"] = asset2_issuer
            
            # Create AMMDeposit transaction
            amm_deposit_tx = AMMDeposit(
                account=Config.XRP_WALLET.address,
                asset=asset1,
                asset2=asset2,
                flags=0
            )
            
            # Add parameters based on deposit type
            if deposit_type == "LPToken":
                amm_deposit_tx.flags = 1  # LPTokenIn flag
                amm_deposit_tx.lp_token_in = {
                    "currency": "LP_TOKEN",
                    "issuer": Config.XRP_WALLET.address,
                    "value": lptoken_out
                }
            elif deposit_type == "SingleAsset":
                amm_deposit_tx.flags = 2  # SingleAsset flag
                if amount1:
                    amm_deposit_tx.amount = amount1_formatted
                if amount2:
                    amm_deposit_tx.amount2 = amount2_formatted
            else:  # TwoAsset (default)
                amm_deposit_tx.amount = amount1_formatted
                amm_deposit_tx.amount2 = amount2_formatted
                
            if lptoken_out and deposit_type != "LPToken":
                amm_deposit_tx.lp_token_out = {
                    "currency": "LP_TOKEN",
                    "issuer": Config.XRP_WALLET.address,
                    "value": lptoken_out
                }

            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": amm_deposit_tx.blob()
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
                    # Format deposit description
                    assets_desc = f"AMM {asset1_currency}/{asset2_currency}"
                    
                    amount1_desc = f"{amount1} {asset1_currency}" if amount1 else "N/A"
                    amount2_desc = f"{amount2} {asset2_currency}" if amount2 else "N/A"
                    
                    response_msg = (
                        f"AMM deposit successful!\n"
                        f"Pool: {assets_desc}\n"
                        f"Deposit Type: {deposit_type}\n"
                    )
                    
                    if amount1:
                        response_msg += f"Asset 1: {amount1_desc}\n"
                    if amount2:
                        response_msg += f"Asset 2: {amount2_desc}\n"
                    if lptoken_out:
                        response_msg += f"LP Tokens: {lptoken_out}"
                    
                    return True, response_msg
                else:
                    return False, f"AMM deposit failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error depositing to AMM: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAMMDepositTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLAMMDepositTool()
    
    # Example for depositing both assets
    example_input = "XRP, , USD, rExampleIssuerAddress, 50, 50, , TwoAsset"
    
    result = tool._run(example_input)
    print(result)