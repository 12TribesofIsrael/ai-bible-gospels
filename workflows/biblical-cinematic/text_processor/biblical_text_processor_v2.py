#!/usr/bin/env python3
"""
Biblical Text Processor V2 - Multi-Section Generator
Automatically breaks large biblical text into multiple 1000-word sections for video generation.
KJV-Preserving: Keeps thou/thee/ye/unto/shalt grammar while fixing OCR/narration issues.
Optional AI: Sentence restructuring for optimal ElevenLabs narration (10-22 words per sentence).

Usage: Run the script to process text from 'Input' file into multiple video-ready sections.
Output: All processed sections saved in 'Output' file with clear separators.
Version: 1.4.0 - KJV Narration Mode + AI Polish + Comprehensive 1611 Normalization (95+ patterns)
"""

import re
import sys
import os
import json
from typing import Optional

# AI Processing (OpenAI API)
try:
    import openai
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# KJV Narration Editor Prompt for AI
KJV_NARRATION_PROMPT = """You are a KJV narration editor preparing Bible passages for ElevenLabs text-to-speech (audiobook-style).
Make the text easy to speak and easy for captions while keeping the King James feel.

DO NOT CHANGE these KJV words: thou, thee, thy, thine, ye, unto, shalt, hast, didst, art. Keep them exactly.

Critical fixes (must):
1) Never output "vs". If the input contains "vs", replace it with "us" (deliver us, upon us, done to us).
2) Remove verse numbers and number/word glue (example: "2Blessed" → "Blessed").
3) Keep all names and places unchanged (Azarias, Ananias, Misael, Jerusalem, Cherubims, Chaldeans, etc.).

ElevenLabs narration rules:
4) Break long sentences into shorter sentences (target 10–22 words).
5) Prefer periods over colons/semicolons. Use commas lightly.
6) Keep meaning EXACTLY the same—no added commentary or explanation.
7) Fix OCR spellings that hurt narration, but keep KJV vocabulary and reverence. Make only these kinds of fixes:
   - vp → up
   - vpon → upon
   - deliuer → deliver
   - iudgement(s) → judgment(s)
   - heauen → heaven
   - aboue → above
   - vnto → unto
   (Do not modernize thou/thee/ye/thy/thine/shalt/hast/didst/art.)

Optional pause control (use sparingly): Insert <break time="0.3s" /> only where a speaker would naturally pause between major thoughts.

Output format: clean paragraphs only. No headings. No bullets. No verse numbers."""

def ai_polish_narration(text: str, api_key: Optional[str] = None) -> Optional[str]:
    """
    Use AI to polish KJV text for ElevenLabs narration.
    Returns polished text or None if AI unavailable/fails.
    """
    if not AI_AVAILABLE:
        print("OpenAI library not installed. Skipping AI polish. Install: pip install openai")
        return None
    
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("No OpenAI API key found. Set OPENAI_API_KEY environment variable or skip AI polish.")
        return None
    
    try:
        print("Calling AI for KJV narration polish...")
        client = openai.OpenAI(api_key=api_key)
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective
            messages=[
                {"role": "system", "content": KJV_NARRATION_PROMPT},
                {"role": "user", "content": f"Polish this KJV passage for narration:\n\n{text}"}
            ],
            temperature=0.3,  # Low temp for consistency
            max_tokens=4000
        )
        
        polished = response.choices[0].message.content.strip()
        print("AI polish complete!")
        return polished
        
    except Exception as e:
        print(f"AI polish failed: {e}")
        print("Continuing with regex-cleaned version...")
        return None

