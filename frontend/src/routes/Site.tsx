export function Site() {
  return (
    <main className="page">
      <section className="surface">
        <h1>Site</h1>
        <p>Landing, forms, and dialogs are being rebuilt here with strict Material Web usage.</p>
        <div className="actions">
          <md-filled-button>Start form</md-filled-button>
          <md-outlined-button>Open dialog</md-outlined-button>
        </div>
      </section>
    </main>
  );
}
