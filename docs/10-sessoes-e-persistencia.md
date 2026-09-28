# Sessões e persistência

Conversas e mensagens ficam no PostgreSQL. Uma sessão mantém título, bases selecionadas, fixação, arquivamento, exclusão e prazo de expurgo. Fixar altera somente a ordenação visual.

Ao reabrir, a API carrega mensagens persistidas, mas reavalia permissões das bases. A lista ordena fixadas por `pinned_at` e restantes por atualização. Exclusão comum move para lixeira; restauração só existe antes do expurgo.

