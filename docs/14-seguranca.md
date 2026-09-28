# Segurança

O backend aplica autenticação por token opaco em cookie HttpOnly, senha com Argon2 e papéis. A rede interna reduz superfície; segredos ficam no `.env`. Uploads aceitam apenas PDF, TXT e MD e têm limite.

Limitações: não há TLS, SSO, antivírus, criptografia de volume ou rotação automática. Use somente em LAN confiável. Para produção, adicione proxy TLS, secret manager, scan de arquivos, backups criptografados, rate limiting e revisão de dependências.
