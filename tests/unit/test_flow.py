"""Máquina de estados de ponta a ponta — Redis fake, OCR/LLM monkeypatchados."""

import asyncio

import pytest

import src.flow.handlers as handlers
from src import messages as m
from src.config import settings
from src.correction.ocr import OcrResult
from src.flow.states import FlowState, load_flow
from tests.unit.conftest import button_msg, image_msg, text_msg

run = asyncio.run

FAKE_OCR_TEXT = "Texto da redação lido pelo OCR. " * 10   # > MIN_ESSAY_CHARS
FAKE_FEEDBACK = "📝 *NOTA ESTIMADA: 800/1000*"
THEME = "Desafios para a valorização de comunidades tradicionais no Brasil"


@pytest.fixture(autouse=True)
def fake_correction(monkeypatch):
    async def fake_ocr(image_bytes, mime_type="image/jpeg"):
        return OcrResult(text=FAKE_OCR_TEXT)

    async def fake_correct(theme, motivators, essay_text):
        return FAKE_FEEDBACK

    monkeypatch.setattr(handlers, "ocr_image", fake_ocr)
    monkeypatch.setattr(handlers, "correct_essay", fake_correct)


async def _consent(channel):
    await handlers.handle_message(channel, button_msg("consent_yes"))


async def _advance_to_confirming(channel):
    """Consentimento → tema → pular motivadores → foto (fica em CONFIRMING)."""
    await _consent(channel)
    await handlers.handle_message(channel, text_msg("/corrigir"))
    await handlers.handle_message(channel, text_msg(THEME))
    await handlers.handle_message(channel, button_msg("skip_motivators"))
    await handlers.handle_message(channel, image_msg())


class TestConsentGate:
    def test_first_contact_asks_consent(self, channel):
        run(handlers.handle_message(channel, text_msg("oi")))
        kind, _, btn_ids = channel.sent[0]
        assert kind == "buttons"
        assert btn_ids == ["consent_yes", "consent_no"]

    def test_nothing_processed_without_consent(self, channel):
        run(handlers.handle_message(channel, text_msg("/corrigir")))
        # Não inicia fluxo: só pede consentimento de novo.
        assert run(load_flow("fake", "aluno1")) is None

    def test_decline_is_respected(self, channel):
        run(handlers.handle_message(channel, button_msg("consent_no")))
        assert ("text", m.CONSENT_DECLINED) in channel.sent


