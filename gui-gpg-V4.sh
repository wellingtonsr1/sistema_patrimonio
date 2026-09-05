#!/bin/bash
#===============================================================================
# Script: gui-gpg-V4.sh
# Descrição: Gerenciador de Credenciais Criptografadas com GPG (CLI/TUI)
# Autor: Wellington
# Versão: 4.0-PRO
# 
# Evolução do V3 com foco em:
#   - Segurança (sem fallback /tmp, sem source de config)
#   - Integridade (backup obrigatório, validação pós-operação)
#   - Atomicidade (gravação via .tmp + mv)
#   - Formato JSON (senhas com caracteres especiais)
#   - Migração V3 → V4
#===============================================================================

umask 077

#================================================================================
# CONFIGURAÇÃO
#================================================================================
readonly VERSION="4.0-PRO"
readonly AUTHOR="Wellington"
readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly CONFIG_DIR="${HOME}/.config/gui-gpg"
readonly GPGFILE="${CONFIG_DIR}/minhasSenhas.txt.gpg"
readonly BACKUP_DIR="${CONFIG_DIR}/backups"
readonly LOG_FILE="${CONFIG_DIR}/gui-gpg.log"
readonly CONFIG_FILE="${CONFIG_DIR}/config"
readonly LOCK_DIR="${CONFIG_DIR}/.lock"
readonly TEMP_BASE="/dev/shm"
readonly VAULT_VERSION=4

#================================================================================
# VARIÁVEIS DE ESTADO
#================================================================================
ID="${GPG_KEY_ID:-Wellington}"
CURRENT_TEMP_DIR=""
LOCK_ACQUIRED=0
VAULT_FORMAT=""        # "v3" ou "v4"
CLIPBOARD_TIMEOUT=30
DEFAULT_PASS_LENGTH=20
DEFAULT_PASS_TYPE="strong"  # alphanumeric, strong, maximum
LOG_LEVEL="INFO"            # ERROR, WARN, INFO, DEBUG
FINGERPRINT=""
KEY_VALID=""

#================================================================================
# CORES / INTERFACE
#================================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

header_box() {
    local title="$1"
    local width=60
    local line=""
    for ((i=0; i<width; i++)); do line+="─"; done
    echo -e "\n${CYAN}┌${line}┐${NC}"
    printf "${CYAN}│${NC} %-$((width-2))s ${CYAN}│${NC}\n" "$title"
    echo -e "${CYAN}└${line}┘${NC}\n"
}

#================================================================================
# LOGGING
#================================================================================
_log() {
    local level="$1"
    local msg="$2"
    local allowed_levels=("ERROR" "WARN" "INFO" "DEBUG")
    local current_idx=-1
    local target_idx=-1
    local i=0
    for lvl in "${allowed_levels[@]}"; do
        [[ "$lvl" == "$LOG_LEVEL" ]] && current_idx=$i
        [[ "$lvl" == "$level" ]] && target_idx=$i
        ((i++))
    done
    [[ $target_idx -le $current_idx ]] && echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $msg" >> "$LOG_FILE"
}

log_error() { _log "ERROR" "$1"; }
log_warn()  { _log "WARN" "$1"; }
log_info()  { _log "INFO" "$1"; }
log_debug() { _log "DEBUG" "$1"; }

#--- Mensagens para o usuário ---
error_msg()   { echo -e "${RED}✗ Erro: $1${NC}" >&2; log_error "$1"; }
success_msg() { echo -e "${GREEN}✓ $1${NC}"; log_info "$1"; }
info_msg()    { echo -e "${BLUE}ℹ $1${NC}"; }
warning_msg() { echo -e "${YELLOW}⚠ $1${NC}"; log_warn "$1"; }
debug_msg()   { echo -e "${DIM}[DEBUG] $1${NC}"; log_debug "$1"; }

#================================================================================
# TRATAMENTO DE ERROS / CLEANUP
#================================================================================
fatal_exit() {
    error_msg "$1"
    cleanup
    exit 1
}

cleanup() {
    destroy_temp_workspace
    release_lock
}

trap cleanup EXIT INT TERM HUP

#================================================================================
# LOCK — AQUISIÇÃO ATÔMICA VIA mkdir
#================================================================================
acquire_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "$$" > "${LOCK_DIR}/pid"
        LOCK_ACQUIRED=1
        log_debug "Lock adquirido (PID $$)"
        return 0
    fi

    # Lock já existe — verificar se é órfão
    local lock_pid=""
    [[ -f "${LOCK_DIR}/pid" ]] && lock_pid=$(<"${LOCK_DIR}/pid")

    # Verificar idade do lock (stale se > 5 minutos)
    local lock_age=0
    if [[ -f "${LOCK_DIR}/pid" ]]; then
        local lock_mtime
        lock_mtime=$(stat -c %Y "${LOCK_DIR}/pid" 2>/dev/null || echo 0)
        local now
        now=$(date +%s)
        lock_age=$(( now - lock_mtime ))
    fi

    if [[ -n "$lock_pid" ]]; then
        if kill -0 "$lock_pid" 2>/dev/null; then
            # Processo vivo — verificar se é o MESMO processo nosso
            if [[ "$lock_pid" == "$$" ]]; then
                # Já somos donos do lock (re-entrant)
                LOCK_ACQUIRED=1
                return 0
            fi
            # Verificar se o lock é antigo (>5min) — stale mesmo com PID vivo
            if [[ $lock_age -gt 300 ]]; then
                warning_msg "Lock antigo detectado (${lock_age}s). PID $lock_pid pode estar travado. Removendo..."
                rm -rf "$LOCK_DIR"
                acquire_lock
                return $?
            fi
            error_msg "Outro processo (PID $lock_pid) está utilizando o cofre."
            error_msg "Se ninguém estiver usando, aguarde 5 minutos ou delete manualmente: rm -rf $LOCK_DIR"
            return 1
        else
            warning_msg "Lock órfão detectado (PID $lock_pid inativo). Removendo..."
            rm -rf "$LOCK_DIR"
            acquire_lock
            return $?
        fi
    else
        warning_msg "Lock sem PID registrado. Removendo..."
        rm -rf "$LOCK_DIR"
        acquire_lock
        return $?
    fi
}

release_lock() {
    if [[ "$LOCK_ACQUIRED" -eq 1 ]]; then
        rm -rf "$LOCK_DIR"
        LOCK_ACQUIRED=0
        log_debug "Lock liberado"
    fi
}

#================================================================================
# TEMPORÁRIOS — EXCLUSIVAMENTE EM /dev/shm
#================================================================================
create_temp_workspace() {
    acquire_lock || return 1

    # Verificar /dev/shm de forma rigorosa
    if [[ ! -d "$TEMP_BASE" ]]; then
        error_msg "O /dev/shm não está disponível."
        error_msg "Por segurança, o programa não irá descriptografar o cofre."
        release_lock
        return 1
    fi

    if [[ ! -w "$TEMP_BASE" ]]; then
        error_msg "O /dev/shm não tem permissão de escrita."
        error_msg "Por segurança, o programa não irá descriptografar o cofre."
        release_lock
        return 1
    fi

    CURRENT_TEMP_DIR=$(mktemp -d "${TEMP_BASE}/gui-gpg-XXXXXX" 2>/dev/null)
    if [[ -z "$CURRENT_TEMP_DIR" || ! -d "$CURRENT_TEMP_DIR" ]]; then
        error_msg "Falha ao criar diretório temporário em /dev/shm."
        release_lock
        return 1
    fi

    chmod 700 "$CURRENT_TEMP_DIR"
    return 0
}

destroy_temp_workspace() {
    if [[ -n "$CURRENT_TEMP_DIR" && -d "$CURRENT_TEMP_DIR" ]]; then
        # Sobrescrever arquivos antes de remover (best-effort)
        find "$CURRENT_TEMP_DIR" -type f -exec sh -c 'dd if=/dev/urandom of="$1" bs=$(stat -c%s "$1" 2>/dev/null || echo 1) count=1 conv=notrunc 2>/dev/null' _ {} \; 2>/dev/null
        rm -rf "$CURRENT_TEMP_DIR"
        CURRENT_TEMP_DIR=""
    fi
}

#================================================================================
# LOGGING — ROTAÇÃO
#================================================================================
rotate_log() {
    local max_size=1048576  # 1MB
    if [[ -f "$LOG_FILE" ]]; then
        local size
        size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
        if [[ "$size" -gt "$max_size" ]]; then
            mv "$LOG_FILE" "${LOG_FILE}.1" 2>/dev/null
            log_info "Log rotacionado"
        fi
    fi
}

#================================================================================
# GPG — OPERAÇÕES SEGURAS
#================================================================================
validate_gpg_key() {
    if ! command -v gpg &>/dev/null; then
        fatal_exit "GPG não encontrado no sistema."
    fi

    # 1. Tentar usar a chave configurada
    local key_info
    key_info=$(gpg --batch --list-keys --with-colons "$ID" 2>/dev/null)
    if [[ $? -eq 0 && -n "$key_info" ]]; then
        _extract_key_info "$key_info"
        return $?
    fi

    # 2. Chave configurada não encontrada — listar chaves disponíveis
    echo
    echo -e "${YELLOW}⚠ Chave GPG para ID '$ID' não encontrada no chaveiro.${NC}"
    echo

    local keys=()
    local fingerprints=()
    local uid_names=()
    local key_idx=0

    # Coletar todas as chaves disponíveis
    while IFS= read -r fpr; do
        [[ -z "$fpr" ]] && continue
        local uid_name
        uid_name=$(gpg --batch --list-keys --with-colons "$fpr" 2>/dev/null | grep '^uid' | head -1 | cut -d: -f10)
        [[ -z "$uid_name" ]] && uid_name="(sem nome)"
        ((key_idx++))
        keys+=("$fpr")
        fingerprints+=("$fpr")
        uid_names+=("$uid_name")
        echo -e "  ${BOLD}$key_idx${NC}) $uid_name"
        echo -e "     Fingerprint: ${DIM}$fpr${NC}"
    done < <(gpg --batch --list-keys --with-colons 2>/dev/null | grep '^fpr' | cut -d: -f10 | sort -u)

    if [[ $key_idx -eq 0 ]]; then
        echo -e "  ${DIM}(Nenhuma chave encontrada no chaveiro)${NC}"
        echo
        echo -e "  ${BOLD}1${NC} - Criar nova chave GPG agora"
        echo -e "  ${BOLD}0${NC} - Sair"
        echo
        read -rp "Opção: " create_opt

        case "$create_opt" in
            1)
                create_gpg_key
                return $? ;;
            *)
                fatal_exit "Nenhuma chave GPG disponível. Crie uma chave para usar o cofre." ;;
        esac
    fi

    # 3. Deixar o usuário escolher
    echo
    echo -e "  ${BOLD}0${NC} - Criar nova chave GPG"
    echo -e "  ${BOLD}C${NC} - Criar nova chave e usar"
    echo
    read -rp "Escolha a chave (1-${key_idx}) ou opção: " choice

    case "$choice" in
        0)
            create_gpg_key
            return $? ;;
        C|c)
            create_gpg_key
            if [[ $? -ne 0 ]]; then
                return 1
            fi
            # Usar a chave recém-criada
            ;;
        "")
            fatal_exit "Nenhuma opção selecionada." ;;
        *)
            if [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le $key_idx ]]; then
                local selected_fpr="${keys[$((choice-1))]}"
                local selected_uid="${uid_names[$((choice-1))]}"
                ID="$selected_fpr"
                save_config_value "GPG_ID" "$ID"
                echo -e "\n${GREEN}✓ Chave selecionada:${NC} $selected_uid"
                echo -e "  Fingerprint: ${DIM}$ID${NC}"

                key_info=$(gpg --batch --list-keys --with-colons "$ID" 2>/dev/null)
                _extract_key_info "$key_info"
                return $?
            else
                fatal_exit "Opção inválida."
            fi
            ;;
    esac

    # Se criou chave nova (opção C), validar
    key_info=$(gpg --batch --list-keys --with-colons "$ID" 2>/dev/null)
    if [[ $? -eq 0 && -n "$key_info" ]]; then
        _extract_key_info "$key_info"
        return $?
    fi

    fatal_exit "Não foi possível configurar a chave GPG."
}

# Função auxiliar para extrair fingerprint e validade
_extract_key_info() {
    local key_info="$1"

    FINGERPRINT=$(echo "$key_info" | grep '^fpr' | head -1 | cut -d: -f10)
    if [[ -z "$FINGERPRINT" ]]; then
        fatal_exit "Não foi possível obter o fingerprint da chave GPG."
    fi

    # Verificar validade: campo 2 = validade (u=ultimate, r=revoked, d=disabled, e=expired)
    local validity
    validity=$(echo "$key_info" | grep '^pub' | head -1 | cut -d: -f2)
    if [[ "$validity" == "r" ]]; then
        fatal_exit "A chave GPG '$ID' foi revogada."
    fi
    if [[ "$validity" == "d" ]]; then
        fatal_exit "A chave GPG '$ID' está desabilitada."
    fi
    if [[ "$validity" == "e" ]]; then
        fatal_exit "A chave GPG '$ID' está expirada."
    fi

    # Verificar expiração: campo 7 = data de expiração (vazio = sem expiração)
    local expiry
    expiry=$(echo "$key_info" | grep '^pub' | head -1 | cut -d: -f7)
    if [[ -n "$expiry" && "$expiry" != "" ]]; then
        local now
        now=$(date +%s)
        if [[ "$expiry" -lt "$now" ]]; then
            fatal_exit "A chave GPG '$ID' expirou em $(date -d "@$expiry" '+%Y-%m-%d' 2>/dev/null || echo "$expiry")"
        fi
    fi

    KEY_VALID="sim"
    log_info "Chave GPG validada: $FINGERPRINT"
}

