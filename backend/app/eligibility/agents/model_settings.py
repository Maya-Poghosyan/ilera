"""Output limits shared by every eligibility agent (API and Functions)."""

# Completion budgets include reasoning tokens; each leaves room for validated JSON.
ELIGIBILITY_MAX_TOKENS = 4096
RESEARCH_MAX_TOKENS = 3072
REASONING_EFFORT = "low"
