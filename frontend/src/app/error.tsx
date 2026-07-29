"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        height: "70vh",
        gap: 20,
        color: "#8b949e",
        padding: "0 20px",
      }}
    >
      <div style={{ fontSize: 60 }}>⚠️</div>
      <h2 style={{ color: "#ff4d4f", margin: 0 }}>
        Une erreur est survenue
      </h2>
      <p
        style={{
          fontSize: 15,
          color: "#f0b2b2",
          textAlign: "center",
          maxWidth: 500,
          lineHeight: 1.5,
        }}
      >
        {error.message || "L'application a rencontré une erreur inattendue."}
      </p>
      <button
        onClick={reset}
        style={{
          padding: "10px 24px",
          borderRadius: 8,
          border: "none",
          background: "#4da6ff",
          color: "#04070c",
          fontSize: 14,
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        🔄 Réessayer
      </button>
    </div>
  );
}
