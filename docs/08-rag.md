# RAG

Retrieval-Augmented Generation recupera evidência antes da geração. O modelo não é treinado novamente: recebe trechos no prompt apenas naquela chamada.

Etapas: extrair, dividir, gerar embeddings, indexar, gerar embedding da pergunta, buscar, limitar, montar contexto e citar. RAG reduz dependência da memória do modelo, mas pode falhar por extração ruim, chunking inadequado, vocabulário, score ou prompt.

