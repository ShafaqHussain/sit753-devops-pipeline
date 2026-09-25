export default function UserSidebar({ users, onlineIds, currentUser }) {
  const sorted = [...users].sort((a, b) => {
    const aOnline = onlineIds.has(a.id) ? 0 : 1;
    const bOnline = onlineIds.has(b.id) ? 0 : 1;
    if (aOnline !== bOnline) return aOnline - bOnline;
    return a.email.localeCompare(b.email);
  });

  return (
    <aside className="user-sidebar">
      <h3>Users</h3>
      <ul>
        {sorted.map((u) => (
          <li key={u.id} className="user-row">
            <span className={`status-dot ${onlineIds.has(u.id) ? "online" : "offline"}`} />
            <span className="user-email">
              {u.email}
              {u.id === currentUser.id && " (you)"}
            </span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
