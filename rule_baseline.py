"""Small English keyword baseline; editable without loading the model."""
import re

KEYWORDS = {
    "billing": ("payment", "payments", "charge", "charges", "charged", "refund", "invoice", "invoices", "receipt", "fee", "price", "renewal", "tax"),
    "technical": ("api", "401", "token", "password", "login", "log in", "sign in", "signing in", "authentication", "two-factor", "app", "dashboard", "upload", "uploads", "error", "errors", "crash", "blank"),
    "delivery": ("parcel", "parcels", "package", "shipment", "tracking", "courier", "delivery", "boxes", "sorting centre", "sorting center"),
}
PRIORITY_MARKERS = ("first", "priority", "main problem", "main issue", "most important")


def keyword_matches(text):
    return {department: [word for word in words if re.search(
        r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, flags=re.IGNORECASE)]
        for department, words in KEYWORDS.items()}


def route_by_rules(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Ticket text must not be empty")
    matches = keyword_matches(text)
    departments = [key for key, words in matches.items() if words]
    primary = []
    if len(departments) > 1:
        for clause in re.split(r"[.;!?]", text):
            if any(re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", clause, re.IGNORECASE)
                   for marker in PRIORITY_MARKERS):
                local = [key for key, words in keyword_matches(clause).items() if words]
                if len(local) == 1:
                    primary.append(local[0])
    if len(set(primary)) == 1:
        choice = primary[0]
    else:
        choice = departments[0] if len(departments) == 1 else "needs_clarification"
    return {"choice": choice, "matches": matches, "primary_clause_matches": primary,
            "model_calls": 0, "probabilities": None}
