import os
import sys
import json
import uuid
from typing import ClassVar
from datetime import datetime, timedelta

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import PaymentChannelFund
from xrpl import transaction as tx
from xrpl.wallet import Wallet
from xrpl.utils import datetime_to_ripple_time

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLPaymentChannelFundTool(BaseCustomTool, BaseTool):
    """
    Tool for funding an existing Payment Channel on the XRPL.
    
    Input should be a comma-separated string:
        "channel_id, amount_in_XRP, expiration_seconds"
        
    - channel_id: The ID of the payment channel to fund
    - amount_in_XRP: Additional XRP amount to add to the channel
    - expiration_seconds: (Optional) New expiration time in seconds from now
    
    You can only fund payment channels where you are the source/owner.
    """
    name: ClassVar[str] = "XRPLPaymentChannelFund"
    description: ClassVar[str] = (
        "Fund an existing Payment Channel on the XRPL or extend its expiration. "
        "Input format: 'channel_id, amount_in_XRP, expiration_seconds'. "
        "You must be the creator of the channel to fund it. "
        "Expiration is optional - if provided, extends the channel's expiration time."
    )

    def _validate_channel_id(self, channel_id: str) -> bool:
        """Validate if channel_id appears to be correctly formatted."""
        return (
            isinstance(channel_id, str) and
            len(channel_id) == 64 and
            all(c in '0123456789ABCDEF' for c in channel_id.upper())
        )
    
    def _run(self, tool_input: str) -> str:
        try:
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) < 2:
                return False, "Input must have at least 2 parts: channel_id, amount_in_XRP"
            
            channel_id = parts[0]
            
            # Validate channel ID
            if not self._validate_channel_id(channel_id):
                return False, f"Invalid Channel ID: {channel_id}. Channel ID should be a 64-character hexadecimal string."
            
            # Parse amount
            try:
                amount_xrp = float(parts[1])
                if amount_xrp <= 0:
                    return False, "Amount must be positive"
                # Convert XRP to drops (1 XRP = 1,000,000 drops)
                amount_drops = str(int(amount_xrp * 1_000_000))
            except ValueError:
                return False, f"Invalid amount: {parts[1]}"
            
            # Parse expiration if provided
            expiration = None
            if len(parts) > 2 and parts[2]:
                try:
                    expiration_seconds = int(parts[2])
                    if expiration_seconds <= 0:
                        return False, "Expiration seconds must be positive"
                    expiration = datetime_to_ripple_time(datetime.now() + timedelta(seconds=expiration_seconds))
                except ValueError:
                    return False, f"Invalid expiration_seconds value: {parts[2]}"
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create PaymentChannelFund transaction
            fund_tx = PaymentChannelFund(
                account=Config.XRP_WALLET.address,
                channel=channel_id,
                amount=amount_drops
            )
            
            # Add expiration if provided
            if expiration:
                fund_tx.expiration = expiration
            
            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": fund_tx.blob()
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
                        f"Payment channel funded successfully!\n"
                        f"Channel ID: {channel_id}\n"
                        f"Additional Amount: {amount_xrp} XRP"
                    )
                    
                    if expiration:
                        expiration_time = datetime.fromtimestamp(expiration + 946684800).strftime('%Y-%m-%d %H:%M:%S')
                        response_msg += f"\nNew Expiration: {expiration_time}"
                    
                    return True, response_msg
                else:
                    return False, f"Payment channel funding failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error funding payment channel: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLPaymentChannelFundTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLPaymentChannelFundTool()
    
    # Example input: "channel_id, amount_in_XRP, expiration_seconds"
    example_input = "5DB01B7FFED6B67E6B0414DED11E051D2EE2B7619CE0EAA6286D67A3A4D5BDB3, 5, 86400"
    
    result = tool._run(example_input)
    print(result)