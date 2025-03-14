import os
import sys
import json
import uuid
from typing import ClassVar

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import PaymentChannelClaim
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLPaymentChannelClaimTool(BaseCustomTool, BaseTool):
    """
    Tool for claiming XRP from a Payment Channel, or requesting to close it.
    
    Input should be a comma-separated string:
        "channel_id, amount_in_XRP, signature, public_key, close"
        
    - channel_id: The ID of the payment channel
    - amount_in_XRP: Amount to claim from the channel (optional if closing)
    - signature: The signature that authorizes the claim (optional)
    - public_key: Public key that created the signature (optional)
    - close: Whether to close the channel (true/false, optional, default: false)
    
    Can be used by either the source (to close) or destination (to claim funds).
    """
    name: ClassVar[str] = "XRPLPaymentChannelClaim"
    description: ClassVar[str] = (
        "Claim XRP from a Payment Channel or request to close it. "
        "Input format: 'channel_id, amount_in_XRP, signature, public_key, close'. "
        "As source, you can close the channel. As destination, you can claim authorized XRP. "
        "Set 'close' to 'true' to request channel closure. Amount, signature, and public_key are optional."
    )

    def _validate_channel_id(self, channel_id: str) -> bool:
        """Validate if channel_id appears to be correctly formatted."""
        return (
            isinstance(channel_id, str) and
            len(channel_id) == 64 and
            all(c in '0123456789ABCDEF' for c in channel_id.upper())
        )
        
    def _validate_signature(self, signature: str) -> bool:
        """Check if the input appears to be a valid signature in hex format."""
        if not signature:
            return True  # Empty is valid (optional field)
        return (
            isinstance(signature, str) and
            all(c in '0123456789ABCDEFabcdef' for c in signature)
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
            
            if len(parts) < 1:
                return False, "Input must include at least the channel_id"
            
            channel_id = parts[0]
            
            # Validate channel ID
            if not self._validate_channel_id(channel_id):
                return False, f"Invalid Channel ID: {channel_id}. Channel ID should be a 64-character hexadecimal string."
            
            # Parse amount if provided
            amount_drops = None
            if len(parts) > 1 and parts[1]:
                try:
                    amount_xrp = float(parts[1])
                    if amount_xrp <= 0:
                        return False, "Amount must be positive"
                    # Convert XRP to drops (1 XRP = 1,000,000 drops)
                    amount_drops = str(int(amount_xrp * 1_000_000))
                except ValueError:
                    return False, f"Invalid amount: {parts[1]}"
            
            # Get signature if provided
            signature = None
            if len(parts) > 2 and parts[2]:
                signature = parts[2]
                if not self._validate_signature(signature):
                    return False, f"Invalid signature format: {signature}"
            
            # Get public key if provided
            public_key = None
            if len(parts) > 3 and parts[3]:
                public_key = parts[3]
                if not self._validate_public_key(public_key):
                    return False, f"Invalid public key: {public_key}"
            
            # Check if we should close the channel
            close = False
            if len(parts) > 4 and parts[4].lower() in ['true', 't', 'yes', 'y', '1']:
                close = True
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create PaymentChannelClaim transaction
            claim_tx = PaymentChannelClaim(
                account=Config.XRP_WALLET.address,
                channel=channel_id
            )
            
            # Add optional fields if provided
            if amount_drops:
                claim_tx.amount = amount_drops
                
            if signature:
                claim_tx.signature = signature
                
            if public_key:
                claim_tx.public_key = public_key
            
            # Set flags based on close parameter
            if close:
                claim_tx.flags = 1  # tfClose flag
            
            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "transaction": claim_tx.blob()
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
                    if close:
                        action_msg = "Channel close requested"
                    elif amount_drops:
                        action_msg = f"Claimed {float(amount_drops) / 1_000_000} XRP"
                    else:
                        action_msg = "Transaction successful"
                    
                    response_msg = (
                        f"Payment channel action successful!\n"
                        f"Channel ID: {channel_id}\n"
                        f"Action: {action_msg}"
                    )
                    
                    return True, response_msg
                else:
                    return False, f"Payment channel claim/close failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error processing payment channel claim: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLPaymentChannelClaimTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLPaymentChannelClaimTool()
    
    # Example for claiming with signature (as destination)
    # example_input = "5DB01B7FFED6B67E6B0414DED11E051D2EE2B7619CE0EAA6286D67A3A4D5BDB3, 1, 30440220718D264EF05CAED7C781FF6DE298DCAC68D002562C9BF3A07C1E721B420C0DAB02203A5A4779EF4D2CCC7BC3EF886676D803A9981B928D3B8ACA483B80ECA3CD7B9B, 0330E7FC9D56BB25D6893BA3F317AE5BCF33B3291BD63DB32654A313222F7FD020"
    
    # Example for closing the channel (as source)
    example_input = "5DB01B7FFED6B67E6B0414DED11E051D2EE2B7619CE0EAA6286D67A3A4D5BDB3, , , , true"
    
    result = tool._run(example_input)
    print(result)