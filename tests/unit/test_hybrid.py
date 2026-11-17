"""Modo híbrido (CORRECTION_MODE=hibrido): partes puras + pipeline com Jev, modelo e LLM falsos.

Nenhum teste depende dos artefatos treinados (gitignorados) nem chama rede.
"""

import asyncio

import pytest

import src.correction.hybrid.jev as jev
import src.correction.hybrid.pipeline as pipeline
from src.config import settings
from src.correction import corrector
from src.correction.hybrid.features import all_features, normalize_ocr_text
from src.correction.hybrid.scoring import checklist_hits, evaluate_gate, pistas_text, reconcile_qp

run = asyncio.run

OCR_TABELA = """|  1 | O poema de Drummond compara os desafios a serem superados na vida a uma pe-  |
| --- | --- |
|  2 | dra. Analogamente, os povos tradicionais brasileiros enfrentam pedras no caminho  |
|  3 | que precisam ser superadas pela sociedade.  |
|  4 | Em primeira instância, cabe analisar a valorização desses povos nas escolas e nas  |
|  5 | faculdades do país, onde a história deles quase não aparece.  |"""


# Acima do mínimo de 70 palavras do portão (o OCR_TABELA tem ~50).
TEXTO_LONGO = "\n".join([OCR_TABELA] * 3)


def _answers(**over) -> dict:
    """Respostas de uma redação normal (nada dispara), com tudo o que features/portão/checklist leem."""
    a = {f"score_c{i}": 3.0 for i in range(1, 6)}
    a.update(
        {
            "c2_aborda_recorte_completo": 0.9,
            "triagem_fuga_total": 0.02,
            "c2_tipo_dissertativo_argumentativo": 0.95,
            "c5_agente_especifico": 0.8,
            "c5_agente_presente": 0.9,
            "c5_acao": 0.9,
            "c5_modo_meio": 0.8,
            "c5_efeito": 0.8,
            "c5_detalhamento": 0.5,
            "c5_tem_proposta": 0.95,
            "c2_repertorio_presente": 0.7,
            "c2_repertorio_legitimado": 0.6,
            "c2_repertorio_produtivo": 0.5,
            "tema_assunto_ref": 0.95,
            "tema_e_emb": 0.9,
            "triagem_prosa": 0.99,
            "triagem_trechos_relacionados": 0.95,
            "triagem_identificacao_v3": 0.01,
            "triagem_improperio": 0.01,
            "triagem_lingua_estrangeira": 0.0,
            "triagem_ininteligivel": 0.02,
            "c2_tese_explicita": 0.9,
            "c5_viola_direitos_humanos": 0.0,
            "c4_articulacao_paragrafos": 0.2,
            "triagem_tipo_textual": {
                "type": "choice",
                "choice": "dissertativo",
                "probabilities": {"dissertativo": 0.9, "carta": 0.05, "lista": 0.05},
            },
        }
    )
    a.update(over)
    return a


ITEMS = {
    "c4_articulacao_paragrafos": {"comp": "C4", "msg": "Ligue os parágrafos.", "sign": 1.0, "thr": -0.5},
}


class TestNormalizeOcr:
    def test_tabela_vira_texto_corrido_com_paragrafos(self):
        out = normalize_ocr_text(OCR_TABELA)
        assert "pedra." in out  # hifenização "pe-" + "dra." desfeita
        assert "|" not in out and "---" not in out
        paras = out.split("\n")
        assert len(paras) == 2  # linha curta terminada em ponto fecha o parágrafo
        assert paras[1].startswith("Em primeira instância")

    def test_texto_comum_so_normaliza_espacos(self):
        assert normalize_ocr_text("Primeiro   parágrafo.\n\n  Segundo.  ") == "Primeiro parágrafo.\nSegundo."


class TestJevAnswers:
    def test_parse_noul_score_choice(self):
        resp = {
            "answers": {
                "a": {"type": "noul", "noul": 0.8},
                "b": {"type": "score", "score": 2.5},
                "c": {"type": "choice", "choice": "carta", "probabilities": {"carta": 0.7}},
            }
        }
        out = jev.parse_answers(resp, {"a", "b", "c"})
        assert out["a"] == 0.8 and out["b"] == 2.5 and out["c"]["choice"] == "carta"

    def test_pergunta_faltando_falha(self):
        with pytest.raises(ValueError):
            jev.parse_answers({"answers": {"a": {"noul": 0.1}}}, {"a", "b"})

    def test_tema_entra_nas_perguntas(self, monkeypatch):
        tpl = {"q": {"instructions": {"pergunta": 'O tema de `redacao` é "§TEMA§"?'}, "criteria": ["§TEMA§"]}}
        monkeypatch.setattr(jev, "questions_template", lambda: tpl)
        q = jev.build_questions("Desafios da educação")
        assert q["q"]["instructions"]["pergunta"] == 'O tema de `redacao` é "Desafios da educação"?'
        assert q["q"]["criteria"] == ["Desafios da educação"]


