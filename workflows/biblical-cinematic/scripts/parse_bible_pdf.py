"""
Parse the 1611 KJV Bible (with Apocrypha) PDF into structured JSON.

Usage:
    python workflows/biblical-cinematic/scripts/parse_bible_pdf.py

Output:
    workflows/biblical-cinematic/assets/bible_chapters.json
"""

import json
import re
import fitz  # PyMuPDF
from pathlib import Path

PDF_PATH = Path(__file__).resolve().parents[3] / "KJVwA" / "1611KjvW_apocrypha.pdf"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "assets" / "bible_chapters.json"

# TOC: (book_name, content_page_start)
# Content page 1 = PDF index 21 → offset = 20
PDF_OFFSET = 20

BOOKS = [
    ("Genesis", 1),
    ("Exodus", 31),
    ("Leviticus", 57),
    ("Numbers", 77),
    ("Deuteronomy", 103),
    ("Joshua", 125),
    ("Judges", 141),
    ("Ruth", 157),
    ("1 Samuel", 159),
    ("2 Samuel", 179),
    ("1 Kings", 195),
    ("2 Kings", 215),
    ("1 Chronicles", 233),
    ("2 Chronicles", 251),
    ("Ezra", 273),
    ("Nehemiah", 279),
    ("Esther", 289),
    ("Job", 295),
    ("Psalms", 309),
    ("Proverbs", 395),
    ("Ecclesiastes", 407),
    ("Song of Songs", 413),
    ("Isaiah", 417),
    ("Jeremiah", 447),
    ("Lamentations", 479),
    ("Ezekiel", 483),
    ("Daniel", 513),
    ("Hosea", 523),
    ("Joel", 527),
    ("Amos", 529),
    ("Obadiah", 533),
    ("Jonah", 535),
    ("Micah", 537),
    ("Nahum", 541),
    ("Habakkuk", 543),
    ("Zephaniah", 545),
    ("Haggai", 547),
    ("Zechariah", 549),
    ("Malachi", 555),
    # Apocrypha
    ("Tobit", 559),
    ("Judith", 567),
    ("Esther (Greek)", 579),
    ("Wisdom", 585),
    ("Sirach", 599),
    ("Baruch", 635),
    ("Letter of Jeremiah", 639),
    ("Prayer of Azariah and the Song of the Three Jews", 641),
    ("Susanna", 643),
    ("Bel and the Dragon", 645),
    ("1 Maccabees", 647),
    ("2 Maccabees", 675),
    ("1 Esdras", 693),
    ("2 Esdras", 707),
    ("Prayer of Manassah", 731),
    # New Testament
    ("Matthew", 733),
    ("Mark", 753),
    ("Luke", 765),
    ("John", 785),
    ("Acts", 801),
    ("Romans", 821),
    ("1 Corinthians", 829),
    ("2 Corinthians", 837),
    ("Galatians", 843),
    ("Ephesians", 847),
    ("Philippians", 851),
    ("Colossians", 853),
    ("1 Thessalonians", 855),
    ("2 Thessalonians", 857),
    ("1 Timothy", 859),
    ("2 Timothy", 861),
    ("Titus", 863),
    ("Philemon", 865),
    ("Hebrews", 867),
    ("James", 873),
    ("1 Peter", 875),
    ("2 Peter", 877),
    ("1 John", 879),
    ("2 John", 881),
    ("3 John", 883),
    ("Jude", 885),
    ("Revelation", 887),
]


def extract_book_text(doc, start_page, end_page):
    """Extract all text for a book from start_page to end_page (content pages)."""
    text = ""
    for content_page in range(start_page, end_page + 1):
        pdf_idx = content_page + PDF_OFFSET
        if pdf_idx >= len(doc):
            break
        page_text = doc[pdf_idx].get_text()
        # Remove page headers like "Page 123" and book name headers
        # These appear at top of pages
        lines = page_text.split("\n")
        filtered = []
        for line in lines:
            stripped = line.strip()
            # Skip "Page NNN" lines
            if re.match(r'^Page \d+$', stripped):
                continue
            filtered.append(line)
        text += "\n".join(filtered) + "\n"
    return text


