@startuml
skinparam shadowing false
skinparam componentStyle rectangle
skinparam wrapWidth 200
skinparam maxMessageSize 200

title AWS API hacia Moodle - Arquitectura de Alto Nivel

actor "Sistema de Validación" as cliente
rectangle "AWS" {
  [Amazon API Gateway\n(API REST con API Key)] as apigw
  [AWS Lambda\n(Lógica de Negocio)] as lambda
  [Amazon CloudWatch Logs\n(Registros y Métricas)] as cwl
}

cloud "Internet" as internet
rectangle "Moodle\n(Sistema Externo LMS)" as moodle

cliente -> apigw : Petición HTTPS\nHeader: x-api-key
apigw -> lambda : Invocación (integración proxy)
lambda --> cwl : Logs estructurados / métricas
lambda --> moodle : Llamada REST HTTPS\n(server.php: wstoken, wsfunction, params)
moodle --> lambda : Respuesta JSON
lambda -> apigw : statusCode + body
apigw -> cliente : Respuesta JSON

note right of apigw
  • API Key
end note

note bottom of lambda
  • Obtiene token de Moodle
  • Reintentos / Timeouts y manejo de errores
end note
@enduml