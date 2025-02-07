from typing import ClassVar
import re
from youtube_transcript_api import YouTubeTranscriptApi
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/youtube.log')

class YouTubeTool(BaseCustomTool, BaseTool):
    """Tool for getting YouTube video transcripts."""
    name: ClassVar[str] = "youtube_transcript"
    description: ClassVar[str] = "Get transcript from a YouTube video URL. The entire raw transcript will be returned verbatim, with no summary."
    
    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from various YouTube URL formats."""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
            r'(?:embed\/)([0-9A-Za-z_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _run(self, tool_input: str) -> str:
        """Execute the YouTube transcript tool."""
        logger.info(f"Getting transcript for YouTube URL: {tool_input}")
        
        try:
            video_id = self._extract_video_id(tool_input)
            
            if not video_id:
                logger.warning(f"Invalid YouTube URL format: {tool_input}")
                return "Invalid YouTube URL format"

            transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
            if not transcript_data:
                logger.warning(f"No transcript available for video: {video_id}")
                return "No transcript available for this video."
                
            formatted_text = " ".join(entry['text'].strip() for entry in transcript_data)
            logger.info(f"Returning transcript for video {video_id}")
            return formatted_text
                
        except Exception as e:
            logger.error(f"Error getting YouTube transcript: {str(e)}", exc_info=True)
            return f"Error getting transcript: {str(e)}"