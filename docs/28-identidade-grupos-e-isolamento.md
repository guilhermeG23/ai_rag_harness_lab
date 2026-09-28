# Identidade, grupos e isolamento

O container `identity` é o proprietário funcional de logins, senhas, grupos e ciclo de vida dos usuários. Ele publica o portal global na porta 8082 e uma API interna consumida pelo frontend. Todas as senhas, inclusive a do administrador global, são armazenadas com Argon2; cookies guardam tokens aleatórios e o banco guarda somente o SHA-256 desses tokens.

`tenants.id` é o UID do grupo. O nome é apenas descritivo e pode mudar sem alterar relações. Cada usuário pertence exatamente a um UID e possui nível `client` ou `admin`: cliente usa chat e seu perfil; administrador também usa o laboratório e gerencia usuários, bases e permissões do próprio grupo. O administrador global do Identity Manager enxerga todos os grupos, mas não é automaticamente um usuário do chat.

O isolamento é aplicado novamente na API de IA. IDs enviados pelo navegador não concedem acesso: bases, documentos, jobs, auditoria, usuários e permissões precisam ter o mesmo UID do usuário autenticado. Desativar usuário ou grupo revoga tokens e bloqueia novas sessões.

E-mails são normalizados para minúsculas e protegidos por índice único. Exclusão de usuário aceita `immediate`, que remove conta, sessões e permissões, ou `30d`, que bloqueia imediatamente e agenda o expurgo. O próprio Identity Manager executa a limpeza periódica.

Valide as fronteiras com `./start.sh identity-test`. O teste usa os grupos `admin1` e `admin2`, tenta acessar uma base pelo grupo incorreto e confirma RBAC de cliente, alteração do próprio perfil e senha, anti-duplicidade, bloqueio, retenção por 30 dias, restauração e exclusão permanente.
