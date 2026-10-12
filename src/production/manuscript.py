"""Bounded, non-executing import of UTF-8 text and Word manuscripts."""
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree

MAX_BYTES = 20 * 1024 * 1024
MAX_CHARACTERS = 2_000_000


def extract(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Select a manuscript file smaller than 20 MiB.')
    suffix = path.suffix.lower()
    if suffix in ('.txt', '.md'):
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeError:
            raise ValueError('Save the manuscript as UTF-8 text, or use DOCX.') from None
    elif suffix == '.docx':
        with zipfile.ZipFile(path) as archive:
            entry = archive.getinfo('word/document.xml')
            if entry.file_size > MAX_BYTES:
                raise ValueError('The expanded Word document exceeds 20 MiB.')
            payload = archive.read(entry)
        if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
            raise ValueError('Word documents containing XML entity declarations are unsupported.')
        root = ElementTree.fromstring(payload)
        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        text = '\n\n'.join(''.join(n.text or '' for n in p.iter(ns + 't')) for p in root.iter(ns + 'p'))
    else:
        raise ValueError('Use a TXT, Markdown or DOCX manuscript. Export PDF/EPUB to UTF-8 text first; scanned pages need OCR.')
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text or '\x00' in text or len(text) > MAX_CHARACTERS:
        raise ValueError('The manuscript must contain readable text, up to 2 million characters.')
    return text


def chunks(text, limit=12000):
    """Cover every source character, preferring paragraph/sentence boundaries."""
    result = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            breaks = [m.end() for m in re.finditer(r'\n\n|(?<=[.!?])\s+', text[start:end])]
            if breaks and breaks[-1] > limit // 2:
                end = start + breaks[-1]
        result.append({'id': f'SRC-{len(result) + 1:04}', 'start': start, 'end': end, 'text': text[start:end]})
        start = end
    return result