# Criar nova chave GPG interativamente
create_gpg_key() {
    echo
    echo -e "${CYAN}════════════════════════════════════════${NC}"
    echo -e "${CYAN}  Criar Nova Chave GPG${NC}"
    echo -e "${CYAN}════════════════════════════════════════${NC}"
    echo
    echo -e "Será criada uma chave RSA 4096-bit."
    echo -e "Você precisará definir uma ${BOLD}passphrase${NC} (senha da chave)."
    echo

    read -rp "Nome/E-mail para a chave: " key_uid
    if [[ -z "$key_uid" ]]; then
        error_msg "Nome/email não pode ser vazio."
        return 1
    fi

    echo
    echo -e "${YELLOW}⚠ A passphrase protege sua chave privada. Escolha uma forte!${NC}"
    echo -e "O GPG irá solicitar a passphrase agora."
    echo

    # Gerar chave usando gpg --gen-key com parâmetros batch
    # NÃO usar --batch com passphrase fixa — melhor deixar o gpg pedir interativamente
    gpg --full-generate-key --cert-digest-algo SHA512 2>&1 <<< "$(cat <<KEYEOF
1
4096
0
$(date -d '+10 years' +%Y-%m-%d 2>/dev/null || echo '0')
${key_uid}

O
KEYEOF
)"

    local result=$?

    if [[ $result -ne 0 ]]; then
        error_msg "Falha ao criar a chave GPG."
        return 1
    fi

    # Encontrar a chave recém-criada
    local new_fpr
    new_fpr=$(gpg --batch --list-keys --with-colons 2>/dev/null | grep '^fpr' | tail -1 | cut -d: -f10)

    if [[ -z "$new_fpr" ]]; then
        error_msg "Chave criada mas não foi possível localizar o fingerprint."
        return 1
    fi

    ID="$new_fpr"
    save_config_value "GPG_ID" "$ID"
    FINGERPRINT="$new_fpr"

    echo
    success_msg "Chave GPG criada com sucesso!"
    echo -e "  Fingerprint: ${DIM}$FINGERPRINT${NC}"
    echo -e "  Config salva em: $CONFIG_FILE"
    echo

    log_info "Nova chave GPG criada: $FINGERPRINT"
    return 0
}

encrypt_vault() {
    local source_txt="$1"
    local dest_gpg="$2"

    if [[ ! -f "$source_txt" ]]; then
        error_msg "Arquivo de origem não encontrado para criptografia."
        return 1
    fi

    local tmp_gpg="${dest_gpg}.tmp.$$"

    if gpg --batch --yes --encrypt \
        --recipient "$ID" \
        --output "$tmp_gpg" \
        "$source_txt" 2>/dev/null; then

        # Verificar se o arquivo temporário é válido
        if [[ ! -s "$tmp_gpg" ]]; then
            error_msg "Arquivo criptografado gerado vazio."
            rm -f "$tmp_gpg"
            return 1
        fi

        chmod 600 "$tmp_gpg"

        # Verificar se podemos descriptografar o que acabamos de criptografar
        local verify_tmp="${CURRENT_TEMP_DIR}/verify_$$.txt"
        if gpg --batch --yes --decrypt "$tmp_gpg" > "$verify_tmp" 2>/dev/null; then
            local orig_size
            orig_size=$(stat -c%s "$source_txt" 2>/dev/null || echo 0)
            local verify_size
            verify_size=$(stat -c%s "$verify_tmp" 2>/dev/null || echo 0)
            rm -f "$verify_tmp"

            if [[ "$orig_size" -ne "$verify_size" ]]; then
                error_msg "Verificação de integridade falhou: tamanhos não conferem."
                rm -f "$tmp_gpg"
                return 1
            fi

            # Tudo OK — mover atômico
            mv -f "$tmp_gpg" "$dest_gpg"
            chmod 600 "$dest_gpg"
            log_info "Cofre criptografado e validado: $dest_gpg"
            return 0
        else
            rm -f "$verify_tmp"
            error_msg "Falha na verificação de integridade pós-criptografia."
            rm -f "$tmp_gpg"
            return 1
        fi
    else
        error_msg "Falha ao criptografar com GPG (Chave: $ID)."
        rm -f "$tmp_gpg"
        return 1
    fi
}

decrypt_vault() {
    local gpg_file="$1"
    local txt_file="$2"

    if [[ ! -f "$gpg_file" ]]; then
        info_msg "Nenhum cofre existente. Será criado um novo banco de dados."
        echo '{"version":4,"records":[]}' > "$txt_file"
        chmod 600 "$txt_file"
        VAULT_FORMAT="v4"
        return 0
    fi

    local tmp_decrypt="${txt_file}.decrypt.$$"

    if gpg --batch --yes --decrypt "$gpg_file" > "$tmp_decrypt" 2>/dev/null; then
        chmod 600 "$tmp_decrypt"

        # Verificar se o arquivo descriptografado tem conteúdo
        if [[ ! -s "$tmp_decrypt" ]]; then
            error_msg "Descriptografia produziu arquivo vazio."
            rm -f "$tmp_decrypt"
            return 1
        fi

        detect_and_normalize_vault "$tmp_decrypt"

        mv -f "$tmp_decrypt" "$txt_file"
        chmod 600 "$txt_file"
        log_info "Cofre descriptografado: formato=$VAULT_FORMAT"
        return 0
    else
        rm -f "$tmp_decrypt"
        error_msg "Falha ao descriptografar. Verifique a senha da sua chave GPG."
        return 1
    fi
}

#================================================================================
# COFRE — OPERAÇÕES ATÔMICAS
#================================================================================
save_vault() {
    local data="$1"
    local gpg_file="$2"

    local work_txt="${CURRENT_TEMP_DIR}/vault_save_$$.json"

    echo "$data" > "$work_txt"
    chmod 600 "$work_txt"

    if encrypt_vault "$work_txt" "$gpg_file"; then
        rm -f "$work_txt"
        return 0
    else
        rm -f "$work_txt"
        return 1
    fi
}

load_vault() {
    local gpg_file="$1"
    local txt_file="$2"

    decrypt_vault "$gpg_file" "$txt_file"
    return $?
}

#================================================================================
# FORMATO V4 — JSON VIA jq OU python3
#================================================================================
has_jq() { command -v jq &>/dev/null; }
has_python3() { command -v python3 &>/dev/null; }

