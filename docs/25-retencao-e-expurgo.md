# Retenção e expurgo

Ao excluir uma conversa, a API calcula `purge_after` usando política do tenant ou global. Valores previstos: imediato, 7, 15, 30, 60 ou 90 dias. O worker de manutenção remove mensagens quando o prazo vence.

Antes do vencimento é possível restaurar. “Definitivo” refere-se aos dados ativos; backups podem seguir retenção própria. Auditoria mínima conserva o fato da operação, não o conteúdo apagado.

