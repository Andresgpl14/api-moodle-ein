# API Moodle EIN

API Serverless sobre AWS Lambda para:
- validar avance de curso en Moodle
- matricular usuarios en cursos Moodle

## Stack

- Python `3.11`
- Serverless Framework `4`
- AWS Lambda
- API Gateway

## Instalacion local

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm install
```

## Configuracion de credenciales AWS

Solicitar al cliente las credenciales IAM de despliegue:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

Configurar el perfil local:

```bash
aws configure --profile ein-prd
```

Completar los valores solicitados por AWS CLI:

```text
AWS Access Key ID [None]: <AWS_ACCESS_KEY_ID>
AWS Secret Access Key [None]: <AWS_SECRET_ACCESS_KEY>
Default region name [None]: us-east-1
Default output format [None]: json
```

Validar que el perfil quedo operativo:

```bash
aws sts get-caller-identity --profile ein-prd
```

## Despliegue

### Despliegue a dev

```bash
AWS_PROFILE=ein-prd npx serverless deploy --stage dev --region us-east-1
```

### Despliegue a produccion

```bash
export AWS_PROFILE=ein-prd
npx serverless deploy --stage prd --region us-east-1
```

## Referencias utiles

- Nombre esperado de la funcion Lambda de validacion en produccion:

```text
api-moodle-ein-prd-validarcurso
```

- Archivo principal de configuracion Serverless:

```text
serverless.yml
```

## Notas

- No registrar credenciales AWS ni tokens en el repositorio.
- Si se usan credenciales temporales, tambien sera necesario `AWS_SESSION_TOKEN`.
- El perfil AWS usado en los comandos de despliegue es `ein-prd`.
