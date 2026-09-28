# Múltiplas bases RAG

Uma IA pode consultar várias bases. Cada base deste harness mapeia para uma coleção Qdrant. A sessão guarda IDs selecionados; a API remove inativas/não autorizadas, consulta cada coleção e combina por score.

Separar coleções reduz risco de um filtro de tenant esquecido e permite desativar, reindexar ou excluir independentemente. Uma instância Qdrant por cliente daria isolamento de processo maior, mas consumiria mais recursos e exigiria outro plano operacional.

