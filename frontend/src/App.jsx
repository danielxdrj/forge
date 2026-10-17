export default function App() {
  return (
    <div className="min-h-screen bg-forge-bg text-forge-text">
      <header className="flex flex-col gap-3 border-b border-forge-line px-8 py-7 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-2xl tracking-widest uppercase">Forge</p>
          <p className="text-forge-muted">Copiloto local</p>
        </div>
        <p className="text-forge-muted">
          Tela visível. A ligação com a API ainda não está configurada.
        </p>
      </header>

      <main className="grid gap-5 p-5 lg:grid-cols-[320px_1fr]">
        <section
          className="rounded-xl border border-forge-line bg-forge-panel p-5"
          aria-labelledby="list-title"
        >
          <h1 id="list-title" className="mb-4 text-lg font-semibold">
            Investigações
          </h1>
          <form className="mb-5 grid gap-2">
            <label className="text-sm text-forge-muted" htmlFor="title">
              Nova investigação
            </label>
            <input
              id="title"
              name="title"
              type="text"
              maxLength={200}
              placeholder="Título"
              disabled
              className="rounded-lg border border-forge-line bg-forge-bg px-3 py-2 disabled:cursor-not-allowed disabled:opacity-55"
            />
            <button
              type="button"
              disabled
              className="w-fit rounded-lg border border-forge-copper bg-forge-copper-dim px-3 py-2 font-semibold text-[#1a1208] disabled:cursor-not-allowed disabled:opacity-55"
            >
              Criar
            </button>
          </form>
          <p className="text-forge-muted">Nenhuma investigação para mostrar.</p>
        </section>

        <section
          className="rounded-xl border border-forge-line bg-forge-panel p-5"
          aria-labelledby="detail-title"
        >
          <h2 id="detail-title" className="mb-4 text-lg font-semibold">
            Detalhe
          </h2>
          <p className="mb-6 text-forge-muted">
            Selecione uma investigação quando a tela estiver ligada à API.
          </p>
          <form className="grid gap-2">
            <label className="text-sm text-forge-muted" htmlFor="log">
              Log local
            </label>
            <textarea
              id="log"
              name="log"
              rows={8}
              placeholder="O texto do log aparece aqui."
              disabled
              className="rounded-lg border border-forge-line bg-forge-bg px-3 py-2 disabled:cursor-not-allowed disabled:opacity-55"
            />
            <button
              type="button"
              disabled
              className="w-fit rounded-lg border border-forge-copper bg-forge-copper-dim px-3 py-2 font-semibold text-[#1a1208] disabled:cursor-not-allowed disabled:opacity-55"
            >
              Anexar log
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}
