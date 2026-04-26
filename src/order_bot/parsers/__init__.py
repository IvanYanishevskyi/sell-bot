from order_bot.parsers.llm_file_parser import LLMFileParser
from order_bot.parsers.models import ParseError, ParseResult

FileParser = LLMFileParser

__all__ = ["LLMFileParser", "FileParser", "ParseError", "ParseResult"]
