# Cache e invalidação

Valkey guarda embeddings e resultados RAG. É limitado a 128 MB com LRU e sem persistência. Falha de cache degrada desempenho, não correção.

Chaves usam hashes, modelo, tenant, usuário, ACL, base/versão e parâmetros. Documento ou estado da base incrementa sua versão; mudança de permissão incrementa `acl_version`. TTL da busca é curto. Respostas finais não são cacheadas.

