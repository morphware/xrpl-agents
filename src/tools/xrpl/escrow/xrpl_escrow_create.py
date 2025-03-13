import os
import sys
import json
import uuid
from typing import ClassVar
from datetime import datetime, timedelta

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import EscrowCreate
from xrpl import transaction as tx
from xrpl.wallet import Wallet
from xrpl.utils import datetime_to_ripple_time

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLEscrowCreateTool(BaseCustomTool, BaseTool):
    """
    Tool for creating an escrow payment on the XRPL.
    An escrow locks up XRP until a specific time or condition is met.
    
    Input should be a comma-separated string:
        "destination_address, amount_in_XRP, finish_after_seconds, cancel_after_seconds, condition"
        
    - destination_address: The XRPL address that can receive the escrowed XRP
    - amount_in_XRP: Amount of XRP to escrow
    - finish_after_seconds: When the funds can be released (in seconds from now)
    - cancel_after_seconds: When the sender can cancel (in seconds from now, must be > finish_after)
    - condition: (Optional) Crypto-condition that must be fulfilled to release the escrow
    
    If finish_after_seconds is empty, the escrow will rely solely on the condition.
    If condition is empty, the escrow will be time-based only.
    """
    name: ClassVar[str] = "XRPLEscrowCreate"
    description: ClassVar[str] = (
        "Create an escrow payment on the XRPL. "
        "Input format: 'destination_address, amount_in_XRP, finish_after_seconds, cancel_after_seconds, condition'. "
        "The escrow locks XRP until a time passes or condition is met. "
        "Leave finish_after_seconds empty for condition-only escrows. "
        "Leave condition empty for time-only escrows. "
        "Cancel_after_seconds must be greater than finish_after_seconds. "
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
        
    def _run(self, tool_input: str) -> str:
        try:
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) < 4:
                return False, "Input must have at least 4 parts: destination_address, amount_in_XRP, finish_after_seconds, cancel_after_seconds"
            
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
            
            # Parse finish_after and cancel_after
            finish_after = None
            if parts[2]:
                try:
                    finish_after_seconds = int(parts[2])
                    if finish_after_seconds < 0:
                        return False, "Finish after seconds must be positive"
                    finish_after = datetime_to_ripple_time(datetime.now() + timedelta(seconds=finish_after_seconds))
                except ValueError:
                    return False, f"Invalid finish_after value: {parts[2]}"
            
            try:
                cancel_after_seconds = int(parts[3])
                if cancel_after_seconds < 0:
                    return False, "Cancel after seconds must be positive"
                cancel_after = datetime_to_ripple_time(datetime.now() + timedelta(seconds=cancel_after_seconds))
            except ValueError:
                return False, f"Invalid cancel_after value: {parts[3]}"
            
            # If both finish_after and cancel_after are provided, validate cancel_after is later
            if finish_after is not None and cancel_after <= finish_after:
                return False, "cancel_after must be later than finish_after"
            
            # Get condition if provided
            condition = None
            if len(parts) > 4 and parts[4]:
                condition = parts[4]
            
            # Validate that either a condition or finish_after is provided
            if finish_after is None and not condition:
                return False, "Either finish_after or condition must be provided"
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Create EscrowCreate transaction
            escrow_tx = EscrowCreate(
                account=Config.XRP_WALLET.address,
                destination=destination,
                amount=amount_drops,
                cancel_after=cancel_after
            )
            
            # Add optional fields if provided
            if finish_after is not None:
                escrow_tx.finish_after = finish_after
            
            if condition:
                escrow_tx.condition = condition
            
            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "transaction": escrow_tx.blob()
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
                        f"Escrow created successfully!\n"
                        f"Destination: {destination}\n"
                        f"Amount: {amount_xrp} XRP\n"
                    )
                    
                    if finish_after is not None:
                        finish_time = datetime.fromtimestamp(finish_after + 946684800).strftime('%Y-%m-%d %H:%M:%S')
                        response_msg += f"Available after: {finish_time}\n"
                    
                    if condition:
                        response_msg += f"Condition: {condition}\n"
                        
                    cancel_time = datetime.fromtimestamp(cancel_after + 946684800).strftime('%Y-%m-%d %H:%M:%S')
                    response_msg += f"Cancellable after: {cancel_time}"
                    
                    return True, response_msg
                else:
                    return False, f"Escrow creation failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error creating escrow: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLEscrowCreateTool.")


if __name__ == "__main__":
    # Example usage:
    # Input format: "destination_address, amount_in_XRP, finish_after_seconds, cancel_after_seconds, condition"
    tool = XRPLEscrowCreateTool()
    
    # Time-based escrow example (release after 1 hour, cancel after 24 hours)
    example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 10, 3600, 86400,"
    
    # Condition-based escrow example (with cancel after 7 days)
    # example_input = "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe, 10, , 604800, A0258020E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855810100"
    
    result = tool._run(example_input)
    print(result)