"""
Módulo de aprendizaje: zona de mejora continua.
Permite al administrador dar feedback sobre las respuestas y agregar pautas
que se inyectan en los prompts del Planner y Responder para mejorar iterativamente.
"""

import json
from pathlib import Path
from typing import Optional

from . import database as db
from .config import FEEDBACK_PATH


class LearningEngine:
    """
    Motor de aprendizaje que inyecta pautas y feedback en los prompts del LLM.
    """

    def __init__(self):
        pass

    def get_pautas_planner(self) -> str:
        """
        Retorna las pautas activas para el Planner, formateadas para inyectar
        en el system prompt.
        """
        pautas = db.get_pautas_activas(tipo="planner")
        if not pautas:
            return ""

        lines = ["\n## PAUTAS DE MEJORA (basadas en feedback anterior):"]
        for i, p in enumerate(pautas, 1):
            lines.append(f"{i}. {p['contenido']}")
        return "\n".join(lines)

    def get_pautas_responder(self) -> str:
        """
        Retorna las pautas activas para el Responder, formateadas para inyectar
        en el system prompt.
        """
        pautas = db.get_pautas_activas(tipo="responder")
        pautas_generales = db.get_pautas_activas(tipo="general")

        todas = pautas + pautas_generales
        if not todas:
            return ""

        lines = ["\n## PAUTAS DE MEJORA (basadas en feedback de clientes):"]
        for i, p in enumerate(todas, 1):
            lines.append(f"{i}. {p['contenido']}")
        return "\n".join(lines)

    def add_pauta(self, tipo: str, contenido: str) -> int:
        """
        Agrega una nueva pauta de mejora.

        Args:
            tipo: 'planner', 'responder', o 'general'.
            contenido: Texto descriptivo de la pauta.

        Returns:
            ID de la pauta creada.
        """
        return db.guardar_pauta(tipo, contenido)

    def add_feedback(
        self,
        consulta_id: int,
        calificacion: str,
        comentario: Optional[str] = None,
    ) -> None:
        """
        Registra feedback sobre una consulta.

        Args:
            consulta_id: ID de la consulta.
            calificacion: 'positiva', 'negativa', o 'neutral'.
            comentario: Comentario opcional.
        """
        db.guardar_feedback(consulta_id, calificacion, comentario)

    def get_historial(self, limit: int = 20) -> list[dict]:
        """Retorna el historial de consultas con feedback."""
        return db.get_ultimas_consultas(limit)

    def get_estadisticas(self) -> dict:
        """Retorna estadísticas del sistema."""
        return db.get_estadisticas()

    def get_contexto_mejora(self) -> dict:
        """
        Retorna un contexto completo para que el admin pueda revisar
        y decidir qué pautas agregar.
        """
        stats = self.get_estadisticas()
        historial = self.get_historial(limit=50)
        pautas = db.get_pautas_activas()

        # Identificar consultas con feedback negativo
        negativas = [h for h in historial if h.get("feedback_calificacion") == "negativa"]

        return {
            "estadisticas": stats,
            "pautas_activas": [dict(p) for p in pautas],
            "consultas_negativas": [
                {
                    "id": n["id"],
                    "mensaje": n["mensaje_cliente"],
                    "respuesta": n["respuesta_enviada"],
                    "comentario": n.get("feedback_comentario"),
                }
                for n in negativas[:10]
            ],
            "total_consultas_con_feedback": len([h for h in historial if h.get("feedback_calificacion")]),
        }


# Instancia global para uso conveniente
engine = LearningEngine()