# Ler registros do JSON V4
# Saída: cada linha = service\tuser\tlogin\tpassword
read_v4_records() {
    local json_file="$1"

    if has_jq; then
        jq -r '.records[] | [.service, .user, .login, .password] | @tsv' "$json_file" 2>/dev/null
    elif has_python3; then
        python3 -c "
import json, sys
with open('$json_file') as f:
    data = json.load(f)
for r in data.get('records', []):
    print(f\"{r.get('service','')}\t{r.get('user','')}\t{r.get('login','')}\t{r.get('password','')}\")
" 2>/dev/null
    else
        error_msg "Necessário 'jq' ou 'python3' para processar formato V4."
        return 1
    fi
}

# Ler registros como array JSON bruto
read_v4_json() {
    local json_file="$1"

    if has_jq; then
        jq -c '.records' "$json_file" 2>/dev/null
    elif has_python3; then
        python3 -c "
import json
with open('$json_file') as f:
    data = json.load(f)
print(json.dumps(data.get('records', [])))
" 2>/dev/null
    else
        return 1
    fi
}

# Contar registros
count_v4_records() {
    local json_file="$1"

    if has_jq; then
        jq '.records | length' "$json_file" 2>/dev/null
    elif has_python3; then
        python3 -c "
import json
with open('$json_file') as f:
    data = json.load(f)
print(len(data.get('records', [])))
" 2>/dev/null
    else
        echo "0"
    fi
}

# Validar estrutura JSON V4
validate_v4_json() {
    local json_file="$1"

    if has_jq; then
        jq -e '.version == 4 and (.records | type) == "array"' "$json_file" &>/dev/null
    elif has_python3; then
        python3 -c "
import json, sys
with open('$json_file') as f:
    data = json.load(f)
if data.get('version') != 4 or not isinstance(data.get('records'), list):
    sys.exit(1)
for r in data['records']:
    if not isinstance(r, dict):
        sys.exit(1)
    if not all(k in r for k in ('service', 'user', 'login', 'password')):
        sys.exit(1)
" 2>/dev/null
    else
        return 1
    fi
}

# Criar JSON V4 vazio
create_empty_v4_json() {
    echo '{"version":4,"records":[]}'
}

# Adicionar registro ao JSON V4
add_v4_record() {
    local json_file="$1"
    local service="$2"
    local user="$3"
    local login="$4"
    local password="$5"

    if has_jq; then
        local new_record
        new_record=$(jq -n \
            --arg s "$service" \
            --arg u "$user" \
            --arg l "$login" \
            --arg p "$password" \
            '{service: $s, user: $u, login: $l, password: $p}')

        jq --argjson rec "$new_record" '.records += [$rec]' "$json_file" > "${json_file}.tmp" \
            && mv -f "${json_file}.tmp" "$json_file"
    elif has_python3; then
        python3 -c "
import json
with open('$json_file') as f:
    data = json.load(f)
data['records'].append({
    'service': '''$(echo "$service" | sed "s/'/\\\\'/g")''',
    'user': '''$(echo "$user" | sed "s/'/\\\\'/g")''',
    'login': '''$(echo "$login" | sed "s/'/\\\\'/g")''',
    'password': '''$(echo "$password" | sed "s/'/\\\\'/g")'''
})
with open('${json_file}.tmp', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
" 2>/dev/null && mv -f "${json_file}.tmp" "$json_file"
    else
        return 1
    fi
}

# Remover registro por índice
remove_v4_record() {
    local json_file="$1"
    local index="$2"

    if has_jq; then
        jq "del(.records[$index])" "$json_file" > "${json_file}.tmp" \
            && mv -f "${json_file}.tmp" "$json_file"
    elif has_python3; then
        python3 -c "
import json
with open('$json_file') as f:
    data = json.load(f)
idx = int('$index')
if 0 <= idx < len(data['records']):
    data['records'].pop(idx)
with open('${json_file}.tmp', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
" 2>/dev/null && mv -f "${json_file}.tmp" "$json_file"
    else
        return 1
    fi
}

# Atualizar registro por índice
update_v4_record() {
    local json_file="$1"
    local index="$2"
    local service="$3"
    local user="$4"
    local login="$5"
    local password="$6"

    if has_jq; then
        local new_record
        new_record=$(jq -n \
            --arg s "$service" \
            --arg u "$user" \
            --arg l "$login" \
            --arg p "$password" \
            '{service: $s, user: $u, login: $l, password: $p}')

        jq --argjson idx "$index" --argjson rec "$new_record" \
            '.records[$idx] = $rec' "$json_file" > "${json_file}.tmp" \
            && mv -f "${json_file}.tmp" "$json_file"
    elif has_python3; then
        python3 -c "
import json
with open('$json_file') as f:
    data = json.load(f)
idx = int('$index')
if 0 <= idx < len(data['records']):
    data['records'][idx] = {
        'service': '''$(echo "$service" | sed "s/'/\\\\'/g")''',
        'user': '''$(echo "$user" | sed "s/'/\\\\'/g")''',
        'login': '''$(echo "$login" | sed "s/'/\\\\'/g")''',
        'password': '''$(echo "$password" | sed "s/'/\\\\'/g")'''
    }
with open('${json_file}.tmp', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
" 2>/dev/null && mv -f "${json_file}.tmp" "$json_file"
    else
        return 1
    fi
}

# Buscar registros V4
search_v4_records() {
    local json_file="$1"
    local termo="$2"
    local modo="${3:-smart}"  # smart, servico, login, usuario, todos

    local q_lower
    q_lower=$(echo "$termo" | tr '[:upper:]' '[:lower:]')

    if has_jq; then
        case "$modo" in
            servico)
                jq -r --arg q "$q_lower" \
                    '.records[] | select((.service // "" | ascii_downcase) | contains($q)) | [.service, .user, .login, .password] | @tsv' \
                    "$json_file" 2>/dev/null
                ;;
            login)
                jq -r --arg q "$q_lower" \
                    '.records[] | select((.login // "" | ascii_downcase) | contains($q)) | [.service, .user, .login, .password] | @tsv' \
                    "$json_file" 2>/dev/null
                ;;
            usuario)
                jq -r --arg q "$q_lower" \
                    '.records[] | select((.user // "" | ascii_downcase) | contains($q)) | [.service, .user, .login, .password] | @tsv' \
                    "$json_file" 2>/dev/null
                ;;
            todos)
                jq -r --arg q "$q_lower" \
                    '.records[] | select(
                        ((.service // "") | ascii_downcase | contains($q)) or
                        ((.login // "") | ascii_downcase | contains($q)) or
                        ((.user // "") | ascii_downcase | contains($q))
                    ) | [.service, .user, .login, .password] | @tsv' \
                    "$json_file" 2>/dev/null
                ;;
            smart)
                # Priorizar serviço → login → usuário
                local result=""
                result=$(jq -r --arg q "$q_lower" \
                    '.records[] | select((.service // "" | ascii_downcase) | contains($q)) | [.service, .user, .login, .password] | @tsv' \
                    "$json_file" 2>/dev/null)

                if [[ -n "$result" ]]; then
                    echo "$result"
                    return 0
                fi

                result=$(jq -r --arg q "$q_lower" \
                    '.records[] | select((.login // "" | ascii_downcase) | contains($q)) | [.service, .user, .login, .password] | @tsv' \
                    "$json_file" 2>/dev/null)

                if [[ -n "$result" ]]; then
                    echo "$result"
                    return 0
                fi

                result=$(jq -r --arg q "$q_lower" \
                    '.records[] | select((.user // "" | ascii_downcase) | contains($q)) | [.service, .user, .login, .password] | @tsv' \
                    "$json_file" 2>/dev/null)

                if [[ -n "$result" ]]; then
                    echo "$result"
                    return 0
                fi
                ;;
        esac
    elif has_python3; then
        python3 -c "
import json, sys

with open('$json_file') as f:
    data = json.load(f)

q = '$q_lower'.lower()
modo = '$modo'
records = data.get('records', [])
results = []

for r in records:
    svc = (r.get('service', '') or '').lower()
    usr = (r.get('user', '') or '').lower()
    log_ = (r.get('login', '') or '').lower()
    pwd = r.get('password', '')

    match = False
    if modo == 'servico':    match = q in svc
    elif modo == 'login':    match = q in log_
    elif modo == 'usuario':  match = q in usr
    elif modo == 'todos':    match = q in svc or q in log_ or q in usr
    elif modo == 'smart':
        if q in svc: match = True
        elif q in log_: match = True
        elif q in usr: match = True

    if match:
        results.append(f'{r.get(\"service\",\"\")}\t{r.get(\"user\",\"\")}\t{r.get(\"login\",\"\")}\t{r.get(\"password\",\"\")}')

for r in results:
    print(r)
" 2>/dev/null
    else
        error_msg "Necessário 'jq' ou 'python3' para busca."
        return 1
    fi
}

#================================================================================
# DETECÇÃO E NORMALIZAÇÃO DE FORMATO
#================================================================================
detect_and_normalize_vault() {
    local vault_file="$1"
    # Retorna: v4, v3, ou vazio se arquivo não existe/vazio

    [[ ! -s "$vault_file" ]] && { VAULT_FORMAT="v4"; return 0; }

    local first_line
    first_line=$(head -1 "$vault_file")

    # V4 com version field
    if echo "$first_line" | grep -q '"version"'; then
        VAULT_FORMAT="v4"
        return 0
    fi

    # JSON sem version (array ou object) — normalizar para V4
    if echo "$first_line" | grep -qE '^\[|^\{'; then
        VAULT_FORMAT="v4"
        if has_jq; then
            if ! jq -e '.version' "$vault_file" &>/dev/null; then
                local tmp="${CURRENT_TEMP_DIR}/norm_$$.json"
                # Se é array, embrulhar; se é objeto sem records, adicionar
                if jq -e 'type == "array"' "$vault_file" &>/dev/null; then
                    jq '{version: 4, records: .}' "$vault_file" > "$tmp" 2>/dev/null \
                        && mv -f "$tmp" "$vault_file"
                elif ! jq -e 'has("records")' "$vault_file" &>/dev/null; then
                    jq '{version: 4, records: .}' "$vault_file" > "$tmp" 2>/dev/null \
                        && mv -f "$tmp" "$vault_file"
                fi
            fi
        elif has_python3; then
            python3 -c "
import json
with open('$vault_file') as f:
    data = json.load(f)
if isinstance(data, list):
    data = {'version': 4, 'records': data}
elif 'records' not in data:
    data = {'version': 4, 'records': data}
with open('$vault_file', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
" 2>/dev/null
        fi
        return 0
    fi

    # Legado delimiter-based
    VAULT_FORMAT="v3"
    return 0
}

#================================================================================
# MIGRAÇÃO V3 → V4
#================================================================================
parse_legacy_line() {
    local line="$1"
    local delimiter=""

    if [[ "$line" == *";"* ]]; then
        delimiter=";"
    elif [[ "$line" == *":"* ]]; then
        delimiter=":"
    elif [[ "$line" == *"|"* ]]; then
        delimiter="|"
    else
        # Espaço como último recurso
        read -ra campos <<< "$line"
        local total=${#campos[@]}
        if [[ $total -ge 4 ]]; then
            echo "${campos[*]:0:$((total-3))}	${campos[$((total-3))]}	${campos[$((total-2))]}	${campos[$((total-1))]}"
        elif [[ $total -eq 3 ]]; then
            echo "${campos[0]}	${campos[1]}	${campos[1]}	${campos[2]}"
        else
            echo "${campos[0]}			"
        fi
        return
    fi

    # Parsear com delimitador identificado
    local IFS_SAVE="$IFS"
    IFS="$delimiter" read -r f1 f2 f3 f4 <<< "$line"
    IFS="$IFS_SAVE"

    if [[ -n "$f4" ]]; then
        echo "${f1}	${f2}	${f3}	${f4}"
    elif [[ -n "$f3" ]]; then
        echo "${f1}	${f2}	${f2}	${f3}"
    elif [[ -n "$f2" ]]; then
        echo "${f1}			${f2}"
    else
        echo "${f1}			"
    fi
}

migrate_v3_to_v4() {
    local v3_txt="$1"

    if [[ ! -s "$v3_txt" ]]; then
        echo '{"version":4,"records":[]}'
        return 0
    fi

    local json_data
    json_data='{"version":4,"records":['

    local first=1
    local count=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" ]] && continue

        local parsed
        parsed=$(parse_legacy_line "$line")

        local svc usr login pwd
        IFS=$'\t' read -r svc usr login pwd <<< "$parsed"

        # Pular linhas inválidas
        [[ -z "$svc" ]] && continue

        if [[ $first -eq 1 ]]; then
            first=0
        else
            json_data+=','
        fi

        # Escapar aspas duplas para JSON
        svc="${svc//\"/\\\"}"
        usr="${usr//\"/\\\"}"
        login="${login//\"/\\\"}"
        pwd="${pwd//\"/\\\"}"

        json_data+="{\"service\":\"${svc}\",\"user\":\"${usr}\",\"login\":\"${login}\",\"password\":\"${pwd}\"}"
        ((count++))
    done < "$v3_txt"

    json_data+=']]}'

    if [[ $count -eq 0 ]]; then
        echo '{"version":4,"records":[]}'
    else
        echo "$json_data"
    fi
}

#================================================================================
# BACKUP — SISTEMA COMPLETO
#================================================================================
readonly MAX_BACKUPS=20

create_backup() {
    local gpg_file="$1"
    local reason="${2:-manual}"

    [[ ! -f "$gpg_file" ]] && return 0

    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${BACKUP_DIR}/vault.BKP.${timestamp}.gpg"

    if cp "$gpg_file" "$backup_file" && chmod 600 "$backup_file"; then
        # Verificar integridade do backup
        local orig_size
        orig_size=$(stat -c%s "$gpg_file" 2>/dev/null || echo 0)
        local bkp_size
        bkp_size=$(stat -c%s "$backup_file" 2>/dev/null || echo 0)

        if [[ "$orig_size" -ne "$bkp_size" ]]; then
            error_msg "Backup corrompido: tamanhos não conferem."
            rm -f "$backup_file"
            return 1
        fi

        log_info "Backup criado: $(basename "$backup_file") [reason=$reason]"
        cleanup_old_backups
        return 0
    else
        error_msg "Falha ao criar backup."
        return 1
    fi
}

# Backup obrigatório — aborta a operação se falhar
mandatory_backup() {
    local reason="$1"

    if [[ ! -f "$GPGFILE" ]]; then
        return 0
    fi

    info_msg "Criando backup obrigatório ($reason)..."
    if ! create_backup "$GPGFILE" "$reason"; then
        error_msg "FALHA no backup obrigatório. Operação cancelada por segurança."
        return 1
    fi
    success_msg "Backup obrigatório criado."
    return 0
}

cleanup_old_backups() {
    local backups=()
    while IFS= read -r -d $'\0' f; do
        [[ -n "$f" ]] && backups+=("$f")
    done < <(find "$BACKUP_DIR" -maxdepth 1 -name "vault.BKP.*.gpg" -type f -printf '%T@ %p\0' 2>/dev/null | sort -z -rn | cut -z -d' ' -f2-)

    if [[ ${#backups[@]} -gt $MAX_BACKUPS ]]; then
        for ((i=MAX_BACKUPS; i<${#backups[@]}; i++)); do
            rm -f "${backups[$i]}" 2>/dev/null
            log_info "Backup antigo removido: $(basename "${backups[$i]}")"
        done
    fi
}

list_backups() {
    local backups=()
    while IFS= read -r -d $'\0' f; do
        [[ -n "$f" ]] && backups+=("$f")
    done < <(find "$BACKUP_DIR" -maxdepth 1 -name "vault.BKP.*.gpg" -type f -printf '%T@ %p\0' 2>/dev/null | sort -z -rn | cut -z -d' ' -f2-)

    if [[ ${#backups[@]} -eq 0 ]]; then
        warning_msg "Nenhum backup encontrado."
        return
    fi

    echo -e "\n${CYAN}===== Backups Disponíveis =====${NC}\n"
    local count=0
    for bkp in "${backups[@]}"; do
        ((count++))
        local name size date_str
        name=$(basename "$bkp")
        size=$(du -h "$bkp" 2>/dev/null | awk '{print $1}')
        date_str=$(stat -c '%y' "$bkp" 2>/dev/null | cut -d. -f1)

        # Verificar integridade básica
        local status="${GREEN}OK${NC}"
        if [[ ! -s "$bkp" ]]; then
            status="${RED}VAZIO${NC}"
        fi

        printf " %2d) %s  %s  Tamanho: %s  Status: %b\n" "$count" "$name" "$date_str" "$size" "$status"
    done
    echo -e "\n${DIM}Total: ${#backups[@]} backups${NC}"
}

verify_backup_integrity() {
    local gpg_file="$1"

    if [[ ! -f "$gpg_file" ]]; then
        error_msg "Arquivo não encontrado."
        return 1
    fi

    local tmp="${CURRENT_TEMP_DIR}/verify_bkp_$$.txt"
    if gpg --batch --yes --decrypt "$gpg_file" > "$tmp" 2>/dev/null; then
        local valid=1
        detect_and_normalize_vault "$tmp"
        if [[ "$VAULT_FORMAT" == "v4" ]]; then
            if ! validate_v4_json "$tmp"; then
                valid=0
            fi
        fi

        rm -f "$tmp"

        if [[ $valid -eq 1 ]]; then
            return 0
        else
            return 1
        fi
    else
        rm -f "$tmp"
        return 1
    fi
}

#================================================================================
# INTEGRIDADE DO COFRE
#================================================================================
verify_vault() {
    local all_ok=1

    echo -e "\n${CYAN}===== Verificação de Integridade do Cofre =====${NC}\n"

    # 1. Arquivo existe
    if [[ -f "$GPGFILE" ]]; then
        echo -e "  ${GREEN}✓${NC} Arquivo encontrado: $GPGFILE"
    else
        echo -e "  ${YELLOW}⚠${NC} Arquivo não encontrado (cofre vazio)"
        return 0
    fi

    # 2. Permissões
    local perms
    perms=$(stat -c '%a' "$GPGFILE" 2>/dev/null)
    if [[ "$perms" == "600" ]]; then
        echo -e "  ${GREEN}✓${NC} Permissão: $perms"
    else
        echo -e "  ${RED}✗${NC} Permissão incorreta: $perms (esperado 600)"
        all_ok=0
    fi

    # 3. Chave GPG
    if [[ -n "$FINGERPRINT" ]]; then
        echo -e "  ${GREEN}✓${NC} Chave GPG: ${DIM}${FINGERPRINT}${NC}"
    else
        echo -e "  ${RED}✗${NC} Chave GPG não validada"
        all_ok=0
    fi

    # 4. Descriptografia
    local test_file="${CURRENT_TEMP_DIR}/integrity_check_$$.txt"
    if gpg --batch --yes --decrypt "$GPGFILE" > "$test_file" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Descriptografia OK"
    else
        echo -e "  ${RED}✗${NC} Falha na descriptografia"
        rm -f "$test_file"
        all_ok=0
        [[ $all_ok -eq 0 ]] && echo -e "\n${RED}STATUS: COFRE COM PROBLEMAS${NC}"
        return 1
    fi

    # 5. Formato
    detect_and_normalize_vault "$test_file"
    if [[ "$VAULT_FORMAT" == "v4" ]]; then
        echo -e "  ${GREEN}✓${NC} Formato: V4 (JSON)"

        # 6. Estrutura
        if validate_v4_json "$test_file"; then
            echo -e "  ${GREEN}✓${NC} Estrutura JSON válida"

            # 7. Registros
            local count
            count=$(count_v4_records "$test_file")
            echo -e "  ${GREEN}✓${NC} Registros: $count"
        else
            echo -e "  ${RED}✗${NC} Estrutura JSON inválida"
            all_ok=0
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} Formato legado V3 detectado (não migrado)"
    fi

    rm -f "$test_file"

    echo
    if [[ $all_ok -eq 1 ]]; then
        echo -e "${GREEN}STATUS: COFRE ÍNTEGRO${NC}"
    else
        echo -e "${RED}STATUS: COFRE COM PROBLEMAS${NC}"
    fi
}

#================================================================================
# CLIPBOARD — X11 / WAYLAND
#================================================================================
CLIPBOARD_TIMER_PID=""

copy_to_clipboard() {
    local text="$1"
    local timeout="${2:-$CLIPBOARD_TIMEOUT}"

    # Limpar timer anterior se existir
    if [[ -n "$CLIPBOARD_TIMER_PID" ]]; then
        kill "$CLIPBOARD_TIMER_PID" 2>/dev/null
        CLIPBOARD_TIMER_PID=""
    fi

    if command -v xclip &>/dev/null && [[ -n "${DISPLAY:-}" ]]; then
        printf '%s' "$text" | xclip -selection clipboard
        info_msg "Senha copiada para a área de transferência!"

        (
            sleep "$timeout"
            curr=$(xclip -selection clipboard -o 2>/dev/null)
            if [[ "$curr" == "$text" ]]; then
                printf '' | xclip -selection clipboard 2>/dev/null
            fi
        ) &>/dev/null &
        CLIPBOARD_TIMER_PID=$!
        disown "$CLIPBOARD_TIMER_PID" 2>/dev/null

        info_msg "A área de transferência será limpa automaticamente em ${timeout}s."
        return 0

    elif command -v wl-copy &>/dev/null && [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        printf '%s' "$text" | wl-copy 2>/dev/null
        info_msg "Senha copiada (Wayland)!"

        (
            sleep "$timeout"
            curr=$(wl-paste 2>/dev/null)
            if [[ "$curr" == "$text" ]]; then
                wl-copy --clear 2>/dev/null || true
            fi
        ) &>/dev/null &
        CLIPBOARD_TIMER_PID=$!
        disown "$CLIPBOARD_TIMER_PID" 2>/dev/null

        info_msg "A área de transferência será limpa automaticamente em ${timeout}s."
        return 0
    fi

    return 1
}

has_clipboard() {
    (command -v xclip &>/dev/null && [[ -n "${DISPLAY:-}" ]]) || \
    (command -v wl-copy &>/dev/null && [[ -n "${WAYLAND_DISPLAY:-}" ]])
}

#================================================================================
# GERADOR DE SENHA
#================================================================================
generate_password() {
    local length="${1:-$DEFAULT_PASS_LENGTH}"
    local type="${2:-$DEFAULT_PASS_TYPE}"

    # Validar comprimento
    if [[ "$length" -lt 8 ]]; then length=8; fi
    if [[ "$length" -gt 128 ]]; then length=128; fi

    local charset=""
    case "$type" in
        alphanumeric)
            charset='A-Za-z0-9'
            ;;
        strong)
            charset='A-Za-z0-9!@#%^&*()-_=+[]{}'
            ;;
        maximum)
            charset='A-Za-z0-9!@#$%^&*()-_=+[]{}<>/?.~`|'
            ;;
        *)
            charset='A-Za-z0-9!@#%^&*()-_=+[]{}'
            ;;
    esac

    LC_ALL=C tr -dc "$charset" < /dev/urandom 2>/dev/null | head -c "$length"
}

password_generator_menu() {
    header_box "Gerador de Senha"

    echo "Selecione o comprimento:"
    echo -e "  ${BOLD}1${NC} - 16 caracteres"
    echo -e "  ${BOLD}2${NC} - 20 caracteres (padrão)"
    echo -e "  ${BOLD}3${NC} - 24 caracteres"
    echo -e "  ${BOLD}4${NC} - 32 caracteres"
    echo -e "  ${BOLD}5${NC} - Personalizado"
    echo
    read -rp "Opção: " len_opt

    local length=20
    case "$len_opt" in
        1) length=16 ;;
        2) length=20 ;;
        3) length=24 ;;
        4) length=32 ;;
        5)
            read -rp "Comprimento (8-128): " length
            if ! [[ "$length" =~ ^[0-9]+$ ]] || [[ "$length" -lt 8 ]] || [[ "$length" -gt 128 ]]; then
                error_msg "Comprimento inválido. Usando 20."
                length=20
            fi
            ;;
        *) length=20 ;;
    esac

    echo -e "\nSelecione o tipo:"
    echo -e "  ${BOLD}1${NC} - Alfanumérica (letras + números)"
    echo -e "  ${BOLD}2${NC} - Forte (letras + números + símbolos)"
    echo -e "  ${BOLD}3${NC} - Máxima (todos os caracteres seguros)"
    echo
    read -rp "Opção: " type_opt

    local ptype="strong"
    case "$type_opt" in
        1) ptype="alphanumeric" ;;
        2) ptype="strong" ;;
        3) ptype="maximum" ;;
        *) ptype="strong" ;;
    esac

    local senha
    senha=$(generate_password "$length" "$ptype")

    if [[ -z "$senha" ]]; then
        error_msg "Falha ao gerar senha."
        return 1
    fi

    echo -e "\n${GREEN}✓ Senha gerada:${NC} ${BOLD}$senha${NC}\n"

    # Oferecer cópia
    if has_clipboard; then
        read -rp "Copiar para a área de transferência? (S/n): " copy_opt
        if [[ ! "$copy_opt" =~ ^[nN]$ ]]; then
            copy_to_clipboard "$senha"
        fi
    fi

    # NUNCA gravar em log
    log_info "Senha gerada (comprimento=$length, tipo=$ptype)"
}

#================================================================================
# VALIDAÇÕES
#================================================================================
validate_input() {
    local input="$1"
    local max_length="${2:-256}"
    [[ -z "$input" ]] && return 1
    [[ ${#input} -gt "$max_length" ]] && return 1
    return 0
}

validate_no_special() {
    local val="$1"
    [[ "$val" == *$'\n'* ]] && return 1
    return 0
}

# Escapar HTML (prevenção de XSS/injeção)
escape_html() {
    local text="$1"
    text="${text//&/&amp;}"
    text="${text//</&lt;}"
    text="${text//>/&gt;}"
    text="${text//\"/&quot;}"
    text="${text//\'/&#39;}"
    printf '%s' "$text"
}

#================================================================================
# MENU — GERENCIAMENTO DE BACKUPS
#================================================================================
backup_menu() {
    while true; do
        header_box "Gerenciar Backups"

        echo -e "  ${BOLD}1${NC} - Listar backups"
        echo -e "  ${BOLD}2${NC} - Criar backup agora"
        echo -e "  ${BOLD}3${NC} - Restaurar backup"
        echo -e "  ${BOLD}4${NC} - Verificar integridade de um backup"
        echo -e "  ${BOLD}5${NC} - Excluir backup"
        echo -e "  ${BOLD}0${NC} - Voltar"
        echo
        read -rp "Opção: " opt

        case "$opt" in
            1) list_backups ;;
            2)
                if mandatory_backup "manual"; then
                    success_msg "Backup criado com sucesso."
                fi
                ;;
            3)
                restore_backup
                ;;
            4)
                verify_backup_interactive
                ;;
            5)
                delete_backup_interactive
                ;;
            0) return ;;
            *) warning_msg "Opção inválida." ;;
        esac

        read -rp "Pressione [Enter] para continuar..."
    done
}