class TestHappyPath:
    def test_full_flow_delivers_feedback_and_clears_state(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert any(FAKE_FEEDBACK in t for t in texts)
        assert any(m.CORRECTION_FOOTER in t for t in texts)
        # Estado limpo após a entrega.
        assert run(load_flow("fake", "aluno1")) is None

    def test_ocr_preview_is_shown_before_confirm(self, channel):
        run(_advance_to_confirming(channel))
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert any(FAKE_OCR_TEXT[:50] in t for t in texts)
        flow = run(load_flow("fake", "aluno1"))
        assert flow.state == FlowState.CONFIRMING

    def test_motivators_are_collected(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/corrigir"))
            await handlers.handle_message(channel, text_msg(THEME))
            await handlers.handle_message(channel, text_msg("Texto motivador I"))
            await handlers.handle_message(channel, text_msg("Texto motivador II"))
            await handlers.handle_message(channel, button_msg("done_motivators"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.motivators == ["Texto motivador I", "Texto motivador II"]
        assert flow.state == FlowState.AWAITING_ESSAY_PHOTO


class TestTextOnlyForThemeAndMotivators:
    def test_photo_as_theme_is_refused(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/corrigir"))
            await handlers.handle_message(channel, image_msg())
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert ("text", m.THEME_MUST_BE_TEXT) in channel.sent
        assert flow.state == FlowState.AWAITING_THEME  # não avançou

    def test_photo_as_motivator_is_refused(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/corrigir"))
            await handlers.handle_message(channel, text_msg(THEME))
            await handlers.handle_message(channel, image_msg())
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert any(s[0] == "buttons" and s[1] == m.MOTIVATORS_MUST_BE_TEXT for s in channel.sent)
        assert flow.state == FlowState.AWAITING_MOTIVATORS

    def test_short_theme_is_rejected(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/corrigir"))
            await handlers.handle_message(channel, text_msg("Drogas"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert ("text", m.THEME_TOO_SHORT) in channel.sent
        assert flow.state == FlowState.AWAITING_THEME


class TestPhotoHandling:
    def test_illegible_photo_asks_again(self, channel, monkeypatch):
        async def bad_ocr(image_bytes, mime_type="image/jpeg"):
            return OcrResult(text="curto")  # < MIN_ESSAY_CHARS

        monkeypatch.setattr(handlers, "ocr_image", bad_ocr)

        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/corrigir"))
            await handlers.handle_message(channel, text_msg(THEME))
            await handlers.handle_message(channel, button_msg("skip_motivators"))
            await handlers.handle_message(channel, image_msg())
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert ("text", m.ESSAY_OCR_FAILED) in channel.sent
        assert flow.state == FlowState.AWAITING_ESSAY_PHOTO
        assert flow.essay_parts == []

    def test_add_photo_concatenates_parts(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("add_photo"))
            await handlers.handle_message(channel, image_msg("media-2"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert len(flow.essay_parts) == 2
        assert flow.state == FlowState.CONFIRMING

    def test_redo_photo_resets_parts(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("redo_photo"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.essay_parts == []
        assert flow.state == FlowState.AWAITING_ESSAY_PHOTO
        # Tema e motivadores são preservados no refazer.
        assert flow.theme == THEME


class TestManualTextEdit:
    EDITED = "Texto ajustado pelo aluno depois do OCR errar a letra dele. " * 5

    def test_edit_button_sends_full_text_to_copy(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("edit_text"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        # O texto integral vai numa mensagem própria, fácil de copiar.
        assert ("text", flow.essay_text) in channel.sent
        assert flow.state == FlowState.EDITING_TEXT

    def test_edited_text_replaces_ocr_and_asks_confirmation(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("edit_text"))
            await handlers.handle_message(channel, text_msg(self.EDITED))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.essay_parts == [self.EDITED.strip()]
        assert flow.state == FlowState.CONFIRMING
        # Eco do texto ajustado com confirmar/editar de novo — sem corrigir ainda.
        kind, body, btn_ids = channel.sent[-1]
        assert kind == "buttons"
        assert self.EDITED[:50] in body
        assert btn_ids == ["confirm_correct", "edit_text"]
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert not any(FAKE_FEEDBACK in t for t in texts)

    def test_correction_uses_edited_text(self, channel, monkeypatch):
        seen = {}

        async def spy_correct(theme, motivators, essay_text):
            seen["essay"] = essay_text
            return FAKE_FEEDBACK

        monkeypatch.setattr(handlers, "correct_essay", spy_correct)

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("edit_text"))
            await handlers.handle_message(channel, text_msg(self.EDITED))
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        assert seen["essay"] == self.EDITED.strip()

    def test_short_edited_text_is_rejected(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("edit_text"))
            await handlers.handle_message(channel, text_msg("ok"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert ("text", m.EDITED_TEXT_TOO_SHORT) in channel.sent
        assert flow.state == FlowState.EDITING_TEXT  # segue esperando o texto
        assert flow.essay_parts == [FAKE_OCR_TEXT.strip()]  # OCR intacto

    def test_photo_during_edit_is_refused(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("edit_text"))
            await handlers.handle_message(channel, image_msg("media-2"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert ("text", m.EDITED_TEXT_MUST_BE_TEXT) in channel.sent
        assert flow.state == FlowState.EDITING_TEXT
        assert flow.essay_parts == [FAKE_OCR_TEXT.strip()]

    def test_edit_again_after_echo_restarts_edit(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("edit_text"))
            await handlers.handle_message(channel, text_msg(self.EDITED))
            await handlers.handle_message(channel, button_msg("edit_text"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.state == FlowState.EDITING_TEXT
        # A cópia reenviada é a versão JÁ editada, não o OCR original.
        assert ("text", self.EDITED.strip()) in channel.sent


class TestLowConfidenceWords:
    FLAGGED = ["intransponível", "hodierno"]

    def _patch_flagging_ocr(self, monkeypatch):
        async def ocr(image_bytes, mime_type="image/jpeg"):
            return OcrResult(text=FAKE_OCR_TEXT, low_confidence_words=list(self.FLAGGED))

        monkeypatch.setattr(handlers, "ocr_image", ocr)

    def test_flagged_words_shown_in_preview(self, channel, monkeypatch):
        self._patch_flagging_ocr(monkeypatch)
        run(_advance_to_confirming(channel))
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        # Poucas palavras (2): mensagem pontual "confira estas palavras".
        assert any("Palavras a conferir" in t and "intransponível" in t for t in texts)
        assert not any("ficou difícil" in t for t in texts)
        flow = run(load_flow("fake", "aluno1"))
        assert flow.flagged_words == self.FLAGGED

    def test_many_flagged_words_asks_to_reread(self, channel, monkeypatch):
        # Letra difícil: OCR incerto em muitas palavras → pede releitura do texto todo.
        many = [f"palavra{i}" for i in range(12)]

        async def ocr(image_bytes, mime_type="image/jpeg"):
            return OcrResult(text=FAKE_OCR_TEXT, low_confidence_words=list(many))

        monkeypatch.setattr(handlers, "ocr_image", ocr)
        run(_advance_to_confirming(channel))
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert any("ficou difícil" in t and "reler o texto inteiro" in t for t in texts)
        # Mostra só as primeiras (piores), não a lista inteira.
        preview = next(t for t in texts if "ficou difícil" in t)
        assert "palavra0" in preview and "palavra11" not in preview

    def test_no_note_when_all_confident(self, channel):
        # OCR padrão (autouse) não devolve palavras incertas → sem nota.
        run(_advance_to_confirming(channel))
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert not any("Palavras a conferir" in t for t in texts)

    def test_manual_edit_clears_flagged(self, channel, monkeypatch):
        self._patch_flagging_ocr(monkeypatch)
        edited = "Texto ajustado pelo aluno com a leitura conferida na folha. " * 5

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("edit_text"))
            await handlers.handle_message(channel, text_msg(edited))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.flagged_words == []

    def test_redo_photo_clears_flagged(self, channel, monkeypatch):
        self._patch_flagging_ocr(monkeypatch)

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("redo_photo"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.flagged_words == []


class TestRateLimitAndFailures:
    def test_rate_limit_blocks_after_daily_quota(self, channel, fake_redis):
        async def scenario():
            await _advance_to_confirming(channel)
            for _ in range(settings.ESSAY_DAILY_LIMIT):
                await handlers.handle_message(channel, button_msg("confirm_correct"))
                await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert any("correções de hoje" in t for t in texts)

    def test_quota_exhausted_skips_ocr(self, channel, monkeypatch):
        """A cota é espiada ANTES do OCR: sem correção disponível, nem chama o
        Mistral à toa (custo evitado)."""
        ocr_calls = 0

        async def counting_ocr(image_bytes, mime_type="image/jpeg"):
            nonlocal ocr_calls
            ocr_calls += 1
            return OcrResult(text=FAKE_OCR_TEXT)

        monkeypatch.setattr(handlers, "ocr_image", counting_ocr)

        async def scenario():
            for _ in range(settings.ESSAY_DAILY_LIMIT):
                await _advance_to_confirming(channel)
                await handlers.handle_message(channel, button_msg("confirm_correct"))
            # Cota esgotada: a próxima foto não deve nem chamar o OCR.
            await _advance_to_confirming(channel)
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert ocr_calls == settings.ESSAY_DAILY_LIMIT  # não rodou na tentativa bloqueada
        assert any("correções de hoje" in t for t in texts)
        assert flow.state == FlowState.AWAITING_ESSAY_PHOTO  # não avançou pra CONFIRMING
        assert flow.essay_parts == []

    def test_correction_failure_refunds_credit_and_keeps_state(self, channel, monkeypatch):
        async def broken_correct(theme, motivators, essay_text):
            raise RuntimeError("boom")

        monkeypatch.setattr(handlers, "correct_essay", broken_correct)

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("confirm_correct"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert ("text", m.CORRECTION_FAILED) in channel.sent
        # Estado preservado: o aluno tenta de novo sem repetir o fluxo.
        assert flow.state == FlowState.CONFIRMING

    def test_refund_leaves_counter_at_zero(self, channel, fake_redis, monkeypatch):
        async def broken_correct(theme, motivators, essay_text):
            raise RuntimeError("boom")

        monkeypatch.setattr(handlers, "correct_essay", broken_correct)

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        counters = [int(v) for k, v in fake_redis.store.items() if k.startswith("essay_count:")]
        assert counters and all(c == 0 for c in counters)


class TestCommands:
    def test_cancel_clears_state(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/corrigir"))
            await handlers.handle_message(channel, text_msg(THEME))
            await handlers.handle_message(channel, text_msg("/cancelar"))
            return await load_flow("fake", "aluno1")

        assert run(scenario()) is None
        assert ("text", m.CANCELLED) in channel.sent

    def test_corrigir_mid_flow_restarts(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, text_msg("/corrigir"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.state == FlowState.AWAITING_THEME
        assert flow.essay_parts == []

    def test_idle_photo_gets_guidance(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, image_msg())

        run(scenario())
        assert any(s[0] == "buttons" and s[1] == m.PHOTO_UNEXPECTED for s in channel.sent)
