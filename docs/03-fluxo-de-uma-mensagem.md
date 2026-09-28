# Fluxo de uma mensagem

1. O browser envia sessão, texto e bases selecionadas.
2. A API autentica, aplica RBAC e guardrail.
3. A mensagem é persistida.
4. A consulta recebe embedding e busca nas coleções autorizadas.
5. Chunks são classificados e adicionados ao prompt.
6. Histórico recente é incluído dentro do orçamento.
7. Ollama transmite tokens; a API converte em SSE.
8. Resposta, fontes e tempos são persistidos.

Falhas de cache usam fallback. Falha de banco ou modelo encerra a requisição porque são dependências essenciais.

