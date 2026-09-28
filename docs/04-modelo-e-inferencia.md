# Modelo e inferência

`gemma3:1b` foi escolhido por caber em CPU/RAM limitadas e compreender português. Ollama expõe `/api/chat`; a API envia mensagens estruturadas e recebe JSON em streaming. `keep_alive` mantém pesos carregados por alguns minutos.

O limite configurado é 4096 tokens, menor que a capacidade nominal, para controlar KV cache e latência. Um modelo 1B pode alucinar e raciocinar mal; RAG fornece evidência, mas não aumenta parâmetros nem garante correção.

