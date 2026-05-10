export default function HomePage(): JSX.Element {
  return (
    <main style={{ padding: '2rem', maxWidth: '720px' }}>
      <h1 style={{ fontSize: '2rem', marginBottom: '1rem' }}>Verixa</h1>
      <p style={{ fontSize: '1.125rem', lineHeight: 1.6 }}>
        Enterprise AI runtime control plane and trust platform. Intercepts,
        verifies, governs, audits, replays, and creates evidence to
        demonstrate and support AI-driven actions before and after they
        affect the real world.
      </p>
      <p style={{ marginTop: '1rem', color: '#666' }}>
        Phase 0 hackathon prototype — UI pages land in CP-15.
      </p>
    </main>
  );
}
