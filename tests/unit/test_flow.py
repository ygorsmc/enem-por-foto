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

    async def fake_correct(theme, motivators, essay_text, mode=None):
        return FAKE_FEEDBACK

    monkeypatch.setattr(handlers, "ocr_image", fake_ocr)
    monkeypatch.setattr(handlers, "correct_essay", fake_correct)
    # Um modo só por padrão (botão "Corrigir agora"); TestDoisModos liga o "ambos". Não depende do .env do dev.
    monkeypatch.setattr(settings, "CORRECTION_MODE", "llm")


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

    def test_accept_starts_the_flow_in_one_message(self, channel):
        # Boas-vindas + pedido do tema numa mensagem só, sem menu com botão "começar".
        run(handlers.handle_message(channel, button_msg("consent_yes")))
        assert channel.sent == [("text", m.WELCOME_START)]
        assert run(load_flow("fake", "aluno1")).state == FlowState.AWAITING_THEME


class TestHappyPath:
    def test_full_flow_delivers_feedback_and_clears_state(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "CORRECTION_MODE", "llm")

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
        bodies = [s[1] for s in channel.sent]
        assert any(FAKE_OCR_TEXT[:50] in t for t in bodies)
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

        async def spy_correct(theme, motivators, essay_text, mode=None):
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
        texts = [s[1] for s in channel.sent]
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
        texts = [s[1] for s in channel.sent]
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
        async def broken_correct(theme, motivators, essay_text, mode=None):
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
        async def broken_correct(theme, motivators, essay_text, mode=None):
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
            await handlers.handle_message(channel, text_msg("/cancelar"))  # o aceite já abre o fluxo
            await handlers.handle_message(channel, image_msg())

        run(scenario())
        assert any(s[0] == "buttons" and s[1] == m.PHOTO_UNEXPECTED for s in channel.sent)


class TestTermoERodape:
    """O termo nomeia os serviços externos por onde a redação passa (LGPD) e o rodapé diz de onde vem a nota."""

    def test_termo_hibrido_nomeia_os_tres_servicos(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "CORRECTION_MODE", "hibrido")
        monkeypatch.setattr(settings, "CORRECTION_PROVIDER", "deepseek")
        run(handlers.handle_message(channel, text_msg("oi")))
        _, body, _ = channel.sent[0]
        for trecho in ("Mistral", "França", "Jev", "TypeSafe AI, EUA", "DeepSeek", "China", "aprendizado de máquina"):
            assert trecho in body
        # O prazo do texto no banco vem do TTL real do estado (expira no próprio Redis).
        assert f"até {settings.FLOW_TTL_SECONDS // 60} minutos" in body and "registro do seu aceite" in body
        assert "{" not in body and "}" not in body

    def test_termo_llm_cita_o_provedor_e_nao_o_jev(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "CORRECTION_MODE", "llm")
        monkeypatch.setattr(settings, "CORRECTION_PROVIDER", "gemini")
        run(handlers.handle_message(channel, text_msg("oi")))
        _, body, _ = channel.sent[0]
        assert "Gemini" in body and "Mistral" in body
        assert "Jev" not in body and "aprendizado de máquina" not in body
        assert "{" not in body

    def test_rodape_hibrido_cita_machine_learning(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "CORRECTION_MODE", "hibrido")

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert any(m.CORRECTION_FOOTER_HIBRIDO in t for t in texts)
        assert "machine learning" in m.CORRECTION_FOOTER_HIBRIDO


