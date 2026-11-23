"""Coleta as respostas do Jev para as redações do notebook e monta `data/essaybr_jev.csv.gz`.

As respostas do Jev não ficam neste repositório: são saídas de um serviço pago, e quem quiser refazer o notebook coleta
as suas com a própria chave da API (https://typesafe.ai), sob os termos da TypeSafe. São 6.475 chamadas, uma por
redação, com as 59 perguntas de `perguntas_jev.json`. O Jev cobra só a entrada (~9,3 mil tokens por chamada), o que dá
cerca de US$ 2,50 no corpus inteiro.

As respostas brutas ficam em `data/jev_respostas/<id>.json`, uma por redação: se a coleta parar, rode de novo e ela
continua de onde parou. Com todas coletadas, o script junta as 64 colunas `jev_*` ao CSV público `data/essaybr.csv.gz`
(texto, tema, notas e divisão oficial do Essay-BR), na ordem de colunas que o notebook e o modelo do bot usam.

O Jev varia um pouco de uma execução para outra, então os números do notebook mudam um pouco em relação aos
publicados.

Uso (na raiz do repositório, com as dependências de `notebooks/requirements.txt`):
    export JEV_API_KEY=...
    python notebooks/coletar_jev.py --limite 5    # teste com 5 redações (~US$ 0,002)
    python notebooks/coletar_jev.py               # o corpus inteiro (mostra o custo estimado e pede confirmação)
"""

import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import pandas as pd

NB = Path(__file__).resolve().parent
sys.path.insert(0, str(NB.parent))
from src.correction.hybrid.features import jev_features  # noqa: E402  (o mesmo código do bot)
from src.correction.pricing import JEV_USD_PER_M_INPUT  # noqa: E402

API_URL = "https://api.typesafe.ai/v1/systemone"
TEMA_SENTINELA = "§TEMA§"
PERGUNTAS = NB / "perguntas_jev.json"
CORPUS = NB / "data" / "essaybr.csv.gz"
RESPOSTAS = NB / "data" / "jev_respostas"
SAIDA = NB / "data" / "essaybr_jev.csv.gz"


class ChaveRecusada(Exception):
    pass


def rel(p: Path) -> str:
    return str(p.relative_to(NB.parent)) if p.is_relative_to(NB.parent) else str(p)


def preencher(obj, tema: str):
    """Troca o marcador do tema em todas as strings (algumas perguntas levam o tema no próprio texto)."""
    if isinstance(obj, str):
        return obj.replace(TEMA_SENTINELA, tema)
    if isinstance(obj, list):
        return [preencher(x, tema) for x in obj]
    if isinstance(obj, dict):
        return {k: preencher(v, tema) for k, v in obj.items()}
    return obj


def payload(cfg: dict, tema: str, redacao: str) -> dict:
    return {
        "model": cfg["modelo"],
        "state": {"tema": tema, "redacao": redacao},
        "questions": preencher(cfg["perguntas"], tema),
    }


def respostas(resp: dict, esperadas: set[str]) -> dict:
    """Resposta da API → {pergunta: probabilidade ou nível | dict da escolha}. Igual a `parse_answers` do bot."""
    out: dict = {}
    for k, ans in (resp.get("answers") or {}).items():
        if ans.get("type") == "choice":
            out[k] = ans
        else:
            out[k] = float(ans["noul"]) if "noul" in ans else float(ans["score"])
    faltando = esperadas - set(out)
    if faltando:
        raise ValueError(f"o Jev não respondeu {len(faltando)} perguntas: {sorted(faltando)[:5]}")
    return out


