import os
import sys
import json
import uuid
from typing import ClassVar, Tuple, Union

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import AMMVote
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLAMMVoteTool(BaseCustomTool, BaseTool):
    """
    Tool for voting on an AMM's trading fee on the XRPL.
    
    Input should be a comma-separated string:
        "asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, trading_fee"
        
    - asset1_currency: The currency code of the first asset (e.g., "XRP" or token code)
    - asset1_issuer: The issuer address of the first asset (empty for XRP)
    - asset2_currency: The currency code of the second asset (e.g., "XRP" or token code)
    - asset2_issuer: The issuer address of the second asset (empty for XRP)
    - trading_fee: The trading fee in basis points (0-1000)
    
    Only LP token holders can vote on the trading fee.
    """
    name: ClassVar[str] = "XRPLAMMVote"
    description: ClassVar[str] = (
        "Vote on an AMM trading fee on the XRPL. "
        "Input format: 'asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, trading_fee'. "
        "The trading fee is specified in basis points (0-1000, where 100 = 1%). "
        "You need to hold LP tokens to vote. "
        "At least one asset must be XRP."
    )

    def _validate_currency(self, currency: str) -> bool:
        """Check if currency is valid."""
        if currency == "XRP":
            return True
        return (
            isinstance(currency, str) and
            len(currency) >= 3 and
            len(currency) <= 20
        )

    def _validate_address(self, address: str) -> bool:
        """Check if address is valid."""
        if not address:  # Empty is valid for XRP
            return True
        return (
            isinstance(address, str) and
            address.startswith('r') and
            len(address) >= 25 and
            len(address) <= 35
        )

    def _validate_asset_pair(self, 
                            asset1_currency: str, 
                            asset1_issuer: str, 
                            asset2_currency: str, 
                            asset2_issuer: str) -> Tuple[bool, str]:
        """Validate asset pair configuration."""
        if not self._validate_currency(asset1_currency):
            return False, f"Invalid asset1 currency: {asset1_currency}"
        
        if not self._validate_currency(asset2_currency):
            return False, f"Invalid asset2 currency: {asset2_currency}"
        
        if not self._validate_address(asset1_issuer):
            return False, f"Invalid asset1 issuer: {asset1_issuer}"
        
        if not self._validate_address(asset2_issuer):
            return False, f"Invalid asset2 issuer: {asset2_issuer}"
        
        # At least one asset must be XRP
        if not (
            (asset1_currency == "XRP" and not asset1_issuer) or 
            (asset2_currency == "XRP" and not asset2_issuer)
        ):
            return False, "At least one asset must be XRP"
        
        return True, ""

    def _run(self, tool_input: str) -> Union[Tuple[bool, str], str]:
        try:
            parts = [p.strip() for p in tool_input.split(',')]
            
            if len(parts) != 5:
                return False, "Input must have 5 parts: asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, trading_fee"
            
            asset1_currency = parts[0]
            asset1_issuer = parts[1]
            asset2_currency = parts[2]
            asset2_issuer = parts[3]
            trading_fee_str = parts[4]
            
            # Validate asset pair
            valid, message = self._validate_asset_pair(asset1_currency, asset1_issuer, asset2_currency, asset2_issuer)
            if not valid:
                return False, message
            
            # Validate trading fee
            try:
                trading_fee = int(trading_fee_str)
                if trading_fee < 0 or trading_fee > 1000:
                    return False, f"Trading fee must be between 0 and 1000 basis points: {trading_fee}"
            except ValueError:
                return False, f"Invalid trading fee: {trading_fee_str}"
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Construct AMM asset pair
            asset1 = {"currency": asset1_currency}
            if asset1_currency != "XRP":
                asset1["issuer"] = asset1_issuer
                
            asset2 = {"currency": asset2_currency}
            if asset2_currency != "XRP":
                asset2["issuer"] = asset2_issuer
            
            # Create vote transaction
            vote_tx = AMMVote(
                account=Config.XRP_WALLET.address,
                asset=asset1,
                asset2=asset2,
                fee_val=trading_fee
            )

            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": vote_tx.blob()
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
                    assets_desc = f"{asset1_currency}"
                    if asset1_currency != "XRP":
                        assets_desc += f" (issuer: {asset1_issuer})"
                    assets_desc += f" / {asset2_currency}"
                    if asset2_currency != "XRP":
                        assets_desc += f" (issuer: {asset2_issuer})"
                        
                    return True, (
                        f"AMM voting successful!\n"
                        f"AMM Pair: {assets_desc}\n"
                        f"Trading Fee Vote: {trading_fee} basis points ({trading_fee/100.0}%)"
                    )
                else:
                    return False, f"AMM vote failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error voting on AMM: {str(e)}"
    
    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAMMVoteTool.")


if __name__ == "__main__":
    # Example usage:
    tool = XRPLAMMVoteTool()
    
    # Example input: "asset1_currency, asset1_issuer, asset2_currency, asset2_issuer, trading_fee"
    example_input = "XRP, , USD, rSomeBankIssuerAddress1234567890abcd, 50"  # 0.5% fee
    
    result = tool._run(example_input)
    print(result)