# Autenticação e RBAC

O container `identity` valida Argon2 e emite token aleatório cujo hash é armazenado. O cookie é HttpOnly e SameSite Lax. O nível `client` opera suas sessões, perfil e bases permitidas; `admin` também gerencia o laboratório e os usuários do próprio UID de grupo.

RBAC não substitui checagem de propriedade. Uma rota deve validar papel, tenant e recurso. Para produção, prefira identidade externa/SSO, MFA, CSRF explícito, rotação e revogação administrativa de sessões.
