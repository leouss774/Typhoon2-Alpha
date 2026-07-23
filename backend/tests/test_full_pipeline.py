#!/usr/bin/env python3
"""
Test complet du pipeline Typhoon — backend API.

Usage :
    python tests/test_full_pipeline.py [--port 8000] [--host 127.0.0.1] [--no-start]

Options :
    --no-start   : utiliser un serveur deja en cours (ne pas en demarrer un nouveau)

Prerequis :
    pip install requests

Deroulement :
    1. Demarre le serveur uvicorn (subprocess)
    2. Attend que /health reponde
    3. Execute 6 scenarios de test
    4. Affiche un tableau recapitulatif avec scores
    5. Arrete proprement le serveur
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

# Activation des sequences ANSI sur Windows (necessite Windows Terminal ou ConHost >= 10)
if sys.platform == "win32":
    os.system("")

# Encodage sortie : remplacer les caracteres non supportes sur Windows (cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1252", "latin-1"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass  # stdout ne supporte pas reconfigure

import requests  # noqa: E402

# ─── Configuration ────────────────────────────────────────────────────────────

HOST = "127.0.0.1"
PORT = 8000
BASE_URL = f"http://{HOST}:{PORT}"
TIMEOUT_WAIT = 30   # secondes max pour attendre le demarrage
TIMEOUT_REQ = 15    # secondes max par requete


# ─── Resultats ────────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


# ─── Couleurs terminal (ANSI) ────────────────────────────────────────────────

def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"

def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"

def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"

def _cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m"

def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _check_keys(data: dict, required: list[str], path: str = "root") -> list[str]:
    """Verifie qu'une liste de cles existe dans un dict (recursif avec '.')"""
    missing = []
    for key in required:
        keys = key.split(".", 1)
        if len(keys) == 1:
            if keys[0] not in data:
                missing.append(f"{path}.{keys[0]}")
        else:
            if keys[0] in data and isinstance(data[keys[0]], dict):
                missing += _check_keys(data[keys[0]], [keys[1]], f"{path}.{keys[0]}")
            else:
                missing.append(f"{path}.{key}")
    return missing


def _score_color(s: int) -> str:
    if s >= 70:
        return _red(str(s))
    if s >= 55:
        return _yellow(str(s))
    if s >= 35:
        return _yellow(str(s))
    return _green(str(s))


def _print_divider(title: str = "", char: str = "=", width: int = 60):
    if title:
        padding = max(2, width - len(title) - 2)
        left = padding // 2
        right = padding - left
        print(f"{char * left}  {_bold(title)}  {char * right}")
    else:
        print(char * width)


def _print_results(results: list[TestResult]):
    """Affiche le tableau des resultats."""
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    _print_divider(f"RESULTATS ({passed}/{total} passes)")

    for r in results:
        icon = _green("PASS") if r.passed else _red("FAIL")
        dur_str = f"{r.duration_ms:.0f}ms" if r.duration_ms > 0 else ""
        print(f"  [{icon}]  {r.name}  {_cyan(dur_str)}")
        if r.detail:
            print(f"         {r.detail}")
        if r.extra:
            for k, v in r.extra.items():
                if v:
                    print(f"         {k}: {v}")
        print()

    _print_divider()
    if passed == total:
        print(f"  {_green(_bold('100% - Tous les tests passent !'))}")
    else:
        print(f"  {_red(_bold(f'{total - passed} test(s) echoue(s)'))}")
    _print_divider()
    print()


# ─── Gestion du serveur ───────────────────────────────────────────────────────

