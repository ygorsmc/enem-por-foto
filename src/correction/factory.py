from src.config import settings
from src.correction.interfaces import ICorrector

# Cache de instâncias por provedor — troca de CORRECTION_PROVIDER não precisa
# de restart para efeito nos testes; em produção só um provedor é usado.
_correctors: dict[str, ICorrector] = {}


def get_corrector(provider: str | None = None) -> ICorrector:
    """Retorna a instância do corretor ('gemini' | 'claude' | 'openai' | 'deepseek' | 'maritaca').

    Sem argumento, usa o provedor global (settings.CORRECTION_PROVIDER).
    """
    p = (provider or settings.CORRECTION_PROVIDER).lower()
    if p not in _correctors:
        if p == "gemini":
            from src.correction.providers.gemini import GeminiCorrector

            _correctors[p] = GeminiCorrector()
        elif p == "claude":
            from src.correction.providers.claude import ClaudeCorrector

            _correctors[p] = ClaudeCorrector()
        elif p == "openai":
            from src.correction.providers.openai_compatible import OpenAICompatibleCorrector

            _correctors[p] = OpenAICompatibleCorrector(
                "openai",
                settings.OPENAI_API_KEY,
                settings.CORRECTION_MODEL,
                max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
                max_tokens_param="max_completion_tokens",  # modelos de raciocínio da OpenAI recusam max_tokens
            )
        elif p == "deepseek":
            from src.correction.providers.openai_compatible import OpenAICompatibleCorrector

            _correctors[p] = OpenAICompatibleCorrector(
                "deepseek",
                settings.DEEPSEEK_API_KEY,
                settings.CORRECTION_MODEL,
                base_url="https://api.deepseek.com",
                reasoning_effort=settings.CORRECTION_EFFORT,
                max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
            )
        elif p == "maritaca":
            from src.correction.providers.openai_compatible import OpenAICompatibleCorrector

            _correctors[p] = OpenAICompatibleCorrector(
                "maritaca",
                settings.MARITACA_API_KEY,
                settings.CORRECTION_MODEL,
                base_url="https://chat.maritaca.ai/api",
            )
        else:
            raise ValueError(f"Provedor de correção não suportado: {p}")
    return _correctors[p]
