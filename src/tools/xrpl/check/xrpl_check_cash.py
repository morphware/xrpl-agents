import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import CheckCash
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLCheckCashTool(BaseCustomTool, BaseTool):
    """
    Tool for cashing a Check on the XRPL.
    
    Input should be a comma-separated string:
        "check_id, amount, currency, issuer"
        
    - check_id: The ID of the Check to cash
    - amount: Optional exact amount to cash (leave blank to use the Check's full amount)
    - currency: Currency code when specifying amount (leave blank if not specifying amount)
    - issuer: Issuer address when specifying token amount (leave blank for XRP or if not specifying amount)
    
    You must be the intended recipient of the Check to cash it.
    """
    name: ClassVar[str] = "XRPLCheckCash"
    description: ClassVar[str] = (
        "Cash a Check on the XRPL that was created for you. "
        "Input format: 'check_id, amount, currency, issuer'. "
        "Only provide amount/currency/issuer if you want to cash for a specific amount (less than check value). "
        "If cashing for the full amount, just provide the check_id and leave the other fields blank."
    )
    
    def _validate_check_id(self, check_id: str) -> bool:
        """Validate if check_id appears to be correctly formatted."""
        return (
            isinstance(check_id, str) and
            len(check_id) == 64 and
            all(c in '0123456789ABCDEF' for c in check_id.upper())
        )
    
    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
    
    def _format_amount(self, currency: str, issuer: str, amount: float) -> dict:
        """Format the amount based on currency type."""
        if currency.upper() == "XRP":
            # Convert XRP to drops (1 XRP = 1,000,000 drops)
            return str(int(amount * 1_000_000))
        else:
            # Return token amount
            return {
                "currency": currency,
                "issuer": issuer,
                "value": str(amount)
            }
    
    def _run(self, tool_input: str) -> str:
        try:
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) < 1:
                return False, "Input must include at least the check_id"
            
            check_id = parts[0]
            
            # Validate check id
            if not self._validate_check_id(check_id):
                return False, f"Invalid Check ID: {check_id}. Check ID should be a 64-character hexadecimal string."
            
            # Check if we're cashing for a specific amount
            amount_specified = False
            amount_value = None
            
            if len(parts) > 1 and parts[1]:
                amount_specified = True
                try:
                    amount_value = float(parts[1])
                    if amount_value <= 0:
                        return False, "Amount must be positive"
                except ValueError:
                    return False, f"Invalid amount: {parts[1]}"
                
                if len(parts) < 4:
                    return False, "When specifying amount, you must include currency and issuer (use empty issuer for XRP)"
                
                currency = parts[2].upper()
                issuer = parts[3]
                
                # Validate issuer for tokens
                if currency != "XRP" and not self._validate_address(issuer):
                    return False, f"Invalid issuer address for {currency}: {issuer}"
                
                # Format the amount
                amount_value = self._format_amount(currency, issuer, amount_value)
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create CheckCash transaction
            check_cash_tx = CheckCash(
                account=Config.XRP_WALLET.address,
                check_id=check_id
            )
            
            # Add amount if specified
            if amount_specified:
                check_cash_tx.amount = amount_value
            else:
                # Use DeliverMin for XRP to prevent transaction fees causing failure
                check_cash_tx.deliver_min = "1" 

            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": check_cash_tx.blob()
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
                    response_msg = f"Check cashed successfully!\nCheck ID: {check_id}"
                    
                    if amount_specified:
                        if isinstance(amount_value, str):
                            # XRP amount
                            amount_desc = f"{float(amount_value) / 1_000_000} XRP"
                        else:
                            # Token amount
                            amount_desc = f"{amount_value['value']} {amount_value['currency']} (Issuer: {amount_value['issuer']})"
                            
                        response_msg += f"\nAmount: {amount_desc}"
                    
                    return True, response_msg
                else:
                    return False, f"Check cashing failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error cashing Check: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCheckCashTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLCheckCashTool()
    
    # Example for cashing for full amount
    example_input = "C1B3B7D10A2670100C08AA1B30E4088640AD92728A1E347E9BB52A3B3AEE80E8"
    
    # Example for cashing for specific amount
    # example_input = "C1B3B7D10A2670100C08AA1B30E4088640AD92728A1E347E9BB52A3B3AEE80E8, 5, XRP, "
    # example_input = "C1B3B7D10A2670100C08AA1B30E4088640AD92728A1E347E9BB52A3B3AEE80E8, 50, USD, rExampleIssuer123456789"
    
    result = tool._run(example_input)
    print(result)