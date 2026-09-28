# Arquitetura

A arquitetura é orientada a serviços, mas não pretende simular Kubernetes. Nginx serve a UI, FastAPI orquestra, Ollama executa modelos, Qdrant busca vetores e PostgreSQL mantém estado. RabbitMQ desacopla tarefas longas; Valkey reduz recomputação. A observabilidade cruza todas as camadas.

Essa separação permite substituir um componente sem reescrever o domínio. O custo é maior complexidade operacional, deliberadamente aceita pelo objetivo didático.

