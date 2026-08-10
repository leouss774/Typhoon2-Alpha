import { defineConfig } from 'vite'

// App « Assistant Rapport IA » — avatar 3D TalkingHead (Ready Player Me) branché
// sur le même backend /api/chat/stream que le chatbot assistant, avec le
// contexte du rapport envoyé par l'app hôte (postMessage depuis ReportChatbot).
export default defineConfig({
  // Évite le cache node_modules/.vite, verrouillé par OneDrive sur Windows.
  cacheDir: '.vite-cache',
  server: {
    port: 5175,
    strictPort: true,
  },
})
