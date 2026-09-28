# FastAPI e camada de API

FastAPI fornece rotas tipadas, Pydantic, dependências, OpenAPI, middleware e StreamingResponse. `current_user` e a dependência administrativa demonstram injeção de dependência para segurança; o container `identity` possui outra aplicação FastAPI dedicada a credenciais e grupos. O middleware cria request ID e mede duração.

Chamadas HTTP ao Ollama/Qdrant são assíncronas no chat. Indexação não usa `BackgroundTasks`: vai para RabbitMQ porque precisa sobreviver a reinícios e executar fora do processo web.
