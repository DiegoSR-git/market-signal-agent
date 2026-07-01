# Premium Research Agents

V1 modular de agentes de research automatizado con datos publicos, Telegram multi-chat, GitHub Models, state anti-spam, snapshots, logs CSV y dashboards en `docs/`.

No ejecutan ordenes, no usan informacion privilegiada y no generan asesoramiento financiero personalizado. El lenguaje de alertas esta orientado a vigilancia, catalizadores y riesgos.

## Agentes

| Agente | Script | Config | Dashboard |
| --- | --- | --- | --- |
| SEC Insider & Filing | `sec_filing_agent.py` | `config_sec.yaml` | `docs/sec_filing_dashboard.html` |
| Macro Regime | `macro_regime_agent.py` | `config_macro.yaml` | `docs/macro_regime_dashboard.html` |
| Sector Rotation | `sector_rotation_agent.py` | `config_sector_rotation.yaml` | `docs/sector_rotation_dashboard.html` |
| DeFi Liquidity | `defi_liquidity_agent.py` | `config_defi.yaml` | `docs/defi_liquidity_dashboard.html` |
| Earnings Catalyst | `earnings_catalyst_agent.py` | `config_earnings.yaml` | `docs/earnings_catalyst_dashboard.html` |
| CFTC Positioning | `cftc_positioning_agent.py` | `config_cftc.yaml` | `docs/cftc_positioning_dashboard.html` |
| Unusual Volume | `unusual_volume_agent.py` | `config_unusual_volume.yaml` | `docs/unusual_volume_dashboard.html` |
| Altcoin Fundamentals | `altcoin_fundamentals_agent.py` | `config_altcoins.yaml` | `docs/altcoin_fundamentals_dashboard.html` |

## Probar en local

```bash
python -u sec_filing_agent.py --dry-run --force
python -u macro_regime_agent.py --dry-run --force
python -u sector_rotation_agent.py --dry-run --force
python -u defi_liquidity_agent.py --dry-run --force
python -u earnings_catalyst_agent.py --dry-run --force
python -u cftc_positioning_agent.py --dry-run --force
python -u unusual_volume_agent.py --dry-run --force
python -u altcoin_fundamentals_agent.py --dry-run --force
```

## Probar en GitHub Actions

En la pestana **Actions**, abre el workflow correspondiente y ejecuta **Run workflow** con:

```text
force=true
```

`force=true` envia el top de eventos aunque no alcance el umbral configurado. En modo normal solo envia Telegram si el score supera `alerts.min_score_to_alert` y respeta `cooldown_hours`.

## Secrets y variables

Secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID` opcional si usas un chat unico

Variables:

- `TELEGRAM_CHAT_IDS` opcional, varios chats separados por coma
- `SEC_USER_AGENT` recomendado para SEC EDGAR, por ejemplo `market-signal-agent diego@example.com`

GitHub Models usa `GITHUB_TOKEN` del workflow con:

```yaml
permissions:
  models: read
```

## Persistencia

Cada agente genera:

- `*_state.json`: cooldown anti-spam y ultima ejecucion
- `*_snapshot.json`: ultimo ranking completo
- `*_log.csv`: historico append-only
- `docs/*_dashboard.html`: dashboard publicado por GitHub Pages

Los workflows hacen commit automatico de estos archivos con `[skip ci]`.
