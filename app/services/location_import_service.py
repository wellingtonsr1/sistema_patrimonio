"""
Serviço de importação em massa de Locais (departamentos/áreas físicas) via CSV.

Colunas esperadas (obrigatórias: nome, filial, departamento):
  - nome       (obrigatório) → name
  - filial     (obrigatório) → branch
  - departamento (obrigatório) → department
  - predio     (opcional)    → building
  - andar      (opcional)    → floor
  - sala       (opcional)    → room
  - gestor     (opcional)    → manager_name
  - descricao  (opcional)    → description

O CSV pode conter colunas adicionais — elas são ignoradas.
A separação pode ser ; (padrão BR) ou , — detectada automaticamente.

Regras:
  - Um local é identificado pelo nome (campo único no modelo Location).
  - A importação é uma operação de criação: não modifica locais existentes.
  - Se o nome já existir, o registro é tratado como duplicata (skip ou erro).
  - Somente locais válidos (todos os campos obrigatórios presentes e nome
    não duplicado) são persistidos na transação final.
"""

import csv
import io
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.location import Location
from app.services.location_service import LocationService

COLUMN_ALIASES = {
    # nome
    "nome": "name",
    "name": "name",
    "identificacao": "name",
    "identificação": "name",
    "local": "name",
    "localizaçao": "name",
    "localização": "name",
    "descricao_local": "name",
    "descricao": "name",
    # filial
    "filial": "branch",
    "branch": "branch",
    "unidade": "branch",
    "empresa": "branch",
    "sede": "branch",
    # departamento
    "departamento": "department",
    "department": "department",
    "setor": "department",
    "area": "department",
    "área": "department",
    "divisao": "department",
    "divisão": "department",
    # predio
    "predio": "building",
    "prédio": "building",
    "predio_sala": "building",
    "predio": "building",
    "edificio": "building",
    "building": "building",
    # andar
    "andar": "floor",
    "floor": "floor",
    "piso": "floor",
    # sala
    "sala": "room",
    "room": "room",
    "comodo": "room",
    "comôdo": "room",
    # gestor
    "gestor": "manager_name",
    "gerente": "manager_name",
    "responsavel": "manager_name",
    "responsável": "manager_name",
    "manager": "manager_name",
    # descricao
    "descricao": "description",
    "descrição": "description",
    "observacoes": "description",
    "observações": "description",
    "obs": "description",
    "notas": "description",
    "notes": "description",
}


def _detect_delimiter(content: str) -> str:
    first_lines = content.splitlines()[:5]
    semicolons = sum(line.count(";") for line in first_lines)
    commas = sum(line.count(",") for line in first_lines)
    return ";" if semicolons > commas else ","


def _normalize_column_name(raw: str) -> str:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if key in COLUMN_ALIASES:
        return COLUMN_ALIASES[key]
    no_accents = key.replace("á", "a").replace("ã", "a").replace("â", "a") \
                     .replace("é", "e").replace("ê", "e") \
                     .replace("í", "i") \
                     .replace("ó", "o").replace("ô", "o").replace("õ", "o") \
                     .replace("ú", "u") \
                     .replace("ç", "c")
    if no_accents in COLUMN_ALIASES:
        return COLUMN_ALIASES[no_accents]
    return no_accents


def _validate_row(row: Dict[str, str], row_num: int) -> List[str]:
    """Valida uma linha do CSV e retorna lista de erros (vazia = OK)."""
    errors = []
    if not row.get("name", "").strip():
        errors.append(f"Linha {row_num}: nome é obrigatório")
    if not row.get("branch", "").strip():
        errors.append(f"Linha {row_num}: filial é obrigatória")
    if not row.get("department", "").strip():
        errors.append(f"Linha {row_num}: departamento é obrigatório")
    return errors


def parse_locations_csv(content: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """Faz o parse do conteúdo CSV e retorna (rows, errors).
    Cada row é um dict com chaves canônicas: name, branch, department,
    building, floor, room, manager_name, description.

    Validação leve com LOWER PARTE TRATADA AQUI:
      - nome é normalizado para minúsculas e espaços em branco removidos;
      - filial e departamento são normalizados para maiúsculas e espaços em
        branco removidos.
    """
    delimiter = _detect_delimiter(content)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)

    fieldnames = reader.fieldnames or []
    normalized_fields = {f: _normalize_column_name(f) for f in fieldnames}

    rows = []
    errors = []

    rows = []
    errors = []

    for i, row in enumerate(reader, start=2):
        normalized: Dict[str, str] = {}
        for orig_key, value in row.items():
            norm_key = normalized_fields.get(orig_key, _normalize_column_name(orig_key))
            normalized[norm_key] = (value or "").strip()

        row_errors = _validate_row(normalized, i)
        errors.extend(row_errors)

        if not row_errors:
            rows.append(normalized)

    return rows, errors


def _find_existing_location(db: Session, name: str) -> Location:
    return LocationService.get_by_name(db, name)


def preview_locations_import(rows: List[Dict[str, str]], db: Session) -> Dict:
    """
    Gera uma pré-visualização da importação de locais, verificando duplicatas
    por nome já cadastrado.

    Retorna dict com 'previews' (lista) e 'summary' (dict).
    """
    previews = []
    duplicates = 0

    for row in rows:
        name = row.get("name", "").strip()
        existing = _find_existing_location(db, name)
        is_dup = existing is not None
        if is_dup:
            duplicates += 1

        previews.append({
            "name": name,
            "branch": row.get("branch", "").strip(),
            "department": row.get("department", "").strip(),
            "building": row.get("building", "").strip() or None,
            "floor": row.get("floor", "").strip() or None,
            "room": row.get("room", "").strip() or None,
            "manager_name": row.get("manager_name", "").strip() or None,
            "description": row.get("description", "").strip() or None,
            "existing_location_id": existing.id if existing else None,
            "is_duplicate": is_dup,
        })

    return {
        "previews": previews,
        "total": len(rows),
        "duplicates": duplicates,
        "new_items": len(rows) - duplicates,
    }


def execute_locations_import(
    rows: List[Dict[str, str]],
    db: Session,
    skip_duplicates: bool = True,
) -> Dict:
    """
    Executa a importação em massa de locais.
    Retorna dict com 'imported', 'skipped', 'errors'.
    """
    imported = 0
    skipped = 0
    errors: List[str] = []

    for i, row in enumerate(rows, start=2):
        try:
            name = row["name"].strip()
            branch = row["branch"].strip()
            department = row["department"].strip()
            building = row.get("building", "").strip() or None
            floor = row.get("floor", "").strip() or None
            room = row.get("room", "").strip() or None
            manager_name = row.get("manager_name", "").strip() or None
            description = row.get("description", "").strip() or None

            # Verifica duplicata por nome
            existing = _find_existing_location(db, name)
            if existing and skip_duplicates:
                skipped += 1
                continue

            if existing and not skip_duplicates:
                # Importação apenas cria novos locais; não sobrescreve existente.
                errors.append(
                    f"Linha {i}: já existe um local cadastrado com o nome '{existing.name}'"
                )
                continue

            # Cria novo local usando o modelo e o serviço existentes
            location = Location(
                name=name,
                branch=branch,
                department=department,
                building=building,
                floor=floor,
                room=room,
                manager_name=manager_name,
                description=description,
            )
            db.add(location)
            db.flush()
            imported += 1

        except Exception as exc:
            errors.append(f"Linha {i}: {str(exc)}")
            continue

    try:
        db.commit()
    except Exception:
        db.rollback()
        errors.append("Erro ao salvar os dados no banco.")

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_processed": imported + skipped + len(errors),
    }
