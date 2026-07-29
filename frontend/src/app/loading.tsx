export default function Loading() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        height: "80vh",
        gap: 16,
        color: "#4da6ff",
      }}
    >
      <div style={{ fontSize: 40 }}>⏳</div>
      <div style={{ fontSize: 20, fontWeight: 700 }}>
        Chargement...
      </div>
      <div style={{ fontSize: 14, color: "#7fb4e8" }}>
        Préparation de l&apos;application Typhoon
      </div>
    </div>
  );
}
