import os
import json
import requests
import traceback

TIMEOUT_SEC = 30


def moodle_call(session, wsfunction, data):
    payload = {
        'wstoken': os.environ['MOODLE_WS_TOKEN'],
        'wsfunction': wsfunction,
        'moodlewsrestformat': 'json',
        **data
    }
    response = session.post(os.environ['MOODLE_WS_URL'], data=payload, timeout=TIMEOUT_SEC)
    response.raise_for_status()
    resultado = response.json()
    if isinstance(resultado, dict) and 'exception' in resultado:
        raise RuntimeError(resultado)
    return resultado


def buscar_usuario_por_email(session, email):
    resultado = moodle_call(
        session,
        'core_user_get_users',
        {
            'criteria[0][key]': 'email',
            'criteria[0][value]': email
        }
    )
    usuarios = resultado.get('users', [])
    return usuarios[0] if usuarios else None


def crear_usuario(event, context):
    respuesta_final = {}
    error_detectado = False  # Flag para controlar errores

    try:
        payload_entrada = json.loads(event['body'])
        print("--[AUDITORIA] Payload de entrada:", json.dumps(payload_entrada))

        usuarios = payload_entrada.get("users")
        usuarios_creados = []
        usuarios_existentes = []
        usuarios_a_matricular = []
        matriculas_realizadas = []

        if not isinstance(usuarios, list):
            respuesta_final = {
                "statusCode": 400,
                "body": json.dumps({"error": "Se esperaba una lista de usuarios en 'users'."})
            }
            error_detectado = True

        if not error_detectado:
            with requests.Session() as session:
                # ---------- 0. Obtener cursos ----------
                lista_cursos = moodle_call(session, 'core_course_get_courses', {})
                curso_id_map = {c['shortname']: c['id'] for c in lista_cursos if 'shortname' in c}

                # ---------- 1. Identificar usuarios existentes y nuevos ----------
                usuarios_nuevos = []

                for i, user in enumerate(usuarios):
                    email = (user.get('email') or '').strip().lower()
                    cursos_shortname = user.get('courses_shortname')

                    if not email:
                        respuesta_final = {
                            "statusCode": 400,
                            "body": json.dumps({
                                "error": f"Usuario {i}: Falta el campo obligatorio 'email'"
                            })
                        }
                        error_detectado = True
                        break

                    if not isinstance(cursos_shortname, list) or not cursos_shortname:
                        respuesta_final = {
                            "statusCode": 400,
                            "body": json.dumps({
                                "error": f"Usuario {i}: Se esperaba una lista no vacia en 'courses_shortname'"
                            })
                        }
                        error_detectado = True
                        break

                    usuario_existente = buscar_usuario_por_email(session, email)

                    if usuario_existente:
                        usuarios_existentes.append(usuario_existente)
                        usuarios_a_matricular.append({
                            "userid": int(usuario_existente['id']),
                            "email": email,
                            "courses_shortname": cursos_shortname
                        })
                        continue

                    campos_requeridos = [
                        'username', 'password', 'firstname', 'lastname',
                        'email', 'dni', 'ruc'
                    ]
                    faltante = next((campo for campo in campos_requeridos if not user.get(campo)), None)
                    if faltante:
                        respuesta_final = {
                            "statusCode": 400,
                            "body": json.dumps({
                                "error": f"Usuario {i}: Falta el campo obligatorio '{faltante}' para crear el usuario"
                            })
                        }
                        error_detectado = True
                        break

                    usuarios_nuevos.append(user)

                # ---------- 2. Crear solo usuarios nuevos ----------
                if not error_detectado and usuarios_nuevos:
                    payload_creacion = {
                        'wstoken': os.environ['MOODLE_WS_TOKEN'],
                        'wsfunction': 'core_user_create_users',
                        'moodlewsrestformat': 'json'
                    }

                    for i, user in enumerate(usuarios_nuevos):
                        payload_creacion[f'users[{i}][username]'] = user['username']
                        payload_creacion[f'users[{i}][password]'] = user['password']
                        payload_creacion[f'users[{i}][firstname]'] = user['firstname']
                        payload_creacion[f'users[{i}][lastname]'] = user['lastname']
                        payload_creacion[f'users[{i}][email]'] = user['email']
                        payload_creacion[f'users[{i}][department]'] = user['dni']
                        payload_creacion[f'users[{i}][city]'] = user['ruc']
                        payload_creacion[f'users[{i}][auth]'] = 'manual'

                        if user.get('areaTrabajo') not in (None, ''):
                            payload_creacion[f'users[{i}][customfields][0][type]'] = 'AreaDeTrabajo'
                            payload_creacion[f'users[{i}][customfields][0][value]'] = user['areaTrabajo']

                    print("--[AUDITORIA] Request de usuarios creados:", payload_creacion)
                    try:
                        usuarios_creados = moodle_call(session, 'core_user_create_users', {
                            k: v for k, v in payload_creacion.items()
                            if k not in ('wstoken', 'wsfunction', 'moodlewsrestformat')
                        })
                    except RuntimeError as moodle_err:
                        respuesta_final = {
                            "statusCode": 400,
                            "body": json.dumps({
                                "error": "Error desde Moodle en creación de usuarios",
                                "moodle_response": moodle_err.args[0]
                            })
                        }
                        error_detectado = True

                    if not error_detectado:
                        print("--[AUDITORIA] Respuesta de usuarios creados:", json.dumps(usuarios_creados))
                        nuevos_por_username = {
                            user['username']: user for user in usuarios_nuevos
                        }
                        for creado in usuarios_creados:
                            username = creado.get('username')
                            cursos_shortname = nuevos_por_username[username].get('courses_shortname', [])
                            usuarios_a_matricular.append({
                                "userid": int(creado['id']),
                                "email": (nuevos_por_username[username].get('email') or '').strip().lower(),
                                "courses_shortname": cursos_shortname
                            })

                # ---------- 3. Matricular usuarios existentes y nuevos ----------
                if not error_detectado:
                    payload_matricula = {
                        'wstoken': os.environ['MOODLE_WS_TOKEN'],
                        'wsfunction': 'enrol_manual_enrol_users',
                        'moodlewsrestformat': 'json'
                    }
                    index = 0

                    for user in usuarios_a_matricular:
                        userid = user['userid']
                        for shortname in set(user.get('courses_shortname', [])):
                            courseid = curso_id_map.get(shortname)
                            if courseid is None:
                                respuesta_final = {
                                    "statusCode": 400,
                                    "body": json.dumps({
                                        "error": f"El curso '{shortname}' no fue encontrado en Moodle"
                                    })
                                }
                                error_detectado = True
                                break

                            payload_matricula[f'enrolments[{index}][roleid]'] = 5
                            payload_matricula[f'enrolments[{index}][userid]'] = userid
                            payload_matricula[f'enrolments[{index}][courseid]'] = courseid

                            matriculas_realizadas.append({
                                "userid": userid,
                                "courseid": courseid,
                                "course_shortname": shortname
                            })
                            index += 1

                        if error_detectado:
                            break

                if not error_detectado and matriculas_realizadas:
                    print("--[AUDITORIA] Request de matricula:", payload_matricula)
                    try:
                        matriculas_resultado = moodle_call(session, 'enrol_manual_enrol_users', {
                            k: v for k, v in payload_matricula.items()
                            if k not in ('wstoken', 'wsfunction', 'moodlewsrestformat')
                        })
                        print("--[AUDITORIA] Respuesta de matricula:", json.dumps(matriculas_resultado))
                    except RuntimeError as moodle_err:
                        respuesta_final = {
                            "statusCode": 400,
                            "body": json.dumps({
                                "error": "Error desde Moodle al matricular",
                                "moodle_response": moodle_err.args[0]
                            })
                        }
                        error_detectado = True

        # ---------- Respuesta final ----------
        if not error_detectado:
            respuesta_final = {
                "statusCode": 200,
                "body": json.dumps({
                    "success": True,
                    "idTransaccion": payload_entrada.get("idTransaccion"),
                    "usuarios_creados": usuarios_creados,
                    "usuarios_existentes": usuarios_existentes,
                    "matriculas": matriculas_realizadas
                })
            }

    except requests.exceptions.HTTPError as http_err:
        try:
            moodle_error = http_err.response.json()
        except ValueError:
            moodle_error = http_err.response.text

        respuesta_final = {
            "statusCode": http_err.response.status_code,
            "body": json.dumps({
                "error": str(http_err),
                "moodle_response": moodle_error
            })
        }

    except RuntimeError as moodle_err:
        respuesta_final = {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Error desde Moodle",
                "moodle_response": moodle_err.args[0]
            })
        }

    except Exception as e:
        traceback_str = traceback.format_exc()
        print("ERROR inesperado:", str(e))
        print("TRACEBACK:\n", traceback_str)
        respuesta_final = {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "trace": traceback_str
            })
        }

    print("--[AUDITORIA] Respuesta final:", json.dumps(respuesta_final))
    return respuesta_final