@dataclass
class ServerProcess:
    process: subprocess.Popen | None = None
    host: str = HOST
    port: int = PORT

    def start(self) -> None:
        """Demarre le serveur uvicorn en arriere-plan."""
        print(f"  Demarrage du serveur sur {self.host}:{self.port}...")
        self.process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "api.main:app",
                "--host", self.host,
                "--port", str(self.port),
                "--log-level", "warning",
            ],
            cwd=os.path.join(os.path.dirname(__file__), "..", "api"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Attendre que le health check passe
        start = time.time()
        last_error = ""
        while time.time() - start < TIMEOUT_WAIT:
            try:
                resp = requests.get(urljoin(BASE_URL, "/health"), timeout=2)
                if resp.status_code == 200:
                    elapsed = time.time() - start
                    print(f"  Serveur pret en {elapsed:.1f}s\n")
                    return
            except requests.ConnectionError as e:
                last_error = str(e)
                time.sleep(0.5)

        # En cas d'echec : tuer le processus et diagnostiquer
        stderr_out = ""
        if self.process:
            try:
                stderr_out = self.process.stderr.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            self.process.kill()
            self.process.wait(timeout=3)
            self.process = None

        raise RuntimeError(
            f"Le serveur n'a pas demarre dans les {TIMEOUT_WAIT}s.\n"
            f"  Port: {self.port}\n"
            f"  Derniere erreur: {last_error}\n"
            f"  stderr: {stderr_out}"
        )

    def stop(self) -> None:
        """Arrete proprement le serveur."""
        if self.process:
            print("  Arret du serveur...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


# ─── Scenarios de test ────────────────────────────────────────────────────────

TEST_ADDRESSES = [
    "12 Rue de Rivoli, 75001 Paris",
    "91400 Saclay, Essonne",
    "Rue de la Republique, 69002 Lyon",
]


def test_health(base_url: str) -> TestResult:
    """Test : GET /health"""
    start = time.time()
    try:
        resp = requests.get(urljoin(base_url, "/health"), timeout=TIMEOUT_REQ)
        dur = (time.time() - start) * 1000
        data = resp.json()
        passed = resp.status_code == 200 and data.get("status") == "ok"
        return TestResult(
            name="Health Check",
            passed=passed,
            detail="Serveur operationnel" if passed else f"Status={resp.status_code}",
            duration_ms=dur,
        )
    except Exception as e:
        return TestResult(name="Health Check", passed=False, detail=str(e))


def test_analyze_simple(base_url: str) -> TestResult:
    """Test : POST /api/analyze avec donnees minimales"""
    start = time.time()
    try:
        payload = {
            "session_id": "test-simple-001",
            "client_form": {
                "adresse": TEST_ADDRESSES[0],
                "type_bien": "Maison individuelle",
                "surface": 100,
                "nb_etages": 1,
                "annee_construction": 1975,
                "type_structure": "Beton arme",
                "etat_structure": "Bon",
            },
        }
        resp = requests.post(
            urljoin(base_url, "/api/analyze"),
            json=payload,
            timeout=TIMEOUT_REQ + 5,
        )
        dur = (time.time() - start) * 1000
        data = resp.json()

        checks = []
        checks.append(("status_code=200", resp.status_code == 200))
        checks.append(("status=ok", data.get("status") == "ok"))
        checks.append(("session_id present", "session_id" in data))

        analysis = data.get("analysis", {})
        required_keys = [
            "adresse", "recommandations.zones", "recommandations.projection_2050",
            "recommandations.synthese_financiere", "analyse_risques.score.global",
            "resume.cout_total_travaux",
        ]
        missing = _check_keys(analysis, required_keys)
        checks.append((f"cles requises ({len(required_keys)})", len(missing) == 0))

        zones = analysis.get("recommandations", {}).get("zones", {})
        expected_zones = {"fondations", "murs_nord", "toiture", "sous_sol"}
        found_zones = set(zones.keys())
        checks.append((f"zones trouvees: {found_zones}", expected_zones == found_zones))

        for zname, zdata in zones.items():
            s = zdata.get("risque", -1)
            checks.append((f"zone {zname}.risque dans [0,100]", 0 <= s <= 100))
            checks.append((f"zone {zname}.niveau non vide", bool(zdata.get("niveau"))))

        all_passed = all(p for _, p in checks)
        failed = [c[0] for c in checks if not c[1]]
        failures = "; ".join(failed) if failed else "OK"

        scores = {z: zones[z].get("risque", "?") for z in sorted(zones)}
        score_global = analysis.get("analyse_risques", {}).get("score", {}).get("global", "?")
        cout = analysis.get("resume", {}).get("cout_total_travaux", "?")

        return TestResult(
            name="Analyse simple (donnees minimales)",
            passed=all_passed,
            detail=failures,
            duration_ms=dur,
            extra={
                "Score global": _score_color(score_global) if isinstance(score_global, int) else str(score_global),
                "Scores zones": ", ".join(f"{k}={_score_color(v)}" for k, v in scores.items()),
                "Cout total": cout,
            },
        )
    except Exception as e:
        return TestResult(name="Analyse simple", passed=False, detail=str(e))


def test_analyze_complet(base_url: str) -> TestResult:
    """Test : POST /api/analyze avec toutes les donnees du formulaire"""
    start = time.time()
    try:
        payload = {
            "session_id": "test-complet-002",
            "client_form": {
                "adresse": TEST_ADDRESSES[1],
                "code_insee": "91345",
                "type_bien": "Maison individuelle",
                "surface": 150,
                "nb_etages": 2,
                "annee_construction": 1965,
                "annee_renovation": 2010,
                "type_structure": "Beton arme",
                "etat_structure": "Moyen",
                "fissures": "Moyennes",
                "affaissement": "Non",
                "type_toiture": "Tuiles",
                "age_toiture": 2000,
                "etat_toiture": "Moyen",
                "infiltrations": "Non",
                "presence_sous_sol": True,
                "presence_cave": False,
                "occupation": "Occupe",
                "installation_electrique_annee": 2000,
                "isolation_toiture": "faible",
                "isolation_murs": "moyenne",
            },
        }
        resp = requests.post(
            urljoin(base_url, "/api/analyze"),
            json=payload,
            timeout=TIMEOUT_REQ + 5,
        )
        dur = (time.time() - start) * 1000
        data = resp.json()

        checks = []
        checks.append(("status=200", resp.status_code == 200))
        analysis = data.get("analysis", {})

        zones = analysis.get("recommandations", {}).get("zones", {})
        for zname in ["fondations", "murs_nord", "toiture", "sous_sol"]:
            zdata = zones.get(zname, {})
            checks.append((f"{zname}.recommandations non vides", len(zdata.get("recommandations", [])) > 0))

        proj = analysis.get("recommandations", {}).get("projection_2050", {}).get("zones", {})
        checks.append(("projection_2050 presente", len(proj) > 0))

        synth = analysis.get("recommandations", {}).get("synthese_financiere", {})
        checks.append(("cout_brut_total contient '€'", "€" in synth.get("cout_brut_total", "")))

        all_passed = all(p for _, p in checks)
        failed = [c[0] for c in checks if not c[1]]

        scores = {}
        for zname, zdata in zones.items():
            recos = zdata.get("recommandations", [])
            scores[zname] = f"{_score_color(zdata.get('risque', '?'))} ({len(recos)} recos)"

        score_global = analysis.get("analyse_risques", {}).get("score", {}).get("global", "?")
        score_txt = _score_color(score_global) if isinstance(score_global, int) else str(score_global)
        cout = analysis.get("resume", {}).get("cout_total_travaux", "?")
        aides = analysis.get("resume", {}).get("aides_mobilisables", "?")
        reste = analysis.get("resume", {}).get("reste_a_charge_net", "?")

        return TestResult(
            name="Analyse complete (tous champs)",
            passed=all_passed,
            detail="; ".join(failed) if failed else "OK",
            duration_ms=dur,
            extra={
                "Score global": score_txt,
                "Scores zones": " | ".join(f"{k}: {v}" for k, v in scores.items()),
                f"Budget": f"Total: {cout} | Aides: {aides} | Reste: {reste}",
            },
        )
    except Exception as e:
        return TestResult(name="Analyse complete", passed=False, detail=str(e))


def test_vulnerability(base_url: str) -> TestResult:
    """Test : POST /api/jumeau/vulnerability-test"""
    start = time.time()
    try:
        payload = {
            "zone_name": "fondations",
            "zone_data": {"risque": 72, "niveau": "eleve"},
        }
        resp = requests.post(
            urljoin(base_url, "/api/jumeau/vulnerability-test"),
            json=payload,
            timeout=TIMEOUT_REQ,
        )
        dur = (time.time() - start) * 1000
        data = resp.json()

        checks = []
        checks.append(("status=200", resp.status_code == 200))
        checks.append(("verdict present", "verdict" in data))
        checks.append(("score_avant dans [0,100]", 0 <= data.get("score_avant", -1) <= 100))
        checks.append(("score_apres_travaux ok", isinstance(data.get("score_apres_travaux"), int)))
        checks.append(("points_vigilance non vides", len(data.get("points_de_vigilance", [])) > 0))

        all_passed = all(p for _, p in checks)
        failed = [c[0] for c in checks if not c[1]]

        return TestResult(
            name="Test de vulnerabilite (zone cliquee)",
            passed=all_passed,
            detail="; ".join(failed) if failed else f"Verdict: {data.get('verdict', '?')}",
            duration_ms=dur,
            extra={
                "Verdict": f"{data.get('verdict', '?')} ({data.get('score_risque', '?')}/100)",
                "Action": data.get("resume", "?"),
            },
        )
    except Exception as e:
        return TestResult(name="Test vulnerabilite", passed=False, detail=str(e))


def test_get_analysis(base_url: str) -> TestResult:
    """
    Test : GET /api/analysis/{id}
    Cree sa propre session via POST d'abord (independant de l'ordre des tests)
    """
    start = time.time()
    try:
        session_id = "test-get-analysis"
        create_resp = requests.post(
            urljoin(base_url, "/api/analyze"),
            json={
                "session_id": session_id,
                "client_form": {
                    "adresse": TEST_ADDRESSES[2],
                    "type_bien": "Appartement",
                    "surface": 80,
                    "annee_construction": 1990,
                },
            },
            timeout=TIMEOUT_REQ + 5,
        )
        if create_resp.status_code != 200:
            return TestResult(
                name="Recuperation analyse GET",
                passed=False,
                detail=f"Creation session echouee: {create_resp.status_code}",
                duration_ms=(time.time() - start) * 1000,
            )

        resp = requests.get(
            urljoin(base_url, f"/api/analysis/{session_id}"),
            timeout=TIMEOUT_REQ,
        )
        dur = (time.time() - start) * 1000
        data = resp.json()

        checks = []
        checks.append(("status=200", resp.status_code == 200))
        checks.append(("adresse presente", "adresse" in data))
        checks.append(("recommandations", "recommandations" in data))

        all_passed = all(p for _, p in checks)
        failed = [c[0] for c in checks if not c[1]]

        return TestResult(
            name="Recuperation analyse GET",
            passed=all_passed,
            detail="; ".join(failed) if failed else f"Analyse chargee: {data.get('adresse', '?')}",
            duration_ms=dur,
        )
    except Exception as e:
        return TestResult(name="GET analyse", passed=False, detail=str(e))


def test_analyze_multiple_addresses(base_url: str) -> TestResult:
    """Test : POST /api/analyze sur plusieurs adresses pour voir la variation des scores"""
    start = time.time()
    try:
        results_by_addr: dict[str, dict[str, Any]] = {}
        all_passed = True

        for i, addr in enumerate(TEST_ADDRESSES):
            payload = {
                "session_id": f"test-multi-{i:03d}",
                "client_form": {
                    "adresse": addr,
                    "type_bien": "Maison individuelle",
                    "surface": 100,
                    "annee_construction": 1975,
                },
            }
            resp = requests.post(
                urljoin(base_url, "/api/analyze"),
                json=payload,
                timeout=TIMEOUT_REQ + 5,
            )
            if resp.status_code != 200:
                all_passed = False
                continue

            data = resp.json()
            zone_scores: dict[str, Any] = {}
            for zname, zdata in data.get("analysis", {}).get("recommandations", {}).get("zones", {}).items():
                zone_scores[zname] = zdata.get("risque", "?")
            results_by_addr[addr] = zone_scores

        dur = (time.time() - start) * 1000

        all_same = True
        if len(results_by_addr) >= 2:
            first_vals = list(results_by_addr.values())[0]
            for other in list(results_by_addr.values())[1:]:
                if other != first_vals:
                    all_same = False
                    break

        if all_passed:
            if all_same:
                detail = "OK - scores identiques (pipeline API non disponible)"
            else:
                detail = "OK - scores differents selon adresse (pipeline API actif)"
        else:
            detail = "Erreur sur une ou plusieurs adresses"

        extra = {}
        for addr, scores in results_by_addr.items():
            short = addr.split(",")[0]
            scores_str = ", ".join(f"{k}={_score_color(v)}" for k, v in scores.items())
            extra[f"Adresse: {short}"] = scores_str

        if not results_by_addr:
            extra["Note"] = "Aucune adresse n'a repondu correctement"

        return TestResult(
            name=f"Analyse multi-adresses ({len(TEST_ADDRESSES)} adresses)",
            passed=all_passed,
            detail=detail,
            duration_ms=dur,
            extra=extra,
        )
    except Exception as e:
        return TestResult(name="Analyse multi-adresses", passed=False, detail=str(e))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print()
    _print_divider("Typhoon - Test complet du pipeline")
    print("  Analyse multi-agents de resilience climatique")
    print()

    # Parse args
    host = HOST
    port = PORT
    skip_start = False
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--port" and i + 2 < len(sys.argv):
            port = int(sys.argv[i + 2])
        if arg == "--host" and i + 2 < len(sys.argv):
            host = sys.argv[i + 2]
        if arg == "--no-start":
            skip_start = True

    base_url = f"http://{host}:{port}"

    # Gestion du serveur
    server = ServerProcess(host=host, port=port)

    try:
        if skip_start:
            print("  Mode --no-start : utilisation d'un serveur deja en cours")
            try:
                requests.get(urljoin(base_url, "/health"), timeout=3)
                print("  Serveur accessible.\n")
            except requests.ConnectionError:
                print(f"  Impossible de joindre {base_url}")
                return 1
        else:
            try:
                resp = requests.get(urljoin(base_url, "/health"), timeout=2)
                if resp.status_code == 200:
                    print(f"  Serveur deja en cours d'execution sur {base_url}\n")
                else:
                    server.start()
            except requests.ConnectionError:
                server.start()

        # Executer les tests
        results: list[TestResult] = []
        tests = [
            ("Health Check", test_health),
            ("Analyse simple", lambda u: test_analyze_simple(u)),
            ("Analyse complete", lambda u: test_analyze_complet(u)),
            ("Vulnerabilite", lambda u: test_vulnerability(u)),
            ("GET analyse", lambda u: test_get_analysis(u)),
            ("Multi-adresses", lambda u: test_analyze_multiple_addresses(u)),
        ]

        for name, test_fn in tests:
            result = test_fn(base_url)
            results.append(result)
            icon = _green("PASS") if result.passed else _red("FAIL")
            dur = f" ({result.duration_ms:.0f}ms)" if result.duration_ms > 0 else ""
            print(f"  [{icon}]  {name}{dur}")

        print()

        # Resume
        _print_results(results)

    finally:
        # Arret du serveur dans tous les cas, meme en cas d'exception
        if not skip_start:
            server.stop()

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