def clean_text(text):
    """Clean and normalize the input text."""
    # Remove extra whitespace and normalize line breaks
    text = re.sub(r'\n+', ' ', text)  # Replace multiple newlines with spaces
    text = re.sub(r'\s+', ' ', text.strip())  # Replace multiple spaces with single space
    
    # NEW: Script formatting cleaning
    print("🎬 Cleaning script formatting...")
    
    # Remove stage directions like [Scene: ...] and [Opening Scene - ...]
    text = re.sub(r'\*\*\[.*?\]\*\*', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    
    # Remove markdown formatting
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # **text** → text
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # *text* → text
    
    # Remove scene separators and dashes
    text = re.sub(r'---+', '', text)
    text = re.sub(r'_{3,}', '', text)
    text = re.sub(r'={3,}', '', text)
    
    # Remove stage directions in parentheses (but preserve biblical content in parentheses)
    # Only remove if it contains video production terms
    text = re.sub(r'\(.*?[Vv]oiceover.*?\)', '', text)
    text = re.sub(r'\(.*?[Ss]cene.*?\)', '', text)
    text = re.sub(r'\(.*?[Cc]inematic.*?\)', '', text)
    text = re.sub(r'\(.*?[Ii]nstrumental.*?\)', '', text)
    
    # Remove common video production terms
    text = re.sub(r'\*\*Narrator \(Voiceover\)\*\*', '', text)
    text = re.sub(r'Narrator \(Voiceover\)', '', text)
    text = re.sub(r'\*\*Title\*\*:', '', text)
    text = re.sub(r'Title:', '', text)
    text = re.sub(r'\*\*\[Final Scene.*?\]\*\*', '', text)
    text = re.sub(r'\*\*\[Opening Scene.*?\]\*\*', '', text)
    
    # EXISTING: Biblical formatting cleaning
    print("📖 Cleaning biblical formatting...")
    
    # Remove verse references like "Deuteronomy 4:7-8" but keep the actual text
    text = re.sub(r'\b[A-Za-z]+\s+\d+:\d+(-\d+)?\s+', '', text)

    # Remove standalone verse numbers (common KJV formatting)
    text = re.sub(r'(?m)^\s*[1-9]\d{0,2}[:.)]?\s+', '', text)       # line-leading
    text = re.sub(r'\s+[1-9]\d{0,2}[:.)]?\s+(?=[A-Za-z])', ' ', text)  # inline
    # Remove verse numbers stuck to the start of words (e.g., "1And", "49O")
    text = re.sub(r'\b[1-9]\d{0,2}[:.)]?\s*(?=[A-Za-z])', '', text)
    # Remove verse numbers with paragraph symbol (e.g., "3¶ ", "16¶ ")
    text = re.sub(r'\b[1-9]\d{0,2}¶\s*', '', text)
    # Remove verse numbers with opening parentheses (e.g., "15(For" → "For")
    text = re.sub(r'\b[1-9]\d{0,2}\(', '(', text)
    # Clean up multiple opening parentheses that may result
    text = re.sub(r'\(\(+', '(', text)
    
    # Clean up punctuation spacing
    text = re.sub(r'([.!?])\s*', r'\1 ', text)
    
    # Remove multiple spaces again
    text = re.sub(r'\s+', ' ', text)
    
    # Remove section headers and precept references (but keep main content)
    text = re.sub(r'Precepts to [^:]+:', '', text)
    text = re.sub(r'How special and Holy they are', '', text)
    text = re.sub(r'THE MOST HIGH CHOSEN PEOPLE', '', text)
    text = re.sub(r'Conclusion', '', text)
    
    # Final cleanup
    text = re.sub(r'\n{3,}', '\n\n', text)  # Remove excessive line breaks
    text = re.sub(r'\s{2,}', ' ', text)     # Remove excessive spaces
    
    # Remove empty lines
    text = '\n'.join(line for line in text.split('\n') if line.strip())
    
    return text.strip()

def kjv_narration_fix(text: str) -> str:
    """
    Fix KJV text for narration/captions while KEEPING archaic pronouns/grammar.
    - Fixes 1611 spellings (v→u, iudgement→judgment, Ierusalem→Jerusalem, etc.)
    - PRESERVES: thou/thee/thy/thine/ye/unto/shalt/hast/didst/art/wilt/doth/saith
    - Keeps KJV grammar intact
    - Narration-ready (no broken transcription)
    """
    
    # Fix standalone "vs" → "us" (people reference, not "versus")
    text = re.sub(r'\bvs\b', 'us', text, flags=re.IGNORECASE)
    
    # CRITICAL: Fix common u→v and other core 1611 patterns FIRST (highest priority)
    text = re.sub(r'\bgiue\b', 'give', text, flags=re.IGNORECASE)
    text = re.sub(r'\bloue\b', 'love', text, flags=re.IGNORECASE)
    text = re.sub(r'\bliue\b', 'live', text, flags=re.IGNORECASE)
    text = re.sub(r'\baliue\b', 'alive', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpreserue\b', 'preserve', text, flags=re.IGNORECASE)
    text = re.sub(r'\bserue\b', 'serve', text, flags=re.IGNORECASE)
    text = re.sub(r'\bobserue\b', 'observe', text, flags=re.IGNORECASE)
    
    # Critical v→u substitutions (1611 print conventions - comprehensive)
    text = re.sub(r'\bvp\b', 'up', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvpon\b', 'upon', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvnto\b', 'unto', text, flags=re.IGNORECASE)  # Keep 'unto' (KJV word) but fix spelling
    text = re.sub(r'\bvnder\b', 'under', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvniust\b', 'unjust', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvniquitie\b', 'iniquity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvncircumcised\b', 'uncircumcised', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvnstable\b', 'unstable', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvnrighteous\b', 'unrighteous', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvnmeasurable\b', 'unmeasurable', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvnsearchable\b', 'unsearchable', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvnworthy\b', 'unworthy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bouer\b', 'over', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmids\b', 'midst', text, flags=re.IGNORECASE)
    text = re.sub(r'\bouen\b', 'oven', text, flags=re.IGNORECASE)
    
    # Names and places (critical for accuracy)
    text = re.sub(r'\bIerusalem\b', 'Jerusalem', text)
    text = re.sub(r'\bIacob\b', 'Jacob', text)
    text = re.sub(r'\bIuda\b', 'Judah', text)
    # I→J names (KJV used I for J sound)
    text = re.sub(r'\bIames\b', 'James', text)
    text = re.sub(r'\bIohn\b', 'John', text)
    text = re.sub(r'\bIudas\b', 'Judas', text)
    text = re.sub(r'\bIesus\b', 'Jesus', text)
    text = re.sub(r'\bIoseph\b', 'Joseph', text)
    text = re.sub(r'\bIoel\b', 'Joel', text)
    text = re.sub(r'\bIonah\b', 'Jonah', text)
    text = re.sub(r'\bIoshua\b', 'Joshua', text)
    
    # CRITICAL pronunciation-breaking spellings (ElevenLabs priority)
    text = re.sub(r'\biudgement', 'judgment', text, flags=re.IGNORECASE)  # judgement/judgements
    text = re.sub(r'\bIudgement', 'Judgment', text)  # Capital version
    text = re.sub(r'\bdeliuer', 'deliver', text, flags=re.IGNORECASE)     # deliver/delivered/deliverance
    text = re.sub(r'\bheauen', 'heaven', text, flags=re.IGNORECASE)       # heaven/heavens/heavenly
    text = re.sub(r'\biniquitie\b', 'iniquity', text, flags=re.IGNORECASE)  # Over-pronounced -tie
    text = re.sub(r'\baboue\b', 'above', text, flags=re.IGNORECASE)
    text = re.sub(r'\beuen\b', 'even', text, flags=re.IGNORECASE)
    text = re.sub(r'\beuer\b', 'ever', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmoue\b', 'move', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmooue\b', 'move', text, flags=re.IGNORECASE)
    text = re.sub(r'\blouing\b', 'loving', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsaued\b', 'saved', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhaue\b', 'have', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwholy\b', 'wholly', text, flags=re.IGNORECASE)  # CRITICAL: read as "holy"
    
    # Common -e endings that break pronunciation
    text = re.sub(r'\bsoule\b', 'soul', text, flags=re.IGNORECASE)
    text = re.sub(r'\boliue\b', 'olive', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpossesse\b', 'possess', text, flags=re.IGNORECASE)
    text = re.sub(r'\bkeepe\b', 'keep', text, flags=re.IGNORECASE)
    text = re.sub(r'\btalke\b', 'talk', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbinde\b', 'bind', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbetweene\b', 'between', text, flags=re.IGNORECASE)
    text = re.sub(r'\balwayes\b', 'always', text, flags=re.IGNORECASE)
    
    # Double consonants and variant spellings
    text = re.sub(r'\bshalbe\b', 'shall be', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsonne\b', 'son', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwelles\b', 'wells', text, flags=re.IGNORECASE)
    text = re.sub(r'\bielous\b', 'jealous', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmilke\b', 'milk', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhony\b', 'honey', text, flags=re.IGNORECASE)
    
    # Commandments variations (critical for this text)
    text = re.sub(r'\bCommaundements\b', 'Commandments', text)
    text = re.sub(r'\bcommaundements\b', 'commandments', text, flags=re.IGNORECASE)
    text = re.sub(r'\bCommandements\b', 'Commandments', text)
    text = re.sub(r'\bcommandements\b', 'commandments', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcommaundement\b', 'commandment', text, flags=re.IGNORECASE)
    
    # Past tense -dst endings (buildedst, filledst, etc.) → modern forms
    text = re.sub(r'\bbuildedst\b', 'built', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfilledst\b', 'filled', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdiggedst\b', 'dug', text, flags=re.IGNORECASE)
    text = re.sub(r'\bplantedst\b', 'planted', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdigged\b', 'dug', text, flags=re.IGNORECASE)
    
    # Additional verb forms
    text = re.sub(r'\bsware\b', 'swore', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshewed\b', 'showed', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsweare\b', 'swear', text, flags=re.IGNORECASE)
    text = re.sub(r'\bHeare\b', 'Hear', text)  # Capital H only
    text = re.sub(r'\bheare\b', 'hear', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsonnes\b', 'sons', text, flags=re.IGNORECASE)
    
    # Righteousness variants
    text = re.sub(r'\brighteousnes\b', 'righteousness', text, flags=re.IGNORECASE)
    
    # OCR artifacts and archaic forms that hurt narration
    text = re.sub(r'\bfornace\b', 'furnace', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshewre\b', 'shower', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshowre\b', 'shower', text, flags=re.IGNORECASE)
    text = re.sub(r'\bholden\b', 'held', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcaptiue\b', 'captive', text, flags=re.IGNORECASE)
    text = re.sub(r'\bAlmightie\b', 'Almighty', text)
    text = re.sub(r'\bdeepe\b', 'deep', text, flags=re.IGNORECASE)
    text = re.sub(r'\bMaiestie\b', 'Majesty', text)
    text = re.sub(r'\bmercifull\b', 'merciful', text, flags=re.IGNORECASE)
    text = re.sub(r'\beuils\b', 'evils', text, flags=re.IGNORECASE)
    text = re.sub(r'\beuill\b', 'evil', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgoodnesse\b', 'goodness', text, flags=re.IGNORECASE)
    text = re.sub(r'\bforgiuenesse\b', 'forgiveness', text, flags=re.IGNORECASE)
    text = re.sub(r'\bforgiue\b', 'forgive', text, flags=re.IGNORECASE)
    text = re.sub(r'\biust\b', 'just', text, flags=re.IGNORECASE)
    text = re.sub(r'\byron\b', 'iron', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprouoked\b', 'provoked', text, flags=re.IGNORECASE)
    text = re.sub(r'\breseruing\b', 'reserving', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsaue\b', 'save', text, flags=re.IGNORECASE)
    
    # Common word endings (plural/verb forms) - comprehensive
    text = re.sub(r'\bmercie', 'mercy', text, flags=re.IGNORECASE)  # mercie/mercies
    text = re.sub(r'\bmercys\b', 'mercies', text, flags=re.IGNORECASE)  # mercys → mercies
    text = re.sub(r'\bsinnes\b', 'sins', text, flags=re.IGNORECASE)
    text = re.sub(r'\bworkes\b', 'works', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwayes\b', 'ways', text, flags=re.IGNORECASE)
    text = re.sub(r'\btrueth\b', 'truth', text, flags=re.IGNORECASE)
    text = re.sub(r'\bseruant', 'servant', text, flags=re.IGNORECASE)    # servant/servants
    text = re.sub(r'\bbeloued\b', 'beloved', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmarueilous\b', 'marvelous', text, flags=re.IGNORECASE)
    text = re.sub(r'\bkindenesse\b', 'kindness', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwindes\b', 'winds', text, flags=re.IGNORECASE)
    text = re.sub(r'\bheate\b', 'heat', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsoules\b', 'souls', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwhome\b', 'whom', text, flags=re.IGNORECASE)
    text = re.sub(r'\bthreatnin', 'threatenin', text, flags=re.IGNORECASE)  # threatning → threatening
    text = re.sub(r'\boffences\b', 'offenses', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcondemne\b', 'condemn', text, flags=re.IGNORECASE)
    
    # Double-e contractions (normalize to modern single) - EXPANDED
    text = re.sub(r'\byee\b', 'ye', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwee\b', 'we', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbee\b', 'be', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhee\b', 'he', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshee\b', 'she', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmee\b', 'me', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgoe\b', 'go', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdoe\b', 'do', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshew\b', 'show', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshall bee\b', 'shall be', text, flags=re.IGNORECASE)
    
    # Additional -e word endings
    text = re.sub(r'\bmeane\b', 'mean', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwhither\b', 'where', text, flags=re.IGNORECASE)  # archaic "whither" → "where"
    text = re.sub(r'\bfeare\b', 'fear', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfrontlets\b', 'frontlets', text, flags=re.IGNORECASE)  # Already correct
    text = re.sub(r'\bsigne\b', 'sign', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsignes\b', 'signs', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwel\b', 'well', text, flags=re.IGNORECASE)
    
    # Additional nature/animal terms
    text = re.sub(r'\bfoules\b', 'fowls', text, flags=re.IGNORECASE)
    text = re.sub(r'\briuers\b', 'rivers', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcattell\b', 'cattle', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmountaines\b', 'mountains', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfountaines\b', 'fountains', text, flags=re.IGNORECASE)
    text = re.sub(r'\beuermore\b', 'evermore', text, flags=re.IGNORECASE)
    text = re.sub(r'\beuery\b', 'every', text, flags=re.IGNORECASE)
    
    # Comprehensive 1611 spellings (extra syllables, stress issues, pronunciation errors)
    text = re.sub(r'\bCouenant\b', 'Covenant', text)
    text = re.sub(r'\bdisanull\b', 'disannul', text, flags=re.IGNORECASE)
    text = re.sub(r'\bNeuerthelesse\b', 'Nevertheless', text)
    text = re.sub(r'\breproch\b', 'reproach', text, flags=re.IGNORECASE)
    text = re.sub(r'\blesse\b', 'less', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfinde\b', 'find', text, flags=re.IGNORECASE)
    text = re.sub(r'\brammes\b', 'rams', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbullockes\b', 'bullocks', text, flags=re.IGNORECASE)
    text = re.sub(r'\blambes\b', 'lambs', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfeare\b', 'fear', text, flags=re.IGNORECASE)
    text = re.sub(r'\bseeke\b', 'seek', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdeale\b', 'deal', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgiue\b', 'give', text, flags=re.IGNORECASE)  # "gee-ve" issue
    text = re.sub(r'\bdoe\b', 'do', text, flags=re.IGNORECASE)
    text = re.sub(r'\bonely\b', 'only', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhote\b', 'hot', text, flags=re.IGNORECASE)
    text = re.sub(r'\btowe\b', 'tow', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfourtie\b', 'forty', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcubites\b', 'cubits', text, flags=re.IGNORECASE)
    text = re.sub(r'\bCaldeans\b', 'Chaldeans', text)
    text = re.sub(r'\bdowne\b', 'down', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfellowes\b', 'fellows', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbene\b', 'been', text, flags=re.IGNORECASE)  # "ben-eh" issue
    text = re.sub(r'\bkingdome\b', 'kingdom', text, flags=re.IGNORECASE)
    text = re.sub(r'\bLorde\b', 'Lord', text)
    text = re.sub(r'\bSunne\b', 'Sun', text)  # "sun-nuh" issue
    text = re.sub(r'\bMoone\b', 'Moon', text)  # "moon-eh" issue
    text = re.sub(r'\bstarres\b', 'stars', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdewes\b', 'dews', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstormes\b', 'storms', text, flags=re.IGNORECASE)  # NEW
    text = re.sub(r'\bdayes\b', 'days', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdarkenesse\b', 'darkness', text, flags=re.IGNORECASE)  # "ness-uh" artifact
    text = re.sub(r'\byce\b', 'ice', text, flags=re.IGNORECASE)  # NEW - ElevenLabs stumbles
    text = re.sub(r'\bcolde\b', 'cold', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhils\b', 'hills', text, flags=re.IGNORECASE)  # Missing L
    text = re.sub(r'\baire\b', 'air', text, flags=re.IGNORECASE)  # Ghost syllable
    text = re.sub(r'\bthankes\b', 'thanks', text, flags=re.IGNORECASE)
    text = re.sub(r'\blyeth\b', 'lieth', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmouthes\b', 'mouths', text, flags=re.IGNORECASE)  # "mouth-es" awkward
    text = re.sub(r'\bCommandement', 'Commandment', text)  # Commandment/Commandments
    text = re.sub(r'\blawlesse\b', 'lawless', text, flags=re.IGNORECASE)  # Double-s cadence
    text = re.sub(r'\bhatefull\b', 'hateful', text, flags=re.IGNORECASE)  # Same issue
    text = re.sub(r'\bwhales\b', 'whales', text, flags=re.IGNORECASE)
    text = re.sub(r'\bspirits\b', 'spirits', text, flags=re.IGNORECASE)
    
    # ── Specific vncleane / vncleannesse (handled before general rule) ────────
    text = re.sub(r'\bvncleane\b', 'unclean', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvncleannesse\b', 'uncleanness', text, flags=re.IGNORECASE)

    # Receive forms (u→v swap in middle of word)
    text = re.sub(r'\breceiueth\b', 'receiveth', text, flags=re.IGNORECASE)
    text = re.sub(r'\breceiued\b', 'received', text, flags=re.IGNORECASE)
    text = re.sub(r'\breceiue\b', 'receive', text, flags=re.IGNORECASE)

    # Common verb/word fixes from Matthew 10
    text = re.sub(r'\btwelue\b', 'twelve', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgaue\b', 'gave', text, flags=re.IGNORECASE)
    text = re.sub(r'\bheale\b', 'heal', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmaner\b', 'manner', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsickenesse\b', 'sickness', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfoorth\b', 'forth', text, flags=re.IGNORECASE)
    text = re.sub(r'\bspeake\b', 'speak', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdrinke\b', 'drink', text, flags=re.IGNORECASE)
    text = re.sub(r'\breturne\b', 'return', text, flags=re.IGNORECASE)
    text = re.sub(r'\bthinke\b', 'think', text, flags=re.IGNORECASE)
    text = re.sub(r'\bloueth\b', 'loveth', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcrosse\b', 'cross', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgiuen\b', 'given', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsolde\b', 'sold', text, flags=re.IGNORECASE)
    text = re.sub(r'\bnumbred\b', 'numbered', text, flags=re.IGNORECASE)

    # Body parts / physical words
    text = re.sub(r'\bfeete\b', 'feet', text, flags=re.IGNORECASE)
    text = re.sub(r'\beare\b', 'ear', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhaires\b', 'hairs', text, flags=re.IGNORECASE)
    text = re.sub(r'\bchilde\b', 'child', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhoure\b', 'hour', text, flags=re.IGNORECASE)

    # Animals / nature
    text = re.sub(r'\bsheepe\b', 'sheep', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwolues\b', 'wolves', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdoues\b', 'doves', text, flags=re.IGNORECASE)
    text = re.sub(r'\bSparrowes\b', 'Sparrows', text)
    text = re.sub(r'\bsparrowes\b', 'sparrows', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdeuils\b', 'devils', text, flags=re.IGNORECASE)

    # Travel / equipment words
    text = re.sub(r'\biourney\b', 'journey', text, flags=re.IGNORECASE)
    text = re.sub(r'\bscrippe\b', 'scrip', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshooes\b', 'shoes', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstaues\b', 'staves', text, flags=re.IGNORECASE)
    text = re.sub(r'\bworkeman\b', 'workman', text, flags=re.IGNORECASE)

    # Titles / roles
    text = re.sub(r'\bPublicane\b', 'Publican', text)
    text = re.sub(r'\bpublicane\b', 'publican', text, flags=re.IGNORECASE)
    text = re.sub(r'\bGouernours\b', 'Governors', text)
    text = re.sub(r'\bgouernours\b', 'governors', text, flags=re.IGNORECASE)
    text = re.sub(r'\bGouernour\b', 'Governor', text)
    text = re.sub(r'\bgouernour\b', 'governor', text, flags=re.IGNORECASE)

    # More -soever compounds
    text = re.sub(r'\bwhatsoeuer\b', 'whatsoever', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwhosoeuer\b', 'whosoever', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhowsoeuer\b', 'howsoever', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwheresoeuer\b', 'wheresoever', text, flags=re.IGNORECASE)

    # Place / location words
    text = re.sub(r'\btowne\b', 'town', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcitie\b', 'city', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmiddest\b', 'midst', text, flags=re.IGNORECASE)

    # Adjectives / adverbs
    text = re.sub(r'\bharmelesse\b', 'harmless', text, flags=re.IGNORECASE)
    text = re.sub(r'\blitle\b', 'little', text, flags=re.IGNORECASE)
    text = re.sub(r'\bProuide\b', 'Provide', text)
    text = re.sub(r'\bprouide\b', 'provide', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsiluer\b', 'silver', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbrasse\b', 'brass', text, flags=re.IGNORECASE)
    text = re.sub(r'\btestimonie\b', 'testimony', text, flags=re.IGNORECASE)

    # Past participles / state words
    text = re.sub(r'\bcouered\b', 'covered', text, flags=re.IGNORECASE)
    text = re.sub(r'\breueiled\b', 'revealed', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhidde\b', 'hidden', text, flags=re.IGNORECASE)
    text = re.sub(r'\bknowen\b', 'known', text, flags=re.IGNORECASE)

    # V→U at word start (U printed as V in 1611)
    text = re.sub(r'\bUerely\b', 'Verily', text)
    text = re.sub(r'\bverely\b', 'verily', text, flags=re.IGNORECASE)

    # iudgment without the extra 'e' (existing rule catches 'iudgement')
    text = re.sub(r'\biudgment\b', 'judgment', text, flags=re.IGNORECASE)

    # Missed words caught in Matthew 10 test pass
    text = re.sub(r'\bsicke\b', 'sick', text, flags=re.IGNORECASE)
    text = re.sub(r'\bconfesse\b', 'confess', text, flags=re.IGNORECASE)
    text = re.sub(r'\bowne\b', 'own', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhoushold\b', 'household', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshal\b', 'shall', text, flags=re.IGNORECASE)  # "shal" short form
    text = re.sub(r'\bwil\b', 'will', text, flags=re.IGNORECASE)   # "wil" short form

    # Matthew 11 additions
    # Common verbs
    text = re.sub(r'\bpasse\b', 'pass', text, flags=re.IGNORECASE)          # "came to passe"
    text = re.sub(r'\bsaide\b', 'said', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcommaunding\b', 'commanding', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvpbraid\b', 'upbraid', text, flags=re.IGNORECASE)     # vp inside word, \bvp\b won't catch
    text = re.sub(r'\blooke\b', 'look', text, flags=re.IGNORECASE)
    text = re.sub(r'\blearne\b', 'learn', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprophecied\b', 'prophesied', text, flags=re.IGNORECASE)
    text = re.sub(r'\breueile\b', 'reveal', text, flags=re.IGNORECASE)      # base form (reueiled already covered)
    # Adjectives
    text = re.sub(r'\bdeafe\b', 'deaf', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpoore\b', 'poor', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmightie\b', 'mighty', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmeeke\b', 'meek', text, flags=re.IGNORECASE)
    text = re.sub(r'\beasie\b', 'easy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bheauy\b', 'heavy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwisedom\b', 'wisdom', text, flags=re.IGNORECASE)
    text = re.sub(r'\biustified\b', 'justified', text, flags=re.IGNORECASE)
    # Nature words
    text = re.sub(r'\breede\b', 'reed', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwinde\b', 'wind', text, flags=re.IGNORECASE)          # singular (windes already covered)
    text = re.sub(r'\bwildernesse\b', 'wilderness', text, flags=re.IGNORECASE)
    # Clothing / physical
    text = re.sub(r'\bweare\b', 'wear', text, flags=re.IGNORECASE)          # "they that weare soft clothing"
    text = re.sub(r'\bcloathing\b', 'clothing', text, flags=re.IGNORECASE)
    # People / roles
    text = re.sub(r'\bborne\b', 'born', text, flags=re.IGNORECASE)          # "born of women"
    text = re.sub(r'\bpublicanes\b', 'publicans', text, flags=re.IGNORECASE)
    # Places
    text = re.sub(r'\bSodome\b', 'Sodom', text)
    # Time / quantity
    text = re.sub(r'\bagoe\b', 'ago', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbeene\b', 'been', text, flags=re.IGNORECASE)          # double-e form (bene already covered)
    text = re.sub(r'\bvntill\b', 'until', text, flags=re.IGNORECASE)        # double-l form
    text = re.sub(r'\bvntil\b', 'until', text, flags=re.IGNORECASE)         # single-l form
    # Devil singular (deuils plural already covered)
    text = re.sub(r'\bdeuill\b', 'devil', text, flags=re.IGNORECASE)
    # soever compound
    text = re.sub(r'\bwhomsoeuer\b', 'whomsoever', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwhoseouer\b', 'whosoever', text, flags=re.IGNORECASE)  # alt spelling (whosoeuer already covered)
    # Special Unicode characters from 1611 print (thorn + macron)
    text = text.replace('þe', 'the').replace('þE', 'The')   # thorn = th
    text = text.replace('frō', 'from').replace('frŌ', 'From')  # macron-o = om

    # Matthew 12 additions
    # Travel / direction
    text = re.sub(r'\bthorow\b', 'through', text, flags=re.IGNORECASE)   # "thorow the corne"
    # Food / agriculture
    text = re.sub(r'\bcorne\b', 'corn', text, flags=re.IGNORECASE)
    text = re.sub(r'\beares\b', 'ears', text, flags=re.IGNORECASE)       # "eares of corne" (eare→ear already covered)
    text = re.sub(r'\bhungred\b', 'hungered', text, flags=re.IGNORECASE) # "an hungred"
    text = re.sub(r'\bflaxe\b', 'flax', text, flags=re.IGNORECASE)
    # Verbs
    text = re.sub(r'\bbeganne\b', 'began', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsaye\b', 'say', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstriue\b', 'strive', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbreake\b', 'break', text, flags=re.IGNORECASE)
    text = re.sub(r'\bspake\b', 'spoke', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdiuided\b', 'divided', text, flags=re.IGNORECASE)
    text = re.sub(r'\bspoile\b', 'spoil', text, flags=re.IGNORECASE)
    # Adjectives / state
    text = re.sub(r'\bblinde\b', 'blind', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdumbe\b', 'dumb', text, flags=re.IGNORECASE)       # KJV "dumb" = mute
    text = re.sub(r'\bguiltlesse\b', 'guiltless', text, flags=re.IGNORECASE)
    text = re.sub(r'\bblamelesse\b', 'blameless', text, flags=re.IGNORECASE)
    text = re.sub(r'\blawfull\b', 'lawful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bemptie\b', 'empty', text, flags=re.IGNORECASE)
    text = re.sub(r'\beuil\b', 'evil', text, flags=re.IGNORECASE)        # single-l (euill already covered)
    text = re.sub(r'\bcertaine\b', 'certain', text, flags=re.IGNORECASE)
    # Nouns
    text = re.sub(r'\bblasphemie\b', 'blasphemy', text, flags=re.IGNORECASE)
    text = re.sub(r'\baccompt\b', 'account', text, flags=re.IGNORECASE)  # "give accompt"
    text = re.sub(r'\bcounsell\b', 'counsel', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwordes\b', 'words', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshepe\b', 'sheep', text, flags=re.IGNORECASE)      # alt spelling (sheepe already covered)
    # Numbers
    text = re.sub(r'\bseuen\b', 'seven', text, flags=re.IGNORECASE)
    # -self reflexives
    text = re.sub(r'\bhimselfe\b', 'himself', text, flags=re.IGNORECASE)
    text = re.sub(r'\bherselfe\b', 'herself', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmyselfe\b', 'myself', text, flags=re.IGNORECASE)
    text = re.sub(r'\bthemselues\b', 'themselves', text, flags=re.IGNORECASE)
    text = re.sub(r'\bselfe\b', 'self', text, flags=re.IGNORECASE)       # catches "it selfe", "in selfe"
    # Connectives
    text = re.sub(r'\bWherfore\b', 'Wherefore', text)
    text = re.sub(r'\bwherfore\b', 'wherefore', text, flags=re.IGNORECASE)
    # Names / places
    text = re.sub(r'\bDauid\b', 'David', text)
    text = re.sub(r'\bPharises\b', 'Pharisees', text)                    # alt spelling (Pharisees already correct)
    text = re.sub(r'\bpharises\b', 'pharisees', text)
    text = re.sub(r'\bEsaias\b', 'Isaiah', text)                         # KJV Greek form → familiar name
    text = re.sub(r'\bIonas\b', 'Jonah', text)                           # KJV Greek form → familiar name
    text = re.sub(r'\bIudges\b', 'Judges', text)                         # capital - role not book
    text = re.sub(r'\biudges\b', 'judges', text, flags=re.IGNORECASE)
    text = re.sub(r'\bNineue\b', 'Nineveh', text)
    text = re.sub(r'\bQueene\b', 'Queen', text)
    text = re.sub(r'\bvttermost\b', 'uttermost', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwisedome\b', 'wisdom', text, flags=re.IGNORECASE)  # alt spelling (wisedom already covered)
    text = re.sub(r'\bdaies\b', 'days', text, flags=re.IGNORECASE)       # alt spelling (dayes already covered)

    # ── General vn→un prefix rule (runs AFTER specific patterns) ────────────
    # Catches any remaining 1611 vn-words not explicitly handled above.
    # Safe: no English word legitimately starts with "vn".
    text = re.sub(r'\bvn([a-z])', lambda m: 'un' + m.group(1), text)
    text = re.sub(r'\bVn([a-zA-Z])', lambda m: 'Un' + m.group(1), text)
    # Fix -e endings that the general rule leaves behind (unlesse, etc.)
    text = re.sub(r'\bunlesse\b', 'unless', text, flags=re.IGNORECASE)
    text = re.sub(r'\bunbeleeue', 'unbelieve', text, flags=re.IGNORECASE)
    text = re.sub(r'\buncleane\b', 'unclean', text, flags=re.IGNORECASE)
    text = re.sub(r'\buncleannesse\b', 'uncleanness', text, flags=re.IGNORECASE)

    # ── Proactive whole-Bible patterns (covers NT + OT common words) ─────────

    # Irregular past tenses (common across all 4 Gospels and Epistles)
    text = re.sub(r'\bknewe\b', 'knew', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgrewe\b', 'grew', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdrewe\b', 'drew', text, flags=re.IGNORECASE)
    text = re.sub(r'\bthrewe\b', 'threw', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfledde\b', 'fled', text, flags=re.IGNORECASE)
    text = re.sub(r'\branne\b', 'ran', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstoode\b', 'stood', text, flags=re.IGNORECASE)
    text = re.sub(r'\btooke\b', 'took', text, flags=re.IGNORECASE)
    text = re.sub(r'\bforsooke\b', 'forsook', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstrooke\b', 'struck', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsprange\b', 'sprang', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstake\b', 'stuck', text, flags=re.IGNORECASE)     # rare alt
    text = re.sub(r'\bholpen\b', 'helped', text, flags=re.IGNORECASE)   # "hath holpen"
    text = re.sub(r'\bwaxe\b', 'wax', text, flags=re.IGNORECASE)        # "wax cold"
    text = re.sub(r'\bcloke\b', 'cloak', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstrake\b', 'struck', text, flags=re.IGNORECASE)

    # Nouns: -ow/-ow words with silent -e
    text = re.sub(r'\bsorrowe\b', 'sorrow', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmorrowe\b', 'morrow', text, flags=re.IGNORECASE)  # "the morrow"
    text = re.sub(r'\bsworde\b', 'sword', text, flags=re.IGNORECASE)
    text = re.sub(r'\broote\b', 'root', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbosome\b', 'bosom', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsinne\b', 'sin', text, flags=re.IGNORECASE)       # singular (sinnes already covered)
    text = re.sub(r'\bgolde\b', 'gold', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmyrrhe\b', 'myrrh', text, flags=re.IGNORECASE)
    text = re.sub(r'\bglasse\b', 'glass', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcompasse\b', 'compass', text, flags=re.IGNORECASE)
    text = re.sub(r'\btrespasse\b', 'trespass', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdarke\b', 'dark', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmarke\b', 'mark', text, flags=re.IGNORECASE)
    text = re.sub(r'\bheele\b', 'heel', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfieldes\b', 'fields', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstorke\b', 'stork', text, flags=re.IGNORECASE)

    # Nouns: -ie → -y (systematic KJV pattern throughout whole Bible)
    text = re.sub(r'\bglorie\b', 'glory', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvictorie\b', 'victory', text, flags=re.IGNORECASE)
    text = re.sub(r'\bauthoritie\b', 'authority', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcountrie\b', 'country', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcompanie\b', 'company', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvirginitie\b', 'virginity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhumilitie\b', 'humility', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvanitie\b', 'vanity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmysterie\b', 'mystery', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprosperie\b', 'prosperity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprosporitie\b', 'prosperity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprosperitie\b', 'prosperity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bremedee\b', 'remedy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bremedee\b', 'remedy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bremedee\b', 'remedy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bremedee\b', 'remedy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbodie\b', 'body', text, flags=re.IGNORECASE)
    text = re.sub(r'\bplentie\b', 'plenty', text, flags=re.IGNORECASE)
    text = re.sub(r'\barmie\b', 'army', text, flags=re.IGNORECASE)
    text = re.sub(r'\benemie\b', 'enemy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfamilie\b', 'family', text, flags=re.IGNORECASE)
    text = re.sub(r'\bstudie\b', 'study', text, flags=re.IGNORECASE)
    text = re.sub(r'\bgluttonie\b', 'gluttony', text, flags=re.IGNORECASE)
    text = re.sub(r'\bceremonies\b', 'ceremony', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhypocrisie\b', 'hypocrisy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bheresie\b', 'heresy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bielousie\b', 'jealousy', text, flags=re.IGNORECASE)
    text = re.sub(r'\btreasuries\b', 'treasury', text, flags=re.IGNORECASE)
    text = re.sub(r'\btreasurie\b', 'treasury', text, flags=re.IGNORECASE)
    text = re.sub(r'\bworthy\b', 'worthy', text, flags=re.IGNORECASE)   # already fine but ensure
    text = re.sub(r'\bworthie\b', 'worthy', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmanie\b', 'many', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcontrarie\b', 'contrary', text, flags=re.IGNORECASE)
    text = re.sub(r'\bnecessarie\b', 'necessary', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpalsie\b', 'palsy', text, flags=re.IGNORECASE)    # Matthew 4/8/9
    text = re.sub(r'\bfurie\b', 'fury', text, flags=re.IGNORECASE)
    text = re.sub(r'\blibertie\b', 'liberty', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpuritie\b', 'purity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcharitie\b', 'charity', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcruelties\b', 'cruelty', text, flags=re.IGNORECASE)

    # People / place names with archaic spellings (whole Bible)
    text = re.sub(r'\bHerode\b', 'Herod', text)
    text = re.sub(r'\bGalilee\b', 'Galilee', text)     # already correct
    text = re.sub(r'\bGalile\b', 'Galilee', text)
    text = re.sub(r'\bGalilei\b', 'Galilee', text)
    text = re.sub(r'\bBethanie\b', 'Bethany', text)
    text = re.sub(r'\bIudea\b', 'Judea', text)
    text = re.sub(r'\bIudaea\b', 'Judea', text)
    text = re.sub(r'\bGolgotha\b', 'Golgotha', text)   # fine
    text = re.sub(r'\bElias\b', 'Elijah', text)        # KJV Greek form used in NT
    text = re.sub(r'\bEliseus\b', 'Elisha', text)      # KJV Greek form
    text = re.sub(r'\bMoses\b', 'Moses', text)         # fine
    text = re.sub(r'\bIob\b', 'Job', text)             # I→J
    text = re.sub(r'\bIoel\b', 'Joel', text)           # already covered
    text = re.sub(r'\bIona\b', 'Jonah', text)
    text = re.sub(r'\bIsrael\b', 'Israel', text)       # fine

    # Adjectives with -ll double ending (common throughout)
    text = re.sub(r'\bsubtill\b', 'subtle', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsubtle\b', 'subtle', text, flags=re.IGNORECASE)   # fine
    text = re.sub(r'\bfaithfull\b', 'faithful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bthankfull\b', 'thankful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpowerfull\b', 'powerful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfearfull\b', 'fearful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfrutefull\b', 'fruitful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfruitefull\b', 'fruitful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwillfull\b', 'willful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bskilfull\b', 'skillful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcarefull\b', 'careful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpitifull\b', 'pitiful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bshamefull\b', 'shameful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwastfull\b', 'wasteful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdeceitfull\b', 'deceitful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsinfull\b', 'sinful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwrathfull\b', 'wrathful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bscornfull\b', 'scornful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsorrowfull\b', 'sorrowful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bjoyefull\b', 'joyful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bjoyfull\b', 'joyful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpeacefull\b', 'peaceful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwonderfull\b', 'wonderful', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmercifull\b', 'merciful', text, flags=re.IGNORECASE)  # already have but reinforcing

    # Common KJV words with extra -e/-ue
    text = re.sub(r'\bsaluacion\b', 'salvation', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsaluaion\b', 'salvation', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsaluation\b', 'salvation', text, flags=re.IGNORECASE)
    text = re.sub(r'\btemptacion\b', 'temptation', text, flags=re.IGNORECASE)
    text = re.sub(r'\btribulaion\b', 'tribulation', text, flags=re.IGNORECASE)
    text = re.sub(r'\btribulacion\b', 'tribulation', text, flags=re.IGNORECASE)
    text = re.sub(r'\btribulaion\b', 'tribulation', text, flags=re.IGNORECASE)
    text = re.sub(r'\bconfirmacion\b', 'confirmation', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdamnacion\b', 'damnation', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdamnation\b', 'damnation', text, flags=re.IGNORECASE)  # fine
    text = re.sub(r'\bcondemnacion\b', 'condemnation', text, flags=re.IGNORECASE)
    text = re.sub(r'\bresurrection\b', 'resurrection', text, flags=re.IGNORECASE)  # fine
    text = re.sub(r'\bperfeccion\b', 'perfection', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdeuotion\b', 'devotion', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdesolacion\b', 'desolation', text, flags=re.IGNORECASE)

    # Additional nature / environment words
    text = re.sub(r'\bdesarte\b', 'desert', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdesert\b', 'desert', text, flags=re.IGNORECASE)    # fine
    text = re.sub(r'\bforrest\b', 'forest', text, flags=re.IGNORECASE)
    text = re.sub(r'\bplaines\b', 'plains', text, flags=re.IGNORECASE)
    text = re.sub(r'\bvalleyes\b', 'valleys', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpastures\b', 'pastures', text, flags=re.IGNORECASE)  # fine

    # Fix "&" → "and" for narration
    text = re.sub(r'\s+&\s+', ' and ', text)

    # ── GENERIC CATCH-ALL PATTERNS (catches 1611 words not individually listed) ──
    # These handle systematic spelling conventions across all inflected forms.

    # Generic: "ue" → "ve" in word (handles belieue/belieued/belieuing/belieues)
    # 1611 KJV used "u" where modern English uses "v" inside words
    _ue_keep = {'true', 'blue', 'due', 'sue', 'rue', 'hue', 'cue', 'clue', 'glue',
                'value', 'argue', 'virtue', 'statue', 'tongue', 'league', 'plague',
                'vague', 'vogue', 'rogue', 'unique', 'technique', 'antique',
                'continue', 'issue', 'tissue', 'rescue', 'avenue', 'revenue',
                'venue', 'pursue', 'ensue', 'ague', 'queue', 'catalogue',
                'dialogue', 'monologue', 'prologue', 'epilogue', 'fatigue',
                'intrigue', 'oblique', 'physique', 'mystique', 'boutique',
                'residue', 'barbecue', 'subdue', 'imbue', 'accrue', 'construe'}
    def _fix_ue(m):
        word = m.group(0)
        if word.lower() in _ue_keep:
            return word
        # Replace ALL "ue" with "ve" — handles belieue→believe, reueiue→reveive
        return re.sub(r'ue', 've', word)
    text = re.sub(r'\b\w*[aeioy]ue\w*\b', _fix_ue, text, flags=re.IGNORECASE)

    # Generic: trailing -inge → -ing (e.g., "blessinge" → "blessing", "cominge" → "coming")
    text = re.sub(r'\b(\w{3,})inge\b', r'\1ing', text, flags=re.IGNORECASE)

    # Generic: trailing -nge with suffix → fix (e.g., "blessinges" → "blessings")
    text = re.sub(r'\b(\w{3,})inges\b', r'\1ings', text, flags=re.IGNORECASE)

    # Generic: -nne → -n (e.g., "beginne" → "begin", "sinne" → "sin")
    _nne_keep = {'anne', 'joanne', 'suzanne', 'dianne', 'antenne'}
    text = re.sub(r'\b(\w{3,})nne\b', lambda m: m.group(0) if m.group(0).lower() in _nne_keep
        else m.group(1) + 'n', text, flags=re.IGNORECASE)

    # Generic: -sse → -ss (e.g., "blesse" → "bless", "passe" → "pass")
    _sse_keep = {'finesse', 'largesse', 'noblesse', 'tendresse'}
    text = re.sub(r'\b(\w{3,})sse\b', lambda m: m.group(0) if m.group(0).lower() in _sse_keep
        else m.group(1) + 'ss', text, flags=re.IGNORECASE)

    # Generic: -ie → -y for nouns 4+ chars (e.g., "envie" → "envy", "prophesie" → "prophesy")
    _ie_keep = {'auntie', 'birdie', 'boogie', 'brownie', 'calorie', 'collie', 'cookie',
                'dearie', 'eerie', 'genie', 'goodie', 'hippie', 'junkie', 'lassie',
                'magpie', 'movie', 'necktie', 'pixie', 'prairie', 'smoothie', 'zombie',
                'die', 'lie', 'tie', 'pie', 'vie', 'hie'}
    text = re.sub(r'\b(\w{3,})ie\b', lambda m: m.group(0) if m.group(0).lower() in _ie_keep
        else m.group(1) + 'y', text, flags=re.IGNORECASE)

    # Generic: -lle → -l (e.g., "fulfille" → "fulfil")
    _lle_keep = {'gazelle', 'belle', 'mademoiselle', 'braille', 'grille', 'ville'}
    text = re.sub(r'\b(\w{3,})lle\b', lambda m: m.group(0) if m.group(0).lower() in _lle_keep
        else m.group(1) + 'l', text, flags=re.IGNORECASE)

    # Generic: -nesse → -ness (e.g., "fulnesse" → "fulness", "goodnesse" → "goodness")
    text = re.sub(r'\b(\w{3,})nesse\b', r'\1ness', text, flags=re.IGNORECASE)

    # Generic: -ousnes → -ousness
    text = re.sub(r'\b(\w+)ousnes\b', r'\1ousness', text, flags=re.IGNORECASE)

    # Generic: trailing -es on words that don't need it
    # e.g., "spoiles" → "spoils", "crownes" → "crowns"
    text = re.sub(r'\b(\w{3,}[ln])es\b', lambda m: m.group(0) if m.group(0).lower() in
        {'candles', 'handles', 'bundles', 'spindles', 'needles', 'riddles',
         'battles', 'bottles', 'castles', 'titles', 'articles', 'angles',
         'singles', 'temples', 'peoples', 'samples', 'examples', 'muscles',
         'circles', 'nobles', 'stables', 'tables', 'cables', 'fables',
         'enables', 'troubles', 'doubles', 'couples', 'bubbles', 'pebbles',
         'struggles', 'puzzles', 'nozzles', 'muzzles', 'buckles', 'knuckles',
         'pickles', 'wrinkles', 'sparkles', 'acles', 'icles', 'uncles',
         'principles', 'particles', 'obstacles', 'miracles', 'spectacles',
         'tentacles', 'chronicles', 'vehicles', 'rules', 'mules', 'holes',
         'poles', 'roles', 'soles', 'wales', 'tales', 'males', 'females',
         'sales', 'scales', 'whales', 'vales', 'bales', 'gales', 'ales',
         'miles', 'files', 'tiles', 'piles', 'smiles', 'styles', 'cycles',
         'lines', 'mines', 'vines', 'wines', 'pines', 'fines', 'dines',
         'shines', 'shrines', 'spines', 'stones', 'bones', 'tones', 'zones',
         'cones', 'drones', 'thrones', 'scenes', 'genes', 'lanes', 'canes',
         'planes', 'cranes', 'manes', 'panes', 'flames', 'names', 'games',
         'frames', 'tunes', 'dunes', 'prunes', 'plumes', 'fumes', 'volumes',
         'assumes', 'resumes', 'consumes', 'perfumes', 'costumes',
         'values', 'issues', 'tissues', 'venues', 'avenues', 'revenues',
         'statues', 'virtues', 'argues', 'continues', 'rescues', 'pursues',
         'gentiles', 'israelites', 'disciples', 'apostles', 'peoples'}
        else m.group(0), text, flags=re.IGNORECASE)

    # Specific remaining 1611 words commonly missed
    text = re.sub(r'\bspoiles\b', 'spoils', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhoste\b', 'host', text, flags=re.IGNORECASE)
    text = re.sub(r'\byeeres\b', 'years', text, flags=re.IGNORECASE)
    text = re.sub(r'\byeere\b', 'year', text, flags=re.IGNORECASE)
    text = re.sub(r'\byeare\b', 'year', text, flags=re.IGNORECASE)
    text = re.sub(r'\byeares\b', 'years', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcrownes\b', 'crowns', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhundreth\b', 'hundred', text, flags=re.IGNORECASE)
    text = re.sub(r'\bperswaded\b', 'persuaded', text, flags=re.IGNORECASE)
    text = re.sub(r'\bperswade\b', 'persuade', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdeuise\b', 'device', text, flags=re.IGNORECASE)
    text = re.sub(r'\bGreekes\b', 'Greeks', text)
    text = re.sub(r'\bgreekes\b', 'Greeks', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwan\b', 'won', text, flags=re.IGNORECASE)
    text = re.sub(r'\bholdes\b', 'holds', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcoate\b', 'coat', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwarres\b', 'wars', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprayse\b', 'praise', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprayses\b', 'praises', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwhilest\b', 'while', text, flags=re.IGNORECASE)
    text = re.sub(r'\bwarre\b', 'war', text, flags=re.IGNORECASE)
    text = re.sub(r'\bkinges\b', 'kings', text, flags=re.IGNORECASE)
    text = re.sub(r'\bprinces\b', 'princes', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcaptaines\b', 'captains', text, flags=re.IGNORECASE)
    text = re.sub(r'\brebelles\b', 'rebels', text, flags=re.IGNORECASE)
    text = re.sub(r'\bidoles\b', 'idols', text, flags=re.IGNORECASE)
    text = re.sub(r'\btemples\b', 'temples', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsacrifises\b', 'sacrifices', text, flags=re.IGNORECASE)
    text = re.sub(r'\bsacrifice\b', 'sacrifice', text, flags=re.IGNORECASE)
    text = re.sub(r'\babominacion\b', 'abomination', text, flags=re.IGNORECASE)
    text = re.sub(r'\boppresse\b', 'oppress', text, flags=re.IGNORECASE)
    text = re.sub(r'\bpossesse\b', 'possess', text, flags=re.IGNORECASE)
    text = re.sub(r'\bincreased\b', 'increased', text, flags=re.IGNORECASE)
    text = re.sub(r'\bslayne\b', 'slain', text, flags=re.IGNORECASE)
    text = re.sub(r'\bslaine\b', 'slain', text, flags=re.IGNORECASE)
    text = re.sub(r'\btenne\b', 'ten', text, flags=re.IGNORECASE)
    text = re.sub(r'\bfiftie\b', 'fifty', text, flags=re.IGNORECASE)
    text = re.sub(r'\bthirtie\b', 'thirty', text, flags=re.IGNORECASE)
    text = re.sub(r'\btwentie\b', 'twenty', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhundred\b', 'hundred', text, flags=re.IGNORECASE)
    text = re.sub(r'\bthousande\b', 'thousand', text, flags=re.IGNORECASE)

    # 1 Maccabees / Apocrypha additions
    text = re.sub(r'\bChettum\b', 'Kittim', text)              # Greek/Latin spelling of Kittim
    text = re.sub(r'\bbin\b', 'been', text, flags=re.IGNORECASE)  # archaic "bin" = "been"
    text = re.sub(r'\bheerein\b', 'herein', text, flags=re.IGNORECASE)
    text = re.sub(r'\bcustomes\b', 'customs', text, flags=re.IGNORECASE)
    text = re.sub(r'\bioyned\b', 'joined', text, flags=re.IGNORECASE)
    text = re.sub(r'\bmischiefe\b', 'mischief', text, flags=re.IGNORECASE)
    text = re.sub(r'\blicence\b', 'license', text, flags=re.IGNORECASE)
    text = re.sub(r'\bordinances\b', 'ordinances', text, flags=re.IGNORECASE)  # already correct

    # Generic I→J at word start for remaining cases (ioyned, iudge, etc.)
    # Only applies when followed by a lowercase vowel (avoid matching proper names handled above)
    text = re.sub(r'\bio([aeou][a-z])', lambda m: 'jo' + m.group(1), text)
    text = re.sub(r'\bIo([aeou][a-z])', lambda m: 'Jo' + m.group(1), text)

    return text

def split_into_words(text):
    """Split text into individual words."""
    return text.split()

def create_sections(words, max_words=1000):
    """Break words into multiple sections - handles both small and large texts."""
    sections = []
    
    # If text is small enough (less than 1.5x max_words), treat as single section
    if len(words) <= max_words * 1.5:
        print(f"📝 Text is {len(words)} words - processing as single section")
        sections.append(words)
        return sections
    
    # For larger texts, break into multiple sections
    print(f"📚 Text is {len(words)} words - breaking into multiple sections")
    current_section = []
    
    i = 0
    while i < len(words):
        # Add words to current section until we reach max_words
        while len(current_section) < max_words and i < len(words):
            current_section.append(words[i])
            i += 1
        
        # If we have a full section, try to end at a complete sentence
        if len(current_section) == max_words and i < len(words):
            section_text = ' '.join(current_section)
            
            # Find last complete sentence
            last_period = section_text.rfind('.')
            last_exclamation = section_text.rfind('!')
            last_question = section_text.rfind('?')
            last_sentence_end = max(last_period, last_exclamation, last_question)
            
            if last_sentence_end > len(section_text) * 0.7:  # Only if we don't cut too much
                clean_section_text = section_text[:last_sentence_end + 1]
                sections.append(clean_section_text.split())
                
                # Move remaining words to next section
                remaining_text = section_text[last_sentence_end + 1:].strip()
                current_section = remaining_text.split() if remaining_text else []
            else:
                # If no good sentence break, just use the full section
                sections.append(current_section[:])
                current_section = []
        else:
            # Add remaining words as final section
            if current_section:
                sections.append(current_section[:])
                current_section = []
    
    return sections

def format_section(words, section_num):
    """Format a single section with proper structure."""
    text = ' '.join(words)
    sentences = re.split(r'([.!?])', text)
    formatted_sentences = []
    sentence_count = 0
    
    for i in range(0, len(sentences) - 1, 2):
        if i + 1 < len(sentences):
            sentence = sentences[i] + sentences[i + 1]
            if sentence.strip():  # Only add non-empty sentences
                formatted_sentences.append(sentence.strip())
                sentence_count += 1
                
                # Add line break every 2 sentences for readability
                if sentence_count % 2 == 0:
                    formatted_sentences.append('\n')
    
    formatted_text = ''.join(formatted_sentences).strip()
    
    # Ensure sentences are spaced correctly: add a space after terminal punctuation
    # when it is immediately followed by a non-whitespace character (e.g., "Bible.Around" → "Bible. Around").
    formatted_text = re.sub(r'([.!?])(?=\S)', r'\1 ', formatted_text)
    
    # Add section header
    word_count = len(words)
    expected_minutes = word_count / 214  # Updated: 1000 words = 4:40 minutes
    expected_scenes = word_count // 40
    
    section_header = f"""
=== SECTION {section_num} ===
Words: {word_count} | Est. Video: {expected_minutes:.1f} min | Scenes: {expected_scenes}
Ready for Biblical Video Generator

"""
    
    return section_header + formatted_text

def read_input_file():
    """Read content from the Input file."""
    input_file = "Input"
    
    if not os.path.exists(input_file):
        print(f"❌ Error: '{input_file}' file not found!")
        print("   Please make sure the 'Input' file exists in the current directory.")
        return None
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        print(f"❌ Error reading '{input_file}': {e}")
        return None

def save_output(sections_text):
    """Save all processed sections to Output file."""
    output_file = "Output"
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(sections_text)
        print(f"All sections saved to: {output_file}")
        return True
    except Exception as e:
        print(f"Error saving to '{output_file}': {e}")
        return False

def main():
    print("=" * 70)
    print("BIBLICAL TEXT PROCESSOR V2 - MULTI-SECTION GENERATOR")
    print("=" * 70)
    print("Processes biblical text - single section OR multiple 1000-word sections")
    print("Each section optimized for Biblical Video Generator") 
    print("Generates ~4-5 minute videos per 1000 words at 214 WPM")
    print("Auto-cleans script formatting (stage directions, markdown, etc.)")
    print("-" * 70)
    
    print("\nReading biblical text from 'Input' file...")
    
    # Read from Input file
    raw_text = read_input_file()
    if raw_text is None:
        return
    
    print("Successfully loaded text from Input file")
    print(f"Raw text length: {len(raw_text)} characters")
    
    # Check if script formatting is present
    has_script_formatting = (
        '[' in raw_text or '**[' in raw_text or '---' in raw_text or 
        'Narrator (Voiceover)' in raw_text or '**(' in raw_text
    )
    
    if has_script_formatting:
        print("Script formatting detected - will be automatically cleaned")
    
    print("\nProcessing text...")
    
    # Clean and process the text
    cleaned_text = clean_text(raw_text)
    print("Fixing KJV text for narration (keeping thou/thee/ye/unto/shalt)...")
    narration_ready = kjv_narration_fix(cleaned_text)
    
    # Optional AI polish for sentence restructuring
    ai_polished = ai_polish_narration(narration_ready)
    if ai_polished:
        final_text = ai_polished
        print("Using AI-polished version (sentence restructuring applied)")
    else:
        final_text = narration_ready
        print("Using regex-cleaned version (AI polish skipped)")
    
    words = final_text.split()
    
    print(f"Total word count after cleaning: {len(words)} words")
    
    # Show cleaning results
    if has_script_formatting:
        print("Script formatting cleaned (stage directions, markdown, etc.)")
    
    if len(words) == 0:
        print("No words found after cleaning. The text may need manual review.")
        return
    
    # Create sections
    sections = create_sections(words, max_words=1000)
    
    if len(sections) == 1:
        print(f"Text processed as single section (ready for one video)")
    else:
        print(f"Text divided into {len(sections)} sections")
    
    # Format all sections
    all_sections_text = ""
    total_words = 0
    
    print("\nSECTION BREAKDOWN:")
    print("-" * 50)
    
    for i, section_words in enumerate(sections, 1):
        word_count = len(section_words)
        expected_minutes = word_count / 214  # Updated: Actual ElevenLabs timing
        total_words += word_count
        
        print(f"Section {i}: {word_count} words → {expected_minutes:.1f} min video")
        
        # Format this section
        formatted_section = format_section(section_words, i)
        all_sections_text += formatted_section
        
        # Add separator between sections (except for last section)
        if i < len(sections):
            all_sections_text += "\n\n" + "="*70 + "\n\n"
    
    print("-" * 50)
    print(f"TOTAL: {total_words} words across {len(sections)} section{'s' if len(sections) > 1 else ''}")
    print(f"Total video time: {(total_words / 214):.1f} minutes")
    if len(sections) == 1:
        print(f"Ready for single video generation")
    else:
        print(f"Ready for {len(sections)} separate video generations")
    
    # Save to Output file
    print(f"\nSaving all sections to 'Output' file...")
    
    # Add header to the output file
    output_header = f"""BIBLICAL TEXT PROCESSOR V2 - PROCESSED SECTIONS
Generated: Multiple sections from large biblical text
Total Sections: {len(sections)}
Total Words: {total_words}
Total Video Time: {(total_words / 214):.1f} minutes

Instructions:
- Each section below is optimized for Biblical Video Generator
- Copy individual sections for separate video generation
- Each section generates ~4-5 minutes of professional biblical video per 1000 words

{'='*70}

"""
    
    final_output = output_header + all_sections_text
    
    if save_output(final_output):
        print("SUCCESS! All sections processed and saved.")
        print(f"\nNext Steps:")
        print(f"   1. Open the 'Output' file")
        if len(sections) == 1:
            print(f"   2. Copy the processed text for your video")
            print(f"   3. Paste into Biblical Video Generator")
            print(f"\nYou now have 1 video-ready biblical section!")
        else:
            print(f"   2. Copy Section 1 for your first video")
            print(f"   3. Paste into Biblical Video Generator")
            print(f"   4. Repeat for remaining {len(sections)-1} sections")
            print(f"\nYou now have {len(sections)} video-ready biblical sections!")
    else:
        print("Error occurred while saving. Please check file permissions.")

if __name__ == "__main__":
    main()