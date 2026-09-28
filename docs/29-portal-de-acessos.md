# Portal de acessos iniciais

O container `access-portal` publica, na porta 8083, uma referência didática das contas e senhas iniciais do Chat/Lab, Identity Manager, Grafana, RabbitMQ, PostgreSQL e Valkey. A interface separa cada serviço em um cartão, oculta senhas visualmente por padrão e oferece ações para revelar ou copiar.

No cartão do Valkey, o usuário é exibido como `default`. Esse é o usuário ACL implícito utilizado quando o servidor é configurado com `--requirepass`; somente a senha é definida pelo ambiente.

As credenciais de infraestrutura chegam ao container por variáveis do `.env`. As contas didáticas `admin1`, `admin2` e `teste1` a `teste6` representam o seed inicial do Identity Manager. O portal não acessa o banco nem consegue reverter hashes Argon2.

Por isso, ele tem validade somente enquanto os valores de bootstrap não forem alterados. Trocar uma senha pelo Grafana, Identity Manager, RabbitMQ ou pelas configurações de perfil não atualiza automaticamente o portal.

Este componente não possui autenticação de propósito. Ele existe para facilitar o estudo em uma LAN controlada e torna-se um vazamento intencional de segredos se a porta 8083 for publicada. Em qualquer uso real, remova o serviço do Compose ou restrinja completamente seu acesso.