restore_backup() {
    local backups=()
    while IFS= read -r -d $'\0' f; do
        [[ -n "$f" ]] && backups+=("$f")
    done < <(find "$BACKUP_DIR" -maxdepth 1 -name "vault.BKP.*.gpg" -type f -printf '%T@ %p\0' 2>/dev/null | sort -z -rn | cut -z -d' ' -f2-)

    if [[ ${#backups[@]} -eq 0 ]]; then
        warning_msg "Nenhum backup disponível para restauração."
        return
    fi

    list_backups

    echo
    read -rp "Número do backup para restaurar (ou 0 para cancelar): " bkp_num

    if ! [[ "$bkp_num" =~ ^[0-9]+$ ]] || [[ "$bkp_num" -lt 1 ]] || [[ "$bkp_num" -gt ${#backups[@]} ]]; then
        info_msg "Operação cancelada."
        return
    fi

    local selected_bkp="${backups[$((bkp_num-1))]}"

    echo -e "\n${RED}${BOLD}ATENÇÃO${NC}"
    echo -e "A restauração substituirá o cofre atual."
    echo -e "Um backup do cofre atual será criado antes da restauração."
    echo -e "\nArquivo de backup: $(basename "$selected_bkp")"
    echo
    read -rp "Digite RESTAURAR para continuar: " confirm

    if [[ "$confirm" != "RESTAURAR" ]]; then
        info_msg "Operação cancelada."
        return
    fi

    # Backup do cofre atual
    if [[ -f "$GPGFILE" ]]; then
        if ! mandatory_backup "pre-restore"; then
            error_msg "Backup pré-restauração falhou. Operação cancelada."
            return
        fi
    fi

    # Restaurar
    if cp "$selected_bkp" "$GPGFILE" && chmod 600 "$GPGFILE"; then
        success_msg "Cofre restaurado com sucesso a partir de $(basename "$selected_bkp")."
        log_info "Cofre restaurado: $(basename "$selected_bkp")"
    else
        error_msg "Falha ao restaurar backup."
    fi
}

verify_backup_interactive() {
    local backups=()
    while IFS= read -r -d $'\0' f; do
        [[ -n "$f" ]] && backups+=("$f")
    done < <(find "$BACKUP_DIR" -maxdepth 1 -name "vault.BKP.*.gpg" -type f -printf '%T@ %p\0' 2>/dev/null | sort -z -rn | cut -z -d' ' -f2-)

    if [[ ${#backups[@]} -eq 0 ]]; then
        warning_msg "Nenhum backup disponível."
        return
    fi

    list_backups

    echo
    read -rp "Número do backup para verificar (ou 0 para cancelar): " bkp_num

    if ! [[ "$bkp_num" =~ ^[0-9]+$ ]] || [[ "$bkp_num" -lt 1 ]] || [[ "$bkp_num" -gt ${#backups[@]} ]]; then
        return
    fi

    local selected_bkp="${backups[$((bkp_num-1))]}"
    create_temp_workspace || return

    echo -e "\nVerificando $(basename "$selected_bkp")..."
    if verify_backup_integrity "$selected_bkp"; then
        success_msg "Backup íntegro e válido."
    else
        error_msg "Backup com problemas de integridade!"
    fi

    destroy_temp_workspace
}

delete_backup_interactive() {
    local backups=()
    while IFS= read -r -d $'\0' f; do
        [[ -n "$f" ]] && backups+=("$f")
    done < <(find "$BACKUP_DIR" -maxdepth 1 -name "vault.BKP.*.gpg" -type f -printf '%T@ %p\0' 2>/dev/null | sort -z -rn | cut -z -d' ' -f2-)

    if [[ ${#backups[@]} -eq 0 ]]; then
        warning_msg "Nenhum backup disponível."
        return
    fi

    list_backups

    echo
    read -rp "Número do backup para excluir (ou 0 para cancelar): " bkp_num

    if ! [[ "$bkp_num" =~ ^[0-9]+$ ]] || [[ "$bkp_num" -lt 1 ]] || [[ "$bkp_num" -gt ${#backups[@]} ]]; then
        return
    fi

    local selected_bkp="${backups[$((bkp_num-1))]}"

    echo -e "\n${RED}ATENÇÃO${NC}: Excluir $(basename "$selected_bkp")?"
    read -rp "Digite EXCLUIR para confirmar: " confirm

    if [[ "$confirm" == "EXCLUIR" ]]; then
        if rm -f "$selected_bkp"; then
            success_msg "Backup excluído."
        else
            error_msg "Falha ao excluir backup."
        fi
    else
        info_msg "Operação cancelada."
    fi
}

#================================================================================
# MENU — CONFIGURAÇÕES
#================================================================================
settings_menu() {
    while true; do
        header_box "Configurações"

        echo -e "  ${BOLD}1${NC} - Alterar chave GPG"
        echo -e "  ${BOLD}2${NC} - Ver fingerprint da chave atual"
        echo -e "  ${BOLD}3${NC} - Configurar timeout do clipboard (${CLIPBOARD_TIMEOUT}s)"
        echo -e "  ${BOLD}4${NC} - Configurar tamanho padrão da senha (${DEFAULT_PASS_LENGTH})"
        echo -e "  ${BOLD}5${NC} - Configurar nível de log (${LOG_LEVEL})"
        echo -e "  ${BOLD}6${NC} - Ver diretórios do sistema"
        echo -e "  ${BOLD}0${NC} - Voltar"
        echo
        read -rp "Opção: " opt

        case "$opt" in
            1) change_gpg_key ;;
            2) show_fingerprint ;;
            3) configure_clipboard_timeout ;;
            4) configure_default_password_length ;;
            5) configure_log_level ;;
            6) show_system_dirs ;;
            0) return ;;
            *) warning_msg "Opção inválida." ;;
        esac

        read -rp "Pressione [Enter] para continuar..."
    done
}

change_gpg_key() {
    echo -e "\nChave GPG atual: ${BOLD}$ID${NC}"
    echo -e "Fingerprint: ${DIM}${FINGERPRINT}${NC}\n"

    echo "Chaves disponíveis no chaveiro:"
    gpg --list-keys --keyid-format LONG 2>/dev/null | grep -E '^(pub|uid)' | head -20
    echo

    read -rp "Novo ID/Email/Fingerprint da chave (Enter para manter): " new_id
    [[ -z "$new_id" ]] && return

    # Validar nova chave
    local old_id="$ID"
    ID="$new_id"

    if ! validate_gpg_key; then
        ID="$old_id"
        error_msg "Chave inválida. Mantendo a chave anterior."
        return
    fi

    # Salvar na configuração
    if save_config_value "GPG_ID" "$ID"; then
        success_msg "Chave GPG alterada para: $ID (${FINGERPRINT})"
    else
        ID="$old_id"
        error_msg "Falha ao salvar configuração."
    fi
}

show_fingerprint() {
    echo -e "\nChave configurada: ${BOLD}$ID${NC}"
    echo -e "Fingerprint: ${DIM}${FINGERPRINT}${NC}"

    if [[ -n "$FINGERPRINT" ]]; then
        echo -e "\nDetalhes da chave:"
        gpg --list-keys --keyid-format LONG "$FINGERPRINT" 2>/dev/null
    fi
}

configure_clipboard_timeout() {
    echo -e "\nTimeout atual: ${BOLD}${CLIPBOARD_TIMEOUT}s${NC}"
    read -rp "Novo timeout em segundos (10-300, Enter para manter): " new_timeout

    [[ -z "$new_timeout" ]] && return

    if [[ "$new_timeout" =~ ^[0-9]+$ ]] && [[ "$new_timeout" -ge 10 ]] && [[ "$new_timeout" -le 300 ]]; then
        CLIPBOARD_TIMEOUT="$new_timeout"
        save_config_value "CLIPBOARD_TIMEOUT" "$CLIPBOARD_TIMEOUT"
        success_msg "Timeout alterado para ${CLIPBOARD_TIMEOUT}s."
    else
        error_msg "Valor inválido (10-300)."
    fi
}

configure_default_password_length() {
    echo -e "\nTamanho atual: ${BOLD}${DEFAULT_PASS_LENGTH}${NC}"
    read -rp "Novo tamanho padrão (8-128, Enter para manter): " new_len

    [[ -z "$new_len" ]] && return

    if [[ "$new_len" =~ ^[0-9]+$ ]] && [[ "$new_len" -ge 8 ]] && [[ "$new_len" -le 128 ]]; then
        DEFAULT_PASS_LENGTH="$new_len"
        save_config_value "DEFAULT_PASS_LENGTH" "$DEFAULT_PASS_LENGTH"
        success_msg "Tamanho alterado para ${DEFAULT_PASS_LENGTH}."
    else
        error_msg "Valor inválido (8-128)."
    fi
}

configure_log_level() {
    echo -e "\nNível atual: ${BOLD}${LOG_LEVEL}${NC}"
    echo "  1 - ERROR (apenas erros)"
    echo "  2 - WARN (erros + avisos)"
    echo "  3 - INFO (geral — padrão)"
    echo "  4 - DEBUG (depuração detalhada)"
    echo
    read -rp "Opção: " lvl_opt

    case "$lvl_opt" in
        1) LOG_LEVEL="ERROR" ;;
        2) LOG_LEVEL="WARN" ;;
        3) LOG_LEVEL="INFO" ;;
        4) LOG_LEVEL="DEBUG" ;;
        *) return ;;
    esac
    save_config_value "LOG_LEVEL" "$LOG_LEVEL"
    success_msg "Nível de log alterado para $LOG_LEVEL."
}

show_system_dirs() {
    echo -e "\n${CYAN}===== Diretórios do Sistema =====${NC}\n"
    echo -e "  Diretório de config:   $CONFIG_DIR"
    echo -e "  Arquivo de config:     $CONFIG_FILE"
    echo -e "  Cofre:                 $GPGFILE"
    echo -e "  Backups:               $BACKUP_DIR"
    echo -e "  Logs:                  $LOG_FILE"
    echo -e "  Lock:                  $LOCK_DIR"
    echo -e "  RAM (shm):             $TEMP_BASE"

    echo -e "\nPermissões:"
    [[ -d "$CONFIG_DIR" ]] && echo -e "  $CONFIG_DIR: $(stat -c '%a' "$CONFIG_DIR" 2>/dev/null)"
    [[ -f "$GPGFILE" ]] && echo -e "  $GPGFILE: $(stat -c '%a' "$GPGFILE" 2>/dev/null)"
    [[ -f "$CONFIG_FILE" ]] && echo -e "  $CONFIG_FILE: $(stat -c '%a' "$CONFIG_FILE" 2>/dev/null)"
    [[ -f "$LOG_FILE" ]] && echo -e "  $LOG_FILE: $(stat -c '%a' "$LOG_FILE" 2>/dev/null)"
    [[ -d "$BACKUP_DIR" ]] && echo -e "  $BACKUP_DIR: $(stat -c '%a' "$BACKUP_DIR" 2>/dev/null)"
}

#================================================================================
# CONFIGURAÇÃO — PARSER SEGURO (SEM source)
#================================================================================
init_config() {
    if [[ ! -d "$TEMP_BASE" ]]; then
        fatal_exit "O /dev/shm não está disponível. Por segurança, o programa não irá funcionar."
    fi

    if [[ ! -d "$CONFIG_DIR" ]]; then
        mkdir -p -m 700 "$CONFIG_DIR" || fatal_exit "Não foi possível criar diretório de configuração."
        log_info "Diretório de configuração criado: $CONFIG_DIR"
    fi

    if [[ ! -d "$BACKUP_DIR" ]]; then
        mkdir -p -m 700 "$BACKUP_DIR" || fatal_exit "Não foi possível criar diretório de backup."
        log_info "Diretório de backup criado: $BACKUP_DIR"
    fi

    # Criar config se não existir
    if [[ ! -f "$CONFIG_FILE" ]]; then
        cat <<'CFGEOF' > "$CONFIG_FILE"
# Configurações do GUI-GPG V4
# Este arquivo é tratado como DADOS, nunca como código Bash.
GPG_ID="Wellington"
CLIPBOARD_TIMEOUT=30
DEFAULT_PASS_LENGTH=20
DEFAULT_PASS_TYPE="strong"
LOG_LEVEL="INFO"
CFGEOF
        chmod 600 "$CONFIG_FILE"
    fi

    # Verificar permissões do arquivo de config
    local config_perms
    config_perms=$(stat -c '%a' "$CONFIG_FILE" 2>/dev/null)
    if [[ "$config_perms" != "600" ]]; then
        warning_msg "Permissão do arquivo de config incorreta ($config_perms). Corrigindo..."
        chmod 600 "$CONFIG_FILE"
    fi

    # Ler configuração COMO DADOS (sem source)
    read_config_value "GPG_ID" "ID"
    read_config_value "CLIPBOARD_TIMEOUT" "CLIPBOARD_TIMEOUT"
    read_config_value "DEFAULT_PASS_LENGTH" "DEFAULT_PASS_LENGTH"
    read_config_value "DEFAULT_PASS_TYPE" "DEFAULT_PASS_TYPE"
    read_config_value "LOG_LEVEL" "LOG_LEVEL"

    # Criar/verificar log
    touch "$LOG_FILE" 2>/dev/null || fatal_exit "Não foi possível criar arquivo de log."
    chmod 600 "$LOG_FILE"
    rotate_log
}

# Ler valor do config — extrai somente o valor de linhas no formato KEY="VALUE" ou KEY=VALUE
read_config_value() {
    local key="$1"
    local var_name="$2"

    local line
    line=$(grep -E "^${key}=" "$CONFIG_FILE" 2>/dev/null | head -1)

    if [[ -z "$line" ]]; then
        return 0
    fi

    # Extrair valor: remover KEY= e aspas
    local value="${line#*=}"
    value="${value%\"}"    # remove aspas final
    value="${value#\"}"    # remove aspas inicial

    # Validar: só permitir caracteres seguros (alphanumeric, ., _, -, /, @, etc.)
    if [[ "$value" =~ ^[a-zA-Z0-9._/@:\ -]+$ ]] || [[ -z "$value" ]]; then
        printf -v "$var_name" '%s' "$value"
    else
        warning_msg "Valor inválido para $key no arquivo de configuração. Usando padrão."
    fi
}

# Salvar valor no config
save_config_value() {
    local key="$1"
    local value="$2"

    if [[ -f "$CONFIG_FILE" ]]; then
        # Remover linha existente e adicionar nova
        grep -v "^${key}=" "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" 2>/dev/null
        echo "${key}=\"${value}\"" >> "${CONFIG_FILE}.tmp"
        mv -f "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
        chmod 600 "$CONFIG_FILE"
        return 0
    fi
    return 1
}

#================================================================================
# CRUD — ADICIONAR CREDENCIAL
#================================================================================
add_credential() {
    header_box "Adicionar Credencial"

    local servico usuario login senha

    read -rp "Nome do serviço (ex: 'GitHub', 'AWS - Root'): " servico
    if ! validate_input "$servico" || [[ -z "$servico" ]]; then
        error_msg "Nome do serviço inválido."
        return
    fi

    read -rp "Usuário (ex: 'Wellington', 'Admin'): " usuario
    if ! validate_input "$usuario"; then
        error_msg "Usuário inválido."
        return
    fi

    read -rp "Login (ex: 'well@example.com', 'admin_corp'): " login
    if ! validate_input "$login"; then
        error_msg "Login inválido."
        return
    fi

    echo -e "\nGerar senha automaticamente?"
    echo -e "  ${BOLD}1${NC} - Sim, senha forte (padrão)"
    echo -e "  ${BOLD}2${NC} - Sim, com opções personalizadas"
    echo -e "  ${BOLD}3${NC} - Não, digitar manualmente"
    echo
    read -rp "Opção: " pass_opt

    case "$pass_opt" in
        1)
            senha=$(generate_password "$DEFAULT_PASS_LENGTH" "strong")
            echo -e "\n${GREEN}✓ Senha gerada:${NC} $senha"
            ;;
        2)
            password_generator_menu
            echo
            read -rp "Cole a senha gerada aqui: " senha
            ;;
        3)
            read -rsp "Senha: " senha
            echo
            ;;
        *)
            senha=$(generate_password "$DEFAULT_PASS_LENGTH" "strong")
            echo -e "\n${GREEN}✓ Senha gerada:${NC} $senha"
            ;;
    esac

    if [[ -z "$senha" ]]; then
        error_msg "Senha não pode ser vazia."
        return
    fi

    create_temp_workspace || return

    # Backup obrigatório
    if ! mandatory_backup "add-credential"; then
        destroy_temp_workspace
        return
    fi

    # Carregar cofre atual
    local vault_json="${CURRENT_TEMP_DIR}/vault.json"
    load_vault "$GPGFILE" "$vault_json"

    # Verificar se precisa migrar
    if [[ "$VAULT_FORMAT" == "v3" ]]; then
        warning_msg "Formato V3 detectado. Migração necessária antes de adicionar."
        destroy_temp_workspace
        prompt_migration
        return
    fi

    # Verificar duplicata por serviço + login
    if has_jq; then
        local exists
        exists=$(jq -r --arg s "$servico" --arg l "$login" \
            '[.records[] | select(.service == $s and .login == $l)] | length' \
            "$vault_json" 2>/dev/null)
        if [[ "$exists" -gt 0 ]]; then
            warning_msg "Conta '$servico' com login '$login' já existe. Atualizando..."
            # Encontrar índice e atualizar
            local idx
            idx=$(jq -r --arg s "$servico" --arg l "$login" \
                '[.records[] | select(.service == $s and .login == $l)][0] | .service as $s | .login as $l | to_entries[] | select(.value.service == $s and .value.login == $l) | .key' \
                "$vault_json" 2>/dev/null)
            update_v4_record "$vault_json" "$idx" "$servico" "$usuario" "$login" "$senha"
        else
            add_v4_record "$vault_json" "$servico" "$usuario" "$login" "$senha"
        fi
    elif has_python3; then
        python3 -c "
import json
with open('$vault_json') as f:
    data = json.load(f)
# Verificar duplicata
for i, r in enumerate(data['records']):
    if r.get('service') == '$servico' and r.get('login') == '$login':
        data['records'][i] = {'service': '''$(echo "$servico" | sed "s/'/\\\\'/g")''', 'user': '''$(echo "$usuario" | sed "s/'/\\\\'/g")''', 'login': '''$(echo "$login" | sed "s/'/\\\\'/g")''', 'password': '''$(echo "$senha" | sed "s/'/\\\\'/g")'''}
        break
else:
    data['records'].append({'service': '''$(echo "$servico" | sed "s/'/\\\\'/g")''', 'user': '''$(echo "$usuario" | sed "s/'/\\\\'/g")''', 'login': '''$(echo "$login" | sed "s/'/\\\\'/g")''', 'password': '''$(echo "$senha" | sed "s/'/\\\\'/g")'''})
with open('$vault_json', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
" 2>/dev/null
    fi

    # Salvar
    local vault_data
    vault_data=$(cat "$vault_json")

    if save_vault "$vault_data" "$GPGFILE"; then
        success_msg "Credencial '$servico' (Usuário: $usuario | Login: $login) salva com sucesso."
    else
        error_msg "Falha ao salvar o cofre. Credencial NÃO foi salva."
    fi

    destroy_temp_workspace
}

#================================================================================
# CRUD — BUSCAR / RECUPERAR CREDENCIAL
#================================================================================
retrieve_credential() {
    header_box "Buscar / Recuperar Credencial"

    [[ ! -f "$GPGFILE" ]] && { warning_msg "Nenhum cofre encontrado."; return; }

    read -rp "Termo de busca (ex: 'GitHub', 'l:email', 's:serviço', 'u:nome'): " termo
    if ! validate_input "$termo"; then
        error_msg "Termo de busca inválido."
        return
    fi

    create_temp_workspace || return
    local vault_json="${CURRENT_TEMP_DIR}/vault.json"
    load_vault "$GPGFILE" "$vault_json"

    detect_and_normalize_vault "$vault_json"

    if [[ "$VAULT_FORMAT" == "v3" ]]; then
        warning_msg "Formato V3 legado detectado. Recomenda-se migrar para V4."
        # Parse V3 legado
        local search_term="${termo,,}"
        local modo="smart"
        local query="$termo"

        if [[ "$termo" =~ ^[sS]: ]]; then modo="servico"; query="${termo:2}"
        elif [[ "$termo" =~ ^[lL]: ]]; then modo="login"; query="${termo:2}"
        elif [[ "$termo" =~ ^[uU]: ]]; then modo="usuario"; query="${termo:2}"
        elif [[ "$termo" =~ ^[tT]: ]]; then modo="todos"; query="${termo:2}"
        fi

        query="${query#"${query%%[![:space:]]*}"}"
        query="${query%"${query##*[![:space:]]}"}"

        [[ -z "$query" ]] && { error_msg "Termo vazio."; destroy_temp_workspace; return; }

        local matches=()
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ -z "$line" ]] && continue
            local parsed
            parsed=$(parse_legacy_line "$line")
            local svc login usr pwd
            IFS=$'\t' read -r svc usr login pwd <<< "$parsed"

            local q_lower
            q_lower=$(echo "$query" | tr '[:upper:]' '[:lower:]')

            case "$modo" in
                servico)  [[ "$(echo "$svc" | tr '[:upper:]' '[:lower:]')" == *"$q_lower"* ]] && matches+=("$line") ;;
                login)    [[ "$(echo "$login" | tr '[:upper:]' '[:lower:]')" == *"$q_lower"* ]] && matches+=("$line") ;;
                usuario)  [[ "$(echo "$usr" | tr '[:upper:]' '[:lower:]')" == *"$q_lower"* ]] && matches+=("$line") ;;
                todos)    [[ "$(echo "$svc$login$usr" | tr '[:upper:]' '[:lower:]')" == *"$q_lower"* ]] && matches+=("$line") ;;
                smart)
                    if [[ "$(echo "$svc" | tr '[:upper:]' '[:lower:]')" == *"$q_lower"* ]]; then
                        matches+=("$line")
                    elif [[ "$(echo "$login" | tr '[:upper:]' '[:lower:]')" == *"$q_lower"* ]]; then
                        matches+=("$line")
                    elif [[ "$(echo "$usr" | tr '[:upper:]' '[:lower:]')" == *"$q_lower"* ]]; then
                        matches+=("$line")
                    fi
                    ;;
            esac
        done < "$vault_json"

        # Converter linhas V3 para formato tab para exibição
        local v4_matches=()
        for m in "${matches[@]}"; do
            local parsed
            parsed=$(parse_legacy_line "$m")
            v4_matches+=("$parsed")
        done
        display_and_select_matches_v4 "${v4_matches[@]}"
        destroy_temp_workspace
        return
    fi

    # V4 — Busca normal
    local modo="smart"
    local query="$termo"

    if [[ "$termo" =~ ^[sS]: ]]; then modo="servico"; query="${termo:2}"
    elif [[ "$termo" =~ ^[lL]: ]]; then modo="login"; query="${termo:2}"
    elif [[ "$termo" =~ ^[uU]: ]]; then modo="usuario"; query="${termo:2}"
    elif [[ "$termo" =~ ^[tT]: ]]; then modo="todos"; query="${termo:2}"
    fi

    query="${query#"${query%%[![:space:]]*}"}"
    query="${query%"${query##*[![:space:]]}"}"

    [[ -z "$query" ]] && { error_msg "Termo vazio."; destroy_temp_workspace; return; }

    local results
    results=$(search_v4_records "$vault_json" "$query" "$modo")

    if [[ -z "$results" ]]; then
        warning_msg "Nenhuma credencial encontrada para '$termo'."
        destroy_temp_workspace
        return
    fi

    # Processar resultados
    local matches=()
    while IFS=$'\t' read -r svc usr login pwd; do
        matches+=("${svc}	${usr}	${login}	${pwd}")
    done <<< "$results"

    display_and_select_matches_v4 "${matches[@]}"
    destroy_temp_workspace
}

