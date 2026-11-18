"""Official text-model catalogue verified on 2026-11-18; quotas remain project-specific."""
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
FREE_TEXT_MODELS = ('gemini-4-hydrogen','gemini-3.8-flash','gemini-3.5-flash-lite','gemini-3.6-flash')
FALLBACK_MODELS = ('gemini-3.8-flash','gemini-3.5-flash-lite')
PRICING_URL = 'https://ai.google.dev/gemini-api/docs/pricing'
MODELS_URL = 'https://ai.google.dev/gemini-api/docs/models'


def candidates(selected):
    # Custom models remain usable, but never silently switch their provider/contract.
    return list(dict.fromkeys([selected]+(list(FALLBACK_MODELS) if selected in FREE_TEXT_MODELS else [])))
