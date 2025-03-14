from typing import ClassVar, Union, Optional, Tuple
from ...exceptions import CryptoToolError
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from .utils import resolve_chain_id, get_chain_info, make_uniblock_request
from datetime import datetime
import re
import json
from typing import Dict, Any

logger = setup_logger(__name__, 'logs/uniblock_tool.log')

class UniblockTool(BaseCustomTool):
    """A comprehensive tool for blockchain interactions using Uniblock API."""
    name: ClassVar[str] = "UniblockTool"
    description: ClassVar[str] = """Blockchain interaction tool with multiple capabilities:
    1. Get token transfer history: 'transfers,chainId,wallet_address' or 'transfers,wallet_address'
    2. Get wallet transactions: 'transactions,chainId,wallet_address' or 'transactions,wallet_address'
    3. Get transaction details: 'transaction,chainId,tx_hash' or 'transaction,tx_hash'
    4. Get token balance: 'balance,chainId,wallet_address' or 'balance,wallet_address'
    Default chain is Ethereum (chainId=1) if not specified."""

    DEFAULT_CHAIN_ID: ClassVar[int] = 1  # Ethereum mainnet
    
    @staticmethod
    def is_valid_eth_address(value: str) -> bool:
        """Validate Ethereum address format."""
        if not value:
            return False
        return bool(re.match(r'^0x[a-fA-F0-9]{40}$', value))

    @staticmethod
    def is_valid_tx_hash(value: str) -> bool:
        """Validate transaction hash format."""
        if not value:
            return False
        return bool(re.match(r'^0x[a-fA-F0-9]{64}$', value))

    def _resolve_chain_id(self, chain_input: Optional[Union[str, int]] = None) -> int:
        """Resolve chain ID from various inputs."""
        if not chain_input:
            return self.DEFAULT_CHAIN_ID
            
        resolved_id = resolve_chain_id(chain_input)
        if resolved_id is not None:
            return resolved_id
            
        raise CryptoToolError(f"Unknown chain: {chain_input}")

    def parse_input(self, input_str: str) -> Tuple[str, int, str]:
        """
        Parse and validate input string.
        Returns: (command, chainId, parameter)
        """
        parts = [p.strip() for p in input_str.split(',')]
        if len(parts) < 2:
            raise CryptoToolError("Insufficient parameters provided")

        command = parts[0].lower()
        
        # Handle different input formats
        if len(parts) == 2:
            # Format: command,parameter (use default chain)
            chain_id = self.DEFAULT_CHAIN_ID
            parameter = parts[1]
        elif len(parts) == 3:
            # Format: command,chain,parameter
            try:
                chain_id = self._resolve_chain_id(parts[1])
            except Exception as e:
                raise CryptoToolError(f"Invalid chain identifier: {str(e)}")
            parameter = parts[2]
        else:
            raise CryptoToolError("Too many parameters provided")

        # Validate parameter format based on command
        if command in ['transfers', 'transactions', 'balance']:
            if not self.is_valid_eth_address(parameter):
                raise CryptoToolError(f"Invalid Ethereum address: {parameter}")
        elif command == 'transaction':
            if not self.is_valid_tx_hash(parameter):
                raise CryptoToolError(f"Invalid transaction hash: {parameter}")
        else:
            raise CryptoToolError(f"Unknown command: {command}")

        return command, chain_id, parameter.lower()


    def _run(self, input_str: str) -> str:
        """Process various blockchain-related commands."""
        try:
            command, chain_id, parameter = self.parse_input(input_str)
            logger.info(f"Executing {command} command for chain {chain_id}")

            if command == 'transfers':
                return self._get_token_transfers(chain_id, parameter)
            elif command == 'transactions':
                return self._get_wallet_transactions(chain_id, parameter)
            elif command == 'transaction':
                return self._get_transaction_details(chain_id, parameter)
            elif command == 'balance':
                return self._get_token_balance(chain_id, parameter)

        except CryptoToolError as e:
            error_msg = str(e)
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def _get_token_transfers(self, chain_id: int, wallet_address: str) -> str:
        """Get token transfer history for a wallet."""
        try:
            data = make_uniblock_request(
                "token/transfers",
                {
                    "chainId": chain_id,
                    "walletAddress": wallet_address.lower()
                }
            )
            
            if not data.get("transfers"):
                return True, "No transfer history found for this wallet address."
                
            transfers = data["transfers"]
            
            # Sort transfers by timestamp in descending order
            transfers.sort(
                key=lambda x: datetime.fromisoformat(
                    x.get('blockTimestamp', '2000-01-01T00:00:00.000Z').replace('Z', '+00:00')
                ),
                reverse=True
            )

            summary = [f"Found {len(transfers)} token transfers."]
            
            # Add recent transfers first
            summary.append("\nMost recent transfers:")
            for transfer in transfers[:5]:
                try:
                    amount = float(transfer.get('amount', 0)) / (10 ** int(transfer.get('decimals', '18')))
                    timestamp = datetime.fromisoformat(transfer.get('blockTimestamp', '').replace('Z', '+00:00'))
                    formatted_time = timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
                    
                    summary.append(
                        f"\n{transfer.get('symbol', 'Unknown')}:"
                        f" {amount:,.4f} tokens"
                        f" | From: {transfer.get('fromAddress', 'Unknown')[:10]}..."
                        f" | To: {transfer.get('toAddress', 'Unknown')[:10]}..."
                        f" | {formatted_time}"
                    )
                except Exception as e:
                    logger.error(f"Error formatting transfer: {str(e)}")
                    continue

            return True, "\n".join(summary)
            
        except Exception as e:
            logger.error(f"Error getting transfer history: {str(e)}", exc_info=True)
            return False, f"Error getting transfer history: {str(e)}"

    def _get_wallet_transactions(self, chain_id: int, wallet_address: str) -> str:
        """Get transaction history for a wallet."""
        try:
            data = make_uniblock_request(
                "transactions",
                {
                    "chainId": chain_id,
                    "walletAddress": wallet_address.lower(),
                    "includeRaw": "false"
                }
            )
            
            txs = data.get('transactions', [])
            if not txs:
                return True, "No transactions found for this wallet."

            summary = [f"Found {len(txs)} transactions for {wallet_address}"]
            
            # Add recent transactions
            summary.append("\nMost recent transactions:")
            for tx in txs[:5]:
                value = float(tx.get('value', '0')) / 1e18
                summary.append(
                    f"\nHash: {tx.get('transactionHash', 'Unknown')[:15]}..."
                    f" | Block: {tx.get('blockNumber', '0')}"
                    f" | Value: {value:.8f} ETH"
                    f" | From: {tx.get('fromAddress', 'Unknown')[:10]}..."
                    f" | To: {tx.get('toAddress', 'Unknown')[:10]}..."
                    f" | Gas Used: {tx.get('gasSpent', 'Unknown')}"
                    f" | Status: {'Success' if tx.get('successful', False) else 'Failed'}"
                )

            return True, "\n".join(summary)
        except Exception as e:
            return False, f"Error getting wallet transactions: {str(e)}"

    def _get_transaction_details(self, chain_id: int, tx_hash: str) -> str:
        """Get details for a specific transaction."""
        try:
            data = make_uniblock_request(
                "transaction",
                {
                    "chainId": chain_id,
                    "transactionHash": tx_hash.lower()
                }
            )
            
            if not data:
                return True, "No transaction details found."
                
            details = [
                "Transaction Details:",
                f"Hash: {data.get('txHash', 'Unknown')}",
                f"Block Number: {data.get('blockNumber', 'Unknown')}",
                f"From: {data.get('fromAddress', 'Unknown')}",
                f"To: {data.get('toAddress', 'Unknown')}",
                f"Value: {float(data.get('value', '0')) / 1e18:.8f} ETH",
                f"Gas Limit: {data.get('gasLimit', 'Unknown')}",
                f"Gas Used: {data.get('gasSpent', 'Unknown')}",
                f"Gas Price: {data.get('gasPrice', 'Unknown')} wei"
            ]
            
            # Add log information if available
            if data.get('logs'):
                details.append("\nTransaction Logs:")
                for log in data['logs']:
                    details.append(f"\nContract: {log.get('address', 'Unknown')}")
                    details.append(f"Topics: {', '.join(log.get('topics', []))}")
                    details.append(f"Data: {log.get('data', 'None')}")
                    
            return True, "\n".join(details)
        except Exception as e:
            return False, f"Error getting transaction details: {str(e)}"

    def _get_token_balance(self, chain_id: int, wallet_address: str) -> str:
        """Get token balances for a wallet."""
        try:
            data = make_uniblock_request(
                "token/balance",
                {
                    "chainId": chain_id,
                    "walletAddress": wallet_address.lower(),
                    "includePrice": "true"
                }
            )
            
            if not data.get('balances'):
                return True, "No token balances found for this wallet."
                
            balances = data['balances']
            summary = [f"Token balances for {wallet_address}:"]
            
            for balance in balances:
                token_amount = float(balance.get('balance', 0)) / (10 ** int(balance.get('decimals', '18')))
                summary.append(
                    f"\n{balance.get('name', 'Unknown')} ({balance.get('symbol', 'Unknown')}):"
                    f" {token_amount:,.4f} tokens"
                )
                
            return True, "\n".join(summary)
        except Exception as e:
            return False, f"Error getting token balances: {str(e)}"