display_and_select_matches_v4() {
    local matches=("$@")

    if [[ ${#matches[@]} -eq 0 ]]; then
        warning_msg "Nenhuma credencial encontrada."
        return
    fi

    if [[ ${#matches[@]} -eq 1 ]]; then
        show_credential_detail "${matches[0]}"
        return
    fi

    echo -e "\n${CYAN}Credenciais encontradas (${#matches[@]}):${NC}\n"
    local i=0
    for match in "${matches[@]}"; do
        ((i++))
        local svc usr login pwd
        IFS=$'\t' read -r svc usr login pwd <<< "$match"
        printf "  ${BOLD}%2d${NC}) %s [Usuário: %s | Login: ${CYAN}%s${NC}]\n" "$i" "$svc" "$usr" "$login"
    done

    echo
    read -rp "Escolha a credencial (1-${#matches[@]}): " choice

    if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 ]] || [[ "$choice" -gt ${#matches[@]} ]]; then
        warning_msg "Opção inválida."
        return
    fi

    show_credential_detail "${matches[$((choice-1))]}"
}

show_credential_detail() {
    local match="$1"
    local svc usr login pwd
    IFS=$'\t' read -r svc usr login pwd <<< "$match"

    echo -e "\n${CYAN}────────────────────────────────────${NC}"
    echo -e "${BOLD}Serviço:${NC} $svc"
    echo -e "${BOLD}Usuário:${NC} $usr"
    echo -e "${BOLD}Login:${NC}   $login"
    echo -e "${CYAN}────────────────────────────────────${NC}"

    # Nunca exibir senha automaticamente
    echo -e "\n  ${BOLD}1${NC} - Copiar senha para a área de transferência"
    echo -e "  ${BOLD}2${NC} - Exibir senha na tela"
    echo -e "  ${BOLD}0${NC} - Cancelar"
    echo
    read -rp "Opção: " detail_opt

    case "$detail_opt" in
        1)
            if has_clipboard; then
                copy_to_clipboard "$pwd"
            else
                warning_msg "Área de transferência não disponível."
                echo -e "  ${BOLD}Senha:${NC} $pwd"
            fi
            ;;
        2)
            echo -e "\n  ${BOLD}Senha:${NC} $pwd"
            ;;
        0|*)
            info_msg "Operação cancelada."
            ;;
    esac

    log_info "Credencial consultada: $svc (Usuário: $usr | Login: $login)"
}

#================================================================================
# CRUD — LISTAR SERVIÇOS
#================================================================================
list_credentials() {
    header_box "Serviços Registrados"

    [[ ! -f "$GPGFILE" ]] && { warning_msg "Nenhum cofre encontrado."; return; }

    create_temp_workspace || return
    local vault_json="${CURRENT_TEMP_DIR}/vault.json"
    load_vault "$GPGFILE" "$vault_json"

    detect_and_normalize_vault "$vault_json"

    if [[ "$VAULT_FORMAT" == "v3" ]]; then
        # Listar V3
        local count=0
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ -z "$line" ]] && continue
            local parsed
            parsed=$(parse_legacy_line "$line")
            local svc usr login pwd
            IFS=$'\t' read -r svc usr login pwd <<< "$parsed"
            ((count++))
            printf "  ${BOLD}%2d${NC}) %s\n" "$count" "$svc"
        done < "$vault_json"

        if [[ $count -eq 0 ]]; then
            warning_msg "Nenhum serviço cadastrado."
        else
            info_msg "Total: $count serviços"
        fi
    else
        # Listar V4
        local count
        count=$(count_v4_records "$vault_json")

        if [[ "$count" -eq 0 ]]; then
            warning_msg "Nenhum serviço cadastrado."
            destroy_temp_workspace
            return
        fi

        echo -e "  ${BOLD}#${NC}  Serviço"
        echo -e "  ${DIM}─────────────────────────────${NC}"

        local i=0
        if has_jq; then
            jq -r '.records[] | .service' "$vault_json" 2>/dev/null | while IFS= read -r svc; do
                ((i++))
                printf "  ${BOLD}%2d${NC}) %s\n" "$i" "$svc"
            done
        elif has_python3; then
            python3 -c "
import json
with open('$vault_json') as f:
    data = json.load(f)
for i, r in enumerate(data.get('records', []), 1):
    print(f'  {i:2d}) {r.get(\"service\", \"\")}')
" 2>/dev/null
        fi

        echo
        info_msg "Total: $count serviços"
    fi

    destroy_temp_workspace
}

#================================================================================
# CRUD — ALTERAR CREDENCIAL
#================================================================================
update_credential() {
    header_box "Alterar Credencial"

    [[ ! -f "$GPGFILE" ]] && { warning_msg "Nenhum cofre encontrado."; return; }

    read -rp "Termo de busca da conta a alterar: " termo
    if ! validate_input "$termo"; then
        error_msg "Termo de busca inválido."
        return
    fi

    create_temp_workspace || return
    local vault_json="${CURRENT_TEMP_DIR}/vault.json"
    load_vault "$GPGFILE" "$vault_json"

    detect_and_normalize_vault "$vault_json"

    if [[ "$VAULT_FORMAT" == "v3" ]]; then
        warning_msg "Formato V3 detectado. Recomenda-se migrar para V4."
        destroy_temp_workspace
        prompt_migration
        return
    fi

    # Buscar
    local modo="smart"
    local query="$termo"
    if [[ "$termo" =~ ^[sS]: ]]; then modo="servico"; query="${termo:2}"
    elif [[ "$termo" =~ ^[lL]: ]]; then modo="login"; query="${termo:2}"
    elif [[ "$termo" =~ ^[uU]: ]]; then modo="usuario"; query="${termo:2}"
    elif [[ "$termo" =~ ^[tT]: ]]; then modo="todos"; query="${termo:2}"
    fi

    query="${query#"${query%%[![:space:]]*}"}"
    query="${query%"${query##*[![:space:]]}"}"

    local results
    results=$(search_v4_records "$vault_json" "$query" "$modo")

    if [[ -z "$results" ]]; then
        warning_msg "Nenhuma credencial encontrada para '$termo'."
        destroy_temp_workspace
        return
    fi

    local matches=()
    while IFS=$'\t' read -r svc usr login pwd; do
        matches+=("${svc}	${usr}	${login}	${pwd}")
    done <<< "$results"

    # Selecionar
    local selected=""
    if [[ ${#matches[@]} -eq 1 ]]; then
        selected="${matches[0]}"
    else
        echo -e "\n${CYAN}Credenciais encontradas (${#matches[@]}):${NC}\n"
        local i=0
        for match in "${matches[@]}"; do
            ((i++))
            local svc usr login pwd
            IFS=$'\t' read -r svc usr login pwd <<< "$match"
            printf "  ${BOLD}%2d${NC}) %s [Usuário: %s | Login: ${CYAN}%s${NC}]\n" "$i" "$svc" "$usr" "$login"
        done
        echo
        read -rp "Escolha a credencial a alterar (1-${#matches[@]}): " choice
        if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 ]] || [[ "$choice" -gt ${#matches[@]} ]]; then
            warning_msg "Opção inválida."
            destroy_temp_workspace
            return
        fi
        selected="${matches[$((choice-1))]}"
    fi

    local svc_atual usr_atual login_atual pwd_atual
    IFS=$'\t' read -r svc_atual usr_atual login_atual pwd_atual <<< "$selected"

    echo -e "\n${CYAN}Valores atuais para '$svc_atual':${NC}"
    echo -e "  Usuário: $usr_atual"
    echo -e "  Login:   $login_atual"
    echo -e "  Senha:   ••••••••••••"
    echo

    local novo_usr novo_login nova_senha
    read -rp "Novo usuário (Enter para manter '$usr_atual'): " novo_usr
    novo_usr=${novo_usr:-$usr_atual}

    read -rp "Novo login (Enter para manter '$login_atual'): " novo_login
    novo_login=${novo_login:-$login_atual}

    echo -e "\nNova senha:"
    echo -e "  ${BOLD}1${NC} - Manter senha atual"
    echo -e "  ${BOLD}2${NC} - Gerar nova senha forte"
    echo -e "  ${BOLD}3${NC} - Gerar com opções personalizadas"
    echo -e "  ${BOLD}4${NC} - Digitar nova senha"
    echo
    read -rp "Opção: " pass_opt

    case "$pass_opt" in
        1) nova_senha="$pwd_atual" ;;
        2) nova_senha=$(generate_password "$DEFAULT_PASS_LENGTH" "strong")
           echo -e "\n${GREEN}✓ Nova senha gerada:${NC} $nova_senha"
           ;;
        3) password_generator_menu
           echo
           read -rp "Cole a senha gerada aqui: " nova_senha
           ;;
        4) read -rsp "Nova senha: " nova_senha; echo ;;
        *) nova_senha="$pwd_atual" ;;
    esac

    if [[ -z "$nova_senha" ]]; then
        error_msg "Senha não pode ser vazia."
        destroy_temp_workspace
        return
    fi

    # Backup obrigatório
    if ! mandatory_backup "update-credential"; then
        destroy_temp_workspace
        return
    fi

    # Encontrar índice e atualizar
    local idx
    if has_jq; then
        idx=$(jq -r --arg s "$svc_atual" --arg l "$login_atual" \
            'to_entries[] | select(.value.service == $s and .value.login == $l) | .key' \
            "$vault_json" 2>/dev/null | head -1)
    elif has_python3; then
        idx=$(python3 -c "
import json
with open('$vault_json') as f:
    data = json.load(f)
for i, r in enumerate(data['records']):
    if r.get('service') == '$svc_atual' and r.get('login') == '$login_atual':
        print(i)
        break
" 2>/dev/null)
    fi

    if [[ -z "$idx" ]]; then
        error_msg "Não foi possível localizar o registro."
        destroy_temp_workspace
        return
    fi

    if update_v4_record "$vault_json" "$idx" "$svc_atual" "$novo_usr" "$novo_login" "$nova_senha"; then
        local vault_data
        vault_data=$(cat "$vault_json")

        if save_vault "$vault_data" "$GPGFILE"; then
            success_msg "Credencial '$svc_atual' atualizada com sucesso."
        else
            error_msg "Falha ao salvar. Credencial NÃO foi alterada."
        fi
    else
        error_msg "Falha ao atualizar o registro."
    fi

    destroy_temp_workspace
}

#================================================================================
# CRUD — EXCLUIR CREDENCIAL
#================================================================================
delete_credential() {
    header_box "Excluir Credencial"

    [[ ! -f "$GPGFILE" ]] && { warning_msg "Nenhum cofre encontrado."; return; }

    read -rp "Termo de busca da conta a excluir: " termo
    if ! validate_input "$termo"; then
        error_msg "Termo de busca inválido."
        return
    fi

    create_temp_workspace || return
    local vault_json="${CURRENT_TEMP_DIR}/vault.json"
    load_vault "$GPGFILE" "$vault_json"

    detect_and_normalize_vault "$vault_json"

    if [[ "$VAULT_FORMAT" == "v3" ]]; then
        warning_msg "Formato V3 detectado. Recomenda-se migrar para V4."
        destroy_temp_workspace
        prompt_migration
        return
    fi

    # Buscar
    local modo="smart"
    local query="$termo"
    if [[ "$termo" =~ ^[sS]: ]]; then modo="servico"; query="${termo:2}"
    elif [[ "$termo" =~ ^[lL]: ]]; then modo="login"; query="${termo:2}"
    elif [[ "$termo" =~ ^[uU]: ]]; then modo="usuario"; query="${termo:2}"
    elif [[ "$termo" =~ ^[tT]: ]]; then modo="todos"; query="${termo:2}"
    fi

    query="${query#"${query%%[![:space:]]*}"}"
    query="${query%"${query##*[![:space:]]}"}"

    local results
    results=$(search_v4_records "$vault_json" "$query" "$modo")

    if [[ -z "$results" ]]; then
        warning_msg "Nenhuma credencial encontrada para '$termo'."
        destroy_temp_workspace
        return
    fi

    local matches=()
    while IFS=$'\t' read -r svc usr login pwd; do
        matches+=("${svc}	${usr}	${login}	${pwd}")
    done <<< "$results"

    local selected=""
    if [[ ${#matches[@]} -eq 1 ]]; then
        selected="${matches[0]}"
    else
        echo -e "\n${CYAN}Credenciais encontradas (${#matches[@]}):${NC}\n"
        local i=0
        for match in "${matches[@]}"; do
            ((i++))
            local svc usr login pwd
            IFS=$'\t' read -r svc usr login pwd <<< "$match"
            printf "  ${BOLD}%2d${NC}) %s [Usuário: %s | Login: ${CYAN}%s${NC}]\n" "$i" "$svc" "$usr" "$login"
        done
        echo
        read -rp "Escolha a credencial a excluir (1-${#matches[@]}): " choice
        if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 ]] || [[ "$choice" -gt ${#matches[@]} ]]; then
            warning_msg "Opção inválida."
            destroy_temp_workspace
            return
        fi
        selected="${matches[$((choice-1))]}"
    fi

    local svc_del usr_del login_del pwd_del
    IFS=$'\t' read -r svc_del usr_del login_del pwd_del <<< "$selected"

    echo -e "\n${RED}${BOLD}ATENÇÃO${NC}"
    echo -e "Você está prestes a excluir:"
    echo -e "\n  Serviço: ${BOLD}$svc_del${NC}"
    echo -e "  Usuário: $usr_del"
    echo -e "  Login:   $login_del"
    echo -e "\n${RED}Essa operação não pode ser desfeita diretamente.${NC}"
    echo
    read -rp "Digite EXCLUIR para confirmar: " confirm

    if [[ "$confirm" != "EXCLUIR" ]]; then
        info_msg "Operação cancelada."
        destroy_temp_workspace
        return
    fi

    # Backup obrigatório
    if ! mandatory_backup "delete-credential"; then
        destroy_temp_workspace
        return
    fi

    # Encontrar índice e remover
    local idx
    if has_jq; then
        idx=$(jq -r --arg s "$svc_del" --arg l "$login_del" \
            'to_entries[] | select(.value.service == $s and .value.login == $l) | .key' \
            "$vault_json" 2>/dev/null | head -1)
    elif has_python3; then
        idx=$(python3 -c "
import json
with open('$vault_json') as f:
    data = json.load(f)
for i, r in enumerate(data['records']):
    if r.get('service') == '$svc_del' and r.get('login') == '$login_del':
        print(i)
        break
" 2>/dev/null)
    fi

    if [[ -z "$idx" ]]; then
        error_msg "Não foi possível localizar o registro para exclusão."
        destroy_temp_workspace
        return
    fi

    if remove_v4_record "$vault_json" "$idx"; then
        local vault_data
        vault_data=$(cat "$vault_json")

        if save_vault "$vault_data" "$GPGFILE"; then
            success_msg "Conta '$svc_del' (Usuário: $usr_del | Login: $login_del) excluída com sucesso."
        else
            error_msg "Falha ao salvar o cofre após exclusão."
        fi
    else
        error_msg "Falha ao excluir o registro."
    fi

    destroy_temp_workspace
}

#================================================================================
# MIGRAÇÃO — PROMPT
#================================================================================
prompt_migration() {
    echo -e "\n${YELLOW}Formato legado V3 detectado.${NC}"
    echo -e "É necessário migrar o cofre para o formato V4."
    echo
    echo -e "  ${BOLD}1${NC} - Fazer migração"
    echo -e "  ${BOLD}2${NC} - Não migrar agora"
    echo -e "  ${BOLD}0${NC} - Cancelar"
    echo
    read -rp "Opção: " mig_opt

    case "$mig_opt" in
        1) migrate_vault ;;
        0|2) info_msg "Migração adiada." ;;
        *) warning_msg "Opção inválida." ;;
    esac
}

migrate_vault() {
    header_box "Migração V3 → V4"

    [[ ! -f "$GPGFILE" ]] && { warning_msg "Nenhum cofre V3 encontrado para migrar."; return; }

    create_temp_workspace || return

    local v3_txt="${CURRENT_TEMP_DIR}/v3_data.txt"
    local v4_json="${CURRENT_TEMP_DIR}/v4_data.json"

    echo -e "${BLUE}Passo 1/7: Descriptografando cofre V3...${NC}"
    if ! decrypt_vault "$GPGFILE" "$v3_txt"; then
        error_msg "Falha na descriptografia do cofre V3."
        destroy_temp_workspace
        return
    fi

    echo -e "${BLUE}Passo 2/7: Backup obrigatório...${NC}"
    # Backup já existe do decrypt_vault anterior
    if ! mandatory_backup "pre-migration"; then
        error_msg "Backup obrigatório falhou. Migração cancelada."
        destroy_temp_workspace
        return
    fi

    echo -e "${BLUE}Passo 3/7: Validando dados V3...${NC}"
    if [[ ! -s "$v3_txt" ]]; then
        echo '{"version":4,"records":[]}' > "$v4_json"
        VAULT_FORMAT="v4"
    else
        detect_and_normalize_vault "$v3_txt"
        if [[ "$VAULT_FORMAT" == "v4" ]]; then
            warning_msg "O cofre já parece ser formato V4."
            destroy_temp_workspace
            return
        fi
    fi

    echo -e "${BLUE}Passo 4/7: Convertendo registros...${NC}"
    if [[ ! -f "$v4_json" ]] || [[ ! -s "$v4_json" ]]; then
        migrate_v3_to_v4 "$v3_txt" > "$v4_json"
    fi

    if [[ ! -s "$v4_json" ]]; then
        echo '{"version":4,"records":[]}' > "$v4_json"
    fi

    echo -e "${BLUE}Passo 5/7: Validando formato V4...${NC}"
    if ! validate_v4_json "$v4_json"; then
        error_msg "Falha na validação do JSON V4 gerado."
        destroy_temp_workspace
        return
    fi

    local count
    count=$(count_v4_records "$v4_json")
    success_msg "$count registros convertidos com sucesso."

    echo -e "${BLUE}Passo 6/7: Criptografando cofre V4...${NC}"
    local vault_data
    vault_data=$(cat "$v4_json")

    # Salvar V3 antigo como backup adicional
    local v3_backup="${BACKUP_DIR}/vault.V3-LEGADO.$(date +%Y%m%d_%H%M%S).gpg"
    cp "$GPGFILE" "$v3_backup" 2>/dev/null && chmod 600 "$v3_backup"

    if save_vault "$vault_data" "$GPGFILE"; then
        echo -e "${BLUE}Passo 7/7: Validando cofre V4 final...${NC}"
        local final_check="${CURRENT_TEMP_DIR}/final_check_$$.txt"
        if decrypt_vault "$GPGFILE" "$final_check"; then
            if validate_v4_json "$final_check"; then
                local final_count
                final_count=$(count_v4_records "$final_check")
                rm -f "$final_check"
                success_msg "Migração concluída! $final_count registros migrados."
                success_msg "Cofre V3 preservado como backup: $(basename "$v3_backup")"
            else
                rm -f "$final_check"
                error_msg "Validação pós-migração falhou. Restaurando V3..."
                cp "$v3_backup" "$GPGFILE"
                chmod 600 "$GPGFILE"
            fi
        else
            rm -f "$final_check"
            error_msg "Verificação pós-migração falhou. Restaurando V3..."
            cp "$v3_backup" "$GPGFILE"
            chmod 600 "$GPGFILE"
        fi
    else
        error_msg "Falha na criptografia V4. Restaurando V3..."
        cp "$v3_backup" "$GPGFILE"
        chmod 600 "$GPGFILE"
    fi

    destroy_temp_workspace
}

#================================================================================
# RECRIPTOGRAFAR / TROCAR CHAVE GPG
#================================================================================
reencrypt_vault() {
    header_box "Recriptografar / Trocar Chave GPG"

    echo -e "Chave atual: ${BOLD}$ID${NC}"
    echo -e "Fingerprint: ${DIM}${FINGERPRINT}${NC}"
    echo
    echo -e "A operação irá:"
    echo -e "  1. Criar backup do cofre atual"
    echo -e "  2. Descriptografar com a chave atual"
    echo -e "  3. Criptografar com a nova chave"
    echo -e "  4. Validar o novo cofre"
    echo -e "  5. Substituir o cofre"
    echo

    read -rp "Nova chave GPG (Enter para recriptografar com a mesma chave): " new_key

    local target_key="$ID"
    if [[ -n "$new_key" ]]; then
        # Validar nova chave
        local old_id="$ID"
        ID="$new_key"
        if ! validate_gpg_key; then
            ID="$old_id"
            error_msg "Chave inválida. Operação cancelada."
            return
        fi
        target_key="$new_key"
    fi

    echo -e "\nChave de destino: ${BOLD}$target_key${NC}"
    echo
    read -rp "Confirmar recriptografia? (s/N): " confirm
    if [[ ! "$confirm" =~ ^[sS]$ ]]; then
        info_msg "Operação cancelada."
        return
    fi

    create_temp_workspace || return

    # Backup obrigatório
    if ! mandatory_backup "reencrypt"; then
        destroy_temp_workspace
        return
    fi

    # Descriptografar
    local work_file="${CURRENT_TEMP_DIR}/reencrypt_$$.txt"
    if ! decrypt_vault "$GPGFILE" "$work_file"; then
        error_msg "Falha na descriptografção do cofre."
        destroy_temp_workspace
        return
    fi

    # Criptografar com nova chave
    local old_recipient="$ID"
    ID="$target_key"

    local new_gpg="${CURRENT_TEMP_DIR}/reencrypted_$$.gpg"
    if gpg --batch --yes --encrypt --recipient "$ID" --output "$new_gpg" "$work_file" 2>/dev/null; then
        chmod 600 "$new_gpg"

        # Verificar se a descriptografacao funciona
        local verify="${CURRENT_TEMP_DIR}/verify_reenc_$$.txt"
        if gpg --batch --yes --decrypt "$new_gpg" > "$verify" 2>/dev/null; then
            local orig_size new_size
            orig_size=$(stat -c%s "$work_file" 2>/dev/null || echo 0)
            new_size=$(stat -c%s "$verify" 2>/dev/null || echo 0)
            rm -f "$verify"

            if [[ "$orig_size" -eq "$new_size" ]]; then
                # Substituir cofre
                mv -f "$new_gpg" "$GPGFILE"
                chmod 600 "$GPGFILE"
                success_msg "Cofre recriptografado com sucesso para a chave $ID."
            else
                error_msg "Verificacao de integridade falhou. Cofre original preservado."
                ID="$old_recipient"
            fi
        else
            rm -f "$verify" "$new_gpg"
            error_msg "Falha na verificacao pos-recriptografia. Cofre original preservado."
            ID="$old_recipient"
        fi
    else
        error_msg "Falha ao criptografar com a nova chave. Cofre original preservado."
        ID="$old_recipient"
    fi

    rm -f "$work_file"
    destroy_temp_workspace
}

#================================================================================
# EXPORTACAO / PDF
#================================================================================
export_inventory() {
    header_box "Exportar Inventario"

    echo -e "  ${BOLD}1${NC} - Exportar inventario SEM senhas (relatorio administrativo)"
    echo -e "  ${BOLD}2${NC} - Exportar credenciais COMPLETAS"
    echo -e "  ${BOLD}0${NC} - Cancelar"
    echo
    read -rp "Opcao: " exp_opt

    case "$exp_opt" in
        1) export_inventory_no_passwords ;;
        2) export_inventory_with_passwords ;;
        0) return ;;
        *) warning_msg "Opcao invalida." ;;
    esac
}

export_inventory_no_passwords() {
    [[ ! -f "$GPGFILE" ]] && { warning_msg "Nenhum cofre encontrado."; return; }

    create_temp_workspace || return
    local vault_json="${CURRENT_TEMP_DIR}/vault.json"
    load_vault "$GPGFILE" "$vault_json"

    detect_and_normalize_vault "$vault_json"

    local csv_file="${HOME}/inventario_patrimonio_$(date +%Y%m%d_%H%M%S).csv"

    echo '"Servico","Usuario","Login"' > "$csv_file"

    if [[ "$VAULT_FORMAT" == "v4" ]]; then
        if has_jq; then
            jq -r '.records[] | [.service, .user, .login] | @csv' "$vault_json" 2>/dev/null >> "$csv_file"
        elif has_python3; then
            python3 -c "
import json, csv, sys
with open('$vault_json') as f:
    data = json.load(f)
with open('$csv_file', 'a', newline='') as f:
    writer = csv.writer(f)
    for r in data.get('records', []):
        writer.writerow([r.get('service',''), r.get('user',''), r.get('login','')])
" 2>/dev/null
        fi
    else
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ -z "$line" ]] && continue
            local parsed
            parsed=$(parse_legacy_line "$line")
            local svc usr login pwd
            IFS=$'\t' read -r svc usr login pwd <<< "$parsed"
            printf '"%s","%s","%s"\n' "$svc" "$usr" "$login" >> "$csv_file"
        done < "$vault_json"
    fi

    destroy_temp_workspace
    success_msg "Inventario exportado: $csv_file"
}

