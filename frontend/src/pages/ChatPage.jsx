import { useEffect, useRef, useState } from "react";

import MessageInput from "../components/MessageInput.jsx";
import MessageList from "../components/MessageList.jsx";
import UserSidebar from "../components/UserSidebar.jsx";
import { getUsers, updatePublicKey } from "../services/api.js";
import {
  decryptMessage,
  encryptForRecipients,
  generateKeyPair,
  loadPrivateKey,
  savePrivateKey,
} from "../services/cryptoService.js";
import { connectSocket, disconnectSocket } from "../services/socketService.js";

export default function ChatPage({ token, user, onLogout }) {
  const [messages, setMessages] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [onlineUsers, setOnlineUsers] = useState([]);
  const [connectionError, setConnectionError] = useState("");
  const [needsKeyRecovery, setNeedsKeyRecovery] = useState(() => !loadPrivateKey(user.id));
  const [regenerating, setRegenerating] = useState(false);

  const socketRef = useRef(null);
  const allUsersRef = useRef([]);
  const myPrivateKeyRef = useRef(loadPrivateKey(user.id));

  async function decryptRaw(raw) {
    const sender = allUsersRef.current.find((u) => u.id === raw.from_user_id);
    const myKey = myPrivateKeyRef.current;
    if (!sender || !myKey) {
      return { ...raw, content: null, decryptFailed: true };
    }
    const content = await decryptMessage({
      ciphertext: raw.ciphertext,
      nonce: raw.nonce,
      senderPublicKeyB64: sender.public_key,
      myPrivateKeyB64: myKey,
    });
    return { ...raw, content, decryptFailed: content === null };
  }

  useEffect(() => {
    let cancelled = false;

    async function init() {
      // Load the public-key directory before connecting, so history that
      // arrives immediately on connect can be decrypted right away.
      try {
        const data = await getUsers(token);
        if (cancelled) return;
        setAllUsers(data.users);
        allUsersRef.current = data.users;
      } catch {
        /* sidebar just shows fewer users if this fails */
      }
      if (cancelled) return;

      const socket = connectSocket(token);
      socketRef.current = socket;

      socket.on("connect_error", (err) => {
        setConnectionError(err.message || "Failed to connect");
        if (err.message?.toLowerCase().includes("auth")) {
          onLogout();
        }
      });

      socket.on("message_history", async ({ messages: history }) => {
        const decrypted = await Promise.all(history.map(decryptRaw));
        setMessages(decrypted);
      });

      socket.on("new_message", async (raw) => {
        const decrypted = await decryptRaw(raw);
        setMessages((prev) => [...prev, decrypted]);
      });

      socket.on("user_joined", async ({ online_users }) => {
        setOnlineUsers(online_users);
        setConnectionError("");
        try {
          const data = await getUsers(token);
          setAllUsers(data.users);
          allUsersRef.current = data.users;
        } catch {
          /* keep the previous directory if this fails */
        }
      });

      socket.on("user_left", ({ online_users }) => {
        setOnlineUsers(online_users);
      });

      socket.on("error", (payload) => {
        setConnectionError(payload?.message || "Something went wrong");
      });
    }

    init();

    return () => {
      cancelled = true;
      disconnectSocket();
    };
  }, [token, onLogout]);

  async function handleSend(content) {
    if (!myPrivateKeyRef.current) return;
    const { nonce, ciphertexts } = await encryptForRecipients(
      content,
      allUsersRef.current,
      myPrivateKeyRef.current
    );
    socketRef.current?.emit("send_message", { nonce, ciphertexts });
  }

  async function handleRegenerateKey() {
    setRegenerating(true);
    try {
      const keyPair = await generateKeyPair();
      await updatePublicKey(token, keyPair.publicKey);
      savePrivateKey(user.id, keyPair.privateKey);
      myPrivateKeyRef.current = keyPair.privateKey;
      setNeedsKeyRecovery(false);

      const data = await getUsers(token);
      setAllUsers(data.users);
      allUsersRef.current = data.users;
    } catch (err) {
      setConnectionError(err.message || "Failed to generate a new key");
    } finally {
      setRegenerating(false);
    }
  }

  function handleLogout() {
    disconnectSocket();
    onLogout();
  }

  const onlineIds = new Set(onlineUsers.map((u) => u.id));

  return (
    <div className="chat-page">
      <UserSidebar users={allUsers} onlineIds={onlineIds} currentUser={user} />

      <div className="chat-main">
        <header className="chat-header">
          <h2>Team Chat 🔒</h2>
          <div className="chat-header-right">
            <span className="current-user">{user.email}</span>
            <button className="btn-secondary" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </header>

        {connectionError && <div className="connection-banner">{connectionError}</div>}

        {needsKeyRecovery && (
          <div className="key-recovery-banner">
            <p>
              No local encryption key found for this account on this device, so
              messages can&apos;t be decrypted here. Generate a new key to send
              and receive new messages — previously sent messages will stay
              unreadable on this device, since they were encrypted for the old
              key.
            </p>
            <button className="btn-primary" onClick={handleRegenerateKey} disabled={regenerating}>
              {regenerating ? "Generating…" : "Generate New Key"}
            </button>
          </div>
        )}

        <MessageList messages={messages} currentUserId={user.id} />

        {!needsKeyRecovery && <MessageInput onSend={handleSend} />}
      </div>
    </div>
  );
}
