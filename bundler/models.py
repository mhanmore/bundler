from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TOCEntry:
    """A single row in the bundle index."""

    entry_type: str               # 'section_heading' | 'heading' | 'document'
    title: str
    file_name: Optional[str] = None     # source PDF filename; None for headings and placeholders
    page_number: Optional[int] = None   # set by pagination calculator; None = placeholder
    dest_name: Optional[str] = None     # PDF named destination, used by merge module