export_inventory_with_passwords() {
    echo -e "\n${RED}${BOLD}ATENCAO${NC}"
    echo -e "Este procedimento criara uma copia DESCRIPTOGRAFADA"
    echo -e "das credenciais."
    echo -e "\nApos a exportacao, proteja o arquivo e delete-o quando terminar."
    echo
    read -rp "Digite EXPORTAR SENHAS para continuar: " confirm

    if [[ "$confirm" != "EXPORTAR SENHAS" ]]; then
        info_msg "Operacao cancelada."
        return
    fi

    [[ ! -f "$GPGFILE" ]] && { warning_msg "Nenhum cofre encontrado."; return; }

    create_temp_workspace || return
    local vault_json="${CURRENT_TEMP_DIR}/vault.json"
    load_vault "$GPGFILE" "$vault_json"

    detect_and_normalize_vault "$vault_json"

    local csv_file="${HOME}/credenciais_completas_$(date +%Y%m%d_%H%M%S).csv"

    echo '"Servico","Usuario","Login","Senha"' > "$csv_file"

    if [[ "$VAULT_FORMAT" == "v4" ]]; then
        if has_jq; then
            jq -r '.records[] | [.service, .user, .login, .password] | @csv' "$vault_json" 2>/dev/null >> "$csv_file"
        elif has_python3; then
            python3 -c "
import json, csv
with open('$vault_json') as f:
    data = json.load(f)
with open('$csv_file', 'a', newline='') as f:
    writer = csv.writer(f)
    for r in data.get('records', []):
        writer.writerow([r.get('service',''), r.get('user',''), r.get('login',''), r.get('password','')])
" 2>/dev/null
        fi
    else
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ -z "$line" ]] && continue
            local parsed
            parsed=$(parse_legacy_line "$line")
            local svc usr login pwd
            IFS=$'\t' read -r svc usr login pwd <<< "$parsed"
            printf '"%s","%s","%s","%s"\n' "$svc" "$usr" "$login" "$pwd" >> "$csv_file"
        done < "$vault_json"
    fi

    destroy_temp_workspace
    chmod 600 "$csv_file"
    success_msg "Credenciais exportadas: $csv_file"
    warning_msg "ATENCAO: Este arquivo contem senhas em texto plano! Delete quando terminar."
}

