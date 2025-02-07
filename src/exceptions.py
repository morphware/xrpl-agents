class ToolError(Exception):
    """Base exception for tool-related errors"""
    pass

class CryptoToolError(ToolError):
    """Exception for cryptocurrency tool errors"""
    pass

class MediaToolError(Exception):
    """Base exception class for media tool errors."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)