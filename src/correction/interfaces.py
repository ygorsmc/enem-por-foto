from abc import ABC, abstractmethod


class ICorrector(ABC):
    """Interface agnóstica de provedor de LLM para a correção ENEM.

    Cada implementação decide sozinha como combinar o bloco estático
    (ENEM_CORRECTION_SYSTEM, ~6000 tokens, idêntico em toda chamada) com o
    bloco dinâmico recebido aqui — cache explícito, cache automático do
    provedor, ou simples concatenação, conforme o que cada API suporta.
    """

    provider_name: str = ""

    @abstractmethod
    async def correct(self, input_block: str) -> str:
        """Corrige a redação a partir do bloco dinâmico já formatado
        (TEMA/TEXTOS MOTIVADORES/REDAÇÃO) e retorna o feedback."""
        pass
