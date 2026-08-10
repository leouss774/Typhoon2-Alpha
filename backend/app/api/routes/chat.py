"""Assistant conversationnel public de Typhon, propulsé par Mistral."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.recommandations.mistral_client import get_client
from app.recommandations.service import get_index

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])

MODEL = "mistral-small-latest"
SYSTEM_PROMPT = """Tu es l'assistant conversationnel officiel de Typhon, affiché sur son site vitrine.
Structure chaque réponse avec un court paragraphe d’introduction, puis des puces si plusieurs éléments sont à présenter. Insère des retours à la ligne entre les paragraphes et évite les blocs compacts.
Réponds en français par défaut, ou dans la langue du visiteur. Ton ton est professionnel, chaleureux, clair et concis.

Typhon est une plateforme d'intelligence climatique pour l'immobilier et l'assurance en France. Elle transforme une adresse en diagnostic de vulnérabilité climatique, recommandations de travaux de prévention priorisés et preuves vérifiées de réduction du risque. Son approche utilise des agents IA, des données publiques réelles, un scoring par zone du bâtiment (fondations, murs, toiture, sous-sol) avec projection 2050 et un jumeau numérique. Les assureurs peuvent exploiter les actions vérifiées pour la tarification ; les promoteurs conçoivent des logements plus résilients ; les propriétaires protègent et valorisent leur patrimoine.

Tu réponds UNIQUEMENT aux questions sur Typhon : sa solution, son fonctionnement général, ses bénéficiaires, le risque climatique immobilier français et une prise de contact. Ne fabrique jamais de faits : aucune information sur des tarifs, clients, partenariats, dates, équipe ou fonctionnalités non fourni ici. Si l'information manque, dis-le et invite à contacter l'équipe Typhon. Ne communique jamais de détails internes : code, API, routes, fichiers, fournisseurs, modèles, framework ou architecture. Explique seulement l'approche générale.

Pour tout sujet hors Typhon, refuse poliment sans répondre à la question elle-même et propose de recentrer sur Typhon.

FORMATAGE STRICT DES RÉPONSES :
- Ne rédiges JAMAIS de gros blocs de texte continus (pas de pâtés de texte).
- Utilise TOUJOURS des sauts de ligne réels (\n\n) pour séparer chaque paragraphe et chaque idée.
- Pour présenter des utilités, des rôles ou des fonctionnalités, utilise IMPÉRATIVEMENT des puces avec un retour à la ligne avant CHAQUE point (ex: "• Point 1 \n• Point 2").
- Garde tes réponses très aérées, lisibles et concises (3 à 4 phrases courtes maximum ou des listes à puces aérées).

