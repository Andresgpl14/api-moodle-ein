import os
import json
import requests
import traceback

def crear_usuario(event, context):
    respuesta_final = {}
    error_detectado = False  # Flag para controlar errores

    try:
        payload_entrada = json.loads(event['body'])
        print("--[AUDITORIA] Payload de entrada:", json.dumps(payload_entrada))

        usuarios = payload_entrada.get("users")
        if not isinstance(usuarios, list):
            respuesta_final = {
                "statusCode": 400,
                "body": json.dumps({"error": "Se esperaba una lista de usuarios en 'users'."})
            }
            error_detectado = True

        if not error_detectado:
            # ---------- 0. Obtener cursos ----------
            payload_cursos = {
                'wstoken': os.environ['MOODLE_WS_TOKEN'],
                'wsfunction': 'core_course_get_courses',
                'moodlewsrestformat': 'json'
            }

            response_cursos = requests.post(os.environ['MOODLE_WS_URL'], data=payload_cursos)
            response_cursos.raise_for_status()
            lista_cursos = response_cursos.json()
            curso_id_map = {c['shortname']: c['id'] for c in lista_cursos if 'shortname' in c}

            # ---------- 1. Crear usuarios ----------
            payload_creacion = {
                'wstoken': os.environ['MOODLE_WS_TOKEN'],
                'wsfunction': 'core_user_create_users',
                'moodlewsrestformat': 'json'
            }

            for i, user in enumerate(usuarios):
                campos_requeridos = ['username', 'password', 'firstname', 'lastname', 'email', 'dni', 'ruc']
                for campo in campos_requeridos:
                    if campo not in user:
                        respuesta_final = {
                            "statusCode": 400,
                            "body": json.dumps({
                                "error": f"Usuario {i}: Falta el campo obligatorio '{campo}'"
                            })
                        }
                        error_detectado = True
                        break

                payload_creacion[f'users[{i}][username]']   = user['username']
                payload_creacion[f'users[{i}][password]']   = user['password']
                payload_creacion[f'users[{i}][firstname]']  = user['firstname']
                payload_creacion[f'users[{i}][lastname]']   = user['lastname']
                payload_creacion[f'users[{i}][email]']      = user['email']
                payload_creacion[f'users[{i}][department]'] = user['dni']
                payload_creacion[f'users[{i}][city]']       = user['ruc']
                payload_creacion[f'users[{i}][auth]']       = 'manual'

                # Custom field
                if 'areaTrabajo' in user and user['areaTrabajo'] not in (None, ''):
                    payload_creacion[f'users[{i}][customfields][0][type]']  = 'AreaDeTrabajo'
                    payload_creacion[f'users[{i}][customfields][0][value]'] = user['areaTrabajo']

        if not error_detectado:
            print("--[AUDITORIA] Request de usuarios creados:", payload_creacion)
            response_creacion = requests.post(os.environ['MOODLE_WS_URL'], data=payload_creacion)
            response_creacion.raise_for_status()
            print("--[AUDITORIA] Respuesta de usuarios creados:", response_creacion.text)
            usuarios_creados = response_creacion.json()
            
            if isinstance(usuarios_creados, dict) and 'exception' in usuarios_creados:
                respuesta_final = {
                    "statusCode": 400,
                    "body": json.dumps({
                        "error": "Error desde Moodle en creación de usuarios",
                        "moodle_response": usuarios_creados
                    })
                }
                error_detectado = True

        if not error_detectado:
            user_by_username = {u['username']: u for u in usuarios}
            payload_matricula = {
                'wstoken': os.environ['MOODLE_WS_TOKEN'],
                'wsfunction': 'enrol_manual_enrol_users',
                'moodlewsrestformat': 'json'
            }

            index = 0
            matriculas_realizadas = []

            for u in usuarios_creados:
                username = u['username']
                userid = u['id']
                cursos_shortname = user_by_username[username].get('courses_shortname', [])

                for shortname in set(cursos_shortname):
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

        if not error_detectado and index > 0:
            print("--[AUDITORIA] Request de matricula:", payload_matricula)
            response_matricula = requests.post(os.environ['MOODLE_WS_URL'], data=payload_matricula)
            response_matricula.raise_for_status()
            print("--[AUDITORIA] Respuesta de matricula:", response_matricula.text)
            matriculas_resultado = response_matricula.json()

            if isinstance(matriculas_resultado, dict) and 'exception' in matriculas_resultado:
                respuesta_final = {
                    "statusCode": 400,
                    "body": json.dumps({
                        "error": "Error desde Moodle al matricular",
                        "moodle_response": matriculas_resultado
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
