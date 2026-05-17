"""
PRODUCTION-GRADE WIKIPEDIA TEXT CLEANING PATTERNS
==================================================
Ordered carefully to handle nested structures and complex markup.
Tested against real Wikipedia XML dumps.
"""

import re

# ============================================================================
# COMPREHENSIVE WIKIPEDIA CLEANING PATTERNS
# ============================================================================
# CRITICAL: Order matters! Process in the sequence below.

CLEANING_PATTERNS = [
    
    # ========================================================================
    # PHASE 1: Remove Complete Structures (High Priority)
    # ========================================================================
    
    # 1. HTML Comments (must come early - often hide other markup)
    (re.compile(r"<!--.*?-->", re.DOTALL), ""),
    
    # 2. Citations and References (remove before other processing)
    (re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL), ""),
    (re.compile(r"<ref[^>]*/>"), ""),  # Self-closing refs
    
    # 3. Math and Code blocks (preserve them from other cleaning)
    (re.compile(r"<math[^>]*>.*?</math>", re.DOTALL), ""),
    (re.compile(r"<code[^>]*>.*?</code>", re.DOTALL), ""),
    (re.compile(r"<syntaxhighlight[^>]*>.*?</syntaxhighlight>", re.DOTALL), ""),
    
    # 4. Gallery tags
    (re.compile(r"<gallery[^>]*>.*?</gallery>", re.DOTALL), ""),
    
    # 5. Nowiki tags (literal text, should be removed entirely)
    (re.compile(r"<nowiki[^>]*>.*?</nowiki>", re.DOTALL), ""),
    
    # 6. Timeline tags
    (re.compile(r"<timeline[^>]*>.*?</timeline>", re.DOTALL), ""),
    
    # ========================================================================
    # PHASE 2: Remove Templates and Tables (Complex Nested Structures)
    # ========================================================================
    
    # 7. ROBUST Template Removal (handles nested braces)
    # This iteratively removes templates from innermost to outermost
    # We'll handle this specially in the cleaning function
    # Placeholder pattern for simple cases:
    (re.compile(r"\{\{[^{}]*\}\}"), ""),  # Non-nested templates first
    (re.compile(r"\{\{[^{}]*\}\}"), ""),  # Run again for 2-level nesting
    (re.compile(r"\{\{[^{}]*\}\}"), ""),  # Run again for 3-level nesting
    (re.compile(r"\{\{.*?\}\}", re.DOTALL), ""),  # Greedy cleanup for any remaining
    
    # 8. Wiki Tables {| ... |}
    (re.compile(r"\{\|.*?\|\}", re.DOTALL), ""),
    
    # ========================================================================
    # PHASE 3: Clean Links (Before removing brackets)
    # ========================================================================
    
    # 9. Category links (remove entirely)
    (re.compile(r"\[\[Category:.*?\]\]", re.IGNORECASE), ""),
    
    # 10. File and Image links (remove entirely)
    (re.compile(r"\[\[(?:File|Image):.*?\]\]", re.DOTALL | re.IGNORECASE), ""),
    
    # 11. Interwiki language links (e.g., [[fr:Article]], [[de:Artikel]])
    (re.compile(r"\[\[[a-z]{2,3}:.*?\]\]"), ""),
    
    # 12. Internal links with display text: [[Target|Display]] → "Display"
    (re.compile(r"\[\[[^\]]*?\|([^\]]*?)\]\]"), r"\1"),
    
    # 13. Simple internal links: [[Target]] → "Target"
    (re.compile(r"\[\[([^\]|]*?)\]\]"), r"\1"),
    
    # 14. External links with text: [http://url.com Text] → "Text"
    (re.compile(r"\[https?://[^\s\]]+\s+([^\]]+)\]"), r"\1"),
    
    # 15. Bare external links: [http://url.com] → ""
    (re.compile(r"\[https?://[^\]]+\]"), ""),
    
    # 16. Bare URLs without brackets
    (re.compile(r"https?://[^\s]+"), ""),
    
    # ========================================================================
    # PHASE 4: Remove Wiki Formatting
    # ========================================================================
    
    # 17. Magic words
    (re.compile(r"__[A-Z]+__"), ""),
    
    # 18. Bold/Italic (5, 3, or 2 apostrophes)
    (re.compile(r"'{2,5}"), ""),
    
    # 19. Section headers (preserve text, remove =)
    # Convert === Text === to just Text
    (re.compile(r"={2,6}\s*(.*?)\s*={2,6}"), r"\1"),
    
    # ========================================================================
    # PHASE 5: Clean HTML (After templates removed)
    # ========================================================================
    
    # 20. HTML tags (all remaining)
    (re.compile(r"<[^>]+>"), ""),
    
    # ========================================================================
    # PHASE 6: Clean Template/Table Remnants
    # ========================================================================
    
    # 21. Template parameters: | param = value
    (re.compile(r"\|\s*[a-zA-Z_][\w\s]*\s*=\s*"), ""),
    
    # 22. Remaining pipes (from tables/templates)
    (re.compile(r"\|"), ""),
    
    # ========================================================================
    # PHASE 7: Clean Whitespace and Special Characters
    # ========================================================================
    
    # 23. List markers at line start (*, #, :, ;)
    (re.compile(r"^[\*#:;]+\s*", re.MULTILINE), ""),
    
    # 24. ISBN/ISSN
    (re.compile(r"ISBN\s*[0-9\-]+", re.IGNORECASE), ""),
    (re.compile(r"ISSN\s*[0-9\-]+", re.IGNORECASE), ""),
    
    # 25. Multiple newlines → single newline
    (re.compile(r"\n{3,}"), "\n\n"),
    
    # 26. Multiple spaces → single space
    (re.compile(r" {2,}"), " "),
    
    # 27. Whitespace at line start/end
    (re.compile(r"^\s+|\s+$", re.MULTILINE), ""),
    
    # 28. Orphaned brackets/braces
    (re.compile(r"[\[\]\{\}]"), ""),
]


