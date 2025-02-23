import xrpl
from xrpl.clients import JsonRpcClient
import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from ...config import Config
from xrpl.models.requests import AccountInfo
from ..base import BaseCustomTool

class XRPLAccountInfoTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving account information from the XRPL.
    Provide a valid XRPL account address as input.
    """
    name: ClassVar[str] = "XRPLAccountInfo"
    description: ClassVar[str] = (
        "Retrieve account information from the XRPL. "
        "Input should be a valid XRPL account address."
        "If the input is for users address, input 'user_account_address'."
        "This does not get token balances, only XRP balance."

    )
    def _run(self, tool_input: str) -> str:
        
        client = JsonRpcClient(Config.XRPL_ENDPOINT)
         # Clean the input
        if "user_account_address" in tool_input.lower():
            tool_input = Config.XRP_WALLET.address
        else:
            tool_input = tool_input.strip()
        try:
            request = AccountInfo(
                account=tool_input,
                strict=True,
                ledger_index="current",
                queue=True
            )
            response = client.request(request)
            account_info = response.result.get("account_data", {})
            if not account_info:
                return False, f"No account data found for account {tool_input}."
            else:
                account_info["Balance"] = float(account_info.get("Balance", 0)) / 1_000_000
            return True, str(account_info)
        except Exception as e:
            return False, f"Error retrieving account info: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAccountInfoTool.")

if __name__ == "__main__":
    tool = XRPLAccountInfoTool()
    account_address = "rHzykWRVdAfEHk6c5fQxyYYHF9waQXN5Dz"
    result = tool._run(account_address)
    print(result)