def split_into_chapters(text):
    """Split book text into chapters using {chapter:verse} markers."""
    chapters = {}

    # Find all verse markers {C:V}
    # Split text by chapter boundaries
    # A new chapter starts when we see {N:1} where N is different from current chapter

    # First, find all {C:V} markers and their positions
    pattern = re.compile(r'\{(\d+):(\d+)\}')

    # Replace verse markers and track chapter boundaries
    parts = pattern.split(text)
    # parts = [text_before, ch, vs, text_after, ch, vs, text_after, ...]

    if len(parts) < 4:
        # No verse markers found, return all text as chapter 1
        cleaned = clean_text(text)
        if cleaned.strip():
            chapters["1"] = cleaned.strip()
        return chapters

    current_chapter = None
    chapter_texts = {}

    i = 0
    # Skip text before first verse marker
    i = 1  # Start at first chapter number

    while i < len(parts) - 2:
        ch = parts[i]
        vs = parts[i + 1]
        verse_text = parts[i + 2]

        if ch not in chapter_texts:
            chapter_texts[ch] = ""
        chapter_texts[ch] += verse_text

        i += 3

    # Clean each chapter
    for ch, text in chapter_texts.items():
        cleaned = clean_text(text)
        if cleaned.strip():
            chapters[ch] = cleaned.strip()

    return chapters


def clean_text(text):
    """Clean text: remove brackets, normalize whitespace."""
    # Remove [brackets] but keep content inside
    text = re.sub(r'\[([^\]]*)\]', r'\1', text)
    # Remove any remaining verse markers (shouldn't be any)
    text = re.sub(r'\{\d+:\d+\}', '', text)
    # Normalize whitespace - join word-wrapped lines
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def remove_book_header(text, book_name):
    """Remove the book title/subtitle that appears at the start."""
    lines = text.strip().split("\n")
    # Skip initial lines that are book titles/subtitles
    # These are typically short lines at the very start before {1:1}
    # Find where {1:1} starts and only keep from there
    first_verse = text.find("{1:1}")
    if first_verse >= 0:
        return text[first_verse:]
    return text


def main():
    doc = fitz.open(str(PDF_PATH))
    print(f"PDF loaded: {len(doc)} pages")

    result = {"books": []}
    total_chapters = 0

    for i, (book_name, start_page) in enumerate(BOOKS):
        # End page is one before next book's start (or end of PDF)
        if i + 1 < len(BOOKS):
            end_page = BOOKS[i + 1][1] - 1
        else:
            end_page = len(doc) - PDF_OFFSET - 1

        raw_text = extract_book_text(doc, start_page, end_page)
        raw_text = remove_book_header(raw_text, book_name)
        chapters = split_into_chapters(raw_text)

        book_entry = {
            "name": book_name,
            "chapters": chapters
        }
        result["books"].append(book_entry)
        total_chapters += len(chapters)
        print(f"  {book_name}: {len(chapters)} chapters")

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== STATS ===")
    print(f"Books: {len(result['books'])}")
    print(f"Total chapters: {total_chapters}")
    print(f"Output: {OUTPUT_PATH}")

    # Sample text
    genesis = result["books"][0]
    print(f"\n=== Genesis 1 (first 300 chars) ===")
    print(genesis["chapters"].get("1", "NOT FOUND")[:300])

    # Find 1 Maccabees
    for book in result["books"]:
        if book["name"] == "1 Maccabees":
            print(f"\n=== 1 Maccabees 1 (first 300 chars) ===")
            print(book["chapters"].get("1", "NOT FOUND")[:300])
            break

    doc.close()


if __name__ == "__main__":
    main()
