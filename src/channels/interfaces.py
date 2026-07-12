from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass
class InboundMessage:
    """Mensagem normalizada, independente do canal de origem."""
    sender_id: str          # phone (WhatsApp) ou chat_id (Telegram)
    text: str
    message_id: str
    message_type: str       # "text" | "interactive" | "image" | "unknown"
    interactive_payload: dict | None = None
    sender_name: str = ""
    # Id da mídia no provedor (foto da redação). O download acontece SEMPRE na
    # task de background (download_media), nunca no handler do webhook (SLA 200ms).
    media_id: str | None = None


class IMessagingChannel(ABC):
    """Interface agnóstica para canais de mensageria (WhatsApp, Telegram, etc.)."""

    # Nome canônico do canal ('whatsapp' | 'telegram'). Também é o namespace das
    # chaves de estado no Redis (flow:{canal}:{sender}).
    channel_name: str = ""

    @abstractmethod
    async def send_text(self, user_id: str, text: str, reply_to: str | None = None) -> dict:
        """Envia texto simples. Texto longo é dividido em várias mensagens."""
        pass

    @abstractmethod
    async def send_buttons(self, user_id: str, body: str, buttons: list[dict], footer: str = "") -> dict:
        """
        Envia uma mensagem com botões interativos (máx 3 no WhatsApp).
        Formato de `buttons`: [{"id": "btn_id", "title": "Btn Title"}]
        """
        pass

    @abstractmethod
    async def send_typing(self, user_id: str) -> None:
        """Indicador de 'digitando...' (no-op no WhatsApp Cloud API)."""
        pass

    @abstractmethod
    async def download_media(self, media_id: str) -> bytes:
        """Baixa uma mídia recebida (foto da redação)."""
        pass

    @abstractmethod
    def parse_inbound(self, raw_payload: dict) -> InboundMessage | None:
        """Converte o payload bruto do provedor em um InboundMessage normalizado."""
        pass

    @abstractmethod
    async def verify_signature(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """Verifica se a requisição de entrada é autêntica e veio do provedor."""
        pass

    @abstractmethod
    def build_verification_response(self, query_params: Mapping[str, str]) -> Any:
        """Responde ao desafio de verificação do provedor (ex: hub.challenge do Meta)."""
        pass