class TestPhotoLimit:
    """Cada foto é uma leitura paga do OCR: PHOTOS_PER_ESSAY por correção permitida no dia."""

    def test_foto_alem_do_limite_e_barrada_sem_chamar_o_ocr(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "ESSAY_DAILY_LIMIT", 2)
        monkeypatch.setattr(settings, "PHOTOS_PER_ESSAY", 3)
        ocr_calls = 0

        async def counting_ocr(image_bytes, mime_type="image/jpeg"):
            nonlocal ocr_calls
            ocr_calls += 1
            return OcrResult(text=FAKE_OCR_TEXT)

        monkeypatch.setattr(handlers, "ocr_image", counting_ocr)

        async def scenario():
            await _advance_to_confirming(channel)  # 1ª foto
            for _ in range(6):  # 2ª a 7ª: refaz e manda de novo, sem nunca confirmar
                await handlers.handle_message(channel, button_msg("redo_photo"))
                await handlers.handle_message(channel, image_msg())

        run(scenario())
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert ocr_calls == 6  # a 7ª não chegou ao OCR
        assert texts[-1] == m.PHOTO_LIMIT_REACHED.format(limit=6, per_essay=3)

    def test_correcoes_nao_consomem_o_limite_de_fotos(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "ESSAY_DAILY_LIMIT", 2)
        monkeypatch.setattr(settings, "PHOTOS_PER_ESSAY", 3)

        async def scenario():
            for _ in range(2):  # 2 correções com 1 foto cada = 2 leituras de 6
                await _advance_to_confirming(channel)
                await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        texts = [s[1] for s in channel.sent if s[0] == "text"]
        assert not any("fotos hoje" in t for t in texts)


LONG_TYPED = "A redação digitada pelo aluno, com os mesmos erros da folha. " * 5


async def _advance_to_essay_step(channel):
    await _consent(channel)
    await handlers.handle_message(channel, text_msg(THEME))
    await handlers.handle_message(channel, button_msg("skip_motivators"))


