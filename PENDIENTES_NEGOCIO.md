# Pendientes de Negocio y Operacion — TIA MARY

Este documento consolida decisiones de negocio y pasos de configuracion
pendientes, detectados durante las Fases 0-3 de hardening del proyecto.
No son bugs de codigo — son decisiones que debe tomar quien vaya a operar
el asistente en un entorno real, o configuracion que debe completarse antes
de exponer el sistema fuera de desarrollo local.

---

## 1. Proveedor real de WhatsApp (Meta implementado; Twilio pendiente de decision)

Meta (WhatsApp Cloud API) YA esta conectado e implementado: el endpoint
`/api/webhook-meta` verifica la firma HMAC-SHA256 nativa de Meta
(`X-Hub-Signature-256`) contra `WHATSAPP_APP_SECRET`, y envia respuestas
reales via Meta Graph API (ver `_enviar_mensaje_whatsapp_meta` en
`src/api.py`). Segun el README, fue probado end-to-end con trafico real.

El endpoint separado `/api/webhook-twilio` sigue siendo solo un sandbox de
prueba: no valida `X-Twilio-Signature` todavia (ver docstring en
`src/api.py`) y queda deshabilitado (404) fuera de `ENTORNO=desarrollo`.

`/api/webhook` (el generico, protegido con `WEBHOOK_SECRET`) sigue siendo
un simulador de webhook para pruebas locales, no un proveedor real.

**Decision requerida:** ¿se necesita soportar Twilio ademas de Meta, o se
retira `/api/webhook-twilio` del proyecto? Si se decide soportarlo, falta
implementar la verificacion de `X-Twilio-Signature` antes de usarlo con
datos reales.

| Aspecto | Twilio | Meta (WhatsApp Cloud API) |
|---|---|---|
| Costo | Cobra por mensaje + markup sobre tarifa de Meta | Tarifa directa de Meta, generalmente mas barata |
| Setup | Cuenta Twilio + numero de WhatsApp Business aprobado | Cuenta Meta Business + numero verificado, proceso de aprobacion propio |
| Header de firma | `X-Twilio-Signature` (HMAC-SHA1, firma URL+params) — NO implementado aun | `X-Hub-Signature-256` (HMAC-SHA256, firma body crudo) — implementado y verificado |
| Formato de payload | `application/x-www-form-urlencoded` | JSON anidado (`entry[].changes[].value.messages[]`) |
| Estado actual | Sandbox de prueba, sin firma verificada | Implementado y probado con trafico real |

**Impacto tecnico de la decision (si se decide soportar Twilio en serio):**
agregar verificacion de `X-Twilio-Signature` (HMAC-SHA1 sobre URL+params,
distinto al mecanismo de Meta) en `webhook_twilio()`, ya que el parsing del
payload (`request.form`, TwiML de salida) ya esta resuelto.