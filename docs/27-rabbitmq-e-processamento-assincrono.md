# RabbitMQ e processamento assíncrono

A API é producer e publica no exchange tópico `ai.jobs`. `document.*` vai à fila durável `documents`; o worker consome com prefetch 1. Mensagens persistentes carregam apenas IDs.

O worker confirma após commit. Falhas são reencaminhadas até três tentativas; depois a mensagem é rejeitada e o dead-letter exchange a entrega a `documents.dlq`. Como a entrega é pelo menos uma vez, handlers verificam estado antes de repetir.

RabbitMQ não é cache nem banco de domínio. PostgreSQL guarda o job observável, RabbitMQ coordena entrega e Valkey acelera cálculos.

