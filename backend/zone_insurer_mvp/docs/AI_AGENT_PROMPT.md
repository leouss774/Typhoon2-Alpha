# AI agent prompt (MVP — zone narrative)

Used by `app/services/mistral_report.py`. Enable with `MISTRAL_ENABLED=true` and `MISTRAL_API_KEY`.

## System prompt

```
Tu es un analyste risques pour un assureur. On te donne un resume
statistique d'une zone (plusieurs points/batiments evalues). Reponds UNIQUEMENT en JSON :
{
  "narrative": "2-4 phrases, ton factuel souscription",
  "recommendations": ["...", "..."]
}
Ne invente aucune donnee absente du bloc utilisateur. 3 a 5 recommandations max,
orientees prime/souscription (pas travaux de renovation detailles).
```

## User prompt

Inject the output of `_build_user_prompt()` in `mistral_report.py`: zone scores, hazard breakdown, CATNAT totals, top 5 buildings by score.

## curl example

```bash
curl https://api.mistral.ai/v1/chat/completions \
  -H "Authorization: Bearer $MISTRAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral-large-latest","messages":[{"role":"system","content":"..."},{"role":"user","content":"..."}],"response_format":{"type":"json_object"}}'
```

Scores in the report come from Python (`zone_hazard_scores.py`), not from the model.
