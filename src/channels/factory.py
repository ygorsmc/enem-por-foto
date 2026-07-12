from src.channels.interfaces import IMessagingChannel
from src.config import settings

# Cache de instâncias por tipo de canal — WhatsApp e Telegram coexistem no
# mesmo processo (cada webhook resolve o seu).
_channels: dict[str, IMessagingChannel] = {}


def get_channel(channel_type: str | None = None) -> IMessagingChannel:
    """Retorna a instância do canal ('whatsapp' | 'telegram').

    Sem argumento, usa o canal global (settings.CHANNEL_BACKEND).
    """
    ct = (channel_type or settings.CHANNEL_BACKEND).lower()
    if ct not in _channels:
        if ct == "telegram":
            from src.channels.telegram import TelegramChannel
            _channels[ct] = TelegramChannel()
        elif ct == "whatsapp":
            from src.channels.whatsapp import WhatsAppChannel
            _channels[ct] = WhatsAppChannel()
        else:
            raise ValueError(f"Canal não suportado: {ct}")
    return _channels[ct]
