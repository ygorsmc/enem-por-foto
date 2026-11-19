"""Configuração de log do app: bibliotecas HTTP não podem logar cada requisição.

O httpx loga em INFO a URL inteira ("HTTP Request: GET <url>"), e as URLs do app carregam segredo (token do
bot do Telegram no caminho, assinatura do link SAS do Blob na query). O SDK da Azure loga cada consulta à
fila com os cabeçalhos.
"""

import logging

import pytest

from src import main


@pytest.mark.parametrize(
    "logger_name",
    ["httpx", "httpcore.connection", "azure.core.pipeline.policies.http_logging_policy"],
)
def test_http_library_request_logs_silenced_below_warning(logger_name):
    main._setup_logging()
    lib = logging.getLogger(logger_name)
    assert not lib.isEnabledFor(logging.INFO)
    assert lib.isEnabledFor(logging.WARNING)


def test_httpx_request_line_with_secret_url_is_not_emitted(caplog):
    main._setup_logging()
    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx").info(
            "HTTP Request: GET https://conta.blob.core.windows.net/c/model.joblib?sv=1&sig=SEGREDO"
        )
    assert "SEGREDO" not in caplog.text
