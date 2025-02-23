import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models import AccountInfo
from xrpl.wallet import Wallet
from ...config import Config
from ..base import BaseCustomTool
from xrpl.account import get_latest_transaction

class XRPLGetLatestTransactionTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving the latest transaction of an XRPL account.
    Input should be a valid XRPL account address.
    """
    name: ClassVar[str] = "XRPLGetLatestTransaction"
    description: ClassVar[str] = (
        "Retrieve the latest transaction of an XRPL account. "
        "Input should be the account address."
    )

    def __init__(self):
        super().__init__()

    def _validate_address(self, address: str) -> bool:
        """Validate if the input looks like a proper XRPL address."""
        return (
            isinstance(address, str) and 
            address.startswith('r') and 
            len(address) >= 25 and 
            len(address) <= 35
        )
    
    def _get_latest_transaction(self, address: str) -> tuple[dict, str]:
        """
        Get the latest transaction for an XRPL address.
        Returns tuple of (transaction_data, error_message)
        """
        try:
            # Create account info request
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            transaction = get_latest_transaction(account=address, client=client)
            
            return (transaction, "")
                
        except Exception as e:
            return (None, str(e))
    
    def _run(self, tool_input: str) -> str:
        """
        Run the tool to get the latest transaction for an address.
        Args:
            tool_input (str): XRPL account address
        Returns:
            str: Formatted transaction response or error message
        """
        # Clean the input
        if tool_input == "user_account_address":
            address = Config.XRP_WALLET.address
        else:
            address = tool_input.strip()
        
        # Validate address format
        if not self._validate_address(address):
            return False, f"Invalid XRPL address format: {address}"

        # Get the balance
        transaction, error = self._get_latest_transaction(address)
        
        # Handle the response
        if error:
            return False, f"Error retrieving latest transaction for {address}: {error}"
        
        return True, f"Latest transaction for account {address}: {transaction}"
    
    async def _arun(self, tool_input: str) -> str:
        """Async execution is not supported."""
        raise NotImplementedError("Async execution is not supported for XRPLGetLatestTransactionTool.")

if __name__ == "__main__":
    tool = XRPLGetLatestTransactionTool()
    # Example usage:
    account_address = "rHzykWRVdAfEHk6c5fQxyYYHF9waQXN5Dz"
    result = tool._run(account_address)
    print(result)