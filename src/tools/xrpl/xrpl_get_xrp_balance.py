import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from xrpl.clients import JsonRpcClient
from xrpl.models import AccountInfo
from xrpl.wallet import Wallet
from ...config import Config
from ..base import BaseCustomTool

class XRPLGetXRPBalanceTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving the XRP balance of an XRPL account.
    Input should be a valid XRPL account address.
    """
    name: ClassVar[str] = "XRPLGetXRPBalance"
    description: ClassVar[str] = (
        "Retrieve the XRP balance of an XRPL account. "
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

    def _get_balance(self, address: str) -> tuple[float, str]:
        """
        Get the balance for an XRPL address.
        Returns tuple of (balance_in_xrp, error_message)
        """
        try:
            # Create account info request
            acct_info = AccountInfo(
                account=address,
                ledger_index="validated"
            )
            
            # Send request and get response
            client = JsonRpcClient(Config.XRPL_ENDPOINT)
            response = client.request(acct_info)
            
            # Extract balance from account data
            if response.status == "success" and "account_data" in response.result:
                balance_drops = int(response.result["account_data"]["Balance"])
                return (balance_drops / 1_000_000, "")
            else:
                return (0.0, "No account data found")
                
        except Exception as e:
            return (0.0, str(e))

    def _run(self, tool_input: str) -> str:
        """
        Run the tool to get XRP balance for an address.
        Args:
            tool_input (str): XRPL account address
        Returns:
            str: Formatted balance response or error message
        """
        # Clean the input
        if "user_account_address" in tool_input:
            address = Config.XRP_WALLET.address
        else:
            address = tool_input.strip()
        
        # Validate address format
        if not self._validate_address(address):
            return False, f"Invalid XRPL address format: {address}"

        # Get the balance
        balance, error = self._get_balance(address)
        
        # Handle the response
        if error:
            return False, f"Error retrieving balance for {address}: {error}"
        
        return True, f"Balance for account {address}: {balance:.6f} XRP"

    async def _arun(self, tool_input: str) -> str:
        """Async execution is not supported."""
        raise NotImplementedError("Async execution is not supported for XRPLGetXRPBalanceTool.")

if __name__ == "__main__":
    tool = XRPLGetXRPBalanceTool()
    # Example usage:
    account_address = "rHzykWRVdAfEHk6c5fQxyYYHF9waQXN5Dz"
    result = tool._run(account_address)
    print(result)