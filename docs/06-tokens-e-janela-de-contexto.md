# Tokens e janela de contexto

Tokens são unidades do tokenizer, não caracteres. A UI mostra estimativa simples; o Ollama/modelo é a autoridade real. O orçamento precisa acomodar sistema, fontes, histórico, pergunta e resposta.

Atualmente o histórico usa até 12 mensagens e o contexto do modelo é limitado por `MODEL_CONTEXT_TOKENS`. Em evolução futura, substitua a estimativa por tokenizer exato e corte por orçamento, não apenas por quantidade de mensagens.

