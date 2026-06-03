"""
Markdown Parser — Generic markdown content extraction
Handles line parsing, section detection, text normalization.
No debate-specific logic (that's in debate_parser.py).
"""

import re
from typing import List, Tuple, Optional, Dict


class MarkdownParser:
    """
    Generic markdown parser for extracting structured content.
    
    Responsibilities:
    - Parse raw markdown into lines
    - Detect section headers
    - Extract text from sections
    - Normalize whitespace
    - Handle formatting markers
    """
    
    # Section header patterns
    SECTION_PATTERN = re.compile(r'^#{1,6}\s+(.+?)(?:\s*\{.*\})?\s*$', re.MULTILINE)
    BOLD_PATTERN = re.compile(r'\*\*(.+?)\*\*')
    ITALIC_PATTERN = re.compile(r'\*(.+?)\*')
    CODE_PATTERN = re.compile(r'`(.+?)`')
    
    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text:
        - Remove extra whitespace
        - Strip leading/trailing spaces
        - Handle newlines
        """
        if not text:
            return ""
        
        # Collapse multiple spaces
        text = re.sub(r' {2,}', ' ', text)
        # Normalize newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
    
    @staticmethod
    def remove_formatting(text: str) -> str:
        """
        Remove markdown formatting markers:
        - **bold** → bold
        - *italic* → italic
        - `code` → code
        """
        if not text:
            return ""
        
        text = MarkdownParser.BOLD_PATTERN.sub(r'\1', text)
        text = MarkdownParser.ITALIC_PATTERN.sub(r'\1', text)
        text = MarkdownParser.CODE_PATTERN.sub(r'\1', text)
        return text
    
    @staticmethod
    def extract_sections(text: str) -> Dict[str, str]:
        """
        Extract sections from markdown by header.
        
        Returns:
            Dict mapping section name to content
        """
        sections = {}
        current_section = "preamble"
        current_content = ""
        
        for line in text.split('\n'):
            match = MarkdownParser.SECTION_PATTERN.match(line)
            if match:
                # Save previous section
                if current_content.strip():
                    sections[current_section] = MarkdownParser.normalize_text(current_content)
                
                # Start new section
                current_section = match.group(1).strip().lower()
                current_content = ""
            else:
                current_content += line + "\n"
        
        # Save last section
        if current_content.strip():
            sections[current_section] = MarkdownParser.normalize_text(current_content)
        
        return sections
    
    @staticmethod
    def parse_lines(
        text: str,
        default_section: str = "propose",
        skip_empty: bool = True
    ) -> List[Tuple[str, str]]:
        """
        Parse markdown into (section, line) tuples.
        
        Each non-empty line is tagged with its section.
        Example:
            "## Propose\nText here\n## Oppose\nMore text"
            →
            [("propose", "Text here"), ("oppose", "More text")]
        
        Args:
            text: Raw markdown content
            default_section: Section name for content before first header
            skip_empty: If True, skip empty lines
        
        Returns:
            List of (section, line) tuples
        """
        lines = []
        current_section = default_section
        
        for raw_line in text.split('\n'):
            # Check for section header
            match = MarkdownParser.SECTION_PATTERN.match(raw_line)
            if match:
                current_section = match.group(1).strip().lower()
                continue
            
            # Process content line
            line = MarkdownParser.normalize_text(raw_line)
            
            if skip_empty and not line:
                continue
            
            lines.append((current_section, line))
        
        return lines
    
    @staticmethod
    def extract_spoken_text(text: str) -> str:
        """
        Extract text meant to be spoken (remove formatting, annotations).
        
        Removes:
        - Markdown formatting (**bold**, *italic*, `code`)
        - Comments in braces {like this}
        - Multiple spaces
        """
        if not text:
            return ""
        
        # Remove comments in braces
        text = re.sub(r'\{[^}]*\}', '', text)
        
        # Remove formatting
        text = MarkdownParser.remove_formatting(text)
        
        # Normalize
        text = MarkdownParser.normalize_text(text)
        
        return text
    
    @staticmethod
    def estimate_duration(text: str, wpm: int = 150) -> float:
        """
        Estimate spoken duration based on word count.
        
        Args:
            text: Text to estimate
            wpm: Words per minute (default 150 = conversational)
        
        Returns:
            Estimated duration in seconds
        """
        if not text:
            return 0.0
        
        word_count = len(text.split())
        minutes = word_count / wpm
        seconds = minutes * 60
        return seconds
    
    @staticmethod
    def split_by_word_count(text: str, target_words: int) -> List[str]:
        """
        Split text into chunks of approximately target_words.
        Respects word boundaries.
        
        Args:
            text: Text to split
            target_words: Target word count per chunk
        
        Returns:
            List of text chunks
        """
        if not text:
            return []
        
        words = text.split()
        if len(words) <= target_words:
            return [text]
        
        chunks = []
        current_chunk = []
        
        for word in words:
            current_chunk.append(word)
            if len(current_chunk) >= target_words:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    @staticmethod
    def extract_timestamp_ranges(text: str) -> List[Tuple[float, float, str]]:
        """
        Extract time ranges from text like "[0:30-0:45] Some text".
        
        Returns:
            List of (start_seconds, end_seconds, text) tuples
        """
        pattern = r'\[(\d+):(\d+)-(\d+):(\d+)\]\s*(.+)'
        ranges = []
        
        for match in re.finditer(pattern, text):
            start_min, start_sec, end_min, end_sec, content = match.groups()
            start = int(start_min) * 60 + int(start_sec)
            end = int(end_min) * 60 + int(end_sec)
            ranges.append((float(start), float(end), content.strip()))
        
        return ranges