class TestTypedEssay:
    """No passo da foto, o aluno pode digitar ou colar o texto: sem OCR e sem gastar leitura de foto."""

    def test_pedido_da_foto_oferece_o_texto_com_aviso_do_corretor(self):
        assert "digitar ou colar o texto" in m.ASK_ESSAY_PHOTO
        assert "corretor automático" in m.ASK_ESSAY_PHOTO and "Competência 1" in m.ASK_ESSAY_PHOTO

    def test_typed_essay_goes_to_confirmation_without_ocr(self, channel, monkeypatch, fake_redis):
        async def no_ocr(*a, **k):
            raise AssertionError("OCR não deveria rodar para texto digitado")

        monkeypatch.setattr(handlers, "ocr_image", no_ocr)

        async def scenario():
            await _advance_to_essay_step(channel)
            await handlers.handle_message(channel, text_msg(LONG_TYPED))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.state == FlowState.CONFIRMING
        assert flow.essay_parts == [LONG_TYPED.strip()]
        kind, body, ids = channel.sent[-1]
        assert kind == "buttons" and LONG_TYPED[:40] in body
        assert ids == ["confirm_correct", "edit_text"]
        assert not any(k.startswith("photo_count:") for k in fake_redis.store)  # leitura de foto não gasta

    def test_typed_essay_is_what_gets_corrected(self, channel, monkeypatch):
        seen = {}

        async def fake_correct(theme, motivators, essay_text, mode=None):
            seen["essay"] = essay_text
            return FAKE_FEEDBACK

        monkeypatch.setattr(handlers, "correct_essay", fake_correct)

        async def scenario():
            await _advance_to_essay_step(channel)
            await handlers.handle_message(channel, text_msg(LONG_TYPED))
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        assert seen["essay"] == LONG_TYPED.strip()

    def test_short_text_gets_reminder(self, channel):
        async def scenario():
            await _advance_to_essay_step(channel)
            await handlers.handle_message(channel, text_msg("ok"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert channel.sent[-1] == ("text", m.ESSAY_AWAITING_PHOTO_REMINDER)
        assert flow.state == FlowState.AWAITING_ESSAY_PHOTO

    def test_typed_essay_respects_daily_quota(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "ESSAY_DAILY_LIMIT", 0)

        async def scenario():
            await _advance_to_essay_step(channel)
            await handlers.handle_message(channel, text_msg(LONG_TYPED))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert channel.sent[-1] == ("text", m.RATE_LIMITED.format(limit=0))
        assert flow.state == FlowState.AWAITING_ESSAY_PHOTO


class TestMenosMensagens:
    """Plano de mensagens enxuto, igual nos dois canais (o WhatsApp cobra por mensagem)."""

    def test_photo_shows_typing_instead_of_a_waiting_message(self, channel):
        run(_advance_to_confirming(channel))
        assert "m2" in channel.typing  # indicador atrelado à mensagem da foto
        assert not any("Estou lendo" in s[1] for s in channel.sent)

    def test_preview_and_buttons_in_one_message(self, channel):
        run(_advance_to_confirming(channel))
        kind, body, ids = channel.sent[-1]
        assert kind == "buttons" and FAKE_OCR_TEXT[:40] in body and body.endswith(m.CHOOSE_ACTION)
        assert ids == ["confirm_correct", "edit_text", "redo_photo"]

    def test_no_button_after_feedback(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "CORRECTION_MODE", "llm")

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        kind, body = channel.sent[-1][:2]
        assert kind == "text" and body.endswith(m.CORRECTION_FOOTER)
        assert "/corrigir" in m.CORRECTION_FOOTER and "botão" not in m.CORRECTION_FOOTER

    def test_full_correction_message_count(self, channel):
        # Aceite → tema → pular motivadores → foto → corrigir: 6 mensagens do bot (eram 10, sem contar a divisão do
        # feedback): boas-vindas+tema, motivadores, pedido da foto, preview+botões, "corrigindo", feedback.
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg(THEME))
            await handlers.handle_message(channel, button_msg("skip_motivators"))
            await handlers.handle_message(channel, image_msg())
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        assert len(channel.sent) == 6



class TestTermoVersionado:
    """O aceite vale para a versão do termo: só é pedido de novo quando o texto muda."""

    def test_consent_is_asked_only_once(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/cancelar"))
            await handlers.handle_message(channel, text_msg("oi"))

        run(scenario())
        assert not any(s[0] == "buttons" and s[2] == ["consent_yes", "consent_no"] for s in channel.sent)

    def test_term_change_asks_again_with_update_notice(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "CORRECTION_PROVIDER", "deepseek")
        run(_consent(channel))
        monkeypatch.setattr(settings, "CORRECTION_PROVIDER", "gemini")  # o termo agora nomeia outro serviço
        run(handlers.handle_message(channel, text_msg("oi")))
        kind, body, ids = channel.sent[-1]
        assert kind == "buttons" and ids == ["consent_yes", "consent_no"]
        assert body.startswith(m.CONSENT_INTRO_UPDATED) and "Gemini" in body

    def test_accepting_new_version_unlocks_the_bot(self, channel, monkeypatch):
        run(_consent(channel))
        monkeypatch.setattr(settings, "FLOW_TTL_SECONDS", 3600)  # prazo de guarda mudou → versão nova
        run(_consent(channel))
        assert channel.sent[-1] == ("text", m.WELCOME_START)
        assert run(handlers.accepted_consent_version("fake", "aluno1")) == handlers._consent_version()

    def test_legacy_consent_is_asked_again(self, channel, fake_redis):
        fake_redis.store["consent:fake:aluno1"] = "1"  # aceites anteriores ao versionamento
        run(handlers.handle_message(channel, text_msg("oi")))
        assert channel.sent[-1][1].startswith(m.CONSENT_INTRO_UPDATED)

    def test_declining_new_version_revokes_old_consent(self, channel, monkeypatch, fake_redis):
        run(_consent(channel))
        monkeypatch.setattr(settings, "FLOW_TTL_SECONDS", 3600)
        run(handlers.handle_message(channel, button_msg("consent_no")))
        assert "consent:fake:aluno1" not in fake_redis.store
        assert run(load_flow("fake", "aluno1")) is None
        assert channel.sent[-1] == ("text", m.CONSENT_DECLINED)

    def test_first_contact_uses_greeting(self, channel):
        run(handlers.handle_message(channel, text_msg("oi")))
        assert channel.sent[0][1].startswith(m.CONSENT_INTRO)


class TestDoisModos:
    """CORRECTION_MODE=ambos: um botão por modo (modelo treinado ou IA) no lugar de "Corrigir agora"."""

    @pytest.fixture(autouse=True)
    def ambos(self, monkeypatch):
        monkeypatch.setattr(settings, "CORRECTION_MODE", "ambos")
        self.calls = []

        async def fake_correct(theme, motivators, essay_text, mode=None):
            self.calls.append(mode)
            return FAKE_FEEDBACK

        monkeypatch.setattr(handlers, "correct_essay", fake_correct)

    def test_preview_offers_both_modes_and_edit(self, channel):
        run(_advance_to_confirming(channel))
        kind, body, ids = channel.sent[-1]
        assert ids == ["correct_ml", "correct_llm", "edit_text"]  # 3 botões: o limite do WhatsApp
        assert body.endswith(m.CHOOSE_MODE + m.REDO_COMMAND_HINT)
        assert "Refazer foto" not in body

    def test_typed_essay_offers_both_modes_without_redo_hint(self, channel):
        async def scenario():
            await _advance_to_essay_step(channel)
            await handlers.handle_message(channel, text_msg(LONG_TYPED))

        run(scenario())
        _, body, ids = channel.sent[-1]
        assert ids == ["correct_ml", "correct_llm", "edit_text"]
        assert m.CHOOSE_MODE in body and "/refazer" not in body

    @pytest.mark.parametrize(("btn", "mode", "footer"), [
        ("correct_ml", "hibrido", m.CORRECTION_FOOTER_HIBRIDO),
        ("correct_llm", "llm", m.CORRECTION_FOOTER),
    ])
    def test_each_button_runs_its_mode(self, channel, btn, mode, footer):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg(btn))

        run(scenario())
        assert self.calls == [mode]
        assert channel.sent[-1][1].endswith(footer)

    def test_old_confirm_button_uses_default_mode(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, button_msg("confirm_correct"))

        run(scenario())
        assert self.calls == ["hibrido"]

    def test_mode_not_offered_falls_back_to_configured(self, channel, monkeypatch):
        async def scenario():
            await _advance_to_confirming(channel)
            monkeypatch.setattr(settings, "CORRECTION_MODE", "llm")  # botão de quando havia dois modos
            # O termo mudou junto com o modo: aceita a versão nova antes de tocar o botão antigo.
            await handlers.grant_consent("fake", "aluno1", handlers._consent_version())
            await handlers.handle_message(channel, button_msg("correct_ml"))

        run(scenario())
        assert self.calls == ["llm"]

    def test_refazer_command_goes_back_to_photo(self, channel):
        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, text_msg("/refazer"))
            return await load_flow("fake", "aluno1")

        flow = run(scenario())
        assert flow.state == FlowState.AWAITING_ESSAY_PHOTO and flow.essay_parts == []
        assert channel.sent[-1] == ("text", m.ASK_ESSAY_PHOTO)

    def test_refazer_without_essay_shows_help(self, channel):
        async def scenario():
            await _consent(channel)
            await handlers.handle_message(channel, text_msg("/refazer"))  # ainda no tema

        run(scenario())
        assert channel.sent[-1] == ("buttons", m.HELP_MENU, ["start_correction"])

    def test_consent_names_both_paths(self, channel):
        run(handlers.handle_message(channel, text_msg("oi")))
        body = channel.sent[0][1]
        assert "Mistral" in body and "Jev" in body and "Você escolhe quem dá a nota" in body

    def test_updated_consent_fits_one_whatsapp_message(self):
        # Quem já usava o bot vê o aviso de termo novo numa mensagem só. No primeiro contato o termo dos dois modos
        # passa de 1.024 caracteres e o WhatsApp o divide em texto + botões (uma vez por aluno).
        from src.channels.markdown import to_whatsapp_markdown

        assert len(to_whatsapp_markdown(handlers._consent_text(updated=True))) <= 1024

    def test_max_photos_keeps_three_buttons(self, channel, monkeypatch):
        monkeypatch.setattr(settings, "MAX_ESSAY_PHOTOS", 1)

        async def scenario():
            await _advance_to_confirming(channel)
            await handlers.handle_message(channel, image_msg(msg_id="m9"))

        run(scenario())
        _, body, ids = channel.sent[-1]
        assert ids == ["correct_ml", "correct_llm", "edit_text"] and "/refazer" in body
