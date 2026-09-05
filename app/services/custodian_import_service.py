"""
Serviço de importação em massa de Colaboradores (Custodiantes) via CSV.

Colunas esperadas (mínimo: matricula, nome, email, cargo, setor):
  - matricula  (obrigatório) → registration_code
  - nome       (obrigatório) → name
  - email      (obrigatório) → email
  - cargo      (obrigatório) → role
  - setor      (obrigatório) → department
  - cpf        (opcional)    → cpf
  - ativo      (opcional)    → is_active (sim/não, true/false, 1/0, ativo/inativo)

O CSV pode conter colunas adicionais — elas são ignoradas.
A separação pode ser ; (padrão BR) ou , — detectado automaticamente.
"""

import csv
import io
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.custodian import Custodian

# Mapeamento de nomes alternativos de colunas → campo canônico
COLUMN_ALIASES = {
    # matricula
    "matricula": "registration_code",
    "matrícula": "registration_code",
    "registration_code": "registration_code",
    "registration": "registration_code",
    "registro": "registration_code",
    "codigo_funcional": "registration_code",
    "código_funcional": "registration_code",
    "cod_funcional": "registration_code",
    "mat": "registration_code",
    "mat_funcional": "registration_code",
    # nome
    "nome": "name",
    "name": "name",
    "nome_completo": "name",
    "nome_completo_do_colaborador": "name",
    "colaborador": "name",
    "funcionario": "name",
    "funcionário": "name",
    # email
    "email": "email",
    "e_mail": "email",
    "e-mail": "email",
    "email_corporativo": "email",
    "e_mail_corporativo": "email",
    "e-mail_corporativo": "email",
    "correio_eletronico": "email",
    "correio_eletrônico": "email",
    # cpf
    "cpf": "cpf",
    "documento": "cpf",
    # cargo
    "cargo": "role",
    "role": "role",
    "funcao": "role",
    "função": "role",
    "cargo_funcao": "role",
    "cargo_função": "role",
    "ocupacao": "role",
    "ocupação": "role",
    # setor
    "setor": "department",
    "department": "department",
    "departamento": "department",
    "area": "department",
    "área": "department",
    "divisao": "department",
    "divisão": "department",
    "unidade": "department",
    # ativo
    "ativo": "is_active",
    "ativa": "is_active",
    "is_active": "is_active",
    "situacao": "is_active",
    "situação": "is_active",
    "status": "is_active",
}

_TRUE_VALUES = {"sim", "s", "yes", "y", "true", "t", "1", "ativo", "ativa"}
_FALSE_VALUES = {"nao", "não", "n", "no", "false", "f", "0", "inativo", "inativa"}


def _detect_delimiter(content: str) -> str:
    """Detecta o delimitador do CSV (pode ser ; ou ,)."""
    first_lines = content.split("\n")[:5]
    semicolons = sum(line.count(";") for line in first_lines)
    commas = sum(line.count(",") for line in first_lines)
    if semicolons > commas:
        return ";"
    return ","


def _strip_accents(key: str) -> str:
    """Remove acentos de um texto simples (sem dependências externas)."""
    replacements = {
        "ç": "c", "á": "a", "à": "a", "ã": "a", "â": "a", "ä": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "õ": "o", "ô": "o", "ö": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u",
        "ñ": "n",
    }
    return "".join(replacements.get(ch, ch) for ch in key)


def _normalize_column_name(raw: str) -> str:
    """Normaliza o nome de uma coluna do cabeçalho para o campo canônico."""
    key = raw.strip().lower().replace(" ", "_")
    key = key.replace("-", "_")
    if key in COLUMN_ALIASES:
        return COLUMN_ALIASES[key]
    # Tenta novamente sem acentos
    key_no_accent = _strip_accents(key)
    if key_no_accent in COLUMN_ALIASES:
        return COLUMN_ALIASES[key_no_accent]
    return key_no_accent


def _normalize_registration_code(value: str) -> str:
    """Normaliza a matrícula: sem espaços e em maiúsculas (evita duplicidade)."""
    return value.strip().upper()


def _normalize_email(value: str) -> str:
    """Normaliza o e-mail: sem espaços e em minúsculas."""
    return value.strip().lower()


def _parse_bool(value: str) -> Optional[bool]:
    """Converte texto livre para booleano. Retorna None se vazio/inexistente."""
    key = value.strip().lower()
    if not key:
        return None
    if key in _TRUE_VALUES:
        return True
    if key in _FALSE_VALUES:
        return False
    return None


def _validate_row(row: Dict[str, str], row_num: int) -> List[str]:
    """Valida uma linha do CSV e retorna lista de erros (vazia = OK)."""
    errors = []
    if not row.get("registration_code", "").strip():
        errors.append(f"Linha {row_num}: matricula é obrigatória")
    if not row.get("name", "").strip():
        errors.append(f"Linha {row_num}: nome é obrigatório")
    if not row.get("email", "").strip():
        errors.append(f"Linha {row_num}: email é obrigatório")
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", row.get("email", "").strip()):
        errors.append(f"Linha {row_num}: email inválido ('{row.get('email', '').strip()}')")
    if not row.get("role", "").strip():
        errors.append(f"Linha {row_num}: cargo é obrigatório")
    if not row.get("department", "").strip():
        errors.append(f"Linha {row_num}: setor é obrigatório")

    active_raw = row.get("is_active", "").strip()
    if active_raw and _parse_bool(active_raw) is None:
        errors.append(
            f"Linha {row_num}: coluna 'ativo' deve ser sim/não, true/false, 1/0 ou ativo/inativo"
        )
    return errors


