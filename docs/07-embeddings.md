# Embeddings

Embedding transforma texto em vetor numérico. Textos semanticamente próximos tendem a vetores próximos. `embeddinggemma` gera vetores multilíngues via Ollama; o mesmo modelo e preparação devem ser usados na indexação e consulta.

O Valkey guarda embeddings por hash de conteúdo e versão do modelo. Mudar o modelo exige nova coleção ou reindexação porque dimensões e espaço vetorial podem mudar.

