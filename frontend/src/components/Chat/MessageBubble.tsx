import type { ChatMessage } from "../../types/models";

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`message-bubble ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-avatar">{isUser ? "👤" : "🌪️"}</div>
      <div className="message-content">
        <p>{message.content}</p>
        <span className="message-time">
          {new Date(message.timestamp).toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
    </div>
  );
}
