import os
import sys
import json
import uuid
from typing import ClassVar
from datetime import datetime

from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import OfferCreate
from xrpl import transaction as tx
from xrpl.wallet import Wallet

from ....config import Config
from ...base import BaseCustomTool
from ....utils.kafka import send_to_kafka, get_kafka_latest_message


class XRPLOfferCreateTool(BaseCustomTool, BaseTool):
    """
    Tool for creating offers (buy/sell orders) on the XRPL DEX.
    Input should be a comma-separated string:
        "gets_currency, gets_issuer, gets_amount, pays_currency, pays_amount, pays_issuer, expiration_seconds"
    
    - For XRP, use 'XRP' as currency and leave issuer empty
    - For other currencies, provide both currency code and issuer address
    - Expiration in seconds is optional (0 means no expiration)
    - Gets = what you want to receive, Pays = what you're offering
    """
    name: ClassVar[str] = "XRPLOfferCreate"
    description: ClassVar[str] = (
        "Create an offer (buy/sell order) on the XRPL decentralized exchange. "
        "Input format: 'gets_currency, gets_issuer, gets_amount, pays_currency, pays_amount, pays_issuer, expiration_seconds'. "
        "'gets_currency' is the currency you want to receive, 'pays_currency' is the currency you're offering. "
        "'gets_issuer' is the issuer address for non-XRP currencies, 'pay_issuer' is the issuer address for non-XRP currencies. "
        "'gets_amount' and 'pays_amount' are the amounts you want to receive and offer, respectively. "
        "For XRP, use 'XRP' as currency and leave issuer empty. "
        "Gets = what you want to receive, Pays = what you're offering. "
        "Expiration in seconds is optional (0 means no expiration)."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        if not address:  # Empty string is valid for XRP
            return True
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
                return False, "Input must have at least 6 parts: gets_currency, gets_issuer, gets_amount, pays_currency, pays_amount, pays_issuer"
            
            gets_currency = parts[0].upper()
            gets_issuer = parts[1]
            gets_amount = parts[2]
            pays_currency = parts[3].upper()
            pays_amount = parts[4]
            pays_issuer = parts[5]
            
            # Optional expiration
            expiration_seconds = 0
            if len(parts) > 6 and parts[6]:
                try:
                    expiration_seconds = int(parts[6])
                except ValueError:
                    return False, f"Invalid expiration value: {parts[6]}"
            
            # Validate currencies
            if gets_currency != "XRP" and not self._validate_address(gets_issuer):
                return False, f"Invalid issuer address for {gets_currency}: {gets_issuer}"
            if pays_currency != "XRP" and not self._validate_address(pays_issuer):
                return False, f"Invalid issuer address for {pays_currency}: {pays_issuer}"
            
            # Format amounts
            try:
                taker_gets = self._format_currency_amount(gets_currency, gets_issuer, gets_amount)
                taker_pays = self._format_currency_amount(pays_currency, pays_issuer, pays_amount)
            except ValueError as e:
                return False, str(e)
            
            # Connect to XRPL
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            
            # Prepare expiration if provided
            expiration = None
            if expiration_seconds > 0:
                current_time = int(datetime.now().timestamp())
                expiration = current_time + expiration_seconds
            
            # Create OfferCreate transaction
            offer_create_tx = OfferCreate(
                account=Config.XRP_WALLET.address,
                taker_gets=taker_gets,
                taker_pays=taker_pays,
                expiration=expiration
            )

            # Send transaction
            try:
                tx_id = str(uuid.uuid4())
                payload = json.dumps(
                    {
                        "msg_type": "tx_send_xrp",
                        "tx_id": tx_id,
                        "raw_tx": offer_create_tx.blob()
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
                    # Format offer description
                    gets_desc = f"{gets_amount} {gets_currency}"
                    if gets_currency != "XRP" and gets_issuer:
                        gets_desc += f" (Issuer: {gets_issuer})"
                    
                    pays_desc = f"{pays_amount} {pays_currency}"
                    if pays_currency != "XRP" and pays_issuer:
                        pays_desc += f" (Issuer: {pays_issuer})"
                    
                    offer_type = "Sell" if pays_currency == "XRP" or gets_currency != "XRP" else "Buy"
                    
                    response_msg = (
                        f"{offer_type} offer created successfully!\n"
                        f"Offering: {pays_desc}\n"
                        f"Requesting: {gets_desc}"
                    )
                    
                    if expiration:
                        exp_time = datetime.fromtimestamp(expiration).strftime('%Y-%m-%d %H:%M:%S')
                        response_msg += f"\nExpires: {exp_time}"
                    
                    return True, response_msg
                else:
                    return False, f"Offer creation failed: {response.tx_status}"
                
            except tx.XRPLReliableSubmissionException as e:
                return False, f"Transaction submission failed: {str(e)}"
                
        except Exception as e:
            return False, f"Error creating offer: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLOfferCreateTool.")


if __name__ == "__main__":
    # Example usage
    tool = XRPLOfferCreateTool()
    
    # Example 1: Sell XRP for USD
    example_input = "USD, rExampleIssuerAddress, 10, XRP, 50, ,"
    
    # Example 2: Buy XRP with USD
    # example_input = "XRP, , 50, USD, 10, rExampleIssuerAddress,"
    
    result = tool._run(example_input)
    print(result)