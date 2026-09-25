import { useEffect, useRef } from "react";

function formatTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function MessageList({ messages, currentUserId }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="message-list">
      {messages.length === 0 && (
        <div className="empty-state">No messages yet. Say hello!</div>
      )}
      {messages.map((msg) => {
        const isOwn = msg.from_user_id === currentUserId;
        return (
          <div key={msg.id} className={`message-row ${isOwn ? "own" : ""}`}>
            <div className="message-bubble">
              <div className="message-meta">
                <span className="message-sender">{isOwn ? "You" : msg.from_email}</span>
                <span className="message-time">{formatTime(msg.timestamp)}</span>
              </div>
              <div className="message-content">
                {msg.decryptFailed ? (
                  <em className="message-undecryptable">🔒 Unable to decrypt this message</em>
                ) : (
                  msg.content
                )}
              </div>
            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
