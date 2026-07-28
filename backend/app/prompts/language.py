# backend/app/prompts/language.py
"""The single prompt-side statement of the CLAUDE.md §2 vocabulary rules.

Every prompt whose output can reach a client imports LANGUAGE_RULES from here.
It used to be copy-pasted per prompt file, and the copies had already drifted —
assessment.py taught the model about "AI Search Ranking" while deliverables.py
did not, so the same banned phrase was allowed in one client-facing surface and
forbidden in another.

This is the *instruction* half of the defense. The *enforcement* half is
app.services.language_sanitizer.sanitize_text(), which every service must still
run over the model's output — prompt rules alone have leaked banned vocabulary
into shipped surfaces twice. Keep the two in step: a term added to
FORBIDDEN_REPLACEMENTS belongs in this string too.
"""

LANGUAGE_RULES = (
    'Vocabulary rules — these are absolute. Never use the words "citation", '
    '"cited", "uncited", "mentioned", "not mentioned", "first mentioned", '
    '"citation rate", "ranking position", "visibility gap", "confidence score", '
    '"char offset", or "token count". Instead say "seen by AI" (or "not seen by '
    'AI"), "first seen by AI", "visibility frequency", "AI Search Ranking", and '
    '"Your competitors are winning here". Never surface internal scoring '
    "internals to the reader."
)
