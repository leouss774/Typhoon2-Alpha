import os
from dotenv import load_dotenv

load_dotenv()

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

CHAT_MODEL = "mistral-large-latest"
EMBED_MODEL = "mistral-embed"

DOCUMENTS_DIR = "data"
DATA_DIR = "data"
REFERENTIEL_PATH = os.path.join(DATA_DIR, "referentiel.json")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")
SOURCES_REGISTRY_PATH = os.path.join(DATA_DIR, "sources_registry.csv")

CHUNK_SIZE = 6000    # caracteres envoyes au modele par appel
CHUNK_OVERLAP = 500  # chevauchement pour ne pas couper une regle en deux

TOP_K = 6            # nombre de fiches recuperees par requete RAG

# Timeout HTTP par requete, en millisecondes. Le defaut du SDK peut etre trop court
# pour des chunks volumineux ou une connexion instable (wifi qui coupe, etc.).
REQUEST_TIMEOUT_MS = 300_000  # 5 minutes
THROTTLE_SECONDS = 3
PROGRESS_PATH = os.path.join(DATA_DIR, "progress.json")
