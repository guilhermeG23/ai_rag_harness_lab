# Painel de serviços

O container `service-map` na porta 8081 apresenta healthchecks e relações. Ele consulta um endpoint agregado da API e não recebe o socket Docker, evitando controle privilegiado do host.

O painel diferencia serviço saudável de fluxo de negócio válido. Use o smoke test e um chat real para validação fim a fim.

