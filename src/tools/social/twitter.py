from typing import ClassVar, Dict, Optional, Union
import tweepy
import os
from pydantic import Field
from ..base import BaseCustomTool
from ...utils.logger import setup_logger
from langchain.tools import BaseTool

logger = setup_logger(__name__, 'logs/twitter.log')

class TwitterTool(BaseCustomTool, BaseTool):
    """Tool for interacting with Twitter API."""
    name: ClassVar[str] = "twitter"
    description: ClassVar[str] = (
        "Interact with Twitter. Available commands: "
        "read_tweet <tweet_id>, "
        "search_tweets <query>, "
        "post_tweet <content>, "
        "retweet <tweet_id>, "
        "delete_tweet <tweet_id>, "
        "user_tweets <username> [max_results]"
    )
    
    client: tweepy.Client = Field(default_factory=lambda: None)

    def __init__(self, **data):
        """Initialize Twitter API client."""
        super().__init__(**data)
        self.client = self._setup_client()
        
    def _setup_client(self) -> tweepy.Client:
        """Set up Twitter API client with credentials."""
        try:
            client = tweepy.Client(
                bearer_token=os.getenv('TWITTER_BEARER_TOKEN'),
                consumer_key=os.getenv('TWITTER_API_KEY'),
                consumer_secret=os.getenv('TWITTER_API_SECRET'),
                access_token=os.getenv('TWITTER_ACCESS_TOKEN'),
                access_token_secret=os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
            )
            return client
        except Exception as e:
            logger.error(f"Error setting up Twitter client: {str(e)}", exc_info=True)
            raise

    def _parse_command(self, tool_input: str) -> tuple[str, str]:
        """Parse the command and content from tool input."""
        try:
            command, content = tool_input.split(' ', 1)
            return command.strip().lower(), content.strip()
        except ValueError:
            raise ValueError("Invalid input format. Use: <command> <content>")

    def _read_tweet(self, tweet_id: str) -> str:
        """Fetch a specific tweet by ID."""
        try:
            tweet = self.client.get_tweet(
                tweet_id, 
                expansions=['author_id'],
                tweet_fields=['created_at', 'text']
            )
            if not tweet.data:
                return "Tweet not found."
            return tweet.data.text
        except Exception as e:
            logger.error(f"Error reading tweet {tweet_id}: {str(e)}", exc_info=True)
            return f"Error reading tweet: {str(e)}"

    def _search_tweets(self, query: str) -> str:
        """Search for tweets matching a query."""
        try:
            tweets = self.client.search_recent_tweets(
                query=query,
                max_results=10,
                tweet_fields=['created_at', 'text']
            )
            if not tweets.data:
                return "No tweets found."
            
            results = []
            for tweet in tweets.data:
                results.append(f"- {tweet.text}\n")
            return "\n".join(results)
        except Exception as e:
            logger.error(f"Error searching tweets: {str(e)}", exc_info=True)
            return f"Error searching tweets: {str(e)}"

    def _get_user_tweets(self, content: str) -> str:
        """Get tweets from a specific user."""
        try:
            # Parse username and optional max_results
            parts = content.split()
            username = parts[0].strip('@')  # Remove @ if present
            
            # Handle max_results parameter
            max_results = 100  # default value
            if len(parts) > 1:
                try:
                    max_results = int(parts[1])
                except ValueError:
                    logger.warning(f"Invalid max_results value: {parts[1]}. Using default of 100.")
                    max_results = 100

            # First get the user ID
            user = self.client.get_user(username=username)
            if not user.data:
                return False, f"User @{username} not found."

            user_id = user.data.id

            # Get user's tweets
            tweets = self.client.get_users_tweets(
                id=user_id,
                max_results=min(max_results, 100),  # API limit is 100
                tweet_fields=['created_at', 'text'],
                exclude=['retweets', 'replies']
            )

            if not tweets.data:
                return True, f"No tweets found for @{username}."

            results = []
            for tweet in tweets.data:
                created_at = tweet.created_at.strftime('%Y-%m-%d %H:%M:%S') if tweet.created_at else 'Unknown date'
                results.append(f"[{created_at}] {tweet.text}\n")

            return True, "\n".join(results)

        except Exception as e:
            logger.error(f"Error getting user tweets: {str(e)}", exc_info=True)
            return False, f"Error getting user tweets: {str(e)}"

    def _post_tweet(self, content: str) -> str:
        """Post a new tweet."""
        try:
            tweet = self.client.create_tweet(text=content)
            if tweet and tweet.data:
                return f"Tweet posted successfully. ID: {tweet.data['id']}"
            return "Error: Tweet could not be posted"
        except Exception as e:
            logger.error(f"Error posting tweet: {str(e)}", exc_info=True)
            return f"Error posting tweet: {str(e)}"

    def _delete_tweet(self, tweet_id: str) -> str:
        """Delete a specific tweet."""
        try:
            result = self.client.delete_tweet(tweet_id)
            if result and result.data and result.data.get('deleted', False):
                return f"Successfully deleted tweet {tweet_id}"
            return f"Error: Could not delete tweet {tweet_id}"
        except Exception as e:
            logger.error(f"Error deleting tweet {tweet_id}: {str(e)}", exc_info=True)
            return f"Error deleting tweet: {str(e)}"

    def _retweet(self, tweet_id: str) -> str:
        """Retweet a specific tweet."""
        try:
            result = self.client.retweet(tweet_id)
            if result and result.data:
                return f"Successfully retweeted tweet {tweet_id}"
            return f"Error: Could not retweet tweet {tweet_id}"
        except Exception as e:
            logger.error(f"Error retweeting tweet {tweet_id}: {str(e)}", exc_info=True)
            return f"Error retweeting tweet: {str(e)}"

    def _run(self, tool_input: str) -> str:
        """Execute the Twitter tool."""
        logger.info(f"Running Twitter tool with input: {tool_input}")
        
        try:
            command, content = self._parse_command(tool_input)
            
            if command == "read_tweet":
                return self._read_tweet(content)
            elif command == "search_tweets":
                return self._search_tweets(content)
            elif command == "post_tweet":
                return self._post_tweet(content)
            elif command == "retweet":
                return self._retweet(content)
            elif command == "user_tweets":
                return self._get_user_tweets(content)
            elif command == "delete_tweet":
                return self._delete_tweet(content)
            else:
                return f"Unknown command: {command}. Available commands: read_tweet, search_tweets, post_tweet, retweet, delete_tweet, user_tweets"
                
        except Exception as e:
            logger.error(f"Error executing Twitter tool: {str(e)}", exc_info=True)
            return f"Error: {str(e)}"