#================================================================================
# STATUS COMPLETO
#================================================================================
show_status() {
    header_box "Status do GUI-GPG"

    # Cofre
    if [[ -f "$GPGFILE" ]]; then
        local size perms
        size=$(du -h "$GPGFILE" 2>/dev/null | awk '{print $1}')
        perms=$(stat -c '%a' "$GPGFILE" 2>/dev/null)
        echo -e "  Cofre:              ${GREEN}OK${NC}"
        echo -e "  Arquivo:            $GPGFILE"
        echo -e "  Tamanho:            $size"
        echo -e "  Permissao:          ${perms}"
    else
        echo -e "  Cofre:              ${YELLOW}Nao criado${NC}"
        echo -e "  Local esperado:     $GPGFILE"
    fi

    # Configuracao
    if [[ -f "$CONFIG_FILE" ]]; then
        local cperms
        cperms=$(stat -c '%a' "$CONFIG_FILE" 2>/dev/null)
        echo -e "  Configuracao:       ${GREEN}OK${NC} ($cperms)"
    else
        echo -e "  Configuracao:       ${YELLOW}Ausente${NC}"
    fi

    # Chave GPG
    if [[ -n "$FINGERPRINT" ]]; then
        echo -e "  Chave GPG:          ${GREEN}OK${NC}"
        echo -e "  Fingerprint:        ${DIM}${FINGERPRINT}${NC}"
    else
        echo -e "  Chave GPG:          ${RED}Nao validada${NC}"
    fi

    # /dev/shm
    if [[ -d "$TEMP_BASE" && -w "$TEMP_BASE" ]]; then
        echo -e "  /dev/shm:           ${GREEN}OK${NC}"
    else
        echo -e "  /dev/shm:           ${RED}Indisponivel${NC}"
    fi

    # Lock
    echo -e "  Lock:               $([ -d "$LOCK_DIR" ] && echo "${YELLOW}Ocupado${NC}" || echo "${GREEN}Livre${NC}")"

    # Backups
    local backup_count=0
    local last_backup="Nenhum"
    if [[ -d "$BACKUP_DIR" ]]; then
        backup_count=$(find "$BACKUP_DIR" -maxdepth 1 -name "vault.BKP.*.gpg" -type f 2>/dev/null | wc -l)
        last_backup=$(find "$BACKUP_DIR" -maxdepth 1 -name "vault.BKP.*.gpg" -type f -printf '%T@ %p\0' 2>/dev/null | sort -z -rn | head -z -1 | cut -z -d' ' -f2- | xargs -0 basename 2>/dev/null || echo "Nenhum")
    fi
    echo -e "  Backups:            $backup_count"
    echo -e "  Ultimo backup:      $last_backup"

    # Clipboard
    local clip_status="Nao disponivel"
    if command -v xclip &>/dev/null && [[ -n "${DISPLAY:-}" ]]; then
        clip_status="Ativo (xclip / X11)"
    elif command -v wl-copy &>/dev/null && [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        clip_status="Ativo (wl-clipboard / Wayland)"
    fi
    echo -e "  Clipboard:          $clip_status"

    # Versao
    echo -e "  Versao:             $VERSION"
    echo
}

#================================================================================
# AJUDA
#================================================================================
show_help() {
    header_box "Ajuda - GUI-GPG $VERSION"

    echo -e "${BOLD}DESCRICAO:${NC}"
    echo -e "  Gerenciador de credenciais criptografadas com GPG."
    echo -e "  Armazena senhas de forma segura using criptografia assimetrica."
    echo
    echo -e "${BOLD}COMO USAR:${NC}"
    echo -e "  Execute o script e interaja pelo menu:"
    echo -e "    ${BOLD}./gui-gpg-V4.sh${NC}"
    echo
    echo -e "${BOLD}ARGUMENTOS:${NC}"
    echo -e "  ${BOLD}--help${NC}         Exibe esta ajuda"
    echo -e "  ${BOLD}--version${NC}      Exibe a versao"
    echo -e "  ${BOLD}--status${NC}       Exibe o status do sistema"
    echo -e "  ${BOLD}--check${NC}        Verifica integridade do cofre"
    echo -e "  ${BOLD}--generate-password${NC}  Gera uma senha forte"
    echo
    echo -e "${BOLD}SEGURANCA:${NC}"
    echo -e "  - Dados temporarios ficam exclusivamente em /dev/shm (RAM)"
    echo -e "  - /tmp NUNCA e usado como fallback"
    echo -e "  - Configuracao tratada como dados, nunca executada"
    echo -e "  - Backup obrigatorio antes de qualquer operacao destrutiva"
    echo -e "  - Gravacao atiomica do cofre (arquivo .tmp + mv)"
    echo -e "  - Senha nunca exibida automaticamente"
    echo -e "  - Senha nunca gravada em logs"
    echo
    echo -e "${BOLD}BARRA DE BUSCA:${NC}"
    echo -e "  Use prefixos para busca especifica:"
    echo -e "    ${BOLD}s:termo${NC}   Busca por nome do servico"
    echo -e "    ${BOLD}l:termo${NC}   Busca por login/email"
    echo -e "    ${BOLD}u:termo${NC}   Busca por nome de usuario"
    echo -e "    ${BOLD}t:termo${NC}   Busca em todos os campos"
    echo -e "    ${BOLD}termo${NC}     Busca inteligente (prioriza servico)"
    echo
    echo -e "${BOLD}ARMAZENAMENTO:${NC}"
    echo -e "  Formato V4: JSON versionado"
    echo -e "  Local: $CONFIG_DIR"
    echo -e "  Chave GPG: $ID"
    echo
    echo -e "${BOLD}EXEMPLOS:${NC}"
    echo -e "  ./gui-gpg-V4.sh --status"
    echo -e "  ./gui-gpg-V4.sh --check"
    echo -e "  ./gui-gpg-V4.sh --generate-password"
}

#================================================================================
# MENU PRINCIPAL
#================================================================================
main_menu() {
    while true; do
        echo -e "\n${CYAN}============================================================================${NC}"
        echo -e "${CYAN}*${NC}                      ${BOLD}GUI-GPG v${VERSION}${NC}                                ${CYAN}*${NC}"
        echo -e "${CYAN}*${NC}              ${BOLD}Gerenciador de Credenciais Criptografadas${NC}                   ${CYAN}*${NC}"
        echo -e "${CYAN}============================================================================${NC}\n"

        echo -e "${BOLD}GERENCIAMENTO${NC}"
        echo -e "  ${BOLD}1${NC}  - Adicionar Credencial"
        echo -e "  ${BOLD}2${NC}  - Buscar / Recuperar Credencial"
        echo -e "  ${BOLD}3${NC}  - Listar Servicos"
        echo -e "  ${BOLD}4${NC}  - Alterar Credencial"
        echo -e "  ${BOLD}5${NC}  - Excluir Credencial"
        echo
        echo -e "${BOLD}COFRE${NC}"
        echo -e "  ${BOLD}6${NC}  - Status / Integridade"
        echo -e "  ${BOLD}7${NC}  - Gerenciar Backups"
        echo -e "  ${BOLD}8${NC}  - Configuracoes"
        echo -e "  ${BOLD}9${NC}  - Recriptografar Cofre"
        echo
        echo -e "${BOLD}FERRAMENTAS${NC}"
        echo -e "  ${BOLD}10${NC} - Gerar Senha"
        echo -e "  ${BOLD}11${NC} - Exportar / PDF"
        echo
        echo -e "  ${BOLD}0${NC}  - Sair\n"

        read -rp "Opcao: " opcao

        case "$opcao" in
            1) add_credential ;;
            2) retrieve_credential ;;
            3) list_credentials ;;
            4) update_credential ;;
            5) delete_credential ;;
            6)
                show_status
                create_temp_workspace || continue
                verify_vault
                destroy_temp_workspace
                ;;
            7) backup_menu ;;
            8) settings_menu ;;
            9) reencrypt_vault ;;
            10) password_generator_menu ;;
            11) export_inventory ;;
            0)
                success_msg "Encerrando. Ate logo!"
                cleanup
                exit 0
                ;;
            *)
                warning_msg "Opcao invalida! Escolha um numero de 0 a 11."
                ;;
        esac

        read -rp "Pressione [Enter] para continuar..."
    done
}

