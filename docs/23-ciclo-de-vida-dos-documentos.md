# Ciclo de vida dos documentos

Estados usuais: `pending`, `extracting`, `embedding`, `ready`, `deleting` e `error`. Upload grava arquivo e job; worker extrai, cria chunks, gera vetores e faz upsert. A base só retorna pontos existentes.

Remoção publica job que apaga pontos por `document_id`, arquivo e registro. O hash evita evoluções futuras duplicarem conteúdo. PDFs de imagem não possuem texto extraível sem OCR.

