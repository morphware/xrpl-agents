import xrpl
from xrpl.clients import JsonRpcClient
import os
import sys
from typing import ClassVar
from langchain.tools import BaseTool
from config import Config
from xrpl.models.requests import AccountInfo

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from base import BaseCustomTool

class XRPLAccountInfoTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving account information from the XRPL.
    Provide a valid XRPL account address as input.
    """
    name: ClassVar[str] = "XRPLAccountInfo"
    description: ClassVar[str] = (
        "Retrieve account information from the XRPL. "
        "Input should be a valid XRPL account address."
    )
    def _run(self, tool_input: str) -> str:
        client = JsonRpcClient("https://s.altnet.rippletest.net:51234")
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
                return f"No account data found for account {tool_input}."
            return str(account_info)
        except Exception as e:
            return f"Error retrieving account info: {str(e)}"

    async def _arun(self, tool_input: str) -> str:
        raise NotImplementedError("Async execution is not supported for XRPLAccountInfoTool.")

if __name__ == "__main__":
    tool = XRPLAccountInfoTool()
    account_address = "rHzykWRVdAfEHk6c5fQxyYYHF9waQXN5Dz"
    result = tool._run(account_address)
    print(result)