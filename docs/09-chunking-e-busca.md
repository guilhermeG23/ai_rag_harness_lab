# Chunking e busca

O worker normaliza linhas e cria chunks de aproximadamente 1200 caracteres com 200 de sobreposição. O overlap preserva frases nas fronteiras, ao custo de vetores repetidos.

A busca usa similaridade cosseno, score mínimo 0,35, até quatro resultados por coleção e seis globais. Esses valores são ponto de partida, não universais. Teste precisão, recall, custo de contexto e diversidade por documento.

