import re
import unicodedata

def generate_slug(text: str) -> str:
    """
    Converts a standard text string into a URL-friendly, lowercase slug.
    """
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower()
    text = re.sub(re.compile(r'[^a-z0-9]+'), '-', text)
    return text.strip('-')
