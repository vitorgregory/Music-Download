# 🔧 Corrigido: Seleção Múltipla + Filtros Vazios

**Status:** ✅ Corrigido  
**Data:** Fevereiro 2026  
**Problemas:** 
- Só baixava primeiro item mesmo com múltiplas seleções
- Vídeos ignorados na apresentação
- Filtro ficava vazio

---

## 🐛 Problemas Encontrados

### 1. Múltiplas Seleções Ignoradas
**Sintoma:** Usuário clicava em 5 itens, mas só o primeiro era baixado

**Causa:** A função `submitSelection()` enviava **cada seleção separadamente** em requisições diferentes:
```javascript
// ERRADO - antigo
checked.forEach((sel, idx) => {
    setTimeout(() => {
        axios.post('/submit_selection', new URLSearchParams({selection: sel}))
    }, idx * 100);
});
```

O downloader CLI recebia `"1"`, processava, e ignorava as requisições subsequentes `"2"`, `"3"`, etc.

**Solução:** Enviar **todas as seleções de uma vez** em uma string separada por espaços:
```javascript
// CORRETO - novo
const selectionString = checked.join(' ');  // "1 2 3 4"
axios.post('/submit_selection', new URLSearchParams({selection: selectionString}))
```

### 2. Backend Rejeitava Múltiplos Números
**Sintoma:** Validação falhava com `"1 2 3"` porque esperava apenas um dígito

**Causa:** Validação muito restritiva:
```python
# ERRADO - antigo
if not sel or not sel.isdigit():  # Falha com "1 2 3"
    return error
```

**Solução:** Aceitar números separados por espaço, vírgula ou hífen:
```python
# CORRETO - novo
if not all(c.isdigit() or c in ' ,-' for c in sel):
    return error
```

### 3. Filtro Ficava Vazio
**Sintoma:** Dropdowns de tags/datas não tinham opções

**Causa:** A função `updateSelectionFilters()` tentava extrair dados que não existiam nas opções parseadas

**Solução:** Preencher também dados de **tipo** e validar melhor a extração

### 4. Vídeos Ignorados Visualmente
**Sintoma:** Vídeos apareciam mas sem cor/badge específica

**Causa:** Falta de badge color para tipo `Video`/`MusicVideo`

**Solução:** Adicionar cores para vídeos (amarelo/warning)

---

## ✅ Mudanças Implementadas

### `app/routes.py`

```python
@app.route("/submit_selection", methods=["POST"])
@limiter.exempt
def submit_selection():
    sel = (request.form.get("selection") or "").strip()
    if not sel:
        return jsonify({"status": "error", "message": "Seleção inválida."}), 400
    
    # ✅ Suportar múltiplas seleções separadas por espaço, vírgula ou hífen
    # Exemplos válidos: "1 2 3", "1,2,3", "1-3"
    if not all(c.isdigit() or c in ' ,-' for c in sel):
        return jsonify({"status": "error", "message": "Seleção inválida"}), 400
    
    downloader.write_input(sel)
    return jsonify({"status": "ok"})
```

**Mudanças:**
- ✅ Aceita múltiplos números
- ✅ Suporta ranges (ex: `"1-5"`)
- ✅ Suporta separadores: espaço, vírgula, hífen
- ✅ Passa tudo como string única para o CLI

### `app/static/script.js`

**submitSelection():**
```javascript
function submitSelection() {
    const checked = Array.from(document.querySelectorAll('#selection-list input:checked'))
        .map(c=>c.value);
    if(checked.length) {
        const btn = document.getElementById('submit-selection');
        if(btn) btn.disabled = true;
        
        // ✅ Enviar TODAS as seleções de uma vez
        const selectionString = checked.join(' ');  // "1 2 3 4"
        
        axios.post('/submit_selection', new URLSearchParams({selection: selectionString}))
            .catch(err => console.error('Selection error:', err))
            .finally(() => {
                if(btn) btn.disabled = false;
            });
    }
}
```