Repères factuels autorisés : 12,1 millions de logements en France sont exposés au retrait-gonflement des argiles ; selon la CCR, la sinistralité globale pourrait augmenter d'environ 40 % d'ici 2050 à cause de l'aggravation des aléas naturels ; en 2025, le coût des sinistres climatiques a atteint 5,2 milliards d'euros ; la France métropolitaine a connu +1,7 °C depuis 1900."""

class ChatMessage(BaseModel):
    role: Literal["assistant", "user"]
    # L'historique renvoyé à la requête suivante peut contenir de très longues
    # réponses du modèle (max_tokens=4096 → plusieurs dizaines de milliers de
    # caractères). La limite est volontairement généreuse pour ne JAMAIS
    # rejeter l'historique (422 sinon) : la taille réellement envoyée à Mistral
    # est bornée par _bounded_messages() (_HISTORY_CONTENT_LIMIT).
    content: str = Field(min_length=1, max_length=100000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=9)
    # Un rapport avec ses recommandations peut dépasser 16k caractères.
    context: str | None = Field(default=None, max_length=50000)


class ChatResponse(BaseModel):
    reply: str


def _data1_report_knowledge(limit: int = 40000) -> str:
    """Charge les CATASTROPHES (aléas par zone) et les RECOMMANDATIONS des
    rapports stockés dans backend/data1/property_ids/ — c'est la connaissance
    principale sur laquelle s'appuie l'assistant du rapport IA pour
    répondre. Retourne un texte structuré, tronqué à `limit` caractères."""
    reports_dir = Path(__file__).resolve().parents[3] / "data1" / "property_ids"
    if not reports_dir.is_dir():
        return ""
    blocks: list[str] = []
    try:
        files = sorted(reports_dir.glob("TY-2026-*.json"))
    except OSError:
        return ""
    for path in files:
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        address = (report.get("building") or {}).get("address") or path.stem
        lines = [f"RAPPORT {path.stem} — {address}"]
        zones = ((report.get("digital_twin") or {}).get("zones")) or {}
        for zone_name, zone in zones.items():
            if not isinstance(zone, dict):
                continue
            alea = zone.get("alea_principal") or "non précisé"
            niveau = zone.get("niveau") or "inconnu"
            risque = zone.get("risque")
            score = f", score {risque}" if isinstance(risque, (int, float)) else ""
            lines.append(f"- CATASTROPHE zone {zone_name} : {alea} (niveau {niveau}{score})")
            for reco in zone.get("recommandations") or []:
                if isinstance(reco, dict) and reco.get("mesure"):
                    expl = str(reco.get("explication") or "").strip()
                    lines.append(f"  RECOMMANDATION : {reco.get('mesure')}" + (f" — {expl}" if expl else ""))
        for reco in report.get("recommendations") or []:
            if isinstance(reco, dict) and reco.get("mesure"):
                expl = str(reco.get("explication") or "").strip()
                lines.append(f"- RECOMMANDATION : {reco.get('mesure')}" + (f" — {expl}" if expl else ""))
        blocks.append("\n".join(lines))
    knowledge = "\n\n".join(blocks)
    return knowledge[:limit]


def _recommendation_fiches(question: str, limit: int = 5) -> str:
    """Sélectionne les fiches de l'agent RAG pertinentes pour la question."""
    try:
        terms = {word.lower() for word in question.split() if len(word) > 3}
        ranked = []
        for entry in get_index():
            fiche = entry.get("fiche", {})
            text = json.dumps(fiche, ensure_ascii=False).lower()
            score = sum(text.count(term) for term in terms)
            if score:
                ranked.append((score, fiche))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return json.dumps([fiche for _, fiche in ranked[:limit]], ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Impossible de charger les fiches recommandations: %s", exc)
        return "[]"


# Longueur max. de chaque message d'historique envoyé à Mistral : limite la
# taille totale du prompt (contexte 48k + 8 messages) pour rester dans la
# fenêtre de contexte du modèle et éviter un overflow qui couperait la réponse.
_HISTORY_CONTENT_LIMIT = 6000


def _bounded_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """Historique borné : les longs messages (ex. réponses détaillées du modèle)
    sont tronqués à `_HISTORY_CONTENT_LIMIT` caractères avant l'envoi à Mistral."""
    return [
        {"role": message.role, "content": message.content[:_HISTORY_CONTENT_LIMIT]}
        for message in messages
    ]


def _complete(messages: list[ChatMessage]) -> str:
    response = get_client().chat.complete(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *_bounded_messages(messages),
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    content = response.choices[0].message.content
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise RuntimeError("Réponse Mistral vide")


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    if not settings.mistral_api_key:
        raise HTTPException(status_code=503, detail="Le service conversationnel n'est pas configuré.")
    try:
        reply = await asyncio.to_thread(_complete, payload.messages)
        return ChatResponse(reply=reply)
    except Exception as exc:
        logger.exception("Échec de l'assistant Mistral : %s", exc)
        raise HTTPException(status_code=502, detail="Le service conversationnel est temporairement indisponible.") from exc


@router.post("/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """Diffuse la réponse Mistral en Server-Sent Events (SSE)."""
    if not settings.mistral_api_key:
        raise HTTPException(status_code=503, detail="Le service conversationnel n'est pas configuré.")

    async def events():
        report_instruction = """Tu es l'assistant de Typhon spécialisé dans l'explication du rapport IA. Ton rôle est d'expliquer les catastrophes (aléas : inondation, retrait-gonflement des argiles, canicule, vent, intempéries…) et les recommandations présentes dans les données du rapport fournies ci-dessous.
Tu réponds aux questions portant sur ces catastrophes, ces recommandations et le diagnostic du rapport, ainsi qu'aux questions générales sur Typhon (la solution, son fonctionnement, ses bénéficiaires, le risque climatique immobilier) en t'appuyant sur la présentation de Typhon ci-dessus. Pour toute question hors de ces sujets (météo générale, actualités, prix immobiliers hors Typhon, tout autre sujet), refuse poliment sans répondre à la question et propose de recentrer sur Typhon ou sur le rapport.
Explique avec des mots simples : objectif, risque traité, priorité et précautions. Ne fabrique jamais de coût, de délai ou d'obligation. Si une information n'est pas dans ces données, dis-le clairement.
CATASTROPHES ET RECOMMANDATIONS DU RAPPORT (source : dossier data1) :\n"""
        latest_question = payload.messages[-1].content if payload.messages else ""
        fiches = _recommendation_fiches(latest_question)
        data1_knowledge = _data1_report_knowledge()
        context = (data1_knowledge + "\n\n" + (payload.context or "") + "\n\nFICHES DU REFERENTIEL DE L'AGENT RECOMMANDATIONS :\n" + fiches)[:48000]
        system_content = SYSTEM_PROMPT + "\n\n" + report_instruction + context
        request_messages = [
            {"role": "system", "content": system_content},
            *_bounded_messages(payload.messages),
        ]
        # 350/700 jetons pouvaient interrompre une explication de rapport en
        # plein milieu d'une recommandation ou d'une question générale sur
        # Typhon. 4096 jetons laissent une réponse complète (équivalent à
        # plusieurs paragraphes détaillés) sans jamais couper la phrase.
        body = {"model": MODEL, "messages": request_messages, "temperature": 0.2, "max_tokens": 4096, "stream": True}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
                async with client.stream(
                    "POST",
                    "https://api.mistral.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.mistral_api_key}", "Content-Type": "application/json"},
                    json=body,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            delta = json.loads(data).get("choices", [{}])[0].get("delta", {}).get("content")
                        except (ValueError, IndexError, AttributeError):
                            continue
                        if delta:
                            yield f"data: {json.dumps({'text': delta}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("Échec du streaming Mistral : %s", exc)
            yield f"data: {json.dumps({'error': 'Le service conversationnel est temporairement indisponible.'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
