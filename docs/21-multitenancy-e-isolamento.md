# Multitenancy e isolamento

Tenant representa cliente. Usuário, conversa, job e base têm vínculo explícito. `knowledge_base_permissions` controla quais bases um usuário pode consultar.

Isolamento é aplicado no backend antes de cache e Qdrant. A chave de cache inclui tenant, usuário, versão de ACL e versões das bases. Teste sempre com conteúdo “segredo A” e “segredo B” em tenants diferentes e tente manipular IDs pela API.

