import os
import sys
import json
import uuid
from typing import ClassVar
from datetime import datetime, timedelta

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import CheckCreate
from xrpl import transaction as tx
from xrpl.wallet import Wallet
from xrpl.utils import datetime_to_ripple_time

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLCheckCreateTool(BaseCustomTool, BaseTool):
    """
    Tool for creating a Check on the XRPL.
    A Check is like a paper check - it's a deferred payment that the recipient can cash.
    
    Input should be a comma-separated string:
        "destination_address, amount, currency, issuer, expiration_seconds"
        
    - destination_address: The XRPL address that can cash the Check
    - amount: Amount to authorize for the Check
    - currency: The currency code (XRP or a token code)
    - issuer: The issuer address of the token (empty for XRP)
    - expiration_seconds: Optional expiration time in seconds from now
    
    If currency is XRP, leave the issuer field empty.
    """
    name: ClassVar[str] = "XRPLCheckCreate"
    description: ClassVar[str] = (
        "Only use this tool to Create a Check on the XRPL that allows the recipient to cash it for payment. "
        "Input format: 'destination_address, amount, currency, issuer, expiration_seconds'. "
        "If currency is XRP, leave the issuer field empty. "
        "Expiration_seconds is optional - if provided, the Check will expire that many seconds from now."
        "This is not to view offers on the XRPL. "  
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
            
            if len(parts) < 4:
                return False, "Input must have at least 4 parts: destination_address, amount, currency, issuer"
            
            destination = parts[0]
            
            # Validate destination address
            if not self._validate_address(destination):
                return False, f"Invalid destination address: {destination}"
            
            # Parse amount
            try:
                amount = float(parts[1])
                if amount <= 0:
                    return False, "Amount must be positive"
            except ValueError:
                return False, f"Invalid amount: {parts[1]}"
            
            # Get currency and issuer
            currency = parts[2].upper()
            issuer = parts[3]
            
            # Validate non-XRP issuer
            if currency != "XRP" and not self._validate_address(issuer):
                return False, f"Invalid issuer address for {currency}: {issuer}"
            
            # Format send max amount
            send_max = self._format_amount(currency, issuer, amount)
            
            # Parse expiration if provided
            expiration = None
            if len(parts) > 4 and parts[4]:
                try:
                    expiration_seconds = int(parts[4])
                    if expiration_seconds <= 0:
                        return False, "Expiration seconds must be positive"
                    expiration = datetime_to_ripple_time(datetime.now() + timedelta(seconds=expiration_seconds))
                except ValueError:
                    return False, f"Invalid expiration_seconds value: {parts[4]}"
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create CheckCreate transaction
            check_tx = CheckCreate(
                account=Config.XRP_WALLET.address,
                destination=destination,
                send_max=send_max
            )
            
            # Add expiration if provided
            if expiration:
                check_tx.expiration = expiration
            
            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": check_tx.blob()
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
                    currency_desc = f"{amount} {currency}"
                    if currency != "XRP":
                        currency_desc += f" (Issuer: {issuer})"
                    
                    response_msg = (
                        f"Check created successfully!\n"
                        f"Destination: {destination}\n"
                        f"Amount: {currency_desc}"
                    )
                    
                    if expiration:
                        expiration_time = datetime.fromtimestamp(expiration + 946684800).strftime('%Y-%m-%d %H:%M:%S')
                        response_msg += f"\nExpires: {expiration_time}"
                    
                    return True, response_msg
                else:
                    return False, f"Check creation failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error creating Check: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLCheckCreateTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLCheckCreateTool()
    
    # XRP Check example
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 10, XRP, , 86400"
    
    # Token Check example
    # example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 100, USD, rExampleIssuer123456789, 86400"
    
    result = tool._run(example_input)
    print(result)