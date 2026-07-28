# Offline & 2FA Cache Changes (v7.1+)

## New Feature: Automatic Offline Reconnection with 2FA Cache

Adicionado suporte para reconexão automática quando a internet cai, com cache de código 2FA.

### Novos Arquivos/Diretórios:
- `data/.credentials` — email/senha criptografados (já existia)
- `data/.2fa_cache` — códigos 2FA criptografados (NOVO)

### Mudanças de Comportamento:
- Credenciais são automaticamente cacheadas após primeiro login (igual antes)
- Códigos 2FA fornecidos durante login agora são cacheados em formato criptografado (NOVO)
- Quando internet cai, app tenta reconectar automaticamente (3 tentativas com 3s de delay)
- Se 2FA está em cache, é usado automaticamente sem intervenção do usuário
- Frontend detecta eventos online/offline e dispara endpoint `/reconnect_offline`

### Novos Endpoints:
- `POST /reconnect_offline` — Tenta reconectar usando credenciais cacheadas e códigos 2FA

### Mudanças no Frontend:
- Detecção offline via `window.online` e `window.offline` events
- Tentativas automáticas de reconexão quando conexão é perdida
- Detecta desconexão do wrapper e tenta recuperação offline

### Como Funciona:
1. Usuário faz login → credenciais salvas criptografadas
2. Código 2FA fornecido → código salvo criptografado
3. Internet cai → app detecta via erro de fetchState ou evento online
4. Tenta auto-reconectar com credenciais cacheadas
5. Se 2FA necessário → usa código cacheado automaticamente
6. Usuário não vê interrupção no serviço

### Notas de Migração:
- Nenhuma mudança de schema no banco de dados
- Formato de cache de credenciais não muda
- Cache 2FA usa mesma encriptação que credenciais existentes
- Seguro fazer downgrade deletando arquivo `data/.2fa_cache`

### Segurança:
- Todos os dados cacheados são encriptados usando módulo crypto existente
- Arquivos cache armazenados em diretório seguro `data/`
- Podem ser limpos manualmente deletando arquivos ou via botão de deletar credenciais na UI

## Arquivos Modificados:

### `app/routes.py`
- Adicionadas funções: `get_2fa_cache_path()`, `load_2fa_cache()`, `save_2fa_cache()`, `clear_2fa_cache()`
- Modificada rota `POST /submit_2fa` para salvar código em cache
- Modificada rota `GET /` para tentar usar 2FA cache automaticamente
- Adicionada nova rota `POST /reconnect_offline` para reconexão com cache
- Adicionada importação de `threading`

### `app/process_manager.py`
- Adicionado atributo `cached_2fa_attempt` à classe `WrapperManager`
- Modificado método `_stream_logs()` para:
  - Detectar falhas de conexão (network, timeout, etc)
  - Limpar flag `cached_2fa_attempt` quando 2FA bem-sucedido
  - Log de queda de internet detectada

### `app/static/script.js`
- Adicionada função `initializeOfflineDetection()` para detectar mudanças de status online/offline
- Adicionada função `attemptOfflineReconnect()` para tentar reconexão com retry exponencial
- Modificada função `fetchState()` para:
  - Detectar wrapper desconectado
  - Detectar erros de conexão
  - Resetar contador de retry em sucesso
  - Chamar `attemptOfflineReconnect()` em caso de falha
- Adicionadas variáveis globais: `offlineRetryCount`, `MAX_OFFLINE_RETRIES`, `lastConnectedStatus`

### `README.md`
- Adicionada seção "4. Reconexão Automática Offline (Novo!)" explicando a nova funcionalidade
- Documentadas as principais características do recurso