class TestScoring:
    @pytest.mark.parametrize(
        "c_hat,total",
        [([3.4, 3.6, 2.9, 3.1, 2.2], 15), ([4.9, 4.8, 4.7, 4.6, 4.9], 25), ([0.2, 0.4, 0.1, 0.3, 0.0], 0)],
    )
    def test_reconcile_soma_exata_e_limites(self, c_hat, total):
        lv = reconcile_qp(c_hat, total)
        assert sum(lv) == total and all(0 <= x <= 5 for x in lv)

    def test_reconcile_ja_consistente_nao_muda(self):
        assert reconcile_qp([3.0, 4.0, 3.0, 3.0, 2.0], 15) == [3, 4, 3, 3, 2]

    def test_portao_redacao_normal(self):
        assert evaluate_gate(_answers(), 300) == (None, [], False)

    def test_portao_fuga_carta_e_texto_curto(self):
        assert evaluate_gate(_answers(tema_assunto_ref=0.1), 300)[0] == "Fuga total ao tema"
        carta = {"type": "choice", "choice": "carta", "probabilities": {"carta": 0.8}}
        assert evaluate_gate(_answers(triagem_tipo_textual=carta), 300)[0] == "Formato de carta"
        assert "insuficiente" in evaluate_gate(_answers(), 40)[0]

    def test_portao_direitos_humanos_e_avisos(self):
        zero, avisos, dh = evaluate_gate(_answers(c5_viola_direitos_humanos=0.9, c2_tese_explicita=0.2), 300)
        assert zero is None and dh is True
        assert "Sem tese explícita" in avisos

    def test_checklist_filtro_estrito(self):
        # c4_articulacao_paragrafos = 0.2 → margem = −0.2 + 0.5 > 0 → dispara
        assert checklist_hits(_answers(), [3, 3, 3, 3, 3], ITEMS)["C4"] == ["Ligue os parágrafos."]
        # nota prevista em C4 ≥ 160 (nível 4) → nenhuma pista em C4
        assert checklist_hits(_answers(), [3, 3, 3, 4, 3], ITEMS)["C4"] == []

    def test_pistas_texto(self):
        txt = pistas_text(
            {"C1": [], "C2": [], "C3": [], "C4": ["Ligue os parágrafos."], "C5": []}, _answers(), []
        )
        assert "C4: Ligue os parágrafos." in txt and "agente: provavelmente presente" in txt
        assert "Avisos: nenhum." in txt

    def test_features_tem_colunas_do_modelo(self):
        f = all_features("Educação no Brasil", normalize_ocr_text(OCR_TABELA), _answers())
        for col in (
            "det_n_palavras",
            "eng_tema_cov_all",
            "eng_jev_c2_gate",
            "jev_tipo_carta",
            "jev_score_c3",
        ):
            assert col in f


class _FakeCorrector:
    def __init__(self, resposta: str):
        self.resposta = resposta
        self.recebido = ""

    async def correct(self, input_block: str) -> str:
        self.recebido = input_block
        return self.resposta


class TestPipeline:
    def _patch(self, monkeypatch, answers: dict, levels: list[int], resposta: str) -> _FakeCorrector:
        async def fake_jev(tema, redacao):
            return answers

        fake = _FakeCorrector(resposta)
        monkeypatch.setattr(pipeline, "ask_jev", fake_jev)
        monkeypatch.setattr(pipeline, "predict_levels", lambda feats, redacao: list(levels))
        monkeypatch.setattr(pipeline.artifacts, "checklist", lambda: ITEMS)
        monkeypatch.setattr(pipeline, "get_corrector", lambda: fake)
        return fake

    def test_notas_fixas_vao_para_o_llm(self, monkeypatch):
        fake = self._patch(monkeypatch, _answers(), [3, 4, 3, 3, 2], "**Ótimo** começo")
        out = run(pipeline.correct_hybrid("BLOCO-ENTRADA", "Tema", TEXTO_LONGO))
        assert fake.recebido.startswith("BLOCO-ENTRADA")
        assert "• C2: 160/200" in fake.recebido and "• Total: 600/1000" in fake.recebido
        assert "C4: Ligue os parágrafos." in fake.recebido
        assert out == "*Ótimo* começo"  # negrito duplo vira simples

    def test_zero_usa_bloco_de_zero(self, monkeypatch):
        fake = self._patch(monkeypatch, _answers(tema_assunto_ref=0.1), [3, 3, 3, 3, 3], "ok")
        run(pipeline.correct_hybrid("X", "Tema", TEXTO_LONGO))
        assert "ZEROU a redação pelo motivo: Fuga total ao tema" in fake.recebido
        assert "• C1:" not in fake.recebido

    def test_direitos_humanos_zera_c5(self, monkeypatch):
        fake = self._patch(monkeypatch, _answers(c5_viola_direitos_humanos=0.9), [3, 4, 3, 3, 2], "ok")
        run(pipeline.correct_hybrid("X", "Tema", TEXTO_LONGO))
        assert "• C5: 0/200" in fake.recebido and "• Total: 520/1000" in fake.recebido


class TestModeDispatch:
    def test_modo_hibrido_chama_o_pipeline(self, monkeypatch):
        chamado = {}

        async def fake_hybrid(input_block, tema, essay_text):
            chamado["tema"] = tema
            return "feedback híbrido"

        monkeypatch.setattr(settings, "CORRECTION_MODE", "hibrido")
        monkeypatch.setattr(pipeline, "correct_hybrid", fake_hybrid)
        assert run(corrector.correct_essay("Tema X", None, "texto")) == "feedback híbrido"
        assert chamado["tema"] == "Tema X"