def parse_custodian_csv(content: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Faz o parse do conteúdo CSV de colaboradores e retorna (rows, errors).
    Cada row é um dict com chaves canônicas: registration_code, name, email,
    cpf, role, department e is_active.
    """
    delimiter = _detect_delimiter(content)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

    # Normaliza os nomes das colunas do cabeçalho
    fieldnames = reader.fieldnames or []
    normalized_fields = {f: _normalize_column_name(f) for f in fieldnames}

    rows = []
    errors = []

    for i, row in enumerate(reader, start=2):  # linha 1 = header
        normalized = {}
        for orig_key, value in row.items():
            norm_key = normalized_fields.get(orig_key, _normalize_column_name(orig_key))
            normalized[norm_key] = (value or "").strip()

        row_errors = _validate_row(normalized, i)
        errors.extend(row_errors)

        if not row_errors:
            rows.append(normalized)

    return rows, errors


def _find_by_registration_code(db: Session, code: str) -> Optional[Custodian]:
    code = _normalize_registration_code(code)
    return db.query(Custodian).filter(Custodian.registration_code == code).first()


def _find_by_email(db: Session, email: str) -> Optional[Custodian]:
    email = _normalize_email(email)
    return db.query(Custodian).filter(Custodian.email == email).first()


def preview_custodian_import(rows: List[Dict[str, str]], db: Session) -> Dict:
    """
    Gera uma pré-visualização da importação, verificando duplicatas
    por matrícula ou e-mail já cadastrados.
    Retorna dict com 'previews' (lista) e 'summary' (dict).
    """
    previews = []
    duplicates = 0

    for row in rows:
        reg_code = _normalize_registration_code(row.get("registration_code", ""))
        email = _normalize_email(row.get("email", ""))

        existing = _find_by_registration_code(db, reg_code) or _find_by_email(db, email)
        is_dup = existing is not None
        if is_dup:
            duplicates += 1

        previews.append({
            "registration_code": reg_code,
            "name": row.get("name", "").strip(),
            "role": row.get("role", "").strip(),
            "department": row.get("department", "").strip(),
            "email": email,
            "existing_custodian_id": existing.id if existing else None,
            "is_duplicate": is_dup,
        })

    return {
        "previews": previews,
        "total": len(rows),
        "duplicates": duplicates,
        "new_items": len(rows) - duplicates,
    }


def execute_custodian_import(
    rows: List[Dict[str, str]],
    db: Session,
    skip_duplicates: bool = True,
) -> Dict:
    """
    Executa a importação em massa de colaboradores.
    Retorna dict com 'imported', 'skipped', 'errors'.
    """
    imported = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows, start=2):
        try:
            reg_code = _normalize_registration_code(row.get("registration_code", ""))
            name = row.get("name", "").strip()
            email = _normalize_email(row.get("email", ""))
            cpf = row.get("cpf", "").strip() or None
            role = row.get("role", "").strip()
            department = row.get("department", "").strip()
            is_active = _parse_bool(row.get("is_active", ""))

            # Verifica duplicata por matrícula
            existing = _find_by_registration_code(db, reg_code)

            if existing and skip_duplicates:
                skipped += 1
                continue

            if existing and not skip_duplicates:
                # Atualiza o colaborador existente (mantém a matrícula original)
                if email != existing.email:
                    email_owner = _find_by_email(db, email)
                    if email_owner and email_owner.id != existing.id:
                        errors.append(
                            f"Linha {i}: e-mail '{email}' já cadastrado para a matrícula "
                            f"'{email_owner.registration_code}' — não é possível atualizar por matrícula diferente"
                        )
                        continue
                existing.name = name
                existing.email = email
                if cpf:
                    existing.cpf = cpf
                existing.role = role
                existing.department = department
                if is_active is not None:
                    existing.is_active = is_active
                db.flush()
                imported += 1
                continue

            # Matrícula nova: verifica se o e-mail já pertence a outro cadastro
            email_owner = _find_by_email(db, email)
            if email_owner:
                if skip_duplicates:
                    skipped += 1
                else:
                    errors.append(
                        f"Linha {i}: e-mail '{email}' já cadastrado para a matrícula "
                        f"'{email_owner.registration_code}' — não é possível atualizar por matrícula diferente"
                    )
                continue

            # Cria novo colaborador
            custodian = Custodian(
                registration_code=reg_code,
                name=name,
                email=email,
                cpf=cpf,
                role=role,
                department=department,
                is_active=True if is_active is None else is_active,
            )
            db.add(custodian)
            db.flush()
            imported += 1

        except Exception as e:
            errors.append(f"Linha {i}: {str(e)}")
            continue

    if errors:
        # Commita o que foi processado corretamente e reporta os erros parciais
        db.commit()
    else:
        db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_processed": imported + skipped + len(errors),
    }