#================================================================================
# ARGUMENTOS DE LINHA DE COMANDO
#================================================================================
parse_args() {
    case "${1:-}" in
        --help|-h)
            show_help
            exit 0
            ;;
        --version|-v)
            echo "GUI-GPG $VERSION"
            exit 0
            ;;
        --status)
            init_config
            validate_gpg_key
            show_status
            exit 0
            ;;
        --check)
            init_config
            validate_gpg_key
            create_temp_workspace
            verify_vault
            destroy_temp_workspace
            exit 0
            ;;
        --generate-password|-g)
            init_config
            password_generator_menu
            exit 0
            ;;
        "")
            ;;
        *)
            echo "Argumento desconhecido: $1"
            echo "Use --help para ver as opcoes disponiveis."
            exit 1
            ;;
    esac
}

#================================================================================
# VERIFICACAO DE DEPENDENCIAS
#================================================================================
check_dependencies() {
    local missing=0
    for cmd in gpg mktemp awk grep find; do
        if ! command -v "$cmd" &>/dev/null; then
            fatal_exit "Comando obrigatorio nao encontrado: $cmd"
        fi
    done

    # jq ou python3 sao obrigatorios para V4
    if ! has_jq && ! has_python3; then
        fatal_exit "Necessario 'jq' ou 'python3' para processar formato V4.\nInstale um deles: sudo apt install jq   ou   sudo apt install python3"
    fi
}

#================================================================================
# INICIALIZACAO
#================================================================================
parse_args "$@"
init_config
check_dependencies
validate_gpg_key
main_menu