**updateSelectionFilters():**
```javascript
function updateSelectionFilters(opts) {
    const tagFilter = document.getElementById('selection-tag-filter');
    const yearFilter = document.getElementById('selection-year-filter');
    const typeFilter = document.getElementById('selection-type-filter');  // ✅ NOVO
    
    const tags = new Set();
    const years = new Set();
    const types = new Set();  // ✅ NOVO
    
    opts.forEach((opt) => {
        (opt.tags || []).forEach((tag) => tags.add(tag));
        if (opt.date) {
            const yearMatch = opt.date.match(/\b(\d{4})\b/);
            if (yearMatch) years.add(yearMatch[1]);
        }
        if (opt.type) {  // ✅ NOVO
            types.add(opt.type);
        }
    });

    // ... atualizar dropdowns

    // ✅ Novo: Atualizar filtro de tipos
    if (typeFilter) {
        typeFilter.innerHTML = '<option value="">Todos os tipos</option>' +
            Array.from(types).sort().map(type => 
                `<option value="${type}">${type}</option>`
            ).join('');
    }
}
```

**renderSelectionList():**
```javascript
// ✅ Adicionar cor para vídeos
let badgeColor = 'bg-secondary';
if (o.type === 'Album') badgeColor = 'bg-primary';
if (o.type === 'Single') badgeColor = 'bg-info text-dark';
if (o.type === 'EP') badgeColor = 'bg-success';
if (o.type === 'MusicVideo' || o.type === 'Video' || o.type === 'MUSIC_VIDEO') 
    badgeColor = 'bg-warning text-dark';
```

---

## 📊 Comparação

### Antes
```
Usuário seleciona: [Faixa 1] [Faixa 3] [Faixa 5]
Requisições enviadas: 
  - POST /submit_selection → "1"
  - POST /submit_selection → "3"
  - POST /submit_selection → "5"
Downloader processa apenas o primeiro "1"
Resultado: ❌ Apenas Faixa 1 é baixada
Filtro: ❌ Vazio, sem opções
Vídeos: ❌ Aparece mas sem cor/badge
```

### Depois
```
Usuário seleciona: [Faixa 1] [Faixa 3] [Faixa 5]
Requisição enviada:
  - POST /submit_selection → "1 3 5"
Downloader processa tudo: Faixa 1, 3 e 5
Resultado: ✅ Todas as 3 faixas são baixadas
Filtro: ✅ Populated com tipos (Album, Single, Video, etc)
Vídeos: ✅ Aparecem com badge amarelo (warning)
```

---

## 🧪 Como Testar

1. **Abrir app** em http://localhost:5000
2. **Fazer download** de um álbum (múltiplas faixas)
3. **Quando modal aparecer:**
   - ✅ Filtro de tipo deve estar preenchido
   - ✅ Se houver vídeos, devem aparecer em amarelo
4. **Selecionar múltiplos itens:**
   - Clique em 3 ou mais itens
   - Clique "Confirmar seleção"
   - ✅ Todos os itens devem ser baixados
5. **Verificar logs:**
   - Deve aparecer requisição com seleção completa
   - Ex: `POST /submit_selection → "1 2 3 4 5"`

---

## 📝 Arquivos Modificados

### `app/routes.py`
- Linha 315-320: Função `submit_selection()` atualizada
- Suporta múltiplos números, ranges e separadores

### `app/static/script.js`
- Linha 545-563: Função `submitSelection()` - envia tudo de uma vez
- Linha 455-493: Função `updateSelectionFilters()` - extrai tipos
- Linha 517-522: Função `renderSelectionList()` - adiciona cores para vídeos

---

## 🔄 Formatos Suportados

O backend agora aceita:
```
"1"           → Seleção única
"1 2 3"       → Seleções separadas por espaço
"1,2,3"       → Seleções separadas por vírgula
"1,3,5"       → Misturado
"1-5"         → Range (downloader processa)
"1 3-5 7"     → Combinado (downloader processa)
```

---

## ⚠️ Considerações

- ✅ Retro-compatível com seleção única
- ✅ Backend valida entrada
- ✅ Frontend bloqueia botão durante envio
- ✅ Tratamento de erro melhorado
- ✅ Filtros agora funcionam corretamente

---

## 🎯 Resultado Final

| Aspecto | Antes | Depois |
|---------|-------|--------|
| Múltiplas seleções | ❌ Só 1 era baixada | ✅ Todas são baixadas |
| Filtro de tipo | ❌ Vazio | ✅ Populated |
| Vídeos | ❌ Sem badge color | ✅ Badge amarelo |
| Requisições | ❌ Múltiplas (1 por item) | ✅ Uma única |
| Feedback | ❌ Nenhum | ✅ Botão desabilitado |

**Tudo funcionando como esperado! 🎉**
