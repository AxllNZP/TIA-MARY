# Pendientes de Negocio y Operacion — TIA MARY

Este documento consolida decisiones de negocio y pasos de configuracion
pendientes, detectados durante las Fases 0-3 de hardening del proyecto.
No son bugs de codigo — son decisiones que debe tomar quien vaya a operar
el asistente en un entorno real, o configuracion que debe completarse antes
de exponer el sistema fuera de desarrollo local.

---

## 1. Proveedor real de WhatsApp (PENDIENTE DE DECISION)

El proyecto aun NO tiene un proveedor de WhatsApp conectado. El endpoint
`/api/webhook` actualmente "simula" el webhook (ver docstring en
`src/api.py`) y esta protegido con un mecanismo de firma HMAC-SHA256
generico (`WEBHOOK_SECRET`), no con la verificacion nativa de ningun
proveedor.

**Decision requerida:** elegir entre Twilio o Meta (WhatsApp Cloud API)
antes de conectar un numero real.

| Aspecto | Twilio | Meta (WhatsApp Cloud API) |
|---|---|---|
| Costo | Cobra por mensaje + markup sobre tarifa de Meta | Tarifa directa de Meta, generalmente mas barata |
| Setup | Cuenta Twilio + numero de WhatsApp Business aprobado | Cuenta Meta Business + numero verificado, proceso de aprobacion propio |
| Header de firma | `X-Twilio-Signature` (HMAC-SHA1, firma URL+params) | `X-Hub-Signature-256` (HMAC-SHA256, firma body crudo) |
| Formato de payload | `application/x-www-form-urlencoded` | JSON anidado (`entry[].changes[].value.messages[]`) |

**Impacto tecnico de la decision:** integrar cualquiera de los dos requiere
reescribir el parsing de `webhook()` en `src/api.py` (no solo la
verificacion de firma) — el formato del payload