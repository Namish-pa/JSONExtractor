from typing import Protocol

class DocumentExtractor(Protocol):
    """
    Protocol for extracting text from document files.
    """
    def extract_text(self, file_bytes: bytes) -> str:
        ...
