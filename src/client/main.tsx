import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { healthSchema } from '../shared/health';
import './styles.css';

function App() {
  const [connection, setConnection] = useState<'checking' | 'ready' | 'error'>('checking');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Health check failed');
        healthSchema.parse(await response.json());
        setConnection('ready');
      })
      .catch(() => { if (!controller.signal.aborted) setConnection('error'); });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <p className="eyebrow">GITAR TAKE-HOME · FOUNDATION</p>
      <h1>Snippet Reviewer</h1>
      <p className="intro">A focused workspace for reviewing code, one snippet at a time.</p>
      <section aria-labelledby="setup-title">
        <h2 id="setup-title">Project foundation</h2>
        <p role="status" className={`status ${connection}`}>
          {connection === 'checking' && 'Checking the API and database…'}
          {connection === 'ready' && 'API connected · SQLite ready'}
          {connection === 'error' && 'Cannot reach the API. Check the server and reload.'}
        </p>
        <p>Snippet creation, reviews, and findings will be added in the next steps.</p>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
