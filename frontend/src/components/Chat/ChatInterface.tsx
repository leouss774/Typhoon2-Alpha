import { useState, useRef, useEffect } from "react";
import { useChat } from "../../hooks/useChat";
import MessageBubble from "./MessageBubble";

interface ChatInterfaceProps {
  sessionId: string;
}

export default function ChatInterface({ sessionId }: ChatInterfaceProps) {
  const { messages, sendMessage, loading } = useChat(sessionId);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setInput("");
    await sendMessage(q);
  };

  return (
    <div className="chat-interface">
      <h3>💬 Conseil Typhoon</h3>
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-welcome">
            <p>Posez vos questions sur le diagnostic :</p>
            <ul>
              <li>Pourquoi ce risque est élevé ?</li>
              <li>Combien coûtent les travaux ?</li>
              <li>Quelle est la priorité ?</li>
            </ul>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        <div ref={endRef} />
      </div>
      <div className="chat-input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Posez une question..."
          disabled={loading}
          className="chat-input"
        />
        <button onClick={handleSend} disabled={loading || !input.trim()} className="chat-send-btn">
          {loading ? "..." : "Envoyer"}
        </button>
      </div>
    </div>
  );
}
