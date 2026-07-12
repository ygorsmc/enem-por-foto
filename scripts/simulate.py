"""Simulador de conversa local — testa o fluxo completo sem Meta/Telegram.

Uso (na raiz do corretor-enem, com Redis rodando e .env preenchido):
    python -m scripts.simulate

Comandos do REPL:
    <texto>        mensagem de texto do aluno (ex.: /corrigir, o tema, etc.)
    foto <path>    simula o envio de uma foto (o arquivo local é a "mídia")
    btn <id>       simula o clique num botão (o id aparece nos botões impressos)
    sair           encerra

OCR e correção são REAIS (exigem MISTRAL_API_KEY e GOOGLE_API_KEY) — os envios
de mensagem são impressos no terminal em vez de irem para um provedor.
"""

import asyncio
import itertools
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.channels.interfaces import IMessagingChannel, InboundMessage  # noqa: E402
from src.flow.handlers import handle_message  # noqa: E402

_ids = itertools.count(1)


class ConsoleChannel(IMessagingChannel):
    """Canal fake: imprime as saídas e lê 'mídia' do disco local."""

    channel_name = "console"

    async def send_text(self, user_id: str, text: str, reply_to: str | None = None) -> dict:
        print(f"\n🤖 ─────────────────────────────\n{text}\n")
        return {}

    async def send_buttons(self, user_id: str, body: str, buttons: list[dict], footer: str = "") -> dict:
        print(f"\n🤖 ─────────────────────────────\n{body}")
        for btn in buttons:
            print(f"   [btn {btn['id']}]  {btn['title']}")
        print()
        return {}

    async def send_typing(self, user_id: str) -> None:
        print("   (digitando...)")

    async def download_media(self, media_id: str) -> bytes:
        return Path(media_id).read_bytes()

    def parse_inbound(self, raw_payload: dict) -> InboundMessage | None:
        return None

    async def verify_signature(self, body: bytes, headers: Mapping[str, str]) -> bool:
        return True

    def build_verification_response(self, query_params: Mapping[str, str]) -> Any:
        return None


def _make_msg(sender: str, line: str) -> InboundMessage | None:
    msg_id = str(next(_ids))
    if line.startswith("btn "):
        btn_id = line[4:].strip()
        return InboundMessage(
            sender_id=sender, text="", message_id=msg_id, message_type="interactive",
            interactive_payload={"type": "button_reply", "id": btn_id, "title": btn_id},
        )
    if line.startswith("foto "):
        path = line[5:].strip()
        if not Path(path).is_file():
            print(f"⚠️  Arquivo não encontrado: {path}")
            return None
        return InboundMessage(
            sender_id=sender, text="", message_id=msg_id, message_type="image", media_id=path,
        )
    return InboundMessage(sender_id=sender, text=line, message_id=msg_id, message_type="text")


async def main() -> None:
    channel = ConsoleChannel()
    sender = "aluno-simulado"
    print(__doc__)

    while True:
        try:
            line = input("👤 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line.lower() == "sair":
            break
        msg = _make_msg(sender, line)
        if msg:
            await handle_message(channel, msg)


if __name__ == "__main__":
    asyncio.run(main())
