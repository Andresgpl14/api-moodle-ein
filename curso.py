import os
import json
import traceback
import requests

MOODLE_URL = os.environ.get("MOODLE_WS_URL")
MOODLE_TOKEN = os.environ.get("MOODLE_WS_TOKEN")
TIMEOUT_SEC = 30

def resp(status, body_dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body_dict, ensure_ascii=False)
    }

def moodle_call(session: requests.Session, wsfunction: str, data: dict):
    payload = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": wsfunction,
        "moodlewsrestformat": "json",
        **data
    }
    r = session.post(MOODLE_URL, data=payload, timeout=TIMEOUT_SEC)
    r.raise_for_status()
    out = r.json()
    if isinstance(out, dict) and "exception" in out:
        # Ej: {"exception":"moodle_exception","errorcode":"someerror","message":"..."}
        raise RuntimeError(f"Moodle error [{out.get('errorcode')}]: {out.get('message')}")
    return out

def _get_user_id(session: requests.Session, username: str) -> int:
    out = moodle_call(
        session,
        "core_user_get_users",
        {
            "criteria[0][key]": "username",
            "criteria[0][value]": username
        }
    )
    users = out.get("users", [])
    if not users:
        raise ValueError(f"Usuario '{username}' no encontrado en Moodle.")
    return int(users[0]["id"])

def _get_course_id_by_shortname(session: requests.Session, shortname: str) -> int:
    out = moodle_call(
        session,
        "core_course_get_courses_by_field",
        {"field": "shortname", "value": shortname}
    )
    courses = out.get("courses", [])
    if not courses:
        raise ValueError(f"Curso con shortname '{shortname}' no encontrado en Moodle.")
    return int(courses[0]["id"])

def _get_completion_status(session: requests.Session, course_id: int, user_id: int) -> dict:
    return moodle_call(
        session,
        "core_completion_get_activities_completion_status",
        {"courseid": course_id, "userid": user_id}
    )

def _evaluate_result(statuses: list) -> tuple[bool, float]:
    """
    Evalúa la lista de estados.
    - Devuelve (completo, porcentaje)
      * completo: True si no hay ningún state=0
      * porcentaje: % de elementos con state en {1,2}
    """
    total = len(statuses)
    if total == 0:
        return False, 0.0

    completados = sum(1 for s in statuses if s.get("state") in (1, 2))
    porcentaje = int(round((completados / total) * 100, 0))

    has_zero = any(s.get("state") == 0 for s in statuses)
    return (not has_zero, porcentaje)

def validar(event, context):
    try:
        if not MOODLE_URL or not MOODLE_TOKEN:
            return resp(500, {"success": False, "error": "Config faltante: MOODLE_WS_URL / MOODLE_WS_TOKEN"})

        body = event.get("body")
        if body is None:
            return resp(400, {"success": False, "error": "Body requerido."})

        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                return resp(400, {"success": False, "error": "Body no es JSON válido."})

        nombre_usuario = (body.get("nombreUsuario") or "").strip()
        curso_corto = (body.get("cursoCorto") or "").strip()

        if not nombre_usuario or not curso_corto:
            return resp(400, {"success": False, "error": "Campos requeridos: nombreUsuario, cursoCorto."})

        with requests.Session() as session:
            user_id = _get_user_id(session, nombre_usuario)
            course_id = _get_course_id_by_shortname(session, curso_corto)

            comp = _get_completion_status(session, course_id, user_id)
            statuses = comp.get("statuses", [])
            detalle = [{"state": s.get("state"), "modname": s.get("modname")} for s in statuses]
            resultado,porcentaje = _evaluate_result(statuses)

            return resp(200, {
                "success": True,
                "data": {
                    "completado": resultado,
                    "porcentaje":porcentaje,
                    "detalle": detalle
                }
            })

    except requests.exceptions.HTTPError as http_err:
        content = None
        try:
            content = http_err.response.json()
        except Exception:
            content = http_err.response.text if hasattr(http_err, "response") and http_err.response is not None else str(http_err)
        return resp(
            http_err.response.status_code if getattr(http_err, "response", None) else 502,
            {
                "success": False,
                "error": "HTTPError al invocar Moodle",
                "detalle": str(http_err),
                "moodle_response": content
            }
        )

    except (ValueError, RuntimeError) as e:
        return resp(400, {"success": False, "error": str(e)})

    except Exception as e:
        return resp(500, {
            "success": False,
            "error": "Error inesperado",
            "detalle": str(e),
            "trace": traceback.format_exc()
        })