def coletar_uma(client: httpx.Client, chave: str, cfg: dict, eid: str, tema: str, redacao: str) -> int:
    p = payload(cfg, tema, redacao)
    headers = {"Authorization": f"Bearer {chave}", "Accept": "application/json"}
    for tentativa in range(3):
        try:
            r = client.post(API_URL, json=p, headers=headers)
            if r.status_code in (401, 403):
                raise ChaveRecusada(f"a API recusou a chave (HTTP {r.status_code})")
            r.raise_for_status()
            resp = r.json()
            respostas(resp, set(cfg["perguntas"]))  # faltou resposta → tenta de novo
            break
        except ChaveRecusada:
            raise
        except Exception:
            if tentativa == 2:
                raise
            time.sleep(2 * (tentativa + 1))
    tokens = int((resp.get("usage") or {}).get("input_tokens") or 0)
    tmp = RESPOSTAS / f"{eid}.json.tmp"
    tmp.write_text(
        json.dumps({"id": eid, "input_tokens": tokens, "response": resp}, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(RESPOSTAS / f"{eid}.json")
    return tokens


def coletar(df: pd.DataFrame, cfg: dict, chave: str, paralelo: int) -> None:
    feitas, tokens, erros = 0, 0, []
    with httpx.Client(timeout=60.0) as client, ThreadPoolExecutor(paralelo) as ex:
        futuros = {
            ex.submit(coletar_uma, client, chave, cfg, r.id, r.tema, r.redacao): r.id for r in df.itertuples()
        }
        for f in as_completed(futuros):
            try:
                tokens += f.result()
                feitas += 1
            except ChaveRecusada as e:
                for g in futuros:
                    g.cancel()
                raise SystemExit(f"Parei: {e}. Confira JEV_API_KEY.") from None
            except Exception as e:
                erros.append(futuros[f])
                print(f"  erro em {futuros[f]}: {type(e).__name__}: {e}", flush=True)
            if feitas and (feitas % 100 == 0 or feitas == len(futuros)):
                print(f"  {feitas}/{len(futuros)} · US$ {tokens * JEV_USD_PER_M_INPUT / 1e6:.3f}", flush=True)
    print(
        f"Coleta: {feitas} respostas, {tokens:,} tokens de entrada, US$ {tokens * JEV_USD_PER_M_INPUT / 1e6:.3f}"
        + (f". {len(erros)} com erro: rode de novo para tentar só essas." if erros else "."),
        flush=True,
    )


def colunas_jev(cfg: dict, resp: dict) -> list[float]:
    """Respostas → as 64 colunas `jev_*` na ordem do notebook (`jev_features` é a função do bot)."""
    jv = jev_features(respostas(resp, set(cfg["perguntas"])))
    return [jv.get(c, math.nan) for c in cfg["colunas"]]


def montar(df: pd.DataFrame, cfg: dict) -> None:
    linhas = [
        colunas_jev(cfg, json.loads((RESPOSTAS / f"{i}.json").read_text(encoding="utf-8"))["response"])
        for i in df.id
    ]
    jev = pd.DataFrame(linhas, columns=cfg["colunas"])
    vazias = int(jev.isna().sum().sum())
    pd.concat([df.reset_index(drop=True), jev], axis=1).to_csv(
        SAIDA, index=False, compression={"method": "gzip", "mtime": 0}
    )
    print(
        f"Pronto: {rel(SAIDA)} ({len(df)} redações, {len(cfg['colunas'])} colunas do Jev"
        + (f", {vazias} valores faltando" if vazias else "")
        + "). Agora rode o notebook."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Coleta as respostas do Jev para o notebook do modelo híbrido.")
    ap.add_argument("--limite", type=int, help="coleta só as N primeiras redações (teste); não monta o CSV")
    ap.add_argument("--paralelo", type=int, default=6, help="chamadas simultâneas (padrão: 6)")
    ap.add_argument("--sim", action="store_true", help="não pede confirmação do custo")
    args = ap.parse_args()

    cfg = json.loads(PERGUNTAS.read_text(encoding="utf-8"))
    df = pd.read_csv(CORPUS)
    if args.limite:
        df = df.head(args.limite)
    RESPOSTAS.mkdir(parents=True, exist_ok=True)
    falta = df[[not (RESPOSTAS / f"{i}.json").exists() for i in df.id]]

    if len(falta):
        chave = os.environ.get("JEV_API_KEY")
        if not chave:
            raise SystemExit("Defina JEV_API_KEY com a sua chave da API do Jev (https://typesafe.ai).")
        chars = sum(
            len(json.dumps(payload(cfg, t, r), ensure_ascii=False)) for t, r in zip(falta.tema, falta.redacao)
        )
        est = chars / 3.2 * JEV_USD_PER_M_INPUT / 1e6  # ~3,2 caracteres por token, medido no Jev
        print(
            f"{len(falta)} de {len(df)} redações sem resposta · {cfg['modelo']} · custo estimado US$ {est:.3f}"
        )
        if not args.sim and input("Continuar? [s/N] ").strip().lower() not in ("s", "sim"):
            return
        coletar(falta, cfg, chave, args.paralelo)

    if any(not (RESPOSTAS / f"{i}.json").exists() for i in df.id):
        raise SystemExit("Ainda faltam respostas; rode de novo para completar.")
    if args.limite:
        print(
            f"Teste ok: {len(df)} respostas em {rel(RESPOSTAS)}. Rode sem --limite para o corpus " "inteiro."
        )
        return
    montar(df, cfg)


if __name__ == "__main__":
    main()
