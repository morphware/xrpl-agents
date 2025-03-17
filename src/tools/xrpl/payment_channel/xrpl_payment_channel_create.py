import os
import sys
import json
import uuid
from typing import ClassVar
from datetime import datetime, timedelta

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import PaymentChannelCreate
from xrpl import transaction as tx
from xrpl.wallet import Wallet
from xrpl.utils import datetime_to_ripple_time

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLPaymentChannelCreateTool(BaseCustomTool, BaseTool):
    """
    Tool for creating a Payment Channel on the XRPL.
    A Payment Channel allows asynchronous XRP payments with very low fees.
    
    Input should be a comma-separated string:
        "destination_address, amount_in_XRP, settle_delay_seconds, public_key, expiration_seconds"
        
    - destination_address: The XRPL address of the channel's destination
    - amount_in_XRP: Amount of XRP to fund the channel
    - settle_delay_seconds: Time in seconds that destination must wait to claim funds after requesting channel closure
    - public_key: (Optional) Public key used to verify claims against this channel, in hex format
    - expiration_seconds: (Optional) Time in seconds from now when the channel expires
    """
    name: ClassVar[str] = "XRPLPaymentChannelCreate"
    description: ClassVar[str] = (
        "Create a Payment Channel on the XRPL for asynchronous, off-ledger XRP payments. "
        "Input format: 'destination_address, amount_in_XRP, settle_delay_seconds, public_key, expiration_seconds'. "
        "Public key and expiration are optional. Settle delay is the time the destination must wait to claim funds."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
        
    def _validate_public_key(self, public_key: str) -> bool:
        """Check if the input appears to be a valid public key in hex format."""
        if not public_key:
            return True  # Empty is valid (optional field)
        return (
            isinstance(public_key, str) and
            len(public_key) == 66 and  # 33 bytes in hex = 66 chars
            all(c in '0123456789ABCDEFabcdef' for c in public_key)
        )
    
    def _run(self, tool_input: str) -> str:
        try:
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) < 3:
                return False, "Input must have at least 3 parts: destination_address, amount_in_XRP, settle_delay_seconds"
            
            destination = parts[0]
            
            # Validate destination address
            if not self._validate_address(destination):
                return False, f"Invalid destination address: {destination}"
            
            # Parse amount
            try:
                amount_xrp = float(parts[1])
                if amount_xrp <= 0:
                    return False, "Amount must be positive"
                # Convert XRP to drops (1 XRP = 1,000,000 drops)
                amount_drops = str(int(amount_xrp * 1_000_000))
            except ValueError:
                return False, f"Invalid amount: {parts[1]}"
            
            # Parse settle delay
            try:
                settle_delay = int(parts[2])
                if settle_delay < 0:
                    return False, "Settle delay must be non-negative"
            except ValueError:
                return False, f"Invalid settle_delay_seconds: {parts[2]}"
            
            # Get optional public key if provided
            public_key = None
            if len(parts) > 3 and parts[3]:
                public_key = parts[3]
                if not self._validate_public_key(public_key):
                    return False, f"Invalid public key: {public_key}. Public key should be in hex format."
            
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
            
            # Create PaymentChannelCreate transaction
            channel_tx = PaymentChannelCreate(
                account=Config.XRP_WALLET.address,
                destination=destination,
                amount=amount_drops,
                settle_delay=settle_delay
            )
            
            # Add optional fields if provided
            if public_key:
                channel_tx.public_key = public_key
                
            if expiration:
                channel_tx.cancel_after = expiration
            
            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": channel_tx.blob()
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
                        f"Payment channel created successfully!\n"
                        f"Destination: {destination}\n"
                        f"Amount: {amount_xrp} XRP\n"
                        f"Settle Delay: {settle_delay} seconds"
                    )
                    
                    if public_key:
                        response_msg += f"\nPublic Key: {public_key}"
                    
                    if expiration:
                        expiration_time = datetime.fromtimestamp(expiration + 946684800).strftime('%Y-%m-%d %H:%M:%S')
                        response_msg += f"\nExpires: {expiration_time}"
                    
                    return True, response_msg
                else:
                    return False, f"Payment channel creation failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error creating payment channel: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLPaymentChannelCreateTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLPaymentChannelCreateTool()
    
    # Example input: "destination_address, amount_in_XRP, settle_delay_seconds, public_key, expiration_seconds"
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 10, 3600, , 86400"
    
    result = tool._run(example_input)
    print(result)