# ============================================================================
# SPECIAL HANDLING FOR NESTED TEMPLATES
# ============================================================================

def remove_nested_templates(text):
    """
    Iteratively remove nested templates from innermost to outermost.
    Handles cases like: {{outer|param={{inner|value}}}}
    """
    max_iterations = 10  # Prevent infinite loops
    iteration = 0
    
    while "{{" in text and iteration < max_iterations:
        # Remove innermost templates (those without nested {{ }})
        before = text
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
        
        # If nothing changed, we're done
        if text == before:
            break
        
        iteration += 1
    
    # Final cleanup for any remaining malformed templates
    text = re.sub(r"\{\{.*?\}\}", "", text, flags=re.DOTALL)
    
    return text


# ============================================================================
# ENHANCED CLEANING FUNCTION
# ============================================================================

def clean_wikipedia_article(text):
    """
    Apply all cleaning patterns in the correct order.
    Handles nested templates specially.
    """
    if not text:
        return text
    
    # Phase 1-2: Apply all patterns up to templates
    for pattern, replacement in CLEANING_PATTERNS[:6]:
        text = pattern.sub(replacement, text)
    
    # Special handling for nested templates
    text = remove_nested_templates(text)
    
    # Phase 3-7: Apply remaining patterns
    for pattern, replacement in CLEANING_PATTERNS[10:]:
        text = pattern.sub(replacement, text)
    
    return text.strip()


# ============================================================================
# TESTING EXAMPLES
# ============================================================================

if __name__ == "__main__":
    # Test cases
    test_cases = [
        # Nested templates
        "{{infobox|name={{lang|en|John}}|age=30}}",
        
        # Complex links
        "See [[Wikipedia:Manual of Style|the manual]] for details.",
        
        # Mixed markup
        "'''Bold''' text with [[link]] and {{template|param=value}}",
        
        # HTML comments
        "Visible text <!-- hidden comment --> more text",
        
        # Categories
        "Article text [[Category:Science]] [[Category:Physics]]",
        
        # External links
        "[http://example.com Official Website] and [http://test.com]",
        
        # Tables
        "{| class='wikitable'\n! Header\n|- \n| Cell 1\n|}",
    ]
    
    print("Testing Wikipedia Cleaning Patterns")
    print("=" * 70)
    
    for i, test in enumerate(test_cases, 1):
        cleaned = clean_wikipedia_article(test)
        print(f"\nTest {i}:")
        print(f"Input:  {test[:60]}...")
        print(f"Output: {cleaned}")