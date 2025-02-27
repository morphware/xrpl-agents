from typing import ClassVar
from xrpl.clients import JsonRpcClient
from xrpl.models.requests.account_lines import AccountLines
from ....config import Config
from ...base import BaseCustomTool
from langchain.tools import BaseTool

class XRPLGetWalletTokenBalancesTool(BaseCustomTool, BaseTool):
    """
    Tool for retrieving token balances for an XRPL wallet.
    Input can be either:
      - A single wallet address, e.g.: "rExampleWalletAddress1234567890"
      - A comma-separated string "TOKEN, wallet_address" to filter by a specific token.
    The tool queries the account's trust lines and returns details for all tokens or the matching token.
    This does not include XRP balance, only trust lines for other tokens.
    """
    name: ClassVar[str] = "XRPLGetWalletTokenBalances"
    description: ClassVar[str] = (
        "Retrieve the token balances of an XRPL wallet. "
        "Input can be either a wallet address or 'TOKEN, wallet_address' to filter the results."
    )

    def _validate_address(self, address: str) -> bool:
        """Check if address appears to be a valid XRPL address."""
        if "user_account_address" in address.lower():
            address = Config.XRP_WALLET.address
        return isinstance(address, str) and address.startswith("r") and 25 <= len(address) <= 35
    
    def _hex_to_currency(self, code: str) -> str:
        if len(code) == 40:
            try:
                code_bytes = bytes.fromhex(code)
                converted = code_bytes.decode("utf-8").rstrip("\0").strip()
                if converted:
                    return converted
            except Exception:
                pass
        return code

    def _run(self, tool_input: str) -> str:
        parts = [p.strip() for p in tool_input.split(",") if p.strip()]
        # If only one part is provided, assume it's the wallet address.
        if len(parts) == 1:
            wallet_address = parts[0]
            token_code = None
        elif len(parts) == 2:
            token_code = parts[0].upper()
            wallet_address = parts[1]
        else:
            return False, "Input must be either a wallet address or 'TOKEN, wallet_address'."
        if "user_account_address" in wallet_address.lower():
            wallet_address = Config.XRP_WALLET.address

        if not self._validate_address(wallet_address):
            return False, f"Invalid XRPL wallet address: {wallet_address}"
        
        client = JsonRpcClient(Config.XRPL_ENDPOINT)
        account_lines_request = AccountLines(
            account=wallet_address,
            ledger_index="validated"
        )
        
        try:
            response = client.request(account_lines_request)
            lines = response.result.get("lines", [])
            if not lines:
                return False, f"No trust lines found for account {wallet_address}."
            
            for line in lines:
                line["currency"] = self._hex_to_currency(line.get("currency", ""))
            
            # If a token filter was provided, filter the trust lines.
            if token_code:
                lines = [line for line in lines if line.get("currency", "").upper() == token_code]
                if not lines:
                    return False, f"No balance found for token {token_code} in wallet {wallet_address}."
            
            result_lines = []
            for line in lines:
                balance = line.get("balance", "0")
                if balance == "0":
                    continue
                issuer = line.get("account", "Unknown")
                limit = line.get("limit", "N/A")
                currency = line.get("currency", "Unknown")
                result_lines.append(f"Issuer: {issuer}, Balance: {balance} {currency}")
            
            return True, "\n".join(result_lines)
        except Exception as e:
            return False, f"Error retrieving token balance: {str(e)}"

if __name__ == "__main__":
    tool = XRPLGetWalletTokenBalancesTool()
    # Example usage:
    # With token filter: "USD, rExampleWalletAddress1234567890"
    # Without token filter: "rExampleWalletAddress1234567890"
    user_input = "rExampleWalletAddress1234567890"
    result = tool._run(user_input)